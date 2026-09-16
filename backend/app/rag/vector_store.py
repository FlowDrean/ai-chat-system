"""向量库抽象层。

业务代码只依赖 `BaseVectorStore` 接口，因此可以随时替换底层实现：

* `SqlVectorStore`   —— 默认实现，向量存 MySQL/SQLite（`document_chunks.embedding`），
                        检索时在内存中做余弦相似度，零外部依赖，适合中小规模知识库。
* `ChromaVectorStore` —— 可选实现（`VECTOR_STORE=chroma`），适合更大规模 / 需要持久化索引。

未来接入 Milvus / Qdrant / PGVector / Elasticsearch 只需新增一个子类。
在生产环境大规模场景下建议切换到外部向量库。
"""

from __future__ import annotations

import struct
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from langchain_core.documents import Document
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import RetrievalError
from app.core.logging import get_logger
from app.models.document import DocumentChunk
from app.repositories.knowledge_repo import DocumentChunkRepository

logger = get_logger(__name__)


@dataclass(slots=True)
class RetrievedChunk:
    """检索结果（同时用于构造引用来源）。"""

    chunk_id: int | None
    document_id: int
    chunk_index: int
    content: str
    score: float
    filename: str | None = None
    file_type: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def page(self) -> int | None:
        page = self.metadata.get("page")
        return int(page) if isinstance(page, (int, str)) and str(page).isdigit() else None

    def to_source(self) -> dict[str, Any]:
        return {
            "document_id": self.document_id,
            "chunk_id": self.chunk_id,
            "chunk_index": self.chunk_index,
            "filename": self.filename,
            "file_type": self.file_type,
            "page": self.page,
            "score": round(float(self.score), 4),
            "content": self.content[:1200],
            "metadata": self.metadata,
        }


def pack_embedding(vector: list[float]) -> bytes:
    return struct.pack(f"<{len(vector)}f", *vector)


def unpack_embedding(blob: bytes | None) -> list[float]:
    if not blob:
        return []
    count = len(blob) // 4
    return list(struct.unpack(f"<{count}f", blob[: count * 4]))


def _cosine_scores(matrix: np.ndarray, query: np.ndarray) -> np.ndarray:
    if matrix.size == 0:
        return np.zeros((0,), dtype=np.float32)
    norms = np.linalg.norm(matrix, axis=1)
    norms[norms == 0] = 1e-9
    query_norm = float(np.linalg.norm(query)) or 1e-9
    return (matrix @ query) / (norms * query_norm)


class BaseVectorStore(ABC):
    """向量库统一接口。"""

    @abstractmethod
    async def add_chunks(self, knowledge_base_id: int, document_id: int, chunks: list[Document],
                         embeddings: list[list[float]]) -> int:
        """写入分块与向量，返回写入数量。"""

    @abstractmethod
    async def delete_document(self, document_id: int) -> int:
        ...

    @abstractmethod
    async def delete_knowledge_base(self, knowledge_base_id: int) -> int:
        ...

    @abstractmethod
    async def similarity_search(
        self,
        knowledge_base_id: int,
        query_vector: list[float],
        *,
        top_k: int = 4,
        threshold: float = 0.0,
    ) -> list[RetrievedChunk]:
        ...

    @abstractmethod
    async def count(self, knowledge_base_id: int) -> int:
        ...


