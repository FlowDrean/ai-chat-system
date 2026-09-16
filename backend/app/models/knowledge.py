"""知识库模型。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Float, ForeignKey, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import BigIntFK, Base, LongText, PKMixin, TimestampMixin

if TYPE_CHECKING:
    from app.models.document import Document
    from app.models.user import User


class KnowledgeBase(Base, PKMixin, TimestampMixin):
    __tablename__ = "knowledge_bases"

    user_id: Mapped[int | None] = mapped_column(
        BigIntFK, ForeignKey("users.id", ondelete="CASCADE"), index=True, default=None, comment="归属用户"
    )
    name: Mapped[str] = mapped_column(String(128), index=True, comment="知识库名称")
    description: Mapped[str | None] = mapped_column(LongText, default=None, comment="描述")

    # Embedding 配置（独立于 LLM 模型配置）
    embedding_provider: Mapped[str] = mapped_column(String(32), default="local", comment="embedding 供应商")
    embedding_model: Mapped[str] = mapped_column(String(128), default="local-hash-512", comment="embedding 模型")
    embedding_base_url: Mapped[str | None] = mapped_column(String(512), default=None)
    _embedding_api_key: Mapped[str | None] = mapped_column("embedding_api_key", String(1024), default=None)
    embedding_dimension: Mapped[int] = mapped_column(Integer, default=512, comment="向量维度")
    embedding_config: Mapped[dict | None] = mapped_column(JSON, default=None, comment="其它 embedding 参数")

    # 切分 / 检索参数
    chunk_size: Mapped[int] = mapped_column(Integer, default=800)
    chunk_overlap: Mapped[int] = mapped_column(Integer, default=120)
    top_k: Mapped[int] = mapped_column(Integer, default=4)
    similarity_threshold: Mapped[float] = mapped_column(Float, default=0.2)
    rerank_enabled: Mapped[bool] = mapped_column(default=False, comment="是否启用轻量重排")

    document_count: Mapped[int] = mapped_column(Integer, default=0)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)

    user: Mapped["User"] = relationship(back_populates="knowledge_bases", lazy="noload")
    documents: Mapped[list["Document"]] = relationship(
        back_populates="knowledge_base", cascade="all, delete-orphan", lazy="noload"
    )

    # ---------------------------------------------------------------- #
    @property
    def embedding_api_key(self) -> str | None:
        from app.core.security import decrypt_secret

        return decrypt_secret(self._embedding_api_key)

    @embedding_api_key.setter
    def embedding_api_key(self, value: str | None) -> None:
        from app.core.security import encrypt_secret

        self._embedding_api_key = encrypt_secret(value) if value else None

    def embedding_runtime_config(self) -> dict:
        """转化为 Embedding Factory 需要的统一结构。"""
        return {
            "provider": self.embedding_provider,
            "model": self.embedding_model,
            "base_url": self.embedding_base_url,
            "api_key": self.embedding_api_key,
            "dimension": self.embedding_dimension,
            **(self.embedding_config or {}),
        }
