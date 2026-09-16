"""RAG 服务：把「检索 + 上下文构造 + Prompt 组装」封装成一组可复用能力。

LangGraph 的 retrieve 节点、知识库检索测试、以及未来的 Agent / 工具调用
都复用这里的实现，保证 RAG 流程只有一份逻辑。
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import RetrievalError
from app.core.logging import get_logger
from app.models.knowledge import KnowledgeBase
from app.rag.prompts import CONTEXT_MARKER, DEFAULT_RAG_SYSTEM_PROMPT
from app.rag.retriever import Retriever, build_context, to_sources
from app.rag.vector_store import RetrievedChunk

logger = get_logger(__name__)


class RagService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ------------------------------------------------------------------ #
    async def retrieve(
        self,
        knowledge_base: KnowledgeBase,
        question: str,
        *,
        top_k: int | None = None,
        threshold: float | None = None,
        rerank: bool | None = None,
    ) -> list[RetrievedChunk]:
        retriever = Retriever(self.session, knowledge_base)
        return await retriever.retrieve(question, top_k=top_k, threshold=threshold, rerank=rerank)

    async def build_rag_prompt(
        self,
        knowledge_base: KnowledgeBase,
        question: str,
        *,
        base_system_prompt: str | None = None,
        top_k: int | None = None,
    ) -> tuple[str, list[dict[str, Any]], str]:
        """返回 `(system_prompt, sources, context_text)`。"""
        chunks = await self.retrieve(knowledge_base, question, top_k=top_k)
        if not chunks:
            return (base_system_prompt or DEFAULT_RAG_SYSTEM_PROMPT).replace("{context}", ""), [], ""

        context_text = build_context(chunks)
        sources = to_sources(chunks)
        template = base_system_prompt or DEFAULT_RAG_SYSTEM_PROMPT
        if "{context}" in template:
            system_prompt = template.replace("{context}", context_text)
        elif CONTEXT_MARKER in template:
            system_prompt = f"{template}\n{context_text}"
        else:
            system_prompt = f"{template}\n\n{CONTEXT_MARKER}\n{context_text}"
        return system_prompt, sources, context_text

    # ------------------------------------------------------------------ #
    async def retrieval_test(
        self, knowledge_base: KnowledgeBase, query: str, *, top_k: int | None = None
    ) -> dict[str, Any]:
        """知识库检索测试（前端「测试检索」按钮）。"""
        import time

        started = time.perf_counter()
        try:
            chunks = await self.retrieve(knowledge_base, query, top_k=top_k)
        except RetrievalError:
            raise
        latency = (time.perf_counter() - started) * 1000
        return {
            "query": query,
            "latency_ms": round(latency, 1),
            "chunks": [chunk.to_source() for chunk in chunks],
            "context_preview": build_context(chunks, max_chars=2000),
        }
