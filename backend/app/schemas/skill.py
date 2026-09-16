"""技能（Skills）Schema。

* `SkillSpecOut` 由后端技能注册表提供，前端据此渲染「动态配置表单」；
* `SkillOut.config` 中的敏感字段（密码类配置）会被脱敏，只返回 `config_masked_keys`。
"""

from __future__ import annotations

from datetime import datetime

from pydantic import Field, field_validator

from app.schemas.common import BaseSchema


class SkillFieldOut(BaseSchema):
    key: str
    label: str
    type: str = "string"
    required: bool = False
    default: object | None = None
    placeholder: str = ""
    help: str = ""
    options: list[dict] = Field(default_factory=list)
    secret: bool = False


class SkillArgOut(BaseSchema):
    name: str
    type: str = "string"
    description: str = ""
    required: bool = True
    default: object | None = None


class SkillSpecOut(BaseSchema):
    type: str
    name: str
    description: str
    icon: str = "ApiOutlined"
    category: str = "general"
    fields: list[SkillFieldOut] = Field(default_factory=list)
    args: list[SkillArgOut] = Field(default_factory=list)
    uses_dynamic_args: bool = False
    configurable: bool = True


class SkillBase(BaseSchema):
    name: str = Field(min_length=1, max_length=64)
    description: str | None = Field(default=None, max_length=2000, description="用途说明，会作为工具描述给模型")
    icon: str | None = Field(default=None, max_length=64)
    enabled: bool = True
    visible_to_users: bool = True
    sort_order: int = 0
    config: dict | None = None


class SkillCreate(SkillBase):
    type: str = Field(min_length=1, max_length=32)
    slug: str | None = Field(default=None, max_length=64, description="唯一标识，留空自动生成")

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


class SkillUpdate(BaseSchema):
    name: str | None = Field(default=None, min_length=1, max_length=64)
    description: str | None = Field(default=None, max_length=2000)
    icon: str | None = Field(default=None, max_length=64)
    enabled: bool | None = None
    visible_to_users: bool | None = None
    sort_order: int | None = None
    config: dict | None = Field(default=None, description="整份覆盖；敏感字段留空表示不修改")


class SkillOut(BaseSchema):
    id: int
    name: str
    slug: str
    type: str
    type_label: str = ""
    category: str = "general"
    description: str | None = None
    icon: str | None = None
    config: dict | None = None
    config_masked_keys: list[str] = Field(default_factory=list)
    enabled: bool = True
    is_builtin: bool = False
    visible_to_users: bool = True
    sort_order: int = 0
    usage_count: int = 0
    last_used_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    spec: SkillSpecOut | None = None


class SkillOptionOut(BaseSchema):
    """聊天页技能选择器用的精简结构。"""

    id: int
    name: str
    slug: str
    type: str
    description: str | None = None
    icon: str | None = None
    configured: bool = True
    """是否已完成必要配置（未配置的技能前端会提示，避免选了就报错）。"""


class SkillTestRequest(BaseSchema):
    arguments: dict = Field(default_factory=dict, description="技能入参")
    config: dict | None = Field(default=None, description="不传则使用已保存的配置")


class SkillTestResult(BaseSchema):
    success: bool
    output: str = ""
    error: str | None = None
    latency_ms: float = 0.0
    tool_name: str | None = None
    arguments: dict | None = None
