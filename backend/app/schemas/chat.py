"""聊天 / 会话 / 消息 Schema。"""

from __future__ import annotations

from datetime import datetime

from pydantic import Field, field_validator

from app.schemas.common import BaseSchema


class ChatParams(BaseSchema):
    """会话级模型参数（只影响当前会话）。"""

    temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    top_p: float | None = Field(default=None, ge=0.0, le=1.0)
    max_tokens: int | None = Field(default=None, ge=1, le=131072)
    frequency_penalty: float | None = Field(default=None, ge=-2.0, le=2.0)
    presence_penalty: float | None = Field(default=None, ge=-2.0, le=2.0)
    streaming: bool = True

    def to_llm_overrides(self) -> dict:
        return {
            k: v
            for k, v in {
                "temperature": self.temperature,
                "top_p": self.top_p,
                "max_tokens": self.max_tokens,
                "frequency_penalty": self.frequency_penalty,
                "presence_penalty": self.presence_penalty,
            }.items()
            if v is not None
        }


class ConversationCreate(BaseSchema):
    title: str | None = Field(default=None, max_length=255)
    model_id: int | None = None
    knowledge_base_id: int | None = None
    prompt_id: int | None = None
    system_prompt: str | None = None
    params: ChatParams | None = None
    skill_ids: list[int] | None = Field(default=None, description="会话启用的技能 id 列表")
    mcp_server_ids: list[int] | None = Field(default=None, description="会话启用的 MCP 服务 id 列表")


class ConversationUpdate(BaseSchema):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    model_id: int | None = None
    knowledge_base_id: int | None = None
    prompt_id: int | None = None
    system_prompt: str | None = None
    params: ChatParams | None = None
    skill_ids: list[int] | None = None
    mcp_server_ids: list[int] | None = None
    is_favorite: bool | None = None
    is_archived: bool | None = None

    @field_validator("title")
    @classmethod
    def _strip_title(cls, v: str | None) -> str | None:
        return v.strip() if isinstance(v, str) else v


class ConversationOut(BaseSchema):
    id: int
    title: str
    model_id: int | None = None
    knowledge_base_id: int | None = None
    prompt_id: int | None = None
    system_prompt: str | None = None
    params: dict | None = None
    skill_ids: list[int] | None = None
    mcp_server_ids: list[int] | None = None
    is_favorite: bool = False
    is_archived: bool = False
    message_count: int = 0
    total_tokens: int = 0
    last_message_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class SourceOut(BaseSchema):
    """RAG 引用来源。"""

    document_id: int | None = None
    filename: str | None = None
    file_type: str | None = None
    page: int | None = None
    chunk_index: int | None = None
    chunk_id: int | None = None
    score: float = 0.0
    content: str | None = None
    metadata: dict | None = None


class SkillCallOut(BaseSchema):
    """一次技能调用记录（展示在回答下方）。"""

    id: int | None = None
    name: str | None = None
    type: str | None = None
    tool_name: str | None = None
    source: str = "skill"
    """来源：skill（本地技能）或 mcp（MCP 工具）"""
    server: str | None = None
    """MCP 工具所属服务名"""
    status: str = "done"
    arguments: dict | None = None
    output: str | None = None
    latency_ms: float = 0.0


class MessageOut(BaseSchema):
    id: int
    conversation_id: int
    role: str
    content: str
    sources: list[SourceOut] | None = None
    skills: list[SkillCallOut] | None = None
    status: str = "done"
    model_id: int | None = None
    model_name: str | None = None
    provider: str | None = None
    knowledge_base_id: int | None = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    latency_ms: float = 0.0
    error_message: str | None = None
    created_at: datetime | None = None


class ChatRequest(BaseSchema):
    """聊天请求（流式 / 非流式共用）。"""

    content: str = Field(min_length=1, max_length=32000, description="用户问题")
    conversation_id: int | None = Field(default=None, description="为空则自动创建会话")
    model_id: int | None = None
    knowledge_base_id: int | None = Field(default=None, description="选择知识库则自动进入 RAG 流程")
    prompt_id: int | None = None
    system_prompt: str | None = None
    params: ChatParams | None = None
    stream: bool = True
    skill_ids: list[int] | None = Field(default=None, description="本次对话启用的技能 id 列表")
    mcp_server_ids: list[int] | None = Field(default=None, description="本次对话启用的 MCP 服务 id 列表")
    regenerate: bool = Field(default=False, description="重新生成：覆盖最后一条助手回复")
    use_rag: bool | None = Field(default=None, description="强制开启/关闭 RAG；默认按是否选择知识库决定")

    @field_validator("content")
    @classmethod
    def _check_content(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("消息内容不能为空")
        return v


class ChatResponse(BaseSchema):
    conversation_id: int
    message: MessageOut
    sources: list[SourceOut] = Field(default_factory=list)
    skills: list[SkillCallOut] = Field(default_factory=list)
    mcp_servers: list[str] = Field(default_factory=list, description="本次对话使用的 MCP 服务名")
    usage: dict | None = None


class TokenStats(BaseSchema):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    latency_ms: float = 0.0
    retrieved_chunks: int = 0
