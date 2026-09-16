"""认证路由：/api/auth/*"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.response import Envelope, ok
from app.db.session import get_db
from app.models.user import User
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse
from app.schemas.common import MessageResponse
from app.schemas.user import PasswordChange, UserOut
from app.services.auth_service import AuthService
from app.services.user_service import to_user_out

router = APIRouter(prefix="/auth", tags=["认证"])


@router.post(
    "/register",
    response_model=Envelope[TokenResponse],
    status_code=status.HTTP_201_CREATED,
    summary="注册（系统首个用户自动成为管理员）",
)
async def register(payload: RegisterRequest, db: AsyncSession = Depends(get_db)) -> dict:
    service = AuthService(db)
    user = await service.register(payload)
    await db.commit()
    return ok(service.build_token_payload(user), "注册成功")


@router.post("/login", response_model=Envelope[TokenResponse], summary="登录")
async def login(payload: LoginRequest, db: AsyncSession = Depends(get_db)) -> dict:
    return ok(await AuthService(db).login(payload), "登录成功")


@router.get("/me", response_model=Envelope[UserOut], summary="获取当前用户信息")
async def me(user: User = Depends(get_current_user)) -> dict:
    return ok(to_user_out(user))


@router.post("/logout", response_model=Envelope[MessageResponse], summary="退出登录")
async def logout(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> dict:
    await AuthService(db).logout(user)
    return ok(MessageResponse(message="已退出登录"))


@router.post("/password", response_model=Envelope[MessageResponse], summary="修改密码")
async def change_password(
    payload: PasswordChange,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    await AuthService(db).change_password(user, payload.old_password, payload.new_password)
    await db.commit()
    return ok(MessageResponse(message="密码修改成功，请重新登录"))
