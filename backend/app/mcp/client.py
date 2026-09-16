"""封装 MCP 客户端：连接、发现工具、调用工具。

设计取舍
--------
* **每次操作建立一次连接**（list_tools / call_tool）：实现简单、进程不会泄漏、
  并发安全；代价是每次调用有一次握手开销（本地 stdio 约几十毫秒）。
  后续如需长连接，可在这一层加连接池，业务代码无需改动。
* 对外只暴露 `list_tools()` / `call_tool()` 与一组可读异常，
  上层（Service / LangChain Tool / API）完全不感知 MCP 协议细节。
* 兼容 mcp 1.x（`streamablehttp_client` / `inputSchema`）与 2.x
  （`streamable_http_client` / `input_schema`），避免因 SDK 大版本升级而不可用。
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
from contextlib import AsyncExitStack, asynccontextmanager
from dataclasses import dataclass, field
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.sse import sse_client
from mcp.client.stdio import stdio_client

from app.core.logging import get_logger

logger = get_logger(__name__)


# --------------------------------------------------------------------------- #
# streamable http：1.x 与 2.x 的函数名不同，这里做兼容
# --------------------------------------------------------------------------- #
try:  # mcp >= 2.0
    from mcp.client.streamable_http import streamable_http_client as _streamable_http
except ImportError:  # pragma: no cover - mcp < 2.0
    from mcp.client.streamable_http import streamablehttp_client as _streamable_http  # type: ignore


class McpError(Exception):
    """MCP 操作的统一异常（信息会被转成可读文本，不抛给前端原始堆栈）。"""


@dataclass(slots=True)
class McpToolInfo:
    name: str
    description: str = ""
    input_schema: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "description": self.description, "input_schema": self.input_schema}


@dataclass(slots=True)
class McpCallResult:
    text: str
    is_error: bool = False
    structured: Any = None


# --------------------------------------------------------------------------- #
# 辅助
# --------------------------------------------------------------------------- #
def _attr(obj: Any, key: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _friendly_error(exc: Exception) -> str:
    text = str(exc)
    lowered = text.lower()
    if isinstance(exc, asyncio.TimeoutError):
        return "连接或调用超时，请检查服务是否可用 / 适当调大超时时间"
    if isinstance(exc, FileNotFoundError) or "no such file" in lowered or "not recognized" in lowered:
        return f"命令不存在或不可执行：{text[:200]}"
    if "connection refused" in lowered or "connect" in lowered and "failed" in lowered:
        return "无法连接到 MCP 服务，请检查地址 / 端口 / 服务是否已启动"
    if "401" in lowered or "unauthorized" in lowered:
        return "鉴权失败：请检查请求头中的 Token / API Key"
    if "404" in lowered:
        return "接口地址不存在（404）：请确认 URL 是否为 MCP 端点"
    if "parse" in lowered or "json" in lowered:
        return f"MCP 协议解析失败：{text[:200]}"
    return text[:400]


def _extract_text(result: Any) -> tuple[str, Any]:
    """把 MCP 的 CallToolResult 转成文本（兼容 content 里各种块类型）。"""
    structured = _attr(result, "structured_content") or _attr(result, "structuredContent")
    chunks: list[str] = []
    for block in _attr(result, "content", []) or []:
        block_type = _attr(block, "type")
        if block_type == "text":
            chunks.append(str(_attr(block, "text", "")))
        elif block_type in {"json", "object"}:
            chunks.append(json.dumps(_attr(block, "data") or _attr(block, "json"), ensure_ascii=False))
        else:
            data = block.model_dump() if hasattr(block, "model_dump") else str(block)
            chunks.append(json.dumps(data, ensure_ascii=False, default=str))
    text = "\n".join(part for part in chunks if part)
    if not text and structured is not None:
        text = json.dumps(structured, ensure_ascii=False)
    return text.strip(), structured


def _tool_input_schema(tool: Any) -> dict[str, Any]:
    """兼容 input_schema（2.x）与 inputSchema（1.x）。"""
    schema = _attr(tool, "input_schema") or _attr(tool, "inputSchema") or {}
    if hasattr(schema, "model_dump"):
        schema = schema.model_dump()
    return dict(schema or {})


def _prepare_stdio_command(command: str, args: list[str]) -> tuple[str, list[str]]:
    """Windows 兼容：把 npx / npm / uvx 这类 .cmd shim 交给 cmd 执行。

    Windows 上 Node 的 npx、npm、pnpm、yarn 以及 Python 的 uvx 都是 .cmd/.bat 批处理，
    `create_subprocess_exec("npx", ...)` 会直接报「命令不存在」；Claude Desktop 的官方示例
    也是用 `cmd /c npx ...`。这里自动判断并改写，用户粘贴配置即可用。
    """
    if os.name != "nt":
        return command, args
    resolved = shutil.which(command) or command
    if resolved.lower().endswith((".cmd", ".bat")):
        return "cmd", ["/c", resolved, *args]
    return resolved, args


def _stdio_env(env: dict[str, Any] | None) -> dict[str, str] | None:
    """stdio 服务的环境变量：在继承当前进程环境的基础上追加。"""
    if not env:
        return None
    merged = {str(k): str(v) for k, v in os.environ.items()}
    merged.update({str(k): str(v) for k, v in env.items() if v is not None})
    return merged


# --------------------------------------------------------------------------- #
# 连接
# --------------------------------------------------------------------------- #
@asynccontextmanager
async def _connect(server: Any):
    """按传输方式建立连接并初始化会话，产出 ClientSession。"""
    transport = str(_attr(server, "transport", "") or "").lower()
    timeout = float(_attr(server, "timeout", 60) or 60)

    if transport == "stdio":
        command = str(_attr(server, "command", "") or "").strip()
        if not command:
            raise McpError("stdio 传输必须配置启动命令（command）")
        prepared_command, prepared_args = _prepare_stdio_command(
            command, [str(a) for a in (_attr(server, "args") or [])]
        )
        params = StdioServerParameters(
            command=prepared_command,
            args=prepared_args,
            env=_stdio_env(_attr(server, "env")),
            cwd=_attr(server, "cwd") or None,
        )
        async with stdio_client(params) as streams:  # type: ignore[attr-defined]
            read, write = streams[0], streams[1]
            async with ClientSession(read, write) as session:
                await asyncio.wait_for(session.initialize(), timeout=timeout)
                yield session
        return

    url = str(_attr(server, "url", "") or "").strip()
    if not url:
        raise McpError(f"{transport} 传输必须配置服务地址（url）")
    headers = {str(k): str(v) for k, v in (_attr(server, "headers") or {}).items() if v is not None}

    if transport == "sse":
        async with sse_client(url, headers=headers or None) as streams:  # type: ignore[attr-defined]
            read, write = streams[0], streams[1]
            async with ClientSession(read, write) as session:
                await asyncio.wait_for(session.initialize(), timeout=timeout)
                yield session
        return

    if transport == "http":
        async with AsyncExitStack() as stack:
            try:  # mcp >= 2.0：headers 挂在自定义 http client 上
                import httpx2

                client = httpx2.AsyncClient(headers=headers or None, timeout=timeout)
                stack.push_async_callback(client.aclose)
                context = _streamable_http(url, http_client=client)  # type: ignore[call-arg]
            except (ImportError, TypeError):  # pragma: no cover - mcp < 2.0
                context = _streamable_http(url, headers=headers or None)  # type: ignore[call-arg]

            streams = await stack.enter_async_context(context)  # type: ignore[arg-type]
            read, write = streams[0], streams[1]
            async with ClientSession(read, write) as session:
                await asyncio.wait_for(session.initialize(), timeout=timeout)
                yield session
        return

    raise McpError(f"不支持的传输方式：{transport}（可选 stdio / sse / http）")


# --------------------------------------------------------------------------- #
# 对外接口
# --------------------------------------------------------------------------- #
async def list_tools(server: Any) -> list[McpToolInfo]:
    """连接 MCP 服务并返回其工具清单。"""
    timeout = float(_attr(server, "timeout", 60) or 60)
    try:
        async with _connect(server) as session:
            result = await asyncio.wait_for(session.list_tools(), timeout=timeout)
    except McpError:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.warning("MCP 工具发现失败 server=%s: %s", _attr(server, "name", "?"), exc)
        raise McpError(_friendly_error(exc)) from exc

    tools: list[McpToolInfo] = []
    for item in _attr(result, "tools", []) or []:
        tools.append(
            McpToolInfo(
                name=str(_attr(item, "name", "")),
                description=str(_attr(item, "description") or ""),
                input_schema=_tool_input_schema(item),
            )
        )
    return tools


async def call_tool(server: Any, tool_name: str, arguments: dict[str, Any] | None = None) -> McpCallResult:
    """调用 MCP 服务上的某个工具。"""
    timeout = float(_attr(server, "timeout", 60) or 60)
    try:
        async with _connect(server) as session:
            result = await asyncio.wait_for(
                session.call_tool(tool_name, arguments=arguments or {}), timeout=timeout
            )
    except McpError:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.warning("MCP 工具调用失败 server=%s tool=%s: %s", _attr(server, "name", "?"), tool_name, exc)
        raise McpError(_friendly_error(exc)) from exc

    text, structured = _extract_text(result)
    is_error = bool(_attr(result, "is_error") or _attr(result, "isError"))
    return McpCallResult(text=text or "（工具返回空内容）", is_error=is_error, structured=structured)
