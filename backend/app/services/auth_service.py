"""认证服务。"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import (
    AccountDisabledError,
    BadRequestError,
    ConflictError,
    UnauthorizedError,
)
from app.core.logging import get_logger
from app.core.security import create_access_token, decode_access_token, hash_password, verify_password
from app.models.user import User, UserRole, UserStatus
from app.repositories.user_repo import UserRepository
from app.schemas.auth import LoginRequest, RegisterRequest
from app.schemas.user import UserOut

logger = get_logger(__name__)


class AuthService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.users = UserRepository(session)

    # ------------------------------------------------------------------ #
    async def register(self, data: RegisterRequest, *, role: str = UserRole.USER) -> User:
        if len(data.password) < settings.password_min_length:
            raise BadRequestError(f"密码长度不能少于 {settings.password_min_length} 位")
        if await self.users.username_exists(data.username):
            raise ConflictError("用户名已被注册")
        if data.email and await self.users.email_exists(data.email):
            raise ConflictError("邮箱已被注册")

        # 系统第一个用户自动成为管理员，方便开箱即用
        is_first_user = not await self.users.exists_any()
        user = User(
            username=data.username.strip(),
            email=(data.email or None),
            nickname=data.nickname or data.username,
            password_hash=hash_password(data.password),
            role=UserRole.ADMIN if (is_first_user or role == UserRole.ADMIN) else UserRole.USER,
            is_superuser=is_first_user,
            status=UserStatus.ACTIVE,
        )
        self.session.add(user)
        await self.session.flush()
        logger.info("注册用户成功 username=%s role=%s", user.username, user.role)
        return user

    # ------------------------------------------------------------------ #
    async def authenticate(self, login: str, password: str) -> User:
        user = await self.users.get_by_login(login)
        if user is None or not verify_password(password, user.password_hash):
            raise UnauthorizedError("用户名或密码错误")
        if not user.is_active:
            raise AccountDisabledError()
        return user

    async def login(self, data: LoginRequest) -> dict:
        user = await self.authenticate(data.username, data.password)
        user.last_login_at = datetime.now()
        await self.session.flush()
        await self.session.commit()
        return self.build_token_payload(user)

    @staticmethod
    def build_token_payload(user: User) -> dict:
        expires_minutes = settings.access_token_expire_minutes
        token = create_access_token(
            user.id,
            expires_minutes=expires_minutes,
            extra={"username": user.username, "role": user.role},
        )
        return {
            "access_token": token,
            "token_type": "bearer",
            "expires_in": expires_minutes * 60,
            "user": UserOut.model_validate(
                {**user.to_dict(exclude={"password_hash"}), "is_admin": user.is_admin}
            ),
        }

    # ------------------------------------------------------------------ #
    async def resolve_user_by_token(self, token: str) -> User:
        payload = decode_access_token(token)
        subject = payload.get("sub")
        if not subject:
            raise UnauthorizedError("登录凭证无效")
        user = await self.users.get(int(subject))
        if user is None:
            raise UnauthorizedError("用户不存在或已被删除")
        if not user.is_active:
            raise AccountDisabledError()
        return user

    async def change_password(self, user: User, old_password: str, new_password: str) -> None:
        if not verify_password(old_password, user.password_hash):
            raise BadRequestError("原密码不正确")
        if len(new_password) < settings.password_min_length:
            raise BadRequestError(f"新密码长度不能少于 {settings.password_min_length} 位")
        if old_password == new_password:
            raise BadRequestError("新密码不能与原密码相同")
        user.password_hash = hash_password(new_password)
        await self.session.flush()
        logger.info("用户 %s 修改密码成功", user.id)

    async def logout(self, user: User) -> None:
        """JWT 无状态，这里仅记录日志；如需强制失效可接入 Redis 黑名单。"""
        logger.info("用户 %s 退出登录", user.id)
