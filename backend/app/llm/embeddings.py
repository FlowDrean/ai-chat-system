"""Embedding Factory。

统一入口：

    embedding = create_embeddings({...统一配置...})

支持（新增供应商只需在这里注册，业务代码无需改动）：
* local        —— 内置轻量本地向量（无需 API Key，离线可用，词法级召回）
* openai       —— text-embedding-3-small / large ...
* qwen         —— 通义 text-embedding-v3（DashScope OpenAI 兼容）
* deepseek/compatible/siliconflow/zhipu —— OpenAI 兼容协议
* ollama       —— 本地 Ollama 服务
"""

from __future__ import annotations

import hashlib
import math
import re
from typing import Any

from langchain_core.embeddings import Embeddings

from app.core.exceptions import ConfigurationError, EmbeddingError
from app.core.logging import get_logger

logger = get_logger(__name__)


# --------------------------------------------------------------------------- #
# 本地轻量 Embedding（hashing trick + 词法权重）
# --------------------------------------------------------------------------- #
class LocalHashEmbeddings(Embeddings):
    """Deterministic hashing embedding。

    使用「英文单词 + 中文单字/双字」特征做 hashing trick 投影到固定维度，
    再做 sublinear TF 加权与 L2 归一化。适合：
      * 完全离线 / 无 API Key 的本地开发与自动化测试；
      * 关键词型（lexical）检索场景。

    如果需要真正的语义召回，请在知识库配置里切换为 openai/qwen/ollama 等
    真实 Embedding 供应商。
    """

    def __init__(self, dimension: int = 512) -> None:
        self.dimension = max(8, int(dimension))

    # ------------------------------------------------------------------ #
    @staticmethod
    def _tokens(text: str) -> list[str]:
        text = (text or "").lower()
        tokens: list[str] = []
        # 英文 / 数字单词
        tokens.extend(re.findall(r"[a-z0-9_]{2,}", text))
        # 中文：单字 + 双字组合
        for run in re.findall(r"[\u4e00-\u9fff]+", text):
            tokens.extend(run)
            tokens.extend(run[i : i + 2] for i in range(len(run) - 1))
        # 标点/数字混合的兜底特征
        tokens.extend(re.findall(r"[a-z]{1,2}", text))
        return tokens

    def _bucket(self, token: str) -> tuple[int, float]:
        digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
        value = int.from_bytes(digest, "big")
        index = value % self.dimension
        sign = 1.0 if (value >> 63) & 1 == 0 else -1.0
        return index, sign

    def _embed_one(self, text: str) -> list[float]:
        vector = [0.0] * self.dimension
        tokens = self._tokens(text)
        if not tokens:
            return vector
        frequency: dict[str, int] = {}
        for token in tokens:
            frequency[token] = frequency.get(token, 0) + 1
        for token, count in frequency.items():
            index, sign = self._bucket(token)
            weight = (1.0 + math.log(count)) * sign
            vector[index] += weight
        norm = math.sqrt(sum(v * v for v in vector))
        if norm > 0:
            vector = [v / norm for v in vector]
        return vector

    # ------------------------------------------------------------------ #
    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_one(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed_one(text)


# --------------------------------------------------------------------------- #
# 供应商预置
# --------------------------------------------------------------------------- #
class EmbeddingProvider:
    LOCAL = "local"
    OPENAI = "openai"
    QWEN = "qwen"
    DEEPSEEK = "deepseek"
    OLLAMA = "ollama"
    ZHIPU = "zhipu"
    SILICONFLOW = "siliconflow"
    CUSTOM = "custom"

    ALL = (LOCAL, OPENAI, QWEN, DEEPSEEK, OLLAMA, ZHIPU, SILICONFLOW, CUSTOM)
    OPENAI_COMPATIBLE = (OPENAI, QWEN, DEEPSEEK, ZHIPU, SILICONFLOW, CUSTOM)

    DEFAULT_BASE_URLS = {
        OPENAI: "https://api.openai.com/v1",
        QWEN: "https://dashscope.aliyuncs.com/compatible-mode/v1",
        DEEPSEEK: "https://api.deepseek.com/v1",
        ZHIPU: "https://open.bigmodel.cn/api/paas/v4",
        SILICONFLOW: "https://api.siliconflow.cn/v1",
        OLLAMA: "http://127.0.0.1:11434",
        LOCAL: "",
        CUSTOM: "",
    }

    PRESETS: dict[str, list[dict[str, Any]]] = {
        LOCAL: [{"value": "local-hash-512", "label": "本地轻量向量 (512维)", "dimension": 512, "requires_api_key": False}],
        OPENAI: [
            {"value": "text-embedding-3-small", "label": "text-embedding-3-small", "dimension": 1536, "requires_api_key": True},
            {"value": "text-embedding-3-large", "label": "text-embedding-3-large", "dimension": 3072, "requires_api_key": True},
            {"value": "text-embedding-ada-002", "label": "text-embedding-ada-002", "dimension": 1536, "requires_api_key": True},
        ],
        QWEN: [
            {"value": "text-embedding-v3", "label": "通义 text-embedding-v3", "dimension": 1024, "requires_api_key": True},
            {"value": "text-embedding-v2", "label": "通义 text-embedding-v2", "dimension": 1536, "requires_api_key": True},
        ],
        ZHIPU: [{"value": "embedding-3", "label": "智谱 embedding-3", "dimension": 2048, "requires_api_key": True}],
        SILICONFLOW: [
            {"value": "BAAI/bge-m3", "label": "BAAI/bge-m3", "dimension": 1024, "requires_api_key": True},
            {"value": "netease-youdao/bce-embedding-base_v1", "label": "bce-embedding-base_v1", "dimension": 768, "requires_api_key": True},
        ],
        DEEPSEEK: [
            {"value": "deepseek-embedding", "label": "deepseek-embedding(兼容)", "dimension": 1024, "requires_api_key": True}
        ],
        OLLAMA: [
            {"value": "nomic-embed-text", "label": "nomic-embed-text", "dimension": 768, "requires_api_key": False},
            {"value": "bge-m3", "label": "bge-m3", "dimension": 1024, "requires_api_key": False},
            {"value": "mxbai-embed-large", "label": "mxbai-embed-large", "dimension": 1024, "requires_api_key": False},
        ],
        CUSTOM: [{"value": "custom-embedding", "label": "自定义 OpenAI 兼容 Embedding", "dimension": 1024, "requires_api_key": True}],
    }


def list_embedding_providers() -> list[dict[str, Any]]:
    """给前端用的供应商 / 预置模型清单。"""
    result: list[dict[str, Any]] = []
    for provider in EmbeddingProvider.ALL:
        result.append(
            {
                "value": provider,
                "label": {
                    EmbeddingProvider.LOCAL: "本地轻量向量（离线可用）",
                    EmbeddingProvider.OPENAI: "OpenAI Embedding",
                    EmbeddingProvider.QWEN: "通义 Embedding",
                    EmbeddingProvider.DEEPSEEK: "DeepSeek Embedding",
                    EmbeddingProvider.OLLAMA: "Ollama Embedding",
                    EmbeddingProvider.ZHIPU: "智谱 Embedding",
                    EmbeddingProvider.SILICONFLOW: "SiliconFlow Embedding",
                    EmbeddingProvider.CUSTOM: "自定义 OpenAI 兼容 Embedding",
                }.get(provider, provider),
                "default_base_url": EmbeddingProvider.DEFAULT_BASE_URLS.get(provider) or None,
                "presets": EmbeddingProvider.PRESETS.get(provider, []),
            }
        )
    return result


# --------------------------------------------------------------------------- #
# Factory
# --------------------------------------------------------------------------- #
def create_embeddings(config: dict[str, Any] | None = None) -> Embeddings:
    """根据统一配置创建 Embedding 实例。

    配置结构（与 `KnowledgeBase.embedding_runtime_config()` 一致）::

        {
          "provider": "openai",
          "model": "text-embedding-3-small",
          "base_url": "https://api.openai.com/v1",
          "api_key": "sk-***",
          "dimension": 1536,
        }
    """
    config = dict(config or {})
    provider = str(config.get("provider") or EmbeddingProvider.LOCAL).lower()
    model = str(config.get("model") or "local-hash-512")
    dimension = int(config.get("dimension") or 512)
    api_key = config.get("api_key")
    base_url = config.get("base_url") or EmbeddingProvider.DEFAULT_BASE_URLS.get(provider) or None
    timeout = float(config.get("timeout") or 60)

    try:
        if provider == EmbeddingProvider.LOCAL:
            return LocalHashEmbeddings(dimension=dimension)

        if provider == EmbeddingProvider.OLLAMA:
            from langchain_ollama import OllamaEmbeddings

            return OllamaEmbeddings(model=model, base_url=base_url or "http://127.0.0.1:11434")

        if provider in EmbeddingProvider.OPENAI_COMPATIBLE:
            from langchain_openai import OpenAIEmbeddings

            if not api_key:
                raise ConfigurationError(f"Embedding 供应商 {provider} 需要配置 API Key")
            return OpenAIEmbeddings(
                model=model,
                api_key=api_key,
                base_url=base_url,
                timeout=timeout,
                # 兼容自建 / 第三方网关：由服务端自行切分超长文本
                check_embedding_ctx_length=False,
            )

        raise ConfigurationError(f"不支持的 Embedding 供应商：{provider}")
    except ConfigurationError:
        raise
    except ImportError as exc:
        raise ConfigurationError(
            f"缺少 {provider} 对应的依赖包：{exc.name}，请先安装后再使用该 Embedding 供应商"
        ) from exc
    except Exception as exc:  # noqa: BLE001
        logger.warning("创建 Embedding 失败 provider=%s model=%s: %s", provider, model, exc)
        raise EmbeddingError(f"创建 Embedding 失败：{exc}") from exc


def probe_embeddings(embedding: Embeddings) -> int:
    """探测维度：失败时抛出 EmbeddingError。"""
    vector = embedding.embed_query("dimension probe")
    return len(vector)
