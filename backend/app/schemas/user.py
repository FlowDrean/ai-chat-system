"""用户相关 Schema。"""

from __future__ import annotations

import re
from datetime import datetime

from pydantic import Field, field_validator

from app.schemas.common import BaseSchema

_USERNAME_RE = re.compile(r"^[A-Za-z0-9_\u4e00-\u9fa5.-]{3,32}$")
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z0-9-]+$")


class UserOut(BaseSchema):
    id: int
    username: str
    email: str | None = None
    nickname: str | None = None
    avatar: str | None = None
    role: str = "user"
    status: int = 1
    is_admin: bool = False
    last_login_at: datetime | None = None
    created_at: datetime | None = None


class UserCreate(BaseSchema):
    username: str = Field(min_length=3, max_length=32)
    password: str = Field(min_length=6, max_length=128)
    email: str | None = Field(default=None, max_length=128)
    nickname: str | None = Field(default=None, max_length=64)
    role: str = Field(default="user", pattern="^(user|admin)$")
    status: int = Field(default=1, ge=0, le=1)

    @field_validator("username")
    @classmethod
    def _check_username(cls, v: str) -> str:
        v = v.strip()
        if not _USERNAME_RE.match(v):
            raise ValueError("用户名只能包含中英文、数字、下划线、点或短横线，长度 3-32")
        return v

    @field_validator("email")
    @classmethod
    def _check_email(cls, v: str | None) -> str | None:
        if v in (None, ""):
            return None
        if not _EMAIL_RE.match(v):
            raise ValueError("邮箱格式不正确")
        return v.lower()


class UserUpdate(BaseSchema):
    nickname: str | None = Field(default=None, max_length=64)
    email: str | None = Field(default=None, max_length=128)
    avatar: str | None = Field(default=None, max_length=512)
    role: str | None = Field(default=None, pattern="^(user|admin)$")
    status: int | None = Field(default=None, ge=0, le=1)

    @field_validator("email")
    @classmethod
    def _check_email(cls, v: str | None) -> str | None:
        if v in (None, ""):
            return None
        if not _EMAIL_RE.match(v):
            raise ValueError("邮箱格式不正确")
        return v.lower()


class PasswordChange(BaseSchema):
    old_password: str = Field(min_length=1)
    new_password: str = Field(min_length=6, max_length=128)


class PasswordReset(BaseSchema):
    new_password: str = Field(min_length=6, max_length=128)
