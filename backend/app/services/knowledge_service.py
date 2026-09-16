"""知识库服务。"""

from __future__ import annotations

import time
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import BadRequestError, NotFoundError
from app.core.logging import get_logger
from app.core.security import mask_secret
from app.llm.embeddings import EmbeddingProvider, create_embeddings, list_embedding_providers
from app.models.document import Document
from app.models.knowledge import KnowledgeBase
from app.rag.pipeline import sanitize_error
from app.rag.retriever import Retriever, build_context
from app.rag.vector_store import get_vector_store
from app.repositories.knowledge_repo import (
    DocumentChunkRepository,
    DocumentRepository,
    KnowledgeBaseRepository,
)
from app.schemas.knowledge import (
    DocumentOut,
    KnowledgeBaseCreate,
    KnowledgeBaseDetail,
    KnowledgeBaseOut,
    KnowledgeBaseUpdate,
)

logger = get_logger(__name__)


def to_kb_out(kb: KnowledgeBase) -> KnowledgeBaseOut:
    data = kb.to_dict(exclude={"_embedding_api_key", "embedding_api_key"})
    plain = kb.embedding_api_key
    data.update(
        {
            "embedding_api_key_masked": mask_secret(plain) if plain else None,
            "has_embedding_api_key": bool(plain),
        }
    )
    return KnowledgeBaseOut.model_validate(data)


def to_document_out(document: Document) -> DocumentOut:
    """文档出参：**不包含** file_path（避免泄露服务器路径）。"""
    return DocumentOut.model_validate(document.to_dict(exclude={"file_path", "file_hash"}))


