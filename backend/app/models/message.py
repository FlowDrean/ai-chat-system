"""消息模型。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import JSON, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import BigIntFK, Base, LongText, PKMixin, TimestampMixin

if TYPE_CHECKING:
    from app.models.conversation import Conversation


class MessageRole:
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"

    ALL = (SYSTEM, USER, ASSISTANT, TOOL)


class MessageStatus:
    DONE = "done"
    STREAMING = "streaming"
    STOPPED = "stopped"
    ERROR = "error"


class Message(Base, PKMixin, TimestampMixin):
    __tablename__ = "messages"

    conversation_id: Mapped[int] = mapped_column(
        BigIntFK, ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(16), index=True, comment="system/user/assistant/tool")
    content: Mapped[str] = mapped_column(LongText, comment="消息内容（Markdown）")
    # RAG 引用来源：[{document_id, filename, page, chunk_index, score, content, metadata}]
    sources: Mapped[list | None] = mapped_column(JSON, default=None, comment="RAG 引用来源")
    # 技能调用记录：[{id, name, type, status, arguments, output, latency_ms}]
    skills: Mapped[list | None] = mapped_column(JSON, default=None, comment="本条回答调用的技能记录")
    status: Mapped[str] = mapped_column(String(16), default=MessageStatus.DONE, comment="done/streaming/stopped/error")

    model_id: Mapped[int | None] = mapped_column(BigIntFK, default=None, comment="生成该消息的模型")
    model_name: Mapped[str | None] = mapped_column(String(128), default=None)
    provider: Mapped[str | None] = mapped_column(String(32), default=None)
    knowledge_base_id: Mapped[int | None] = mapped_column(BigIntFK, default=None, comment="本次使用的知识库")

    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0)
    latency_ms: Mapped[float] = mapped_column(Float, default=0.0, comment="耗时（毫秒）")
    error_message: Mapped[str | None] = mapped_column(String(1024), default=None)
    extra: Mapped[dict | None] = mapped_column(JSON, default=None, comment="路由信息等扩展字段")

    conversation: Mapped["Conversation"] = relationship(back_populates="messages", lazy="noload")
