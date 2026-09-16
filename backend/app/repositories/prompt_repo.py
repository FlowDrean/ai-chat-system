"""Prompt / 调用日志仓储。"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, or_, select

from app.models.prompt import Prompt
from app.models.usage import UsageLog, UsageSource
from app.repositories.base import BaseRepository


class PromptRepository(BaseRepository[Prompt]):
    model = Prompt
    not_found_message = "Prompt 不存在"

    async def list_visible(
        self,
        user_id: int,
        *,
        keyword: str | None = None,
        scene: str | None = None,
        enabled: bool | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[Prompt], int]:
        """可见范围 = 系统内置（user_id 为空） + 自己的。"""
        where = [or_(Prompt.user_id == user_id, Prompt.user_id.is_(None))]
        if keyword:
            like = f"%{keyword.strip()}%"
            where.append(or_(Prompt.name.like(like), Prompt.description.like(like)))
        if scene:
            where.append(Prompt.scene == scene)
        if enabled is not None:
            where.append(Prompt.enabled.is_(enabled))
        return await self.paginate(
            *where, order_by=[Prompt.is_builtin.desc(), Prompt.id.desc()], offset=offset, limit=limit
        )

    async def get_visible(self, prompt_id: int, user_id: int | None) -> Prompt | None:
        if user_id is None:
            return await self.get(prompt_id)
        return await self.find_one(Prompt.id == prompt_id, or_(Prompt.user_id == user_id, Prompt.user_id.is_(None)))

    async def list_builtin(self) -> list[Prompt]:
        return await self.list_all(Prompt.is_builtin.is_(True), order_by=[Prompt.id.asc()])


class UsageRepository(BaseRepository[UsageLog]):
    model = UsageLog
    not_found_message = "调用日志不存在"

    async def log(
        self,
        *,
        user_id: int | None = None,
        conversation_id: int | None = None,
        message_id: int | None = None,
        knowledge_base_id: int | None = None,
        provider: str | None = None,
        model_name: str | None = None,
        source: str = UsageSource.CHAT,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        total_tokens: int = 0,
        retrieved_chunks: int = 0,
        latency_ms: float = 0.0,
        success: bool = True,
        error_message: str | None = None,
    ) -> UsageLog:
        return await self.create(
            user_id=user_id,
            conversation_id=conversation_id,
            message_id=message_id,
            knowledge_base_id=knowledge_base_id,
            provider=provider,
            model_name=model_name,
            source=source,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            retrieved_chunks=retrieved_chunks,
            latency_ms=latency_ms,
            success=success,
            error_message=error_message,
        )

    async def count_between(self, start: datetime, end: datetime, user_id: int | None = None) -> int:
        where = [UsageLog.created_at >= start, UsageLog.created_at < end]
        if user_id is not None:
            where.append(UsageLog.user_id == user_id)
        return await self.count(*where)

    async def sum_tokens_between(self, start: datetime, end: datetime, user_id: int | None = None) -> int:
        stmt = select(func.coalesce(func.sum(UsageLog.total_tokens), 0)).where(
            UsageLog.created_at >= start, UsageLog.created_at < end
        )
        if user_id is not None:
            stmt = stmt.where(UsageLog.user_id == user_id)
        result = await self.session.execute(stmt)
        return int(result.scalar_one() or 0)

    async def count_by_source_between(
        self, start: datetime, end: datetime, source: str, user_id: int | None = None
    ) -> int:
        where = [UsageLog.created_at >= start, UsageLog.created_at < end, UsageLog.source == source]
        if user_id is not None:
            where.append(UsageLog.user_id == user_id)
        return await self.count(*where)

    async def sum_retrieved_chunks_between(self, start: datetime, end: datetime, user_id: int | None = None) -> int:
        stmt = select(func.coalesce(func.sum(UsageLog.retrieved_chunks), 0)).where(
            UsageLog.created_at >= start, UsageLog.created_at < end
        )
        if user_id is not None:
            stmt = stmt.where(UsageLog.user_id == user_id)
        result = await self.session.execute(stmt)
        return int(result.scalar_one() or 0)

    async def daily_trend(self, start: datetime, end: datetime, user_id: int | None = None) -> list[dict]:
        """按天聚合：消息数 / Token / 调用次数。"""
        date_col = func.date(UsageLog.created_at).label("day")
        stmt = (
            select(
                date_col,
                func.count().label("calls"),
                func.coalesce(func.sum(UsageLog.total_tokens), 0).label("tokens"),
            )
            .where(UsageLog.created_at >= start, UsageLog.created_at < end)
            .group_by(date_col)
            .order_by(date_col.asc())
        )
        if user_id is not None:
            stmt = stmt.where(UsageLog.user_id == user_id)
        result = await self.session.execute(stmt)
        return [{"date": str(row.day), "calls": int(row.calls), "tokens": int(row.tokens)} for row in result.all()]

    async def model_distribution(self, start: datetime, end: datetime, user_id: int | None = None) -> list[dict]:
        stmt = (
            select(UsageLog.model_name, UsageLog.provider, func.count().label("calls"))
            .where(UsageLog.created_at >= start, UsageLog.created_at < end, UsageLog.model_name.is_not(None))
            .group_by(UsageLog.model_name, UsageLog.provider)
            .order_by(func.count().desc())
            .limit(10)
        )
        if user_id is not None:
            stmt = stmt.where(UsageLog.user_id == user_id)
        result = await self.session.execute(stmt)
        return [{"name": row.model_name, "provider": row.provider, "value": int(row.calls)} for row in result.all()]

    async def knowledge_distribution(self, start: datetime, end: datetime, user_id: int | None = None) -> list[dict]:
        stmt = (
            select(UsageLog.knowledge_base_id, func.count().label("calls"))
            .where(
                UsageLog.created_at >= start,
                UsageLog.created_at < end,
                UsageLog.knowledge_base_id.is_not(None),
                UsageLog.retrieved_chunks > 0,
            )
            .group_by(UsageLog.knowledge_base_id)
            .order_by(func.count().desc())
            .limit(10)
        )
        if user_id is not None:
            stmt = stmt.where(UsageLog.user_id == user_id)
        result = await self.session.execute(stmt)
        return [{"kb_id": row.knowledge_base_id, "value": int(row.calls)} for row in result.all()]
