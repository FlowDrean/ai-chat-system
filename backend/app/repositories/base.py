"""仓储基类：封装通用 CRUD / 分页，保持 SQLAlchemy 2.x async 风格。"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Generic, TypeVar

from sqlalchemy import Select, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.db.base import Base

ModelT = TypeVar("ModelT", bound=Base)


class BaseRepository(Generic[ModelT]):
    model: type[ModelT]
    not_found_message = "资源不存在"

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ------------------------------------------------------------------ 查询
    async def get(self, obj_id: int) -> ModelT | None:
        return await self.session.get(self.model, obj_id)

    async def get_or_none(self, obj_id: int) -> ModelT | None:
        return await self.get(obj_id)

    async def get_or_404(self, obj_id: int, message: str | None = None) -> ModelT:
        obj = await self.get(obj_id)
        if obj is None:
            raise NotFoundError(message or self.not_found_message)
        return obj

    async def find_one(self, *where: Any) -> ModelT | None:
        stmt = select(self.model).where(*where).limit(1)
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def list_all(
        self,
        *where: Any,
        order_by: Sequence[Any] | None = None,
        offset: int = 0,
        limit: int | None = None,
        stmt: Select | None = None,
    ) -> list[ModelT]:
        query = stmt if stmt is not None else select(self.model)
        if where:
            query = query.where(*where)
        if order_by:
            query = query.order_by(*order_by)
        if offset:
            query = query.offset(offset)
        if limit is not None:
            query = query.limit(limit)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def paginate(
        self,
        *where: Any,
        order_by: Sequence[Any] | None = None,
        offset: int = 0,
        limit: int = 20,
    ) -> tuple[list[ModelT], int]:
        items = await self.list_all(*where, order_by=order_by, offset=offset, limit=limit)
        total = await self.count(*where)
        return items, total

    async def count(self, *where: Any) -> int:
        stmt = select(func.count()).select_from(self.model)
        if where:
            stmt = stmt.where(*where)
        result = await self.session.execute(stmt)
        return int(result.scalar_one() or 0)

    # ------------------------------------------------------------------ 写入
    async def create(self, **values: Any) -> ModelT:
        obj = self.model(**values)
        self.session.add(obj)
        await self.session.flush()
        return obj

    async def save(self, obj: ModelT) -> ModelT:
        self.session.add(obj)
        await self.session.flush()
        return obj

    async def update(self, obj: ModelT, **values: Any) -> ModelT:
        for key, value in values.items():
            if value is not None:
                setattr(obj, key, value)
        self.session.add(obj)
        await self.session.flush()
        return obj

    async def delete(self, obj: ModelT) -> None:
        await self.session.delete(obj)
        await self.session.flush()

    async def delete_by_id(self, obj_id: int) -> bool:
        result = await self.session.execute(delete(self.model).where(self.model.id == obj_id))  # type: ignore[attr-defined]
        await self.session.flush()
        return bool(result.rowcount)

    async def refresh(self, obj: ModelT) -> ModelT:
        await self.session.refresh(obj)
        return obj
