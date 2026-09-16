"""把 MCP 工具桥接成 LangChain Tool，从而复用已有的 tool-calling 链路。

    MCP Server ──tools/list──> McpToolInfo(name/description/inputSchema)
                                      │
                                      v
                         json_schema_to_model()  →  pydantic 入参模型
                                      │
                                      v
                      StructuredTool（name/description/args_schema）
                                      │
                                      v
                    LangGraph：generate ⇄ tools（与「技能」完全同一套流程）

注意：工具闭包里只持有**普通 dict 快照**（不是 ORM 对象），
这样即使在后台任务 / 会话关闭后执行也不会出现 detached 实例问题。
"""

from __future__ import annotations

import json
import re
from typing import Any

from langchain_core.tools import BaseTool, StructuredTool
from pydantic import BaseModel, Field, create_model

from app.core.logging import get_logger
from app.mcp import client as mcp_client
from app.mcp.client import McpError

logger = get_logger(__name__)

_NAME_SAFE = re.compile(r"[^a-zA-Z0-9_-]")

_TYPE_MAP: dict[str, type] = {
    "string": str,
    "integer": int,
    "number": float,
    "boolean": bool,
    "array": list,
    "object": dict,
}


def tool_name_for(server_slug: str, tool_name: str) -> str:
    """生成符合 OpenAI function name 规范的工具名：mcp_<server>_<tool>。"""
    raw = f"mcp_{server_slug}_{tool_name}"
    cleaned = _NAME_SAFE.sub("_", raw).strip("_") or "mcp_tool"
    return cleaned[:64]


def _python_type(spec: dict[str, Any]) -> type:
    """把 JSON Schema 的类型映射成 Python 类型（兼容 anyOf/oneOf 的可空写法）。"""
    json_type = spec.get("type")
    if isinstance(json_type, list):  # ["string", "null"]
        json_type = next((item for item in json_type if item != "null"), "string")
    if not json_type:
        for key in ("anyOf", "oneOf", "allOf"):
            options = spec.get(key) or []
            for option in options:
                if isinstance(option, dict) and option.get("type") not in (None, "null"):
                    return _python_type(option)
    if isinstance(json_type, str) and json_type in _TYPE_MAP:
        return _TYPE_MAP[json_type]
    return str


def json_schema_to_model(schema: dict[str, Any] | None, model_name: str) -> type[BaseModel]:
    """把 MCP 工具的 inputSchema 转成 pydantic 模型（LangChain `args_schema`）。"""
    schema = schema or {}
    properties = schema.get("properties") or {}
    required = set(schema.get("required") or [])

    fields: dict[str, Any] = {}
    for key, spec in properties.items():
        if not isinstance(spec, dict):
            spec = {"type": "string"}
        py_type = _python_type(spec)
        description = str(spec.get("description") or spec.get("title") or key)
        if key in required:
            fields[key] = (py_type, Field(..., description=description))
        else:
            default = spec.get("default")
            fields[key] = (py_type | None, Field(default=default, description=description))

    if not fields:
        # 无入参的工具：给一个可选占位字段，避免 pydantic 报「空模型」
        fields["_noop"] = (str | None, Field(default=None, description="该工具无需参数"))

    safe_name = _NAME_SAFE.sub("_", model_name) or "McpArgs"
    return create_model(f"McpArgs_{safe_name}", **fields)  # type: ignore[call-overload]


def server_snapshot(server: Any) -> dict[str, Any]:
    """把 MCP Server 配置抽成普通 dict（供工具闭包与后台任务安全使用）。"""
    if isinstance(server, dict):
        return dict(server)
    return {
        "id": getattr(server, "id", None),
        "name": getattr(server, "name", None),
        "slug": getattr(server, "slug", None),
        "transport": getattr(server, "transport", None),
        "command": getattr(server, "command", None),
        "args": getattr(server, "args", None),
        "env": getattr(server, "env", None),
        "cwd": getattr(server, "cwd", None),
        "url": getattr(server, "url", None),
        "headers": getattr(server, "headers", None),
        "timeout": getattr(server, "timeout", 60),
    }


def build_mcp_tools(servers: list[Any], *, use_cache: bool = True) -> list[BaseTool]:
    """把多个 MCP Server 的工具批量转成 LangChain Tool。"""
    tools, _ = build_mcp_tools_with_meta(servers, use_cache=use_cache)
    return tools


def build_mcp_tools_with_meta(
    servers: list[Any], *, use_cache: bool = True
) -> tuple[list[BaseTool], dict[str, dict[str, Any]]]:
    """同上，但额外返回 tool_name -> 元信息（供聊天流程展示「来自哪个 MCP 服务」）。"""
    tools: list[BaseTool] = []
    meta: dict[str, dict[str, Any]] = {}
    for server in servers:
        cached = server.get("tools_cache") if isinstance(server, dict) else getattr(server, "tools_cache", None)
        snapshot = server_snapshot(server)
        slug = str(snapshot.get("slug") or snapshot.get("id") or "server")
        server_name = str(snapshot.get("name") or slug)

        for item in list(cached or []):
            tool_name = str(item.get("name") or "")
            if not tool_name:
                continue
            python_name = tool_name_for(slug, tool_name)
            description = str(item.get("description") or "").strip()
            header = f"来自 MCP 服务「{server_name}」的工具 {tool_name}。"
            full_description = f"{header} {description}".strip() or header

            try:
                args_model = json_schema_to_model(item.get("input_schema"), python_name)
            except Exception as exc:  # noqa: BLE001 - 单个工具 schema 异常不影响其它工具
                logger.warning("MCP 工具 schema 解析失败 server=%s tool=%s: %s", server_name, tool_name, exc)
                continue

            tools.append(
                _make_tool(snapshot, server_name, tool_name, python_name, full_description, args_model)
            )
            meta[python_name] = {
                "id": snapshot.get("id"),
                "name": f"{server_name}  {tool_name}",
                "type": "mcp",
                "source": "mcp",
                "server": server_name,
                "server_id": snapshot.get("id"),
                "tool": tool_name,
            }

    if tools and not use_cache:  # pragma: no cover - 预留：强制实时拉取工具的扩展点
        logger.info("已构建 %s 个 MCP 工具（实时模式）", len(tools))
    return tools, meta


def _make_tool(
    snapshot: dict[str, Any],
    server_name: str,
    tool_name: str,
    python_name: str,
    description: str,
    args_model: type[BaseModel],
) -> BaseTool:
    async def _run(**kwargs: Any) -> str:
        arguments = {k: v for k, v in kwargs.items() if k != "_noop"}
        logger.info("MCP 工具调用 server=%s tool=%s args=%s", server_name, tool_name, list(arguments))
        try:
            result = await mcp_client.call_tool(snapshot, tool_name, arguments)
        except McpError as exc:
            return f"[技能执行失败] MCP 调用失败：{exc}"
        except Exception as exc:  # noqa: BLE001
            return f"[技能执行失败] MCP 调用异常：{type(exc).__name__}: {exc}"
        if result.is_error:
            return f"[技能执行失败] MCP 返回错误：{result.text}"
        return result.text

    return StructuredTool.from_function(
        coroutine=_run,
        name=python_name,
        description=description,
        args_schema=args_model,
    )


def preview_schema(schema: dict[str, Any] | None) -> str:
    """给前端展示用的 schema 精简文本。"""
    if not schema:
        return "{}"
    return json.dumps(schema, ensure_ascii=False, indent=2)
