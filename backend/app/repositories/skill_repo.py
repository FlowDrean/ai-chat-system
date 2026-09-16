"""技能仓储。"""

from __future__ import annotations

from sqlalchemy import or_, select

from app.models.skill import Skill
from app.repositories.base import BaseRepository


class SkillRepository(BaseRepository[Skill]):
    model = Skill
    not_found_message = "技能不存在"

    async def list_skills(
        self,
        *,
        keyword: str | None = None,
        type: str | None = None,  # noqa: A002 - 与字段名保持一致
        enabled: bool | None = None,
        visible: bool | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> tuple[list[Skill], int]:
        where = []
        if keyword:
            like = f"%{keyword.strip()}%"
            where.append(or_(Skill.name.like(like), Skill.slug.like(like), Skill.description.like(like)))
        if type:
            where.append(Skill.type == type)
        if enabled is not None:
            where.append(Skill.enabled == enabled)
        if visible is not None:
            where.append(Skill.visible_to_users == visible)
        return await self.paginate(
            *where,
            order_by=[Skill.sort_order.asc(), Skill.id.asc()],
            offset=offset,
            limit=limit,
        )

    async def get_by_slug(self, slug: str) -> Skill | None:
        return await self.find_one(Skill.slug == slug)

    async def list_active(
        self, *, visible_only: bool = False, offset: int = 0, limit: int = 100
    ) -> list[Skill]:
        where = [Skill.enabled.is_(True)]
        if visible_only:
            where.append(Skill.visible_to_users.is_(True))
        return await self.list_all(
            *where, order_by=[Skill.sort_order.asc(), Skill.id.asc()], offset=offset, limit=limit
        )

    async def list_by_ids(self, ids: list[int]) -> list[Skill]:
        if not ids:
            return []
        stmt = (
            select(Skill)
            .where(Skill.id.in_(ids), Skill.enabled.is_(True))
            .order_by(Skill.sort_order.asc(), Skill.id.asc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def count_all(self) -> int:
        return await self.count()
