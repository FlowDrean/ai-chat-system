"""文档入库流水线。

    上传文件 → 文件保存 → 文档解析 → 文本清洗 → Document Loader
            → Text Splitter → Chunk → Embedding → Vector Store → 完成

全流程异步执行，并实时把进度写回 documents 表，前端轮询即可看到：
等待处理 / 处理中 xx% / 处理完成 / 处理失败。
"""

from __future__ import annotations

import asyncio
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from langchain_core.documents import Document as LCDocument

from app.core.exceptions import EmbeddingError, FileParseError, AppError
from app.core.logging import get_logger
from app.db.session import AsyncSessionLocal
from app.llm.embeddings import create_embeddings
from app.models.document import Document, DocumentChunk, DocumentStatus
from app.rag.loader import load_documents
from app.rag.splitter import estimate_tokens, split_documents
from app.rag.vector_store import SqlVectorStore, get_vector_store
from app.repositories.knowledge_repo import (
    DocumentChunkRepository,
    DocumentRepository,
    KnowledgeBaseRepository,
)

logger = get_logger(__name__)

_PATH_PATTERN = re.compile(r"[A-Za-z]:\\[^\s\"']+|/(?:home|Users|var|opt|root)/[^\s\"']+")

# 同一时间只处理一个文档，避免本地 Embedding / API 限流被打爆
_ingest_lock = asyncio.Semaphore(2)


def sanitize_error(message: str, *, limit: int = 500) -> str:
    """错误信息脱敏：隐藏服务器文件路径，避免泄露内部结构。"""
    text = _PATH_PATTERN.sub("<path>", str(message))
    text = text.replace("\n", " ").strip()
    return text[:limit]


async def _update_stage(
    session,  # noqa: ANN001 - AsyncSession
    document: Document,
    status: str,
    progress: int,
    message: str,
    *,
    commit: bool = True,
) -> None:
    document.status = status
    document.progress = max(0, min(100, progress))
    document.stage_message = message
    await session.flush()
    if commit:
        await session.commit()


async def ingest_document(document_id: int, *, overwrite: bool = True) -> dict[str, Any]:
    """执行一次完整的文档入库；返回处理结果摘要。"""
    async with _ingest_lock:
        return await _ingest(document_id, overwrite=overwrite)


async def _ingest(document_id: int, *, overwrite: bool) -> dict[str, Any]:
    started = time.perf_counter()
    async with AsyncSessionLocal() as session:
        document = await DocumentRepository(session).get(document_id)
        if document is None:
            logger.warning("文档 %s 不存在，跳过入库", document_id)
            return {"document_id": document_id, "status": "missing", "chunk_count": 0}

        knowledge_base = await KnowledgeBaseRepository(session).get(document.knowledge_base_id)
        if knowledge_base is None:
            document.status = DocumentStatus.FAILED
            document.error_message = "知识库不存在"
            await session.commit()
            return {"document_id": document_id, "status": "failed", "chunk_count": 0, "error": "知识库不存在"}

        try:
            await _update_stage(session, document, DocumentStatus.PARSING, 5, "正在解析文档…")

            file_path = Path(document.file_path)
            documents, meta = await load_documents(file_path, document.file_type)
            char_count = int(meta.get("char_count", 0))

            await _update_stage(session, document, DocumentStatus.SPLITTING, 25, "正在切分文本…")
            chunks = await asyncio.to_thread(
                split_documents,
                documents,
                int(knowledge_base.chunk_size),
                int(knowledge_base.chunk_overlap),
                extra_metadata={
                    "document_id": document.id,
                    "filename": document.filename,
                    "file_type": document.file_type,
                },
            )
            if not chunks:
                raise FileParseError("文档切分后没有产生任何有效文本块")

            # 重新向量化时先清空旧数据
            if overwrite:
                await DocumentChunkRepository(session).delete_by_document(document.id)
                store = get_vector_store(session, None)
                if not isinstance(store, SqlVectorStore):
                    await store.delete_document(document.id)
                await session.commit()

            await _update_stage(session, document, DocumentStatus.EMBEDDING, 40, "正在生成向量…")

            embeddings = create_embeddings(knowledge_base.embedding_runtime_config())
            vectors, dimension = await _embed_chunks(session, document, chunks, embeddings)

            if dimension and dimension != knowledge_base.embedding_dimension:
                knowledge_base.embedding_dimension = dimension
                knowledge_base.embedding_config = {
                    **(knowledge_base.embedding_config or {}),
                    "detected_dimension": dimension,
                }

            await _update_stage(session, document, DocumentStatus.EMBEDDING, 92, "正在写入向量库…")

            store = get_vector_store(session, embeddings)
            if isinstance(store, SqlVectorStore):
                written = await store.add_chunks(knowledge_base.id, document.id, chunks, vectors)
            else:
                written = await _persist_chunk_rows(session, document, chunks, embeddings, dimension)
                await store.add_chunks(knowledge_base.id, document.id, chunks, vectors)

            document.chunk_count = written
            document.char_count = char_count
            document.doc_metadata = {**(document.doc_metadata or {}), **meta}
            document.error_message = None
            document.processed_at = _now()
            await _update_stage(session, document, DocumentStatus.COMPLETED, 100, "处理完成", commit=False)

            await KnowledgeBaseRepository(session).recalculate_counts(knowledge_base.id)
            await session.commit()

            elapsed = (time.perf_counter() - started) * 1000
            logger.info(
                "文档入库完成 id=%s file=%s chunks=%s dim=%s 耗时=%.0fms",
                document.id,
                document.filename,
                written,
                dimension,
                elapsed,
            )
            return {
                "document_id": document.id,
                "status": DocumentStatus.COMPLETED,
                "chunk_count": written,
                "char_count": char_count,
                "embedding_dimension": dimension,
                "elapsed_ms": round(elapsed, 1),
            }

        except AppError as exc:
            await _fail(session, document, exc.message)
            return {"document_id": document_id, "status": DocumentStatus.FAILED, "error": exc.message}
        except Exception as exc:  # noqa: BLE001
            message = sanitize_error(f"处理失败：{exc}")
            logger.exception("文档入库失败 id=%s: %s", document_id, exc)
            await _fail(session, document, message)
            return {"document_id": document_id, "status": DocumentStatus.FAILED, "error": message}


