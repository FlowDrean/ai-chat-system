"""MCP（Model Context Protocol）服务端配置模型。

一条记录 = 一个 MCP Server，支持三种传输方式：

| transport | 用途 | 关键字段 |
| --- | --- | --- |
| `stdio` | 本地进程（`npx @modelcontextprotocol/server-*`、自建脚本） | `command` / `args` / `env` / `cwd` |
| `sse` | 远程 SSE 端点（MCP 旧版 HTTP 传输） | `url` / `headers` |
| `http` | 远程 Streamable HTTP（MCP 新版传输） | `url` / `headers` |

`tools_cache` 缓存最近一次 `tools/list` 的结果（含 JSON Schema），
前端可离线展示工具清单，聊天时也能在没有实时连接的情况下构建工具。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import BigIntFK, Base, LongText, PKMixin, TimestampMixin


class McpTransport:
    STDIO = "stdio"
    SSE = "sse"
    HTTP = "http"
    ALL = (STDIO, SSE, HTTP)

    LABELS = {STDIO: "本地进程 (stdio)", SSE: "远程 SSE", HTTP: "Streamable HTTP"}


class McpStatus:
    UNKNOWN = "unknown"
    OK = "ok"
    ERROR = "error"


class McpServer(Base, PKMixin, TimestampMixin):
    __tablename__ = "mcp_servers"

    name: Mapped[str] = mapped_column(String(64), comment="展示名称")
    slug: Mapped[str] = mapped_column(String(64), unique=True, index=True, comment="唯一标识（用于工具命名）")
    transport: Mapped[str] = mapped_column(String(16), index=True, comment="stdio / sse / http")
    description: Mapped[str | None] = mapped_column(LongText, default=None, comment="说明（会拼进工具描述）")

    # ---- stdio ----
    command: Mapped[str | None] = mapped_column(String(512), default=None, comment="可执行命令，如 npx / python")
    args: Mapped[list | None] = mapped_column(JSON, default=None, comment="命令参数数组")
    env: Mapped[dict | None] = mapped_column(JSON, default=None, comment="环境变量（敏感值加密存储）")
    cwd: Mapped[str | None] = mapped_column(String(512), default=None, comment="工作目录")

    # ---- sse / http ----
    url: Mapped[str | None] = mapped_column(String(1024), default=None, comment="服务端地址")
    headers: Mapped[dict | None] = mapped_column(JSON, default=None, comment="请求头（敏感值加密存储）")

    # ---- 通用 ----
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    visible_to_users: Mapped[bool] = mapped_column(Boolean, default=True, comment="是否允许在聊天页选择")
    timeout: Mapped[int] = mapped_column(Integer, default=60, comment="连接 / 调用超时（秒）")
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    # ---- 状态与缓存 ----
    status: Mapped[str] = mapped_column(String(16), default=McpStatus.UNKNOWN, comment="ok / error / unknown")
    status_message: Mapped[str | None] = mapped_column(String(512), default=None)
    last_connected_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    tool_count: Mapped[int] = mapped_column(Integer, default=0, comment="最近一次发现的工具数量")
    tools_cache: Mapped[list | None] = mapped_column(JSON, default=None, comment="缓存的工具清单")
    usage_count: Mapped[int] = mapped_column(Integer, default=0, comment="累计调用次数")
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)

    created_by: Mapped[int | None] = mapped_column(BigIntFK, default=None)

    def cached_tools(self) -> list[dict]:
        return list(self.tools_cache or [])
