"""API 依赖：当前用户、权限校验、分页参数。"""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Depends, Query, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import PermissionDeniedError, UnauthorizedError
from app.core.logging import user_id_ctx
from app.db.session import get_db
from app.models.user import User
from app.services.auth_service import AuthService

bearer_scheme = HTTPBearer(auto_error=False, description="Bearer <access_token>")


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """解析 Bearer Token → 当前用户。"""
    token: str | None = None
    if credentials is not None and credentials.scheme.lower() == "bearer":
        token = credentials.credentials
    if not token:
        # 兼容 SSE（EventSource 无法自定义请求头）等场景
        token = request.headers.get("X-Access-Token") or request.query_params.get("token")
    if not token:
        raise UnauthorizedError("缺少访问令牌，请先登录")

    user = await AuthService(db).resolve_user_by_token(token)
    user_id_ctx.set(str(user.id))
    return user


async def get_current_admin(user: User = Depends(get_current_user)) -> User:
    """要求管理员权限。"""
    if not user.is_admin:
        raise PermissionDeniedError("该操作仅管理员可用")
    return user


async def get_optional_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User | None:
    if credentials is None:
        return None
    try:
        return await AuthService(db).resolve_user_by_token(credentials.credentials)
    except Exception:  # noqa: BLE001
        return None


@dataclass(slots=True)
class Pagination:
    page: int = 1
    page_size: int = 20

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


def pagination(
    page: int = Query(1, ge=1, le=10000, description="页码"),
    page_size: int = Query(20, ge=1, le=200, description="每页条数"),
) -> Pagination:
    return Pagination(page=page, page_size=page_size)