async def _embed_chunks(
    session,  # noqa: ANN001
    document: Document,
    chunks: list[LCDocument],
    embeddings: Any,
) -> tuple[list[list[float]], int]:
    """分批向量化，并刷新进度。"""
    from app.core.config import settings

    batch_size = max(1, int(settings.embedding_batch_size))
    texts = [chunk.page_content for chunk in chunks]
    vectors: list[list[float]] = []
    dimension = 0

    for start in range(0, len(texts), batch_size):
        batch = texts[start : start + batch_size]
        try:
            aembed = getattr(embeddings, "aembed_documents", None)
            if aembed is not None:
                batch_vectors = await aembed(batch)
            else:  # pragma: no cover
                batch_vectors = await asyncio.to_thread(embeddings.embed_documents, batch)
        except AppError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise EmbeddingError(f"文档向量化失败：{exc}") from exc

        for vector in batch_vectors:
            vectors.append(list(vector))
            dimension = dimension or len(vector)

        done = min(len(texts), start + len(batch))
        progress = 40 + int(done / max(1, len(texts)) * 50)
        await _update_stage(session, document, DocumentStatus.EMBEDDING, progress, f"正在生成向量 {done}/{len(texts)}")

    if not vectors:
        raise EmbeddingError("文档向量化失败：未生成任何向量")
    return vectors, dimension


async def _persist_chunk_rows(
    session,  # noqa: ANN001
    document: Document,
    chunks: list[LCDocument],
    embeddings: Any,
    dimension: int,
) -> int:
    """外部向量库模式下，仅在关系库中保存分块内容（用于预览 / 引用回溯）。"""
    repository = DocumentChunkRepository(session)
    for index, chunk in enumerate(chunks):
        metadata = dict(chunk.metadata or {})
        await repository.create(
            document_id=document.id,
            knowledge_base_id=document.knowledge_base_id,
            chunk_index=int(metadata.get("chunk_index", index)),
            content=chunk.page_content,
            token_count=estimate_tokens(chunk.page_content),
            embedding=None,
            embedding_dim=dimension,
            embedding_model=getattr(embeddings, "model", None),
            meta=metadata,
        )
    await session.flush()
    return len(chunks)


async def _fail(session, document: Document, message: str) -> None:  # noqa: ANN001
    document.status = DocumentStatus.FAILED
    document.progress = 100
    document.stage_message = "处理失败"
    document.error_message = message[:1000]
    await session.commit()


def _now() -> datetime:
    return datetime.now()
