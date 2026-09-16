"""Prompt 模板模型。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import BigIntFK, Base, LongText, PKMixin, TimestampMixin

if TYPE_CHECKING:
    from app.models.user import User


class PromptScene:
    SYSTEM = "system"  # 作为 System Prompt 使用
    RAG = "rag"  # RAG 问答模板（含 {context}）
    CHAT = "chat"  # 普通对话模板

    ALL = (SYSTEM, RAG, CHAT)


class Prompt(Base, PKMixin, TimestampMixin):
    __tablename__ = "prompts"

    user_id: Mapped[int | None] = mapped_column(
        BigIntFK, ForeignKey("users.id", ondelete="CASCADE"), index=True, default=None, comment="为空表示系统内置"
    )
    name: Mapped[str] = mapped_column(String(128), index=True, comment="Prompt 名称")
    content: Mapped[str] = mapped_column(
        LongText, comment="Prompt 内容，支持 {{question}} / {{context}} 等变量"
    )
    description: Mapped[str | None] = mapped_column(LongText, default=None)
    variables: Mapped[list | None] = mapped_column(JSON, default=None, comment="变量名列表")
    tags: Mapped[list | None] = mapped_column(JSON, default=None, comment="标签")
    scene: Mapped[str] = mapped_column(String(16), default=PromptScene.SYSTEM, comment="system/rag/chat")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    is_builtin: Mapped[bool] = mapped_column(Boolean, default=False, comment="内置模板不可删除")
    usage_count: Mapped[int] = mapped_column(default=0, comment="使用次数")

    user: Mapped["User"] = relationship(back_populates="prompts", lazy="noload")

    def render(self, **kwargs: object) -> str:
        """极简模板渲染：把 `{{var}}` / `{var}` 替换为传入值，未提供的变量保留原样。"""
        import re

        text = self.content

        def _replace(match: re.Match[str]) -> str:
            name = (match.group(1) or match.group(2) or "").strip()
            value = kwargs.get(name)
            return str(value) if value is not None else match.group(0)

        text = re.sub(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}", _replace, text)
        text = re.sub(r"(?<!\{)\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}(?!\})", _replace, text)
        return text
