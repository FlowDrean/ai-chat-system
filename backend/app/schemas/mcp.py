"""MCP（Model Context Protocol）相关 Schema。"""

from __future__ import annotations

from datetime import datetime

from pydantic import Field, field_validator

from app.models.mcp_server import McpTransport
from app.schemas.common import BaseSchema


class McpToolOut(BaseSchema):
    name: str
    description: str = ""
    input_schema: dict = Field(default_factory=dict)


class McpServerBase(BaseSchema):
    name: str = Field(min_length=1, max_length=64)
    transport: str = Field(default=McpTransport.STDIO)
    description: str | None = Field(default=None, max_length=2000)

    # stdio
    command: str | None = Field(default=None, max_length=512, description="可执行命令，如 npx / python")
    args: list[str] | None = Field(default=None, description="命令参数数组")
    cwd: str | None = Field(default=None, max_length=512)

    # sse / http
    url: str | None = Field(default=None, max_length=1024, description="MCP 服务地址")

    enabled: bool = True
    visible_to_users: bool = True
    timeout: int = Field(default=60, ge=5, le=600)
    sort_order: int = 0

    @field_validator("transport")
    @classmethod
    def _check_transport(cls, v: str) -> str:
        value = (v or "").strip().lower()
        if value not in McpTransport.ALL:
            raise ValueError(f"不支持的传输方式：{value}（可选 stdio / sse / http）")
        return value

    @field_validator("args")
    @classmethod
    def _check_args(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return None
        return [str(item) for item in v if str(item).strip() != ""]

    def validate_transport_fields(self) -> None:
        """按传输方式校验必填项（在 Service 里调用，便于给出中文提示）。"""
        if self.transport == McpTransport.STDIO:
            if not (self.command or "").strip():
                raise ValueError("stdio 传输必须填写启动命令（command）")
        elif not (self.url or "").strip():
            raise ValueError(f"{self.transport} 传输必须填写服务地址（url）")


class McpServerCreate(McpServerBase):
    slug: str | None = Field(default=None, max_length=64, description="唯一标识，留空按名称生成")
    env: dict | None = Field(default=None, description="环境变量（敏感值加密存储）")
    headers: dict | None = Field(default=None, description="请求头（敏感值加密存储）")

    @field_validator("slug")
    @classmethod
    def _check_slug(cls, v: str | None) -> str | None:
        if v in (None, ""):
            return None
        allowed = set("abcdefghijklmnopqrstuvwxyz0123456789_-")
        cleaned = "".join(ch for ch in v.strip().lower() if ch in allowed)
        if not cleaned:
            raise ValueError("slug 只能包含小写字母、数字、下划线与短横线")
        return cleaned


class McpServerUpdate(BaseSchema):
    name: str | None = Field(default=None, min_length=1, max_length=64)
    transport: str | None = None
    description: str | None = Field(default=None, max_length=2000)
    command: str | None = Field(default=None, max_length=512)
    args: list[str] | None = None
    cwd: str | None = Field(default=None, max_length=512)
    url: str | None = Field(default=None, max_length=1024)
    env: dict | None = Field(default=None, description="整份覆盖；敏感字段留空表示不修改")
    headers: dict | None = None
    enabled: bool | None = None
    visible_to_users: bool | None = None
    timeout: int | None = Field(default=None, ge=5, le=600)
    sort_order: int | None = None

    @field_validator("transport")
    @classmethod
    def _check_transport(cls, v: str | None) -> str | None:
        if v is None:
            return None
        value = v.strip().lower()
        if value not in McpTransport.ALL:
            raise ValueError(f"不支持的传输方式：{value}")
        return value


class McpServerOut(BaseSchema):
    id: int
    name: str
    slug: str
    transport: str
    transport_label: str = ""
    description: str | None = None
    command: str | None = None
    args: list[str] | None = None
    env: dict | None = None
    cwd: str | None = None
    url: str | None = None
    headers: dict | None = None
    masked_keys: list[str] = Field(default_factory=list, description="已脱敏的字段名")
    enabled: bool = True
    visible_to_users: bool = True
    timeout: int = 60
    sort_order: int = 0
    status: str = "unknown"
    status_message: str | None = None
    last_connected_at: datetime | None = None
    tool_count: int = 0
    tools: list[McpToolOut] = Field(default_factory=list, description="最近一次发现的工具（缓存）")
    usage_count: int = 0
    last_used_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class McpServerOption(BaseSchema):
    """聊天页选择器用的精简结构。"""

    id: int
    name: str
    slug: str
    transport: str
    description: str | None = None
    tool_count: int = 0
    status: str = "unknown"


class McpTestResult(BaseSchema):
    success: bool
    message: str = ""
    latency_ms: float = 0.0
    tool_count: int = 0
    tools: list[McpToolOut] = Field(default_factory=list)


class McpToolCallRequest(BaseSchema):
    tool_name: str = Field(min_length=1, max_length=128)
    arguments: dict = Field(default_factory=dict)


class McpToolCallResult(BaseSchema):
    success: bool
    output: str = ""
    error: str | None = None
    latency_ms: float = 0.0
    is_error: bool = False


class McpTransportInfo(BaseSchema):
    value: str
    label: str
    description: str
    fields: list[str] = Field(default_factory=list, description="该传输方式需要填写的字段")


# --------------------------------------------------------------------------- #
# 配置导入 / 导出（兼容 Claude Desktop、Cursor 等 mcpServers 格式）
# --------------------------------------------------------------------------- #
class McpImportRequest(BaseSchema):
    payload: str | dict | list = Field(..., description="mcpServers JSON 文本或对象")
    strategy: str = Field(default="rename", description="名称冲突处理：skip 跳过 / overwrite 覆盖 / rename 自动重命名")
    auto_test: bool = Field(default=True, description="导入后自动连接并发现工具")
    enabled: bool = Field(default=True, description="导入后的启用状态（配置里显式 disabled=true 时会被覆盖为禁用）")
    visible_to_users: bool = True

    @field_validator("strategy")
    @classmethod
    def _check_strategy(cls, v: str) -> str:
        value = (v or "rename").strip().lower()
        if value not in {"skip", "overwrite", "rename"}:
            raise ValueError("strategy 只能是 skip / overwrite / rename")
        return value


class McpImportItemResult(BaseSchema):
    name: str
    slug: str = ""
    server_id: int | None = None
    transport: str = ""
    action: str = "created"
    """created / updated / renamed / skipped / failed"""
    success: bool = True
    message: str = ""
    tool_count: int = 0
    tools: list[McpToolOut] = Field(default_factory=list)


class McpImportResult(BaseSchema):
    total: int = 0
    created: int = 0
    updated: int = 0
    skipped: int = 0
    failed: int = 0
    items: list[McpImportItemResult] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class McpExportResult(BaseSchema):
    content: str = Field(default="", description="mcpServers 格式的 JSON 文本")
    count: int = 0
    include_secrets: bool = False