class SqlVectorStore(BaseVectorStore):
    """基于关系库的向量检索实现（默认）。"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.chunks = DocumentChunkRepository(session)

    async def add_chunks(
        self,
        knowledge_base_id: int,
        document_id: int,
        chunks: list[Document],
        embeddings: list[list[float]],
    ) -> int:
        if len(chunks) != len(embeddings):
            raise RetrievalError("分块数量与向量数量不一致")

        from app.models.document import Document
        from app.repositories.knowledge_repo import DocumentRepository

        document = await DocumentRepository(self.session).get(document_id)
        filename = document.filename if document is not None else None
        file_type = document.file_type if document is not None else None

        for index, (chunk, vector) in enumerate(zip(chunks, embeddings, strict=True)):
            metadata = dict(chunk.metadata or {})
            metadata.setdefault("filename", filename)
            metadata.setdefault("file_type", file_type)
            self.session.add(
                DocumentChunk(
                    document_id=document_id,
                    knowledge_base_id=knowledge_base_id,
                    chunk_index=int(metadata.get("chunk_index", index)),
                    content=chunk.page_content,
                    token_count=int(metadata.get("token_count", max(1, len(chunk.page_content) // 2))),
                    embedding=pack_embedding(vector),
                    embedding_dim=len(vector),
                    embedding_model=str(metadata.get("embedding_model") or ""),
                    meta=metadata,
                )
            )
        await self.session.flush()
        return len(chunks)

    async def delete_document(self, document_id: int) -> int:
        return await self.chunks.delete_by_document(document_id)

    async def delete_knowledge_base(self, knowledge_base_id: int) -> int:
        return await self.chunks.delete_by_kb(knowledge_base_id)

    async def similarity_search(
        self,
        knowledge_base_id: int,
        query_vector: list[float],
        *,
        top_k: int = 4,
        threshold: float = 0.0,
    ) -> list[RetrievedChunk]:
        rows = await self.chunks.list_with_embeddings(knowledge_base_id)
        if not rows:
            return []
        query = np.asarray(query_vector, dtype=np.float32)
        if query.size == 0:
            return []

        valid: list[DocumentChunk] = []
        vectors: list[np.ndarray] = []
        for row in rows:
            vector = np.asarray(unpack_embedding(row.embedding), dtype=np.float32)
            if vector.size != query.size:
                # 维度不一致（例如中途更换了 Embedding 模型）→ 跳过，并提示重新向量化
                continue
            valid.append(row)
            vectors.append(vector)
        if not valid:
            logger.warning("知识库 %s 的向量维度与当前 Embedding 不一致，请重新向量化文档", knowledge_base_id)
            return []

        matrix = np.vstack(vectors)
        scores = _cosine_scores(matrix, query)
        order = np.argsort(-scores)[: max(top_k * 3, top_k)]

        results: list[RetrievedChunk] = []
        for idx in order:
            score = float(scores[int(idx)])
            if score < threshold:
                continue
            row = valid[int(idx)]
            results.append(self._to_chunk(row, score))
            if len(results) >= top_k:
                break
        return results

    @staticmethod
    def _to_chunk(row: DocumentChunk, score: float) -> RetrievedChunk:
        meta = dict(row.meta or {})
        return RetrievedChunk(
            chunk_id=row.id,
            document_id=row.document_id,
            chunk_index=row.chunk_index,
            content=row.content,
            score=score,
            filename=meta.get("filename"),
            file_type=meta.get("file_type"),
            metadata=meta,
        )

    async def count(self, knowledge_base_id: int) -> int:
        return await self.chunks.count_by_kb(knowledge_base_id)


class ChromaVectorStore(BaseVectorStore):
    """Chroma 实现（可选，需安装 chromadb 并设置 VECTOR_STORE=chroma）。"""

    def __init__(self, embeddings: Any, persist_dir: str | None = None) -> None:
        try:
            from langchain_chroma import Chroma
        except ImportError as exc:  # pragma: no cover
            raise RetrievalError("未安装 chromadb / langchain-chroma，无法使用 Chroma 向量库") from exc

        self._chroma_cls = Chroma
        self.embeddings = embeddings
        self.persist_dir = persist_dir or str(settings.vector_path)
        self._stores: dict[int, Any] = {}

    def _collection_name(self, knowledge_base_id: int) -> str:
        return f"kb_{knowledge_base_id}"

    def _store(self, knowledge_base_id: int) -> Any:
        if knowledge_base_id not in self._stores:
            self._stores[knowledge_base_id] = self._chroma_cls(
                collection_name=self._collection_name(knowledge_base_id),
                embedding_function=self.embeddings,
                persist_directory=self.persist_dir,
            )
        return self._stores[knowledge_base_id]

    async def add_chunks(self, knowledge_base_id, document_id, chunks, embeddings) -> int:  # noqa: ANN001
        ids = [f"{document_id}-{i}" for i in range(len(chunks))]
        await self._store(knowledge_base_id).aadd_documents(documents=chunks, ids=ids)
        return len(chunks)

    async def delete_document(self, document_id: int) -> int:
        for kb_id, store in self._stores.items():
            await store.adelete(where={"document_id": document_id})
        return 0

    async def delete_knowledge_base(self, knowledge_base_id: int) -> int:
        try:
            await self._store(knowledge_base_id).adelete_collection()
        except Exception as exc:  # noqa: BLE001
            logger.warning("删除 Chroma collection 失败：%s", exc)
        self._stores.pop(knowledge_base_id, None)
        return 0

    async def similarity_search(self, knowledge_base_id, query_vector, *, top_k=4, threshold=0.0) -> list[RetrievedChunk]:  # noqa: ANN001
        # Chroma 自带向量化，这里用文本检索更直接：由 Retriever 走 query 文本路径
        raise RetrievalError("Chroma 实现请使用 retriever 的文本检索路径")

    async def count(self, knowledge_base_id: int) -> int:
        return len(await self._store(knowledge_base_id).aget())

    async def asimilarity_search_text(
        self, knowledge_base_id: int, query: str, top_k: int = 4, threshold: float = 0.0
    ) -> list[RetrievedChunk]:
        """Chroma 专用：直接按文本检索。"""
        docs_and_scores = await self._store(knowledge_base_id).asimilarity_search_with_relevance_scores(
            query, k=top_k
        )
        results: list[RetrievedChunk] = []
        for doc, score in docs_and_scores:
            if score < threshold:
                continue
            meta = dict(doc.metadata or {})
            results.append(
                RetrievedChunk(
                    chunk_id=None,
                    document_id=int(meta.get("document_id", 0)),
                    chunk_index=int(meta.get("chunk_index", 0)),
                    content=doc.page_content,
                    score=float(score),
                    filename=meta.get("filename"),
                    file_type=meta.get("file_type"),
                    metadata=meta,
                )
            )
        return results


def get_vector_store(session: AsyncSession, embeddings: Any | None = None) -> BaseVectorStore:
    """工厂：按配置返回向量库实现。"""
    backend = (settings.vector_store or "sql").lower()
    if backend == "chroma":
        return ChromaVectorStore(embeddings)
    if backend != "sql":
        logger.warning("未知的 VECTOR_STORE=%s，回退为 sql 实现", backend)
    return SqlVectorStore(session)
