"""模型配置（对应 `models` 表）。

系统不写死任何供应商：`provider` 决定使用哪个 LangChain 集成，
`base_url` 决定实际请求地址，`model_name` 决定模型 ID。
支持 `extra_params` 存放供应商特有参数（例如 `top_k`、`thinking`、`api_version`）。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Integer, JSON, SmallInteger, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import BigIntFK, Base, LongText, PKMixin, TimestampMixin


class Provider:
    """支持的模型供应商（新增供应商只需在 LLM Factory 注册，不影响业务逻辑）。"""

    OPENAI = "openai"
    DEEPSEEK = "deepseek"
    QWEN = "qwen"  # 通义千问（DashScope OpenAI 兼容模式）
    OLLAMA = "ollama"
    GEMINI = "gemini"
    CLAUDE = "claude"
    MOONSHOT = "moonshot"  # Kimi
    ZHIPU = "zhipu"  # 智谱 GLM
    SILICONFLOW = "siliconflow"
    CUSTOM = "custom"  # 任意 OpenAI Compatible API
    MOCK = "mock"  # 本地回显模型（离线开发 / 演示 / 自检）

    ALL = (OPENAI, DEEPSEEK, QWEN, OLLAMA, GEMINI, CLAUDE, MOONSHOT, ZHIPU, SILICONFLOW, CUSTOM, MOCK)

    LABELS = {
        OPENAI: "OpenAI",
        DEEPSEEK: "DeepSeek",
        QWEN: "通义千问",
        OLLAMA: "Ollama",
        GEMINI: "Gemini",
        CLAUDE: "Claude",
        MOONSHOT: "Moonshot",
        ZHIPU: "智谱 GLM",
        SILICONFLOW: "SiliconFlow",
        CUSTOM: "OpenAI Compatible",
        MOCK: "本地 Mock 模型",
    }

    # 使用 OpenAI 兼容协议的供应商 -> 默认 base_url
    DEFAULT_BASE_URLS = {
        OPENAI: "https://api.openai.com/v1",
        DEEPSEEK: "https://api.deepseek.com/v1",
        QWEN: "https://dashscope.aliyuncs.com/compatible-mode/v1",
        OLLAMA: "http://127.0.0.1:11434/v1",
        MOONSHOT: "https://api.moonshot.cn/v1",
        ZHIPU: "https://open.bigmodel.cn/api/paas/v4",
        SILICONFLOW: "https://api.siliconflow.cn/v1",
        GEMINI: "https://generativelanguage.googleapis.com",
        CLAUDE: "https://api.anthropic.com",
        CUSTOM: "",
        MOCK: "",
    }

    # 需要 api_key 的供应商
    REQUIRES_API_KEY = {OPENAI, DEEPSEEK, QWEN, MOONSHOT, ZHIPU, SILICONFLOW, GEMINI, CLAUDE}


class ModelStatus:
    UNKNOWN = "unknown"
    OK = "ok"
    ERROR = "error"


class ModelConfig(Base, PKMixin, TimestampMixin):
    __tablename__ = "models"

    name: Mapped[str] = mapped_column(String(128), comment="用户自定义名称")
    provider: Mapped[str] = mapped_column(String(32), default=Provider.CUSTOM, index=True, comment="供应商")
    model_name: Mapped[str] = mapped_column(String(128), comment="模型 ID，如 deepseek-chat")
    base_url: Mapped[str | None] = mapped_column(String(512), default=None, comment="API 地址")
    _api_key: Mapped[str | None] = mapped_column("api_key", String(1024), default=None, comment="加密后的 API Key")

    # 默认模型参数
    temperature: Mapped[float] = mapped_column(Float, default=0.7, comment="温度")
    top_p: Mapped[float] = mapped_column(Float, default=1.0, comment="Top P")
    max_tokens: Mapped[int] = mapped_column(Integer, default=4096, comment="最大输出 Token")
    frequency_penalty: Mapped[float] = mapped_column(Float, default=0.0, comment="频率惩罚")
    presence_penalty: Mapped[float] = mapped_column(Float, default=0.0, comment="存在惩罚")

    enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True, comment="是否启用")
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, index=True, comment="是否默认模型")
    supports_stream: Mapped[bool] = mapped_column(Boolean, default=True, comment="是否支持流式")
    supports_vision: Mapped[bool] = mapped_column(Boolean, default=False, comment="是否支持视觉")

    extra_params: Mapped[dict | None] = mapped_column(JSON, default=None, comment="供应商特有参数")
    description: Mapped[str | None] = mapped_column(LongText, default=None, comment="备注")

    # 连接测试状态
    status: Mapped[str] = mapped_column(String(16), default=ModelStatus.UNKNOWN, comment="ok/error/unknown")
    status_message: Mapped[str | None] = mapped_column(String(512), default=None, comment="测试结果描述")
    last_tested_at: Mapped[datetime | None] = mapped_column(DateTime, default=None, comment="最后测试时间")

    created_by: Mapped[int | None] = mapped_column(BigIntFK, default=None, comment="创建人 user_id")

    # ----------------------------------------------------------------- #
    # API Key 属性：数据库存密文，读取时自动解密
    # ----------------------------------------------------------------- #
    @property
    def api_key(self) -> str | None:
        from app.core.security import decrypt_secret

        return decrypt_secret(self._api_key)

    @api_key.setter
    def api_key(self, value: str | None) -> None:
        from app.core.security import encrypt_secret

        self._api_key = encrypt_secret(value) if value else None

    @property
    def has_api_key(self) -> bool:
        return bool(self._api_key)

    def effective_base_url(self) -> str | None:
        return self.base_url or Provider.DEFAULT_BASE_URLS.get(self.provider) or None

    def default_params(self) -> dict:
        return {
            "temperature": self.temperature,
            "top_p": self.top_p,
            "max_tokens": self.max_tokens,
            "frequency_penalty": self.frequency_penalty,
            "presence_penalty": self.presence_penalty,
        }
