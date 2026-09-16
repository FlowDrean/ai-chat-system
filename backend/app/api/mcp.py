"""MCP 管理路由：/api/mcp/*

* `/mcp/servers`                 MCP 服务 CRUD（管理员）
* `/mcp/servers/{id}/test`       连接测试 + 刷新工具清单
* `/mcp/servers/{id}/tools`      查看缓存的工具清单（含 JSON Schema）
* `/mcp/servers/{id}/call-tool`  调试调用某个工具
* `/mcp/available`               聊天页可选的 MCP 服务（任意登录用户）
* `/mcp/transports`              传输方式说明（前端动态表单）
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Pagination, get_current_admin, get_current_user, pagination
from app.core.response import Envelope, ListEnvelope, ok, page
from app.db.session import get_db
from app.models.user import User
from app.schemas.common import MessageResponse
from app.schemas.mcp import (
    McpExportResult,
    McpImportRequest,
    McpImportResult,
    McpServerCreate,
    McpServerOption,
    McpServerOut,
    McpServerUpdate,
    McpTestResult,
    McpToolCallRequest,
    McpToolCallResult,
    McpToolOut,
    McpTransportInfo,
)
from app.services.mcp_service import McpService

router = APIRouter(prefix="/mcp", tags=["MCP 管理"])


@router.get("/transports", response_model=Envelope[list[McpTransportInfo]], summary="传输方式说明")
async def list_transports(_: User = Depends(get_current_admin), db: AsyncSession = Depends(get_db)) -> dict:
    return ok(McpService(db).transports_info())


@router.post("/import", response_model=Envelope[McpImportResult], summary="导入 mcpServers 配置（管理员）")
async def import_servers(
    payload: McpImportRequest,
    _: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """支持 Claude Desktop / Cursor 的 mcpServers 格式；可自动测试连接并发现工具。"""
    result = await McpService(db).import_servers(payload)
    await db.commit()
    if result["failed"]:
        message = f"导入完成：成功 {result['created'] + result['updated']} 个，失败 {result['failed']} 个"
    else:
        message = f"导入完成：新增 {result['created']} 个，覆盖 {result['updated']} 个，跳过 {result['skipped']} 个"
    return ok(result, message)


@router.get("/export", response_model=Envelope[McpExportResult], summary="导出 mcpServers 配置（管理员）")
async def export_servers(
    include_secrets: bool = Query(False, description="是否包含明文密钥（默认脱敏）"),
    _: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    result = await McpService(db).export_servers(include_secrets=include_secrets)
    return ok(result, f"已导出 {result['count']} 个服务" + ("" if include_secrets else "（密钥已脱敏）"))


@router.get("/available", response_model=Envelope[list[McpServerOption]], summary="聊天可用的 MCP 服务")
async def list_available(_: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> dict:
    return ok([item.model_dump() for item in await McpService(db).list_available()])


@router.get("/servers", response_model=ListEnvelope[McpServerOut], summary="MCP 服务列表（管理员）")
async def list_servers(
    keyword: str | None = Query(None, description="按名称 / 标识 / 地址搜索"),
    transport: str | None = Query(None, description="stdio / sse / http"),
    enabled: bool | None = Query(None),
    page_params: Pagination = Depends(pagination),
    _: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    items, total = await McpService(db).list_servers(
        keyword=keyword,
        transport=transport,
        enabled=enabled,
        page=page_params.page,
        page_size=page_params.page_size,
    )
    return ok(page([item.model_dump() for item in items], total, page_params.page, page_params.page_size))


@router.post("/servers", response_model=Envelope[McpServerOut], summary="新增 MCP 服务（管理员）")
async def create_server(
    payload: McpServerCreate,
    user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    server = await McpService(db).create_server(payload, operator_id=user.id)
    await db.commit()
    return ok(server, "MCP 服务已创建")


@router.get("/servers/{server_id}", response_model=Envelope[McpServerOut], summary="MCP 服务详情")
async def get_server(
    server_id: int,
    _: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    from app.services.mcp_service import to_server_out

    server = await McpService(db).get_server(server_id)
    return ok(to_server_out(server))


@router.put("/servers/{server_id}", response_model=Envelope[McpServerOut], summary="编辑 MCP 服务（管理员）")
async def update_server(
    server_id: int,
    payload: McpServerUpdate,
    _: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    server = await McpService(db).update_server(server_id, payload)
    await db.commit()
    return ok(server, "MCP 服务已更新")


@router.patch("/servers/{server_id}/enabled", response_model=Envelope[McpServerOut], summary="启用 / 禁用")
async def toggle_server(
    server_id: int,
    enabled: bool = Query(..., description="true 启用 false 禁用"),
    _: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    server = await McpService(db).toggle_server(server_id, enabled)
    await db.commit()
    return ok(server, "状态已更新")


@router.delete("/servers/{server_id}", response_model=Envelope[MessageResponse], summary="删除 MCP 服务（管理员）")
async def delete_server(
    server_id: int,
    _: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    await McpService(db).delete_server(server_id)
    await db.commit()
    return ok(MessageResponse(message="MCP 服务已删除"))


@router.post("/servers/{server_id}/test", response_model=Envelope[McpTestResult], summary="连接测试 + 发现工具")
async def test_server(
    server_id: int,
    _: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    service = McpService(db)
    server = await service.get_server(server_id)
    result = await service.refresh_tools(server)
    await db.commit()
    return ok(result, result["message"])


@router.post("/servers/{server_id}/refresh-tools", response_model=Envelope[McpTestResult], summary="刷新工具清单")
async def refresh_tools(
    server_id: int,
    _: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    service = McpService(db)
    server = await service.get_server(server_id)
    result = await service.refresh_tools(server)
    await db.commit()
    return ok(result, result["message"])


@router.get("/servers/{server_id}/tools", response_model=Envelope[list[McpToolOut]], summary="工具清单（缓存）")
async def list_server_tools(
    server_id: int,
    _: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    server = await McpService(db).get_server(server_id)
    return ok(server.cached_tools())


@router.post(
    "/servers/{server_id}/call-tool",
    response_model=Envelope[McpToolCallResult],
    summary="调试调用 MCP 工具",
)
async def call_server_tool(
    server_id: int,
    payload: McpToolCallRequest,
    _: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    result = await McpService(db).call_tool(server_id, payload.tool_name, payload.arguments)
    return ok(result, "调用完成" if result["success"] else (result["error"] or "调用失败"))
