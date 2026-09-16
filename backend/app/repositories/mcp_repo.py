"""MCP Server 仓储。"""

from __future__ import annotations

from sqlalchemy import or_, select

from app.models.mcp_server import McpServer
from app.repositories.base import BaseRepository


class McpServerRepository(BaseRepository[McpServer]):
    model = McpServer
    not_found_message = "MCP 服务不存在"

    async def list_servers(
        self,
        *,
        keyword: str | None = None,
        transport: str | None = None,
        enabled: bool | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[McpServer], int]:
        where = []
        if keyword:
            like = f"%{keyword.strip()}%"
            where.append(or_(McpServer.name.like(like), McpServer.slug.like(like), McpServer.url.like(like)))
        if transport:
            where.append(McpServer.transport == transport)
        if enabled is not None:
            where.append(McpServer.enabled == enabled)
        return await self.paginate(
            *where,
            order_by=[McpServer.sort_order.asc(), McpServer.id.asc()],
            offset=offset,
            limit=limit,
        )

    async def get_by_slug(self, slug: str) -> McpServer | None:
        return await self.find_one(McpServer.slug == slug)

    async def list_active(self, *, visible_only: bool = False) -> list[McpServer]:
        where = [McpServer.enabled.is_(True)]
        if visible_only:
            where.append(McpServer.visible_to_users.is_(True))
        return await self.list_all(
            *where, order_by=[McpServer.sort_order.asc(), McpServer.id.asc()], limit=100
        )

    async def list_by_ids(self, ids: list[int]) -> list[McpServer]:
        if not ids:
            return []
        stmt = (
            select(McpServer)
            .where(McpServer.id.in_(ids), McpServer.enabled.is_(True))
            .order_by(McpServer.sort_order.asc(), McpServer.id.asc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def count_all(self) -> int:
        return await self.count()
