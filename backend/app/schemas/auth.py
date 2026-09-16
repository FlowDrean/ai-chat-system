"""认证相关 Schema。"""

from __future__ import annotations

from pydantic import Field, field_validator

from app.schemas.common import BaseSchema
from app.schemas.user import UserOut


class LoginRequest(BaseSchema):
    username: str = Field(min_length=1, max_length=64, description="用户名或邮箱")
    password: str = Field(min_length=1, max_length=128)

    @field_validator("username")
    @classmethod
    def _strip(cls, v: str) -> str:
        return v.strip()


class RegisterRequest(BaseSchema):
    username: str = Field(min_length=3, max_length=32)
    password: str = Field(min_length=6, max_length=128)
    email: str | None = Field(default=None, max_length=128)
    nickname: str | None = Field(default=None, max_length=64)


class TokenResponse(BaseSchema):
    access_token: str
    token_type: str = "bearer"
    expires_in: int = Field(description="有效期（秒）")
    user: UserOut


class LoginResponse(TokenResponse):
    pass
