"""用户管理路由：/api/users/*（管理员）与 /api/profile（个人）"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Pagination, get_current_admin, get_current_user, pagination
from app.core.response import Envelope, ListEnvelope, ok, page
from app.db.session import get_db
from app.models.user import User
from app.schemas.common import MessageResponse
from app.schemas.user import PasswordReset, UserCreate, UserOut, UserUpdate
from app.services.user_service import UserService, to_user_out

router = APIRouter(tags=["用户管理"])


@router.get("/users", response_model=ListEnvelope[UserOut], summary="用户列表（管理员）")
async def list_users(
    keyword: str | None = Query(None, description="用户名 / 邮箱 / 昵称"),
    role: str | None = Query(None, description="user/admin"),
    status: int | None = Query(None, description="1 正常 0 禁用"),
    page_params: Pagination = Depends(pagination),
    _: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    items, total = await UserService(db).list_users(
        keyword=keyword,
        role=role,
        status=status,
        page=page_params.page,
        page_size=page_params.page_size,
    )
    return ok(page([item.model_dump() for item in items], total, page_params.page, page_params.page_size))


@router.post("/users", response_model=Envelope[UserOut], summary="新建用户（管理员）")
async def create_user(
    payload: UserCreate,
    _: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    user = await UserService(db).create_user(payload)
    await db.commit()
    return ok(user, "用户创建成功")


@router.put("/users/{user_id}", response_model=Envelope[UserOut], summary="编辑用户（管理员）")
async def update_user(
    user_id: int,
    payload: UserUpdate,
    operator: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    user = await UserService(db).update_user(user_id, payload, operator=operator)
    await db.commit()
    return ok(user, "用户已更新")


@router.post("/users/{user_id}/reset-password", response_model=Envelope[MessageResponse], summary="重置密码")
async def reset_password(
    user_id: int,
    payload: PasswordReset,
    _: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    await UserService(db).reset_password(user_id, payload.new_password)
    await db.commit()
    return ok(MessageResponse(message="密码已重置"))


@router.delete("/users/{user_id}", response_model=Envelope[MessageResponse], summary="删除用户（管理员）")
async def delete_user(
    user_id: int,
    operator: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    await UserService(db).delete_user(user_id, operator=operator)
    await db.commit()
    return ok(MessageResponse(message="用户已删除"))


# --------------------------------------------------------------------------- #
# 个人资料
# --------------------------------------------------------------------------- #
profile_router = APIRouter(prefix="/profile", tags=["个人中心"])


@profile_router.get("", response_model=Envelope[UserOut], summary="我的资料")
async def get_profile(user: User = Depends(get_current_user)) -> dict:
    return ok(to_user_out(user))


@profile_router.put("", response_model=Envelope[UserOut], summary="更新我的资料")
async def update_profile(
    payload: UserUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    result = await UserService(db).update_profile(user, payload)
    await db.commit()
    return ok(result, "资料已更新")
