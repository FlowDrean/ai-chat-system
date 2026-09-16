"""MCP Server 服务：CRUD + 连接测试 + 工具发现 + 调试调用 + 聊天时解析可用服务。

安全设计（与「技能」一致）：
* `env` / `headers` 里的敏感值（key、token、secret、password、authorization）加密存储，
  出参只返回掩码；
* 更新时敏感字段传空字符串表示「保持原值不变」，避免前端回显掩码把密钥覆盖掉；
* 连接失败只返回可读原因，不暴露命令路径 / 协议堆栈。
"""

from __future__ import annotations

import json
import re
import time
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BadRequestError, NotFoundError
from app.core.logging import get_logger
from app.core.security import encrypt_secret, mask_secret
from app.mcp import bridge
from app.mcp.client import McpError, McpToolInfo, call_tool, list_tools
from app.models.mcp_server import McpServer, McpStatus, McpTransport
from app.repositories.mcp_repo import McpServerRepository
from app.schemas.mcp import (
    McpImportItemResult,
    McpImportRequest,
    McpImportResult,
    McpServerCreate,
    McpServerOption,
    McpServerOut,
    McpServerUpdate,
    McpToolOut,
)

logger = get_logger(__name__)

_SLUG_SAFE = re.compile(r"[^a-z0-9_-]")
_SECRET_KEY_RE = re.compile(r"(api[_-]?key|secret|token|password|authorization|auth)", re.I)

# 敏感值加密后统一加这个前缀，便于识别「已加密」与「历史明文」
_ENC_PREFIX = "enc::"


def _slugify(text: str) -> str:
    """生成 ASCII slug；纯中文名称时退化为 srv+短哈希（工具名必须是 ASCII）。"""
    import hashlib

    base = _SLUG_SAFE.sub("-", (text or "").strip().lower())
    base = re.sub(r"-{2,}", "-", base).strip("-")
    if base:
        return base
    digest = hashlib.blake2b((text or "mcp").encode("utf-8"), digest_size=4).hexdigest()
    return f"srv{digest}"


def _encrypt_mapping(data: dict[str, Any] | None) -> dict[str, str] | None:
    """加密 env / headers 里所有值（保持简单：整份值都加密，出参再脱敏）。"""
    if not data:
        return None
    result: dict[str, str] = {}
    for key, value in data.items():
        text = "" if value is None else str(value)
        if not text:
            result[str(key)] = ""
            continue
        result[str(key)] = f"{_ENC_PREFIX}{encrypt_secret(text) or ''}"
    return result


def _decrypt_value(raw: str | None) -> str:
    if not raw:
        return ""
    if raw.startswith(_ENC_PREFIX):
        from app.core.security import decrypt_secret

        return decrypt_secret(raw[len(_ENC_PREFIX) :]) or ""
    return raw


def _decrypt_mapping(data: dict[str, Any] | None) -> dict[str, str]:
    if not data:
        return {}
    return {str(k): _decrypt_value(v if isinstance(v, str) else str(v)) for k, v in data.items()}


def _mask_mapping(data: dict[str, Any] | None) -> tuple[dict[str, str] | None, list[str]]:
    """出参脱敏：敏感 key 只返回掩码。"""
    if not data:
        return None, []
    masked: dict[str, str] = {}
    keys: list[str] = []
    for key, value in data.items():
        plain = _decrypt_value(value if isinstance(value, str) else str(value))
        if _SECRET_KEY_RE.search(str(key)) and plain:
            masked[str(key)] = mask_secret(plain) or "******"
            keys.append(str(key))
        else:
            masked[str(key)] = plain
    return masked, keys


def to_server_out(server: McpServer) -> McpServerOut:
    env, env_keys = _mask_mapping(server.env)
    headers, header_keys = _mask_mapping(server.headers)
    data = server.to_dict(exclude={"tools_cache"})
    data.update(
        {
            "transport_label": McpTransport.LABELS.get(server.transport, server.transport),
            "env": env,
            "headers": headers,
            "masked_keys": sorted(set(env_keys + header_keys)),
            "tools": server.cached_tools(),
        }
    )
    return McpServerOut.model_validate(data)