class KnowledgeService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.kbs = KnowledgeBaseRepository(session)
        self.documents = DocumentRepository(session)
        self.chunks = DocumentChunkRepository(session)

    # ------------------------------------------------------------------ #
    async def list_knowledge_bases(
        self,
        user_id: int,
        *,
        keyword: str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[KnowledgeBaseOut], int]:
        items, total = await self.kbs.list_for_user(
            user_id, keyword=keyword, offset=(page - 1) * page_size, limit=page_size
        )
        return [to_kb_out(kb) for kb in items], total

    async def get_knowledge_base(self, kb_id: int, user_id: int | None) -> KnowledgeBase:
        kb = await self.kbs.get(kb_id)
        if kb is None or (user_id is not None and kb.user_id != user_id):
            raise NotFoundError("知识库不存在")
        return kb

    async def get_detail(self, kb_id: int, user_id: int | None) -> KnowledgeBaseDetail:
        kb = await self.get_knowledge_base(kb_id, user_id)
        documents, _ = await self.documents.list_by_kb(kb.id, limit=100)
        detail = KnowledgeBaseDetail(**to_kb_out(kb).model_dump(), documents=[to_document_out(d) for d in documents])
        return detail

    # ------------------------------------------------------------------ #
    async def create_knowledge_base(self, data: KnowledgeBaseCreate, user_id: int) -> KnowledgeBaseOut:
        self._validate_embedding(data.embedding_provider, data.embedding_model)
        if data.embedding_provider in EmbeddingProvider.OPENAI_COMPATIBLE and not data.embedding_api_key:
            raise BadRequestError(f"Embedding 供应商 {data.embedding_provider} 需要填写 API Key")

        kb = KnowledgeBase(
            user_id=user_id,
            name=data.name.strip(),
            description=data.description,
            embedding_provider=data.embedding_provider,
            embedding_model=data.embedding_model,
            embedding_base_url=data.embedding_base_url,
            embedding_dimension=data.embedding_dimension,
            embedding_config=data.embedding_config,
            chunk_size=data.chunk_size,
            chunk_overlap=data.chunk_overlap,
            top_k=data.top_k,
            similarity_threshold=data.similarity_threshold,
            rerank_enabled=data.rerank_enabled,
        )
        kb.embedding_api_key = data.embedding_api_key
        self.session.add(kb)
        await self.session.flush()
        logger.info("创建知识库 id=%s name=%s embedding=%s", kb.id, kb.name, kb.embedding_model)
        return to_kb_out(kb)

    async def update_knowledge_base(
        self, kb_id: int, data: KnowledgeBaseUpdate, user_id: int | None
    ) -> KnowledgeBaseOut:
        kb = await self.get_knowledge_base(kb_id, user_id)
        payload = data.model_dump(exclude_unset=True)

        api_key = payload.pop("embedding_api_key", None)
        if api_key is not None:
            kb.embedding_api_key = api_key or None

        new_provider = payload.get("embedding_provider") or kb.embedding_provider
        new_model = payload.get("embedding_model") or kb.embedding_model
        self._validate_embedding(new_provider, new_model)

        chunk_size = payload.get("chunk_size", kb.chunk_size)
        chunk_overlap = payload.get("chunk_overlap", kb.chunk_overlap)
        if chunk_overlap >= chunk_size:
            raise BadRequestError("chunk_overlap 必须小于 chunk_size")

        embedding_changed = (
            new_provider != kb.embedding_provider
            or new_model != kb.embedding_model
            or payload.get("embedding_base_url") not in (None, kb.embedding_base_url)
        )

        for key, value in payload.items():
            setattr(kb, key, value)
        await self.session.flush()

        if embedding_changed and kb.chunk_count:
            logger.warning("知识库 %s 的 Embedding 配置已变更，已有向量需要重新向量化", kb.id)
        return to_kb_out(kb)

    async def delete_knowledge_base(self, kb_id: int, user_id: int | None) -> None:
        kb = await self.get_knowledge_base(kb_id, user_id)
        documents = await self.documents.list_all(Document.knowledge_base_id == kb.id)

        # 1. 删除向量
        store = get_vector_store(self.session, None)
        await store.delete_knowledge_base(kb.id)
        await self.chunks.delete_by_kb(kb.id)

        # 2. 删除物理文件（失败不影响删除流程）
        for document in documents:
            try:
                path = Path(document.file_path)
                if path.exists() and path.is_file():
                    path.unlink()
            except OSError as exc:  # pragma: no cover
                logger.warning("删除文件失败 %s: %s", document.id, exc)

        # 3. 删除知识库（文档记录级联删除）
        await self.kbs.delete(kb)
        logger.info("删除知识库 id=%s name=%s", kb_id, kb.name)

    # ------------------------------------------------------------------ #
    async def test_retrieval(
        self, kb_id: int, user_id: int | None, query: str, top_k: int | None = None
    ) -> dict:
        """检索测试：不调用 LLM，只验证向量化 + 召回是否正常。"""
        kb = await self.get_knowledge_base(kb_id, user_id)
        started = time.perf_counter()
        retriever = Retriever(self.session, kb)
        chunks = await retriever.retrieve(query, top_k=top_k)
        latency = (time.perf_counter() - started) * 1000
        return {
            "query": query,
            "latency_ms": round(latency, 1),
            "context_preview": build_context(chunks, max_chars=2000),
            "chunks": [chunk.to_source() for chunk in chunks],
        }

    async def embedding_options(self) -> list[dict]:
        return list_embedding_providers()

    async def verify_embedding_config(self, kb: KnowledgeBase) -> int:
        """校验 Embedding 配置是否可用，返回检测到的维度。"""
        embeddings = create_embeddings(kb.embedding_runtime_config())
        vector = await embeddings.aembed_query("维度探测")
        return len(vector)

    # ------------------------------------------------------------------ #
    @staticmethod
    def _validate_embedding(provider: str, model: str) -> None:
        if provider not in EmbeddingProvider.ALL:
            raise BadRequestError(f"不支持的 Embedding 供应商：{provider}")
        if not model:
            raise BadRequestError("Embedding 模型不能为空")

    @staticmethod
    def resolve_upload_dir() -> Path:
        path = settings.upload_path
        path.mkdir(parents=True, exist_ok=True)
        return path

    @staticmethod
    def friendly_error(message: str) -> str:
        return sanitize_error(message)
