"""用户仓储。"""

from __future__ import annotations

from sqlalchemy import or_, select

from app.models.user import User, UserRole, UserStatus
from app.repositories.base import BaseRepository


class UserRepository(BaseRepository[User]):
    model = User
    not_found_message = "用户不存在"

    async def get_by_username(self, username: str) -> User | None:
        return await self.find_one(User.username == username)

    async def get_by_login(self, login: str) -> User | None:
        """支持用户名或邮箱登录。"""
        stmt = select(User).where(or_(User.username == login, User.email == login.lower())).limit(1)
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def username_exists(self, username: str, exclude_id: int | None = None) -> bool:
        stmt = select(User.id).where(User.username == username)
        if exclude_id:
            stmt = stmt.where(User.id != exclude_id)
        result = await self.session.execute(stmt.limit(1))
        return result.scalars().first() is not None

    async def email_exists(self, email: str, exclude_id: int | None = None) -> bool:
        stmt = select(User.id).where(User.email == email.lower())
        if exclude_id:
            stmt = stmt.where(User.id != exclude_id)
        result = await self.session.execute(stmt.limit(1))
        return result.scalars().first() is not None

    async def search(
        self,
        keyword: str | None = None,
        *,
        role: str | None = None,
        status: int | None = None,
        offset: int = 0,
        limit: int = 20,
    ) -> tuple[list[User], int]:
        where = []
        if keyword:
            like = f"%{keyword.strip()}%"
            where.append(or_(User.username.like(like), User.email.like(like), User.nickname.like(like)))
        if role:
            where.append(User.role == role)
        if status is not None:
            where.append(User.status == status)
        return await self.paginate(*where, order_by=[User.id.desc()], offset=offset, limit=limit)

    async def count_admins(self) -> int:
        return await self.count(User.role == UserRole.ADMIN)

    async def count_all(self) -> int:
        return await self.count()

    async def exists_any(self) -> bool:
        result = await self.session.execute(select(User.id).limit(1))
        return result.scalars().first() is not None

    async def count_active(self) -> int:
        return await self.count(User.status == UserStatus.ACTIVE)