class McpService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.servers = McpServerRepository(session)

    # ------------------------------------------------------------------ #
    # 查询
    # ------------------------------------------------------------------ #
    async def list_servers(
        self,
        *,
        keyword: str | None = None,
        transport: str | None = None,
        enabled: bool | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[McpServerOut], int]:
        items, total = await self.servers.list_servers(
            keyword=keyword,
            transport=transport,
            enabled=enabled,
            offset=(page - 1) * page_size,
            limit=page_size,
        )
        return [to_server_out(item) for item in items], total

    async def get_server(self, server_id: int) -> McpServer:
        return await self.servers.get_or_404(server_id)

    async def list_available(self) -> list[McpServerOption]:
        rows = await self.servers.list_active(visible_only=True)
        return [
            McpServerOption(
                id=row.id,
                name=row.name,
                slug=row.slug,
                transport=row.transport,
                description=row.description,
                tool_count=row.tool_count,
                status=row.status,
            )
            for row in rows
        ]

    # ------------------------------------------------------------------ #
    # 写入
    # ------------------------------------------------------------------ #
    async def create_server(self, data: McpServerCreate, operator_id: int | None = None) -> McpServerOut:
        try:
            data.validate_transport_fields()
        except ValueError as exc:
            raise BadRequestError(str(exc)) from exc

        slug = data.slug or _slugify(data.name)
        if await self.servers.get_by_slug(slug) is not None:
            if data.slug:
                raise BadRequestError(f"标识「{slug}」已被占用，请换一个")
            slug = await self._unique_slug(slug)

        server = McpServer(
            name=data.name.strip(),
            slug=slug,
            transport=data.transport,
            description=data.description,
            command=(data.command or "").strip() or None,
            args=data.args,
            env=_encrypt_mapping(data.env),
            cwd=(data.cwd or "").strip() or None,
            url=(data.url or "").strip() or None,
            headers=_encrypt_mapping(data.headers),
            enabled=data.enabled,
            visible_to_users=data.visible_to_users,
            timeout=data.timeout,
            sort_order=data.sort_order,
            created_by=operator_id,
        )
        self.session.add(server)
        await self.session.flush()
        logger.info(
            "新建 MCP 服务 id=%s name=%s transport=%s", server.id, server.name, server.transport
        )
        return to_server_out(server)

    async def update_server(self, server_id: int, data: McpServerUpdate) -> McpServerOut:
        server = await self.get_server(server_id)
        payload = data.model_dump(exclude_unset=True)

        env = payload.pop("env", None)
        if env is not None:
            server.env = self._merge_secrets(server.env, env)
        headers = payload.pop("headers", None)
        if headers is not None:
            server.headers = self._merge_secrets(server.headers, headers)

        for key in ("name", "transport", "description", "command", "args", "cwd", "url",
                    "enabled", "visible_to_users", "timeout", "sort_order"):
            if key in payload and payload[key] is not None:
                setattr(server, key, payload[key])

        # 传输相关字段变更后，旧工具缓存可能失效
        if any(key in payload for key in ("transport", "command", "args", "url", "env", "headers")):
            server.status = McpStatus.UNKNOWN
            server.status_message = "配置已变更，请重新测试连接"

        if server.transport == McpTransport.STDIO and not (server.command or "").strip():
            raise BadRequestError("stdio 传输必须填写启动命令（command）")
        if server.transport in (McpTransport.SSE, McpTransport.HTTP) and not (server.url or "").strip():
            raise BadRequestError(f"{server.transport} 传输必须填写服务地址（url）")

        await self.session.flush()
        logger.info("更新 MCP 服务 id=%s name=%s", server.id, server.name)
        return to_server_out(server)

    async def delete_server(self, server_id: int) -> None:
        server = await self.get_server(server_id)
        await self.servers.delete(server)
        logger.info("删除 MCP 服务 id=%s name=%s", server_id, server.name)

    async def toggle_server(self, server_id: int, enabled: bool) -> McpServerOut:
        server = await self.get_server(server_id)
        server.enabled = enabled
        await self.session.flush()
        return to_server_out(server)

    # ------------------------------------------------------------------ #
    # 连接测试 / 工具发现
    # ------------------------------------------------------------------ #
    async def test_server(self, server_id: int) -> dict[str, Any]:
        server = await self.get_server(server_id)
        return await self.refresh_tools(server)

    async def refresh_tools(self, server: McpServer) -> dict[str, Any]:
        """连接并拉取工具清单，结果写入缓存与状态。"""
        from datetime import datetime

        started = time.perf_counter()
        try:
            tools = await list_tools(server)
        except McpError as exc:
            latency = (time.perf_counter() - started) * 1000
            server.status = McpStatus.ERROR
            server.status_message = str(exc)[:500]
            await self.session.flush()
            return {
                "success": False,
                "message": str(exc),
                "latency_ms": round(latency, 1),
                "tool_count": 0,
                "tools": [],
            }

        latency = (time.perf_counter() - started) * 1000
        server.tools_cache = [tool.to_dict() for tool in tools]
        server.tool_count = len(tools)
        server.status = McpStatus.OK
        server.status_message = f"连接成功，发现 {len(tools)} 个工具"
        server.last_connected_at = datetime.now()
        await self.session.flush()
        logger.info("MCP 工具发现成功 id=%s name=%s tools=%s", server.id, server.name, len(tools))
        return {
            "success": True,
            "message": server.status_message,
            "latency_ms": round(latency, 1),
            "tool_count": len(tools),
            "tools": [tool.to_dict() for tool in tools],
        }

    async def ensure_tools(self, server: McpServer) -> list[dict[str, Any]]:
        """聊天前确保有工具缓存（首次自动发现一次）。"""
        if server.cached_tools():
            return server.cached_tools()
        result = await self.refresh_tools(server)
        await self.session.commit()
        if not result["success"]:
            logger.info("MCP 服务 %s 自动发现工具失败：%s", server.name, result["message"])
        return server.cached_tools()

    async def call_tool(
        self, server_id: int, tool_name: str, arguments: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """调试用：直接调用某个 MCP 工具。"""
        server = await self.get_server(server_id)
        started = time.perf_counter()
        try:
            result = await call_tool(server, tool_name, arguments or {})
        except McpError as exc:
            return {
                "success": False,
                "output": "",
                "error": str(exc),
                "latency_ms": round((time.perf_counter() - started) * 1000, 1),
                "is_error": True,
            }
        latency = (time.perf_counter() - started) * 1000
        return {
            "success": not result.is_error,
            "output": result.text,
            "error": result.text if result.is_error else None,
            "latency_ms": round(latency, 1),
            "is_error": result.is_error,
        }

    # ------------------------------------------------------------------ #
    # 聊天集成
    # ------------------------------------------------------------------ #
    async def resolve_for_chat(self, server_ids: list[int] | None) -> list[McpServer]:
        """解析本次对话可用的 MCP 服务（自动过滤禁用 / 不可见 / 无工具的）。"""
        if not server_ids:
            return []
        rows = await self.servers.list_by_ids([int(i) for i in server_ids if i])
        usable: list[McpServer] = []
        for row in rows:
            if not row.visible_to_users:
                continue
            tools = await self.ensure_tools(row)
            if tools:
                usable.append(row)
        return usable

    # ------------------------------------------------------------------ #
    # 配置导入 / 导出（mcpServers 格式）
    # ------------------------------------------------------------------ #
    @staticmethod
    def parse_import_payload(raw: Any) -> list[tuple[str, dict[str, Any]]]:
        """解析多种常见的 MCP 配置写法，返回 [(名称, 原始配置), ...]。

        支持：
        * Claude Desktop / Cursor：`{"mcpServers": {"name": {...}}}`
        * VS Code 风格：`{"servers": {...}}` / `{"mcp": {"servers": {...}}}`
        * 只粘贴单个服务对象：`{"command": "npx", ...}` 或 `{"url": "..."}`
        * 直接粘贴服务数组：`[{"name": "x", "command": "npx"}]`
        """
        if isinstance(raw, str):
            text = raw.strip()
            if not text:
                raise BadRequestError("导入内容为空")
            try:
                data = json.loads(text)
            except ValueError as exc:
                raise BadRequestError(f"JSON 解析失败：{exc}") from exc
        else:
            data = raw

        def looks_like_server(item: Any) -> bool:
            return isinstance(item, dict) and any(
                key in item for key in ("command", "url", "serverUrl", "endpoint", "type", "transport")
            )

        if isinstance(data, list):
            items = [(str(item.get("name") or f"mcp-{index + 1}"), item) for index, item in enumerate(data) if isinstance(item, dict)]
            if not items:
                raise BadRequestError("配置数组里没有有效的服务定义")
            return items

        if not isinstance(data, dict):
            raise BadRequestError("配置必须是 JSON 对象或数组")

        # 逐层解开常见包装
        for key in ("mcpServers", "mcp_servers", "servers", "mcp"):
            value = data.get(key)
            if isinstance(value, dict):
                if "servers" in value and isinstance(value["servers"], dict):
                    value = value["servers"]
                nested = {
                    str(name): spec
                    for name, spec in value.items()
                    if isinstance(spec, dict)
                }
                if nested:
                    return list(nested.items())
            elif isinstance(value, list):
                nested = [(str(item.get("name") or f"mcp-{i + 1}"), item) for i, item in enumerate(value) if isinstance(item, dict)]
                if nested:
                    return nested

        if looks_like_server(data):
            return [(str(data.get("name") or "imported-mcp"), data)]

        # 兜底：直接当成 {名称: 配置}
        nested = [(str(name), spec) for name, spec in data.items() if looks_like_server(spec)]
        if nested:
            return nested
        raise BadRequestError(
            "无法识别配置格式：需要 mcpServers / servers 包裹，或包含 command / url 的服务定义"
        )

    @staticmethod
    def normalize_import_item(name: str, spec: dict[str, Any]) -> dict[str, Any]:
        """把外部配置规范化为本系统的字段结构。"""
        env = spec.get("env") or spec.get("environment") or {}
        headers = spec.get("headers") or {}
        url = spec.get("url") or spec.get("serverUrl") or spec.get("endpoint") or spec.get("baseUrl")
        command = spec.get("command")
        type_hint = str(spec.get("type") or spec.get("transport") or "").strip().lower()

        if command:
            transport = McpTransport.STDIO
        elif url:
            if type_hint in {"sse"}:
                transport = McpTransport.SSE
            elif type_hint in {"stdio"}:
                transport = McpTransport.STDIO
            else:  # http / streamable-http / streamable_http / 未标注  默认新版 HTTP 传输
                transport = McpTransport.HTTP
        else:
            raise BadRequestError(f"服务「{name}」既没有 command 也没有 url，无法导入")

        disabled = bool(spec.get("disabled") or spec.get("enabled") is False)
        return {
            "name": str(spec.get("title") or spec.get("name") or name).strip() or name,
            "slug": str(name),
            "transport": transport,
            "description": (spec.get("description") or spec.get("desc") or "").strip() or None,
            "command": str(command).strip() if command else None,
            "args": [str(item) for item in (spec.get("args") or [])] if isinstance(spec.get("args") or [], list) else None,
            "env": {str(k): "" if v is None else str(v) for k, v in env.items()} if isinstance(env, dict) else None,
            "cwd": spec.get("cwd") or None,
            "url": str(url).strip() if url else None,
            "headers": {str(k): "" if v is None else str(v) for k, v in headers.items()} if isinstance(headers, dict) else None,
            "timeout": int(spec.get("timeout") or 60),
            "disabled": disabled,
        }

    async def import_servers(self, payload: McpImportRequest) -> dict[str, Any]:
        """批量导入 MCP 服务（可自动测试连接）。"""
        import asyncio
        import time

        try:
            parsed = self.parse_import_payload(payload.payload)
        except BadRequestError:
            raise

        warnings: list[str] = []
        items: list[McpImportItemResult] = []
        to_test: list[tuple[McpServer, McpImportItemResult]] = []

        for raw_name, spec in parsed:
            try:
                normalized = self.normalize_import_item(raw_name, spec)
            except BadRequestError as exc:
                items.append(McpImportItemResult(name=raw_name, action="failed", success=False, message=str(exc)))
                continue

            # 统一走 slugify（纯中文名称会退化为 srv<短哈希>），再入库
            slug = _slugify(normalized["slug"] or normalized["name"])
            normalized["slug"] = slug
            existing = await self.servers.get_by_slug(slug)
            action = "created"

            if existing is not None:
                if payload.strategy == "skip":
                    items.append(
                        McpImportItemResult(
                            name=normalized["name"], slug=existing.slug, server_id=existing.id,
                            transport=existing.transport, action="skipped",
                            message="已存在同名服务，按策略跳过", tool_count=existing.tool_count,
                        )
                    )
                    continue
                if payload.strategy == "overwrite":
                    normalized["slug"] = existing.slug
                    action = "updated"
                else:  # rename
                    new_slug = await self._unique_slug(slug)
                    normalized["slug"] = new_slug
                    action = "renamed"
                    warnings.append(f"「{normalized['name']}」标识已存在，已自动重命名为 {new_slug}")

            if action == "updated" and existing is not None:
                server = await self.servers.get(existing.id)
                await self._apply_import_update(server, normalized, payload)
                await self.session.flush()
                out = to_server_out(server)
                result = McpImportItemResult(
                    name=out.name, slug=out.slug, server_id=out.id, transport=out.transport,
                    action="updated", message="已按策略覆盖原有配置",
                )
                items.append(result)
                to_test.append((server, result))
                continue

            created = await self.create_server(
                McpServerCreate(
                    name=normalized["name"],
                    slug=normalized["slug"],
                    transport=normalized["transport"],
                    description=normalized["description"],
                    command=normalized["command"],
                    args=normalized["args"],
                    env=normalized["env"],
                    cwd=normalized["cwd"],
                    url=normalized["url"],
                    headers=normalized["headers"],
                    enabled=False if normalized["disabled"] else payload.enabled,
                    visible_to_users=payload.visible_to_users,
                    timeout=normalized["timeout"],
                )
            )
            server = await self.servers.get(created.id)
            result = McpImportItemResult(
                name=created.name, slug=created.slug, server_id=created.id,
                transport=created.transport, action=action, message="导入成功",
            )
            items.append(result)
            to_test.append((server, result))

        if payload.auto_test and to_test:
            started = time.perf_counter()
            results = await asyncio.gather(
                *[self.refresh_tools(server) for server, _ in to_test], return_exceptions=True
            )
            for (server, item), outcome in zip(to_test, results):
                if isinstance(outcome, BaseException):
                    item.success = False
                    item.message = f"导入成功，但连接测试异常：{type(outcome).__name__}"
                    continue
                item.tool_count = int(outcome.get("tool_count") or 0)
                item.tools = [McpToolOut.model_validate(tool) for tool in (outcome.get("tools") or [])]
                if outcome.get("success"):
                    item.message = f"导入成功，连接正常（发现 {item.tool_count} 个工具）"
                    item.success = True
                else:
                    item.success = True  # 服务本身已导入成功，只是连不上
                    item.message = f"导入成功，但连接失败：{outcome.get('message')}"
            logger.info("MCP 批量导入完成，共测试 %s 个服务，耗时 %.1fms", len(to_test), (time.perf_counter() - started) * 1000)

        summary = {
            "total": len(items),
            "created": sum(1 for item in items if item.action in {"created", "renamed"}),
            "updated": sum(1 for item in items if item.action == "updated"),
            "skipped": sum(1 for item in items if item.action == "skipped"),
            "failed": sum(1 for item in items if item.action == "failed"),
            "items": [item.model_dump() for item in items],
            "warnings": warnings,
        }
        return summary

    async def _apply_import_update(
        self, server: McpServer, normalized: dict[str, Any], payload: McpImportRequest
    ) -> None:
        """覆盖已存在的服务（敏感值整份替换）。"""
        server.name = normalized["name"]
        server.transport = normalized["transport"]
        server.description = normalized["description"]
        server.command = normalized["command"]
        server.args = normalized["args"]
        server.cwd = normalized["cwd"]
        server.url = normalized["url"]
        server.timeout = normalized["timeout"]
        server.enabled = False if normalized["disabled"] else payload.enabled
        server.visible_to_users = payload.visible_to_users
        if normalized.get("env") is not None:
            server.env = _encrypt_mapping(normalized["env"])
        if normalized.get("headers") is not None:
            server.headers = _encrypt_mapping(normalized["headers"])
        server.status = McpStatus.UNKNOWN
        server.status_message = "配置已通过导入覆盖，请重新测试连接"
        server.tools_cache = None
        server.tool_count = 0

    async def export_servers(self, *, include_secrets: bool = False) -> dict[str, Any]:
        """导出为 mcpServers 格式（默认脱敏，便于分享）。"""
        rows = await self.servers.list_all(order_by=[McpServer.sort_order.asc(), McpServer.id.asc()], limit=200)
        servers: dict[str, Any] = {}
        for row in rows:
            item: dict[str, Any] = {"type": row.transport if row.transport != McpTransport.HTTP else "http"}
            if row.transport == McpTransport.STDIO:
                item.pop("type", None)
                item["command"] = row.command
                if row.args:
                    item["args"] = list(row.args)
                env = _decrypt_mapping(row.env) if include_secrets else _mask_mapping(row.env)[0]
                if env:
                    item["env"] = env
                if row.cwd:
                    item["cwd"] = row.cwd
            else:
                item["url"] = row.url
                headers = _decrypt_mapping(row.headers) if include_secrets else _mask_mapping(row.headers)[0]
                if headers:
                    item["headers"] = headers
            if row.description:
                item["description"] = row.description
            if not row.enabled:
                item["disabled"] = True
            servers[row.slug] = item
        return {
            "content": json.dumps({"mcpServers": servers}, ensure_ascii=False, indent=2),
            "count": len(servers),
            "include_secrets": include_secrets,
        }

    async def mark_used(self, server_ids: list[int]) -> None:
        if not server_ids:
            return
        from datetime import datetime

        from sqlalchemy import update

        await self.session.execute(
            update(McpServer)
            .where(McpServer.id.in_(server_ids))
            .values(usage_count=McpServer.usage_count + 1, last_used_at=datetime.now())
        )
        await self.session.flush()

    def transports_info(self) -> list[dict[str, Any]]:
        return [
            {
                "value": McpTransport.STDIO,
                "label": McpTransport.LABELS[McpTransport.STDIO],
                "description": "在本机启动一个 MCP 进程，通过标准输入输出通信；适合 npx 官方 server、自建脚本",
                "fields": ["command", "args", "env", "cwd"],
            },
            {
                "value": McpTransport.SSE,
                "label": McpTransport.LABELS[McpTransport.SSE],
                "description": "连接远程 SSE 端点（MCP 旧版 HTTP 传输）",
                "fields": ["url", "headers"],
            },
            {
                "value": McpTransport.HTTP,
                "label": McpTransport.LABELS[McpTransport.HTTP],
                "description": "连接远程 Streamable HTTP 端点（MCP 新版传输，推荐）",
                "fields": ["url", "headers"],
            },
        ]

    # ------------------------------------------------------------------ #
    def _merge_secrets(self, stored: dict[str, Any] | None, incoming: dict[str, Any]) -> dict[str, str]:
        """合并敏感配置：传空字符串表示保持原值。"""
        merged: dict[str, str] = {str(k): v for k, v in (stored or {}).items()}
        for key, value in incoming.items():
            key = str(key)
            text = "" if value is None else str(value)
            if text == "" and key in merged:
                continue  # 前端回显的是掩码，留空即不修改
            merged[key] = text
        return _encrypt_mapping(merged) or {}

    async def _unique_slug(self, base: str) -> str:
        slug = base
        index = 2
        while await self.servers.get_by_slug(slug) is not None:
            slug = f"{base}-{index}"
            index += 1
        return slug


__all__ = [
    "McpService",
    "McpToolInfo",
    "bridge",
    "to_server_out",
    "NotFoundError",
]
