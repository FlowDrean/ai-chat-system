"""Prompt / Dashboard Schema。"""

from __future__ import annotations

from datetime import datetime

from pydantic import Field, field_validator

from app.schemas.common import BaseSchema


class PromptBase(BaseSchema):
    name: str = Field(min_length=1, max_length=128)
    content: str = Field(min_length=1, max_length=32000)
    description: str | None = Field(default=None, max_length=2000)
    variables: list[str] | None = None
    tags: list[str] | None = None
    scene: str = Field(default="system", pattern="^(system|rag|chat)$")
    enabled: bool = True

    @field_validator("tags")
    @classmethod
    def _check_tags(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return None
        return [t.strip() for t in v if t and t.strip()][:12]


class PromptCreate(PromptBase):
    pass


class PromptUpdate(BaseSchema):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    content: str | None = Field(default=None, min_length=1, max_length=32000)
    description: str | None = None
    variables: list[str] | None = None
    tags: list[str] | None = None
    scene: str | None = Field(default=None, pattern="^(system|rag|chat)$")
    enabled: bool | None = None


class PromptOut(BaseSchema):
    id: int
    user_id: int | None = None
    name: str
    content: str
    description: str | None = None
    variables: list[str] | None = None
    tags: list[str] | None = None
    scene: str = "system"
    enabled: bool = True
    is_builtin: bool = False
    usage_count: int = 0
    created_at: datetime | None = None
    updated_at: datetime | None = None


class PromptRenderRequest(BaseSchema):
    variables: dict = Field(default_factory=dict)


# --------------------------------------------------------------------------- #
# Dashboard
# --------------------------------------------------------------------------- #
class DashboardStats(BaseSchema):
    today_conversations: int = 0
    today_messages: int = 0
    today_tokens: int = 0
    today_model_calls: int = 0
    today_retrievals: int = 0
    total_conversations: int = 0
    total_messages: int = 0
    total_tokens: int = 0
    model_count: int = 0
    enabled_model_count: int = 0
    knowledge_base_count: int = 0
    document_count: int = 0
    chunk_count: int = 0
    user_count: int = 0


class TrendPoint(BaseSchema):
    date: str
    conversations: int = 0
    messages: int = 0
    tokens: int = 0
    model_calls: int = 0


class DistributionItem(BaseSchema):
    name: str
    value: int = 0
    extra: float | None = None


class RecentConversation(BaseSchema):
    id: int
    title: str
    message_count: int = 0
    total_tokens: int = 0
    updated_at: datetime | None = None


class DashboardOut(BaseSchema):
    stats: DashboardStats
    trends: list[TrendPoint] = Field(default_factory=list)
    model_usage: list[DistributionItem] = Field(default_factory=list)
    knowledge_usage: list[DistributionItem] = Field(default_factory=list)
    recent_conversations: list[RecentConversation] = Field(default_factory=list)
