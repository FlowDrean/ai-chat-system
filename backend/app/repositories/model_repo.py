"""模型配置仓储。"""

from __future__ import annotations

from sqlalchemy import or_, select, update

from app.models.model_config import ModelConfig
from app.repositories.base import BaseRepository


class ModelRepository(BaseRepository[ModelConfig]):
    model = ModelConfig
    not_found_message = "模型不存在"

    async def list_models(
        self,
        *,
        keyword: str | None = None,
        provider: str | None = None,
        enabled: bool | None = None,
        offset: int = 0,
        limit: int = 100,
        only_enabled: bool = False,
    ) -> tuple[list[ModelConfig], int]:
        where = []
        if keyword:
            like = f"%{keyword.strip()}%"
            where.append(or_(ModelConfig.name.like(like), ModelConfig.model_name.like(like)))
        if provider:
            where.append(ModelConfig.provider == provider)
        if enabled is not None:
            where.append(ModelConfig.enabled == enabled)
        if only_enabled:
            where.append(ModelConfig.enabled.is_(True))
        return await self.paginate(
            *where,
            order_by=[ModelConfig.is_default.desc(), ModelConfig.id.desc()],
            offset=offset,
            limit=limit,
        )

    async def get_default(self) -> ModelConfig | None:
        stmt = (
            select(ModelConfig)
            .where(ModelConfig.enabled.is_(True), ModelConfig.is_default.is_(True))
            .order_by(ModelConfig.id.desc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        model = result.scalars().first()
        if model is not None:
            return model
        # 没有显式默认模型时，退化为第一个可用模型
        stmt = select(ModelConfig).where(ModelConfig.enabled.is_(True)).order_by(ModelConfig.id.asc()).limit(1)
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def clear_default(self, exclude_id: int | None = None) -> None:
        stmt = update(ModelConfig).where(ModelConfig.is_default.is_(True))
        if exclude_id:
            stmt = stmt.where(ModelConfig.id != exclude_id)
        await self.session.execute(stmt.values(is_default=False))

    async def count_enabled(self) -> int:
        return await self.count(ModelConfig.enabled.is_(True))

    async def count_all(self) -> int:
        return await self.count()
