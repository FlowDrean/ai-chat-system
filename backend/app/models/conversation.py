"""会话模型。"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import BigIntFK, Base, LongText, PKMixin, TimestampMixin

if TYPE_CHECKING:
    from app.models.message import Message
    from app.models.user import User


class Conversation(Base, PKMixin, TimestampMixin):
    __tablename__ = "conversations"

    user_id: Mapped[int] = mapped_column(BigIntFK, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(255), default="新对话", comment="会话标题")
    model_id: Mapped[int | None] = mapped_column(BigIntFK, ForeignKey("models.id", ondelete="SET NULL"), default=None)
    knowledge_base_id: Mapped[int | None] = mapped_column(
        BigIntFK, ForeignKey("knowledge_bases.id", ondelete="SET NULL"), default=None, comment="绑定的知识库"
    )
    prompt_id: Mapped[int | None] = mapped_column(
        BigIntFK, ForeignKey("prompts.id", ondelete="SET NULL"), default=None, comment="绑定的 Prompt"
    )
    system_prompt: Mapped[str | None] = mapped_column(LongText, default=None, comment="System Prompt")
    # 本会话启用的技能 id 列表（为空表示不使用任何技能）
    skill_ids: Mapped[list | None] = mapped_column(JSON, default=None, comment="会话启用的技能 id 列表")
    mcp_server_ids: Mapped[list | None] = mapped_column(JSON, default=None, comment="会话启用的 MCP 服务 id 列表")
    # 会话级模型参数（只影响当前会话，见开发文档 §6）
    params: Mapped[dict | None] = mapped_column(JSON, default=None, comment="temperature/top_p/max_tokens/...")
    summary: Mapped[str | None] = mapped_column(LongText, default=None, comment="历史消息摘要（长上下文压缩）")

    is_favorite: Mapped[bool] = mapped_column(Boolean, default=False, index=True, comment="是否收藏")
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False, index=True, comment="是否归档")
    message_count: Mapped[int] = mapped_column(Integer, default=0, comment="消息数量")
    total_tokens: Mapped[int] = mapped_column(Integer, default=0, comment="累计 Token")
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime, default=None, index=True)

    user: Mapped["User"] = relationship(back_populates="conversations", lazy="noload")
    messages: Mapped[list["Message"]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        lazy="noload",
        order_by="Message.id",
    )

    def effective_params(self) -> dict:
        return dict(self.params or {})
