"""用户模型。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from datetime import datetime

from sqlalchemy import Boolean, DateTime, SmallInteger, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, PKMixin, TimestampMixin

if TYPE_CHECKING:
    from app.models.conversation import Conversation
    from app.models.knowledge import KnowledgeBase
    from app.models.prompt import Prompt


class UserRole:
    USER = "user"
    ADMIN = "admin"


class UserStatus:
    DISABLED = 0
    ACTIVE = 1


class User(Base, PKMixin, TimestampMixin):
    __tablename__ = "users"

    username: Mapped[str] = mapped_column(String(64), unique=True, index=True, comment="用户名")
    email: Mapped[str | None] = mapped_column(String(128), unique=True, index=True, default=None, comment="邮箱")
    password_hash: Mapped[str] = mapped_column(String(255), comment="密码哈希（PBKDF2）")
    avatar: Mapped[str | None] = mapped_column(String(512), default=None, comment="头像地址")
    nickname: Mapped[str | None] = mapped_column(String(64), default=None, comment="昵称")
    role: Mapped[str] = mapped_column(String(16), default=UserRole.USER, index=True, comment="角色 user/admin")
    status: Mapped[int] = mapped_column(SmallInteger, default=UserStatus.ACTIVE, comment="1 正常 0 禁用")
    is_superuser: Mapped[bool] = mapped_column(Boolean, default=False, comment="是否超级管理员")
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, default=None, comment="最后登录时间")

    conversations: Mapped[list["Conversation"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", lazy="selectin"
    )
    knowledge_bases: Mapped[list["KnowledgeBase"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", lazy="noload"
    )
    prompts: Mapped[list["Prompt"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", lazy="noload"
    )

    @property
    def is_admin(self) -> bool:
        return self.role == UserRole.ADMIN or self.is_superuser

    @property
    def is_active(self) -> bool:
        return self.status == UserStatus.ACTIVE

    def __repr__(self) -> str:  # pragma: no cover
        return f"<User id={self.id} username={self.username!r}>"
