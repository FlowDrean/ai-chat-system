"""模型配置 Schema。

注意：`api_key` 只允许写入，读取时永远返回脱敏值（`api_key_masked`）。
"""

from __future__ import annotations

from datetime import datetime

from pydantic import Field, field_validator

from app.models.model_config import Provider
from app.schemas.common import BaseSchema


class ModelParams(BaseSchema):
    """模型默认参数。"""

    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    top_p: float = Field(default=1.0, ge=0.0, le=1.0)
    max_tokens: int = Field(default=4096, ge=1, le=131072)
    frequency_penalty: float = Field(default=0.0, ge=-2.0, le=2.0)
    presence_penalty: float = Field(default=0.0, ge=-2.0, le=2.0)


class ModelBase(BaseSchema):
    name: str = Field(min_length=1, max_length=128, description="用户自定义名称")
    provider: str = Field(default=Provider.CUSTOM)
    model_name: str = Field(min_length=1, max_length=128, description="模型 ID")
    base_url: str | None = Field(default=None, max_length=512)
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    top_p: float = Field(default=1.0, ge=0.0, le=1.0)
    max_tokens: int = Field(default=4096, ge=1, le=131072)
    frequency_penalty: float = Field(default=0.0, ge=-2.0, le=2.0)
    presence_penalty: float = Field(default=0.0, ge=-2.0, le=2.0)
    enabled: bool = True
    is_default: bool = False
    supports_stream: bool = True
    supports_vision: bool = False
    extra_params: dict | None = None
    description: str | None = None

    @field_validator("provider")
    @classmethod
    def _check_provider(cls, v: str) -> str:
        v = (v or "").strip().lower()
        if v not in Provider.ALL:
            raise ValueError(f"不支持的供应商：{v}")
        return v

    @field_validator("base_url")
    @classmethod
    def _check_base_url(cls, v: str | None) -> str | None:
        if v in (None, ""):
            return None
        v = v.strip().rstrip("/")
        if not v.startswith(("http://", "https://")):
            raise ValueError("Base URL 必须以 http:// 或 https:// 开头")
        return v


class ModelCreate(ModelBase):
    api_key: str | None = Field(default=None, max_length=512, description="API Key（只写不读）")


class ModelUpdate(BaseSchema):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    provider: str | None = None
    model_name: str | None = Field(default=None, min_length=1, max_length=128)
    base_url: str | None = None
    api_key: str | None = Field(default=None, max_length=512, description="留空表示不修改")
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    top_p: float | None = Field(default=None, ge=0.0, le=1.0)
    max_tokens: int | None = Field(default=None, ge=1, le=131072)
    frequency_penalty: float | None = Field(default=None, ge=-2.0, le=2.0)
    presence_penalty: float | None = Field(default=None, ge=-2.0, le=2.0)
    enabled: bool | None = None
    is_default: bool | None = None
    supports_stream: bool | None = None
    supports_vision: bool | None = None
    extra_params: dict | None = None
    description: str | None = None

    @field_validator("provider")
    @classmethod
    def _check_provider(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip().lower()
        if v not in Provider.ALL:
            raise ValueError(f"不支持的供应商：{v}")
        return v


class ModelOut(BaseSchema):
    id: int
    name: str
    provider: str
    provider_label: str = ""
    model_name: str
    base_url: str | None = None
    api_key_masked: str | None = None
    has_api_key: bool = False
    temperature: float = 0.7
    top_p: float = 1.0
    max_tokens: int = 4096
    frequency_penalty: float = 0.0
    presence_penalty: float = 0.0
    enabled: bool = True
    is_default: bool = False
    supports_stream: bool = True
    supports_vision: bool = False
    extra_params: dict | None = None
    description: str | None = None
    status: str = "unknown"
    status_message: str | None = None
    last_tested_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ModelTestResult(BaseSchema):
    success: bool
    message: str
    latency_ms: float = 0.0
    model_name: str | None = None
    provider: str | None = None
    reply_preview: str | None = None
    usage: dict | None = None


class ProviderInfo(BaseSchema):
    value: str
    label: str
    default_base_url: str | None = None
    requires_api_key: bool = True
    requires_base_url: bool = False
    description: str | None = None
