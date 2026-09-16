"""调用日志 / Token 统计模型（Dashboard 数据来源）。"""

from __future__ import annotations

from sqlalchemy import Boolean, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import BigIntFK, Base, PKMixin, TimestampMixin


class UsageSource:
    CHAT = "chat"
    EMBEDDING = "embedding"
    MODEL_TEST = "model_test"


class UsageLog(Base, PKMixin, TimestampMixin):
    __tablename__ = "usage_logs"

    user_id: Mapped[int | None] = mapped_column(
        BigIntFK, ForeignKey("users.id", ondelete="SET NULL"), index=True, default=None
    )
    conversation_id: Mapped[int | None] = mapped_column(BigIntFK, index=True, default=None)
    message_id: Mapped[int | None] = mapped_column(BigIntFK, index=True, default=None)
    knowledge_base_id: Mapped[int | None] = mapped_column(BigIntFK, index=True, default=None)

    provider: Mapped[str | None] = mapped_column(String(32), index=True, default=None)
    model_name: Mapped[str | None] = mapped_column(String(128), default=None)
    source: Mapped[str] = mapped_column(String(16), default=UsageSource.CHAT, index=True)

    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0)
    retrieved_chunks: Mapped[int] = mapped_column(Integer, default=0, comment="本次检索到的分块数")
    latency_ms: Mapped[float] = mapped_column(Float, default=0.0)
    success: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    error_message: Mapped[str | None] = mapped_column(String(512), default=None)
