"""LLM Factory —— 系统里唯一创建大模型实例的地方。

业务代码永远只调用::

    llm = create_llm(runtime_config)

不要在聊天 / RAG / Agent 代码里直接出现 `ChatOpenAI(...)` / `ChatDeepSeek(...)`。
新增供应商只需要在 `_BUILDERS` 注册一个构造函数。
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from app.core.config import settings
from app.core.exceptions import ConfigurationError, ModelCallError
from app.core.logging import get_logger
from app.models.model_config import ModelConfig, Provider

logger = get_logger(__name__)


# --------------------------------------------------------------------------- #
# 统一运行时配置
# --------------------------------------------------------------------------- #
@dataclass(slots=True)
class LLMRuntimeConfig:
    provider: str = Provider.CUSTOM
    model_name: str = ""
    base_url: str | None = None
    api_key: str | None = None
    temperature: float = 0.7
    top_p: float = 1.0
    max_tokens: int = 4096
    frequency_penalty: float = 0.0
    presence_penalty: float = 0.0
    streaming: bool = True
    timeout: float = field(default_factory=lambda: float(settings.llm_request_timeout))
    max_retries: int = field(default_factory=lambda: settings.llm_max_retries)
    extra_params: dict[str, Any] = field(default_factory=dict)

    @property
    def effective_base_url(self) -> str | None:
        return self.base_url or Provider.DEFAULT_BASE_URLS.get(self.provider) or None

    def display_name(self) -> str:
        return f"{self.provider}:{self.model_name}"


def build_runtime_config(
    model: ModelConfig,
    overrides: dict[str, Any] | None = None,
    *,
    streaming: bool = True,
) -> LLMRuntimeConfig:
    """ORM 模型配置 + 会话级参数覆盖 → 运行时配置。"""
    params = {**model.default_params(), **(overrides or {})}
    return LLMRuntimeConfig(
        provider=(model.provider or Provider.CUSTOM).lower(),
        model_name=model.model_name,
        base_url=model.effective_base_url(),
        api_key=model.api_key,
        temperature=float(params.get("temperature", 0.7)),
        top_p=float(params.get("top_p", 1.0)),
        max_tokens=int(params.get("max_tokens", 4096)),
        frequency_penalty=float(params.get("frequency_penalty", 0.0)),
        presence_penalty=float(params.get("presence_penalty", 0.0)),
        streaming=streaming,
        extra_params=dict(model.extra_params or {}),
    )


# --------------------------------------------------------------------------- #
# 各供应商构造器
# --------------------------------------------------------------------------- #
def _require_api_key(config: LLMRuntimeConfig) -> str:
    if config.provider in Provider.REQUIRES_API_KEY and not config.api_key:
        raise ConfigurationError(
            f"模型「{config.model_name}」缺少 API Key，请在「模型管理」中补全配置"
        )
    return config.api_key or ""


def _filter_kwargs(target: type, kwargs: dict[str, Any]) -> dict[str, Any]:
    """只保留目标类真实支持的参数（含别名），避免不同供应商字段差异导致报错。"""
    supported = set(target.model_fields)
    supported.update(f.alias for f in target.model_fields.values() if f.alias)
    return {k: v for k, v in kwargs.items() if k in supported and v is not None}


def _common_params(config: LLMRuntimeConfig) -> dict[str, Any]:
    return {
        "temperature": config.temperature,
        "top_p": config.top_p,
        "max_tokens": config.max_tokens,
        "timeout": config.timeout,
        "max_retries": config.max_retries,
    }


def _build_openai_compatible(config: LLMRuntimeConfig) -> BaseChatModel:
    from langchain_openai import ChatOpenAI

    api_key = _require_api_key(config)
    if config.provider == Provider.OLLAMA and not api_key:
        api_key = "ollama"  # Ollama 不校验 Key，但 OpenAI SDK 要求非空

    base_url = config.effective_base_url
    if config.provider == Provider.CUSTOM and not base_url:
        raise ConfigurationError("自定义 OpenAI 兼容模型必须填写 Base URL")

    kwargs: dict[str, Any] = {
        "model": config.model_name,
        "api_key": api_key or "not-needed",
        "base_url": base_url,
        "streaming": config.streaming,
        **_common_params(config),
        "frequency_penalty": config.frequency_penalty,
        "presence_penalty": config.presence_penalty,
    }
    kwargs.update({k: v for k, v in config.extra_params.items() if k not in kwargs})
    return ChatOpenAI(**_filter_kwargs(ChatOpenAI, kwargs))


def _build_claude(config: LLMRuntimeConfig) -> BaseChatModel:
    from langchain_anthropic import ChatAnthropic

    kwargs = {
        "model": config.model_name,
        "api_key": _require_api_key(config),
        "base_url": config.effective_base_url,
        "streaming": config.streaming,
        **_common_params(config),
    }
    return ChatAnthropic(**_filter_kwargs(ChatAnthropic, kwargs))


def _build_gemini(config: LLMRuntimeConfig) -> BaseChatModel:
    from langchain_google_genai import ChatGoogleGenerativeAI

    kwargs = {
        "model": config.model_name,
        "google_api_key": _require_api_key(config),
        "temperature": config.temperature,
        "top_p": config.top_p,
        "max_tokens": config.max_tokens,
        "timeout": config.timeout,
        "max_retries": config.max_retries,
    }
    kwargs.update({k: v for k, v in config.extra_params.items() if k not in kwargs})
    return ChatGoogleGenerativeAI(**_filter_kwargs(ChatGoogleGenerativeAI, kwargs))


def _build_mock(config: LLMRuntimeConfig) -> BaseChatModel:
    from app.llm.mock import MockChatModel

    return MockChatModel(model_name=config.model_name or "mock-chat", temperature=config.temperature)


_BUILDERS: dict[str, Callable[[LLMRuntimeConfig], BaseChatModel]] = {
    Provider.OPENAI: _build_openai_compatible,
    Provider.DEEPSEEK: _build_openai_compatible,
    Provider.QWEN: _build_openai_compatible,
    Provider.OLLAMA: _build_openai_compatible,
    Provider.MOONSHOT: _build_openai_compatible,
    Provider.ZHIPU: _build_openai_compatible,
    Provider.SILICONFLOW: _build_openai_compatible,
    Provider.CUSTOM: _build_openai_compatible,
    Provider.CLAUDE: _build_claude,
    Provider.GEMINI: _build_gemini,
    Provider.MOCK: _build_mock,
}


def create_llm(config: LLMRuntimeConfig | ModelConfig | dict[str, Any]) -> BaseChatModel:
    """根据运行时配置创建 LangChain ChatModel。"""
    if isinstance(config, LLMRuntimeConfig):
        runtime = config
    elif isinstance(config, ModelConfig):
        runtime = build_runtime_config(config)
    elif isinstance(config, dict):
        runtime = LLMRuntimeConfig(**config)
    else:  # pragma: no cover - 防御式
        raise ConfigurationError("无法识别的模型配置类型")

    builder = _BUILDERS.get(runtime.provider)
    if builder is None:
        raise ConfigurationError(f"暂不支持的模型供应商：{runtime.provider}")

    try:
        return builder(runtime)
    except ConfigurationError:
        raise
    except ImportError as exc:
        raise ConfigurationError(
            f"供应商 {runtime.provider} 需要额外依赖包：{exc.name}，请先安装"
        ) from exc
    except Exception as exc:  # noqa: BLE001
        logger.warning("创建 LLM 失败 provider=%s model=%s: %s", runtime.provider, runtime.model_name, exc)
        raise ConfigurationError(f"创建模型失败：{exc}") from exc


# --------------------------------------------------------------------------- #
# 连接测试
# --------------------------------------------------------------------------- #
async def probe_llm(llm: BaseChatModel, prompt: str = "ping") -> tuple[bool, str, float, str | None]:
    """测试模型连通性。

    返回 `(是否成功, 描述, 耗时毫秒, 回复预览)`。
    """
    started = time.perf_counter()
    try:
        response = await llm.ainvoke(
            [SystemMessage(content="You are a health-check probe. Reply in one short sentence."), HumanMessage(content=prompt)]
        )
        latency = (time.perf_counter() - started) * 1000
        content = response.content if isinstance(response.content, str) else str(response.content)
        return True, "连接成功", latency, content[:200]
    except Exception as exc:  # noqa: BLE001
        latency = (time.perf_counter() - started) * 1000
        message = _friendly_error(exc)
        logger.info("模型连通性测试失败：%s", message)
        return False, message, latency, None


def _friendly_error(exc: Exception) -> str:
    """把底层 SDK 异常转换成可读、且不泄露密钥的提示。"""
    text = str(exc)
    lowered = text.lower()
    if "401" in lowered or "invalid api key" in lowered or "unauthorized" in lowered or "authentication" in lowered:
        return "鉴权失败：API Key 无效或已过期"
    if "404" in lowered or "not found" in lowered:
        return "模型或接口地址不存在：请检查 Model 名称与 Base URL"
    if "403" in lowered:
        return "无权限访问该模型：请检查 API Key 权限或模型开通状态"
    if "429" in lowered or "rate limit" in lowered:
        return "请求过于频繁或额度不足（429）"
    if "timeout" in lowered or "timed out" in lowered:
        return "请求超时：请检查网络或 Base URL 是否可访问"
    if "connection" in lowered or "connect" in lowered or "getaddrinfo" in lowered or "ssl" in lowered:
        return "网络连接失败：请检查 Base URL、代理或本地服务是否启动"
    if "insufficient" in lowered or "balance" in lowered or "quota" in lowered:
        return "账户额度不足"
    return f"调用失败：{text[:300]}"


def wrap_model_error(exc: Exception) -> ModelCallError:
    return ModelCallError(_friendly_error(exc))


# --------------------------------------------------------------------------- #
# 供应商元数据（前端「模型管理」使用）
# --------------------------------------------------------------------------- #
PROVIDER_DESCRIPTIONS: dict[str, str] = {
    Provider.OPENAI: "官方 OpenAI API",
    Provider.DEEPSEEK: "DeepSeek 开放平台（OpenAI 兼容）",
    Provider.QWEN: "阿里云百炼 / DashScope OpenAI 兼容模式",
    Provider.OLLAMA: "本地 Ollama 服务（OpenAI 兼容 /v1）",
    Provider.GEMINI: "Google Gemini（原生 SDK）",
    Provider.CLAUDE: "Anthropic Claude（原生 SDK）",
    Provider.MOONSHOT: "月之暗面 Kimi（OpenAI 兼容）",
    Provider.ZHIPU: "智谱 GLM（OpenAI 兼容）",
    Provider.SILICONFLOW: "SiliconFlow 硅基流动（OpenAI 兼容）",
    Provider.CUSTOM: "任意 OpenAI Compatible 网关 / 私有部署",
    Provider.MOCK: "本地 Mock 模型：无需 API Key，用于离线开发与自检",
}


def list_provider_infos() -> list[dict[str, Any]]:
    return [
        {
            "value": provider,
            "label": Provider.LABELS.get(provider, provider),
            "default_base_url": Provider.DEFAULT_BASE_URLS.get(provider) or None,
            "requires_api_key": provider in Provider.REQUIRES_API_KEY,
            "requires_base_url": provider == Provider.CUSTOM,
            "description": PROVIDER_DESCRIPTIONS.get(provider),
        }
        for provider in Provider.ALL
    ]
