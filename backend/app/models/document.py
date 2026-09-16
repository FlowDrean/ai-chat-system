"""文档模型 + 文档分块模型。

`DocumentChunk` 同时作为内置向量库（VECTOR_STORE=sql）的存储表：
向量以 float32 二进制保存在 `embedding` 字段中，检索时在内存中做余弦相似度。
切换到 chroma 等外部向量库时，该表仍然保留（作为分块预览 / 引用回溯的依据）。
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, LargeBinary, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import BigIntFK, Base, LongText, PKMixin, TimestampMixin

if TYPE_CHECKING:
    from app.models.knowledge import KnowledgeBase


class DocumentStatus:
    PENDING = "pending"  # 等待处理
    PARSING = "parsing"  # 解析中
    SPLITTING = "splitting"  # 切分中
    EMBEDDING = "embedding"  # 向量化中
    COMPLETED = "completed"  # 处理完成
    FAILED = "failed"  # 处理失败


class Document(Base, PKMixin, TimestampMixin):
    __tablename__ = "documents"

    knowledge_base_id: Mapped[int] = mapped_column(
        BigIntFK, ForeignKey("knowledge_bases.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[int | None] = mapped_column(BigIntFK, index=True, default=None)

    filename: Mapped[str] = mapped_column(String(255), comment="原始文件名")
    file_path: Mapped[str] = mapped_column(String(1024), comment="服务器存储路径（不返回给前端）")
    file_type: Mapped[str] = mapped_column(String(16), comment="pdf/docx/txt/md/csv/xlsx")
    file_size: Mapped[int] = mapped_column(Integer, default=0, comment="字节")
    file_hash: Mapped[str | None] = mapped_column(String(64), default=None, comment="内容 SHA256，用于去重")

    status: Mapped[str] = mapped_column(String(16), default=DocumentStatus.PENDING, index=True)
    progress: Mapped[int] = mapped_column(Integer, default=0, comment="处理进度 0-100")
    stage_message: Mapped[str | None] = mapped_column(String(255), default=None, comment="当前阶段描述")
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    char_count: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(String(1024), default=None)
    doc_metadata: Mapped[dict | None] = mapped_column(JSON, default=None, comment="解析出的元数据")
    processed_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)

    knowledge_base: Mapped["KnowledgeBase"] = relationship(back_populates="documents", lazy="noload")
    chunks: Mapped[list["DocumentChunk"]] = relationship(
        back_populates="document", cascade="all, delete-orphan", lazy="noload"
    )


class DocumentChunk(Base, PKMixin, TimestampMixin):
    __tablename__ = "document_chunks"

    document_id: Mapped[int] = mapped_column(
        BigIntFK, ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    knowledge_base_id: Mapped[int] = mapped_column(
        BigIntFK, ForeignKey("knowledge_bases.id", ondelete="CASCADE"), index=True
    )
    chunk_index: Mapped[int] = mapped_column(Integer, default=0, comment="分块序号")
    content: Mapped[str] = mapped_column(LongText, comment="分块文本")
    token_count: Mapped[int] = mapped_column(Integer, default=0, comment="近似 token 数")
    # 向量以 float32 二进制保存：MySQL 下 length=2^24 会映射为 MEDIUMBLOB（最大 16MB），
    # 足以容纳 8192 维向量（8192 * 4B = 32KB），SQLite 下为 BLOB。
    embedding: Mapped[bytes | None] = mapped_column(
        LargeBinary(2**24), default=None, comment="float32 向量字节"
    )
    embedding_dim: Mapped[int] = mapped_column(Integer, default=0)
    embedding_model: Mapped[str | None] = mapped_column(String(128), default=None)
    meta: Mapped[dict | None] = mapped_column(JSON, default=None, comment="页码 / 来源等元数据")
    score: Mapped[float] = mapped_column(Float, default=0.0, comment="最近一次检索相似度（调试用）")

    document: Mapped["Document"] = relationship(back_populates="chunks", lazy="noload")
