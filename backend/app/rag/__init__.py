"""RAG 模块：加载 → 切分 → 向量化 → 检索 → 上下文构造。"""

from app.rag.loader import SUPPORTED_EXTENSIONS, compute_file_hash, detect_file_type, load_documents
from app.rag.pipeline import ingest_document, sanitize_error
from app.rag.prompts import (
    CONTEXT_MARKER,
    DEFAULT_RAG_SYSTEM_PROMPT,
    DEFAULT_SYSTEM_PROMPT,
    RETRIEVAL_EMPTY_HINT,
    TITLE_GENERATE_PROMPT,
)
from app.rag.retriever import Retriever, build_context, lexical_score, to_sources
from app.rag.splitter import build_splitter, estimate_tokens, split_documents
from app.rag.vector_store import (
    BaseVectorStore,
    RetrievedChunk,
    SqlVectorStore,
    get_vector_store,
    pack_embedding,
    unpack_embedding,
)

__all__ = [
    "CONTEXT_MARKER",
    "DEFAULT_RAG_SYSTEM_PROMPT",
    "DEFAULT_SYSTEM_PROMPT",
    "RETRIEVAL_EMPTY_HINT",
    "SUPPORTED_EXTENSIONS",
    "TITLE_GENERATE_PROMPT",
    "BaseVectorStore",
    "RetrievedChunk",
    "Retriever",
    "SqlVectorStore",
    "build_context",
    "build_splitter",
    "compute_file_hash",
    "detect_file_type",
    "estimate_tokens",
    "get_vector_store",
    "ingest_document",
    "lexical_score",
    "load_documents",
    "pack_embedding",
    "sanitize_error",
    "split_documents",
    "to_sources",
    "unpack_embedding",
]
