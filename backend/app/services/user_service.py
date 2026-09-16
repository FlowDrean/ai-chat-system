"""用户管理服务（管理员 / 个人资料）。"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import BadRequestError, ConflictError, PermissionDeniedError
from app.core.logging import get_logger
from app.core.security import hash_password
from app.models.user import User, UserRole, UserStatus
from app.repositories.user_repo import UserRepository
from app.schemas.user import UserCreate, UserOut, UserUpdate

logger = get_logger(__name__)


def to_user_out(user: User) -> UserOut:
    return UserOut.model_validate({**user.to_dict(exclude={"password_hash"}), "is_admin": user.is_admin})


class UserService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.users = UserRepository(session)

    # ------------------------------------------------------------------ #
    async def list_users(
        self,
        *,
        keyword: str | None = None,
        role: str | None = None,
        status: int | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[UserOut], int]:
        users, total = await self.users.search(
            keyword, role=role, status=status, offset=(page - 1) * page_size, limit=page_size
        )
        return [to_user_out(u) for u in users], total

    async def get_user(self, user_id: int) -> User:
        return await self.users.get_or_404(user_id)

    # ------------------------------------------------------------------ #
    async def create_user(self, data: UserCreate) -> UserOut:
        if len(data.password) < settings.password_min_length:
            raise BadRequestError(f"密码长度不能少于 {settings.password_min_length} 位")
        if await self.users.username_exists(data.username):
            raise ConflictError("用户名已存在")
        if data.email and await self.users.email_exists(data.email):
            raise ConflictError("邮箱已存在")

        user = User(
            username=data.username,
            email=data.email,
            nickname=data.nickname or data.username,
            password_hash=hash_password(data.password),
            role=data.role,
            status=data.status,
        )
        self.session.add(user)
        await self.session.flush()
        logger.info("管理员创建用户 username=%s role=%s", user.username, user.role)
        return to_user_out(user)

    async def update_user(self, user_id: int, data: UserUpdate, *, operator: User) -> UserOut:
        user = await self.users.get_or_404(user_id)
        payload = data.model_dump(exclude_unset=True)

        if "email" in payload and payload["email"] and await self.users.email_exists(payload["email"], user_id):
            raise ConflictError("邮箱已被其他用户使用")

        if payload.get("role") == UserRole.USER and user.role == UserRole.ADMIN:
            if await self.users.count_admins() <= 1:
                raise BadRequestError("系统必须至少保留一个管理员")
            if user.id == operator.id:
                raise BadRequestError("不能取消自己的管理员权限")

        if payload.get("status") == UserStatus.DISABLED and user.id == operator.id:
            raise BadRequestError("不能禁用当前登录账号")

        for key, value in payload.items():
            setattr(user, key, value)
        await self.session.flush()
        return to_user_out(user)

    async def update_profile(self, user: User, data: UserUpdate) -> UserOut:
        """普通用户更新自己的资料（不允许改角色 / 状态）。"""
        payload = data.model_dump(exclude_unset=True)
        payload.pop("role", None)
        payload.pop("status", None)
        if "email" in payload and payload["email"] and await self.users.email_exists(payload["email"], user.id):
            raise ConflictError("邮箱已被其他用户使用")
        for key, value in payload.items():
            setattr(user, key, value)
        await self.session.flush()
        return to_user_out(user)

    # ------------------------------------------------------------------ #
    async def reset_password(self, user_id: int, new_password: str) -> None:
        if len(new_password) < settings.password_min_length:
            raise BadRequestError(f"密码长度不能少于 {settings.password_min_length} 位")
        user = await self.users.get_or_404(user_id)
        user.password_hash = hash_password(new_password)
        await self.session.flush()
        logger.info("管理员重置用户 %s 的密码", user_id)

    async def delete_user(self, user_id: int, *, operator: User) -> None:
        user = await self.users.get_or_404(user_id)
        if user.id == operator.id:
            raise PermissionDeniedError("不能删除当前登录账号")
        if user.role == UserRole.ADMIN and await self.users.count_admins() <= 1:
            raise BadRequestError("系统必须至少保留一个管理员")
        await self.users.delete(user)
        logger.info("管理员 %s 删除了用户 %s", operator.id, user_id)
