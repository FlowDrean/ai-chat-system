"""检索器：Query → Embedding → Vector Search → （可选）ReRank → Context。

对上层（LangGraph / ChatService）暴露一个方法：

    chunks = await retriever.retrieve("问题")
"""

from __future__ import annotations

import asyncio
import re
import time
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import EmbeddingError, RetrievalError
from app.core.logging import get_logger
from app.llm.embeddings import create_embeddings
from app.models.knowledge import KnowledgeBase
from app.rag.vector_store import BaseVectorStore, RetrievedChunk, get_vector_store

logger = get_logger(__name__)

_TOKEN_RE = re.compile(r"[A-Za-z0-9_]{2,}|[\u4e00-\u9fff]")


def _tokenize(text: str) -> set[str]:
    tokens = set(_TOKEN_RE.findall((text or "").lower()))
    for run in re.findall(r"[\u4e00-\u9fff]{2,}", text or ""):
        tokens.update(run[i : i + 2] for i in range(len(run) - 1))
    return tokens


def lexical_score(query: str, content: str) -> float:
    """词法重合度（用于轻量 ReRank，弥补纯向量召回的不足）。"""
    query_tokens = _tokenize(query)
    if not query_tokens:
        return 0.0
    content_tokens = _tokenize(content)
    if not content_tokens:
        return 0.0
    overlap = query_tokens & content_tokens
    return len(overlap) / len(query_tokens)


class Retriever:
    """知识库检索器。"""

    def __init__(
        self,
        session: AsyncSession,
        knowledge_base: KnowledgeBase,
        *,
        store: BaseVectorStore | None = None,
        embeddings: Any | None = None,
    ) -> None:
        self.session = session
        self.kb = knowledge_base
        self.embeddings = embeddings or create_embeddings(knowledge_base.embedding_runtime_config())
        self.store = store or get_vector_store(session, self.embeddings)

    # ------------------------------------------------------------------ #
    async def embed_query(self, question: str) -> list[float]:
        try:
            aembed = getattr(self.embeddings, "aembed_query", None)
            if aembed is not None:
                vector = await aembed(question)
            else:  # pragma: no cover - 兜底
                vector = await asyncio.to_thread(self.embeddings.embed_query, question)
            return list(vector)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Query Embedding 失败 kb=%s: %s", self.kb.id, exc)
            raise EmbeddingError(f"Query 向量化失败：{exc}") from exc

    async def retrieve(
        self,
        question: str,
        *,
        top_k: int | None = None,
        threshold: float | None = None,
        rerank: bool | None = None,
    ) -> list[RetrievedChunk]:
        """检索与问题最相关的分块。"""
        started = time.perf_counter()
        top_k = int(top_k or self.kb.top_k or 4)
        threshold = float(self.kb.similarity_threshold if threshold is None else threshold)
        rerank = self.kb.rerank_enabled if rerank is None else rerank

        try:
            # Chroma 走文本检索路径（其内部完成向量化）
            if hasattr(self.store, "asimilarity_search_text"):
                chunks = await self.store.asimilarity_search_text(  # type: ignore[attr-defined]
                    self.kb.id, question, top_k=max(top_k, top_k * 3), threshold=threshold
                )
            else:
                query_vector = await self.embed_query(question)
                chunks = await self.store.similarity_search(
                    self.kb.id, query_vector, top_k=max(top_k, top_k * 3), threshold=threshold
                )
        except (EmbeddingError, RetrievalError):
            raise
        except Exception as exc:  # noqa: BLE001
            logger.exception("知识库检索失败 kb=%s: %s", self.kb.id, exc)
            raise RetrievalError(f"知识库检索失败：{exc}") from exc

        if rerank and chunks:
            chunks = self._rerank(question, chunks)

        chunks = self._dedupe(chunks)[:top_k]
        logger.info(
            "检索完成 kb=%s top_k=%s 命中=%s 耗时=%.0fms",
            self.kb.id,
            top_k,
            len(chunks),
            (time.perf_counter() - started) * 1000,
        )
        return chunks

    # ------------------------------------------------------------------ #
    @staticmethod
    def _rerank(question: str, chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
        """轻量 ReRank：向量相似度 + 词法重合度加权，避免纯语义检索漏掉关键词。"""
        for chunk in chunks:
            lexical = lexical_score(question, chunk.content)
            chunk.score = float(0.65 * chunk.score + 0.35 * lexical)
        return sorted(chunks, key=lambda c: c.score, reverse=True)

    @staticmethod
    def _dedupe(chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
        """去掉内容高度重复的分块（保留得分更高的）。"""
        seen: list[str] = []
        result: list[RetrievedChunk] = []
        for chunk in chunks:
            fingerprint = chunk.content[:120].strip()
            if any(fingerprint and fingerprint in s for s in seen):
                continue
            seen.append(fingerprint)
            result.append(chunk)
        return result


# --------------------------------------------------------------------------- #
# 上下文构造
# --------------------------------------------------------------------------- #
def build_context(chunks: list[RetrievedChunk], *, max_chars: int = 8000) -> str:
    """把检索结果拼成带编号的上下文文本（编号用于回答中的 [1][2] 引用）。"""
    if not chunks:
        return ""
    parts: list[str] = []
    used = 0
    for index, chunk in enumerate(chunks, start=1):
        location = ""
        if chunk.page:
            location = f" 第 {chunk.page} 页"
        elif chunk.metadata.get("sheet"):
            location = f" 工作表「{chunk.metadata['sheet']}」"
        header = f"[{index}] 《{chunk.filename or '未知文档'}》{location}（相似度 {chunk.score:.2f}）"
        block = f"{header}\n{chunk.content.strip()}"
        if used + len(block) > max_chars and parts:
            break
        parts.append(block)
        used += len(block)
    return "\n\n".join(parts)


def to_sources(chunks: list[RetrievedChunk]) -> list[dict[str, Any]]:
    return [chunk.to_source() for chunk in chunks]
