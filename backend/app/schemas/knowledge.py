"""知识库 / 文档 Schema。"""

from __future__ import annotations

from datetime import datetime

from pydantic import Field, field_validator

from app.schemas.common import BaseSchema


class KnowledgeBaseBase(BaseSchema):
    name: str = Field(min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=2000)

    embedding_provider: str = Field(default="local", max_length=32)
    embedding_model: str = Field(default="local-hash-512", max_length=128)
    embedding_base_url: str | None = Field(default=None, max_length=512)
    embedding_dimension: int = Field(default=512, ge=8, le=8192)

    chunk_size: int = Field(default=800, ge=100, le=8000)
    chunk_overlap: int = Field(default=120, ge=0, le=2000)
    top_k: int = Field(default=4, ge=1, le=50)
    similarity_threshold: float = Field(default=0.2, ge=-1.0, le=1.0)
    rerank_enabled: bool = False

    @field_validator("chunk_overlap")
    @classmethod
    def _check_overlap(cls, v: int, info) -> int:  # noqa: ANN001
        chunk_size = info.data.get("chunk_size")
        if chunk_size is not None and v >= chunk_size:
            raise ValueError("chunk_overlap 必须小于 chunk_size")
        return v


class KnowledgeBaseCreate(KnowledgeBaseBase):
    embedding_api_key: str | None = Field(default=None, max_length=512, description="只写不读")
    embedding_config: dict | None = None


class KnowledgeBaseUpdate(BaseSchema):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=2000)
    embedding_provider: str | None = None
    embedding_model: str | None = None
    embedding_base_url: str | None = None
    embedding_api_key: str | None = Field(default=None, description="留空表示不修改")
    embedding_dimension: int | None = Field(default=None, ge=8, le=8192)
    embedding_config: dict | None = None
    chunk_size: int | None = Field(default=None, ge=100, le=8000)
    chunk_overlap: int | None = Field(default=None, ge=0, le=2000)
    top_k: int | None = Field(default=None, ge=1, le=50)
    similarity_threshold: float | None = Field(default=None, ge=-1.0, le=1.0)
    rerank_enabled: bool | None = None


class KnowledgeBaseOut(BaseSchema):
    id: int
    user_id: int | None = None
    name: str
    description: str | None = None
    embedding_provider: str = "local"
    embedding_model: str = "local-hash-512"
    embedding_base_url: str | None = None
    embedding_dimension: int = 512
    embedding_api_key_masked: str | None = None
    has_embedding_api_key: bool = False
    chunk_size: int = 800
    chunk_overlap: int = 120
    top_k: int = 4
    similarity_threshold: float = 0.2
    rerank_enabled: bool = False
    document_count: int = 0
    chunk_count: int = 0
    created_at: datetime | None = None
    updated_at: datetime | None = None


class KnowledgeBaseDetail(KnowledgeBaseOut):
    documents: list["DocumentOut"] = Field(default_factory=list)


class EmbeddingOption(BaseSchema):
    value: str
    label: str
    dimension: int
    requires_api_key: bool = True
    default_base_url: str | None = None
    description: str | None = None


class RetrievalTestRequest(BaseSchema):
    query: str = Field(min_length=1, max_length=2000)
    top_k: int | None = Field(default=None, ge=1, le=50)


class RetrievalTestResult(BaseSchema):
    query: str
    chunks: list[dict] = Field(default_factory=list)
    latency_ms: float = 0.0


class DocumentOut(BaseSchema):
    id: int
    knowledge_base_id: int
    filename: str
    file_type: str
    file_size: int = 0
    status: str = "pending"
    progress: int = 0
    stage_message: str | None = None
    chunk_count: int = 0
    char_count: int = 0
    error_message: str | None = None
    doc_metadata: dict | None = None
    processed_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class DocumentDetail(DocumentOut):
    preview_chunks: list[dict] = Field(default_factory=list)


class DocumentChunkOut(BaseSchema):
    id: int
    document_id: int
    chunk_index: int
    content: str
    token_count: int = 0
    meta: dict | None = None
    score: float = 0.0
