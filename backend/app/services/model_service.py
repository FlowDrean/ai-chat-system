"""模型配置服务：CRUD / 启用禁用 / 默认模型 / 连通性测试。

安全约定：API Key 只允许写入，读取一律返回脱敏值；日志中不得出现明文 Key。
"""

from __future__ import annotations

import time

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    BadRequestError,
    ConflictError,
    ModelDisabledError,
    ModelNotFoundError,
)
from app.core.logging import get_logger
from app.core.security import mask_secret
from app.llm.factory import create_llm, probe_llm
from app.models.model_config import ModelConfig, ModelStatus, Provider
from app.models.usage import UsageSource
from app.repositories.model_repo import ModelRepository
from app.repositories.prompt_repo import UsageRepository
from app.schemas.model_config import ModelCreate, ModelOut, ModelUpdate

logger = get_logger(__name__)


def to_model_out(model: ModelConfig) -> ModelOut:
    """ORM → 出参（API Key 脱敏）。"""
    data = model.to_dict(exclude={"_api_key", "api_key"})
    plain = model.api_key
    data.update(
        {
            "api_key_masked": mask_secret(plain, head=4, tail=4) if plain else None,
            "has_api_key": bool(plain),
            "provider_label": Provider.LABELS.get(model.provider, model.provider),
        }
    )
    return ModelOut.model_validate(data)


class ModelService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.models = ModelRepository(session)
        self.usage = UsageRepository(session)

    # ------------------------------------------------------------------ #
    async def list_models(
        self,
        *,
        keyword: str | None = None,
        provider: str | None = None,
        enabled: bool | None = None,
        page: int = 1,
        page_size: int = 100,
    ) -> tuple[list[ModelOut], int]:
        models, total = await self.models.list_models(
            keyword=keyword,
            provider=provider,
            enabled=enabled,
            offset=(page - 1) * page_size,
            limit=page_size,
        )
        return [to_model_out(m) for m in models], total

    async def get_model(self, model_id: int) -> ModelConfig:
        model = await self.models.get(model_id)
        if model is None:
            raise ModelNotFoundError()
        return model

    async def get_default_model(self) -> ModelConfig:
        model = await self.models.get_default()
        if model is None:
            raise ModelNotFoundError("系统中还没有可用的模型，请先在「模型管理」中添加")
        return model

    async def resolve_for_chat(self, model_id: int | None) -> ModelConfig:
        """聊天时解析使用的模型：指定模型 → 默认模型。"""
        model = await self.models.get(model_id) if model_id else await self.models.get_default()
        if model is None:
            raise ModelNotFoundError("模型不存在或已被删除")
        if not model.enabled:
            raise ModelDisabledError()
        return model

    # ------------------------------------------------------------------ #
    async def create_model(self, data: ModelCreate, *, operator_id: int | None = None) -> ModelOut:
        if data.provider in Provider.REQUIRES_API_KEY and not data.api_key:
            raise BadRequestError(f"供应商 {data.provider} 必须填写 API Key")

        model = ModelConfig(
            name=data.name.strip(),
            provider=data.provider,
            model_name=data.model_name.strip(),
            base_url=data.base_url,
            temperature=data.temperature,
            top_p=data.top_p,
            max_tokens=data.max_tokens,
            frequency_penalty=data.frequency_penalty,
            presence_penalty=data.presence_penalty,
            enabled=data.enabled,
            is_default=data.is_default,
            supports_stream=data.supports_stream,
            supports_vision=data.supports_vision,
            extra_params=data.extra_params,
            description=data.description,
            created_by=operator_id,
        )
        model.api_key = data.api_key
        self.session.add(model)
        await self.session.flush()

        if data.is_default or await self.models.count() == 1:
            await self._make_default(model)
        logger.info("新增模型 name=%s provider=%s model=%s", model.name, model.provider, model.model_name)
        return to_model_out(model)

    async def update_model(self, model_id: int, data: ModelUpdate) -> ModelOut:
        model = await self.get_model(model_id)
        payload = data.model_dump(exclude_unset=True)

        api_key = payload.pop("api_key", None)
        if api_key is not None:
            if api_key == "":
                model._api_key = None
            else:
                model.api_key = api_key

        new_provider = payload.get("provider")
        if new_provider and new_provider in Provider.REQUIRES_API_KEY and not model.api_key:
            raise BadRequestError(f"供应商 {new_provider} 必须填写 API Key")

        for key, value in payload.items():
            if key == "is_default":
                continue
            setattr(model, key, value)

        if payload.get("is_default"):
            await self._make_default(model)
        elif payload.get("is_default") is False and model.is_default:
            model.is_default = False

        await self.session.flush()
        logger.info("更新模型 id=%s name=%s", model.id, model.name)
        return to_model_out(model)

    async def delete_model(self, model_id: int) -> None:
        model = await self.get_model(model_id)
        was_default = model.is_default
        await self.models.delete(model)
        # 删除了默认模型 → 自动把第一个可用模型设为默认
        if was_default:
            candidate = await self.models.get_default()
            if candidate is not None:
                candidate.is_default = True
        logger.info("删除模型 id=%s", model_id)

    async def toggle_model(self, model_id: int, enabled: bool) -> ModelOut:
        model = await self.get_model(model_id)
        model.enabled = enabled
        if not enabled and model.is_default:
            model.is_default = False
            candidate = await self.models.get_default()
            if candidate is not None:
                candidate.is_default = True
        await self.session.flush()
        return to_model_out(model)

    async def set_default(self, model_id: int) -> ModelOut:
        model = await self.get_model(model_id)
        if not model.enabled:
            raise BadRequestError("已禁用的模型不能设为默认模型")
        await self._make_default(model)
        return to_model_out(model)

    async def _make_default(self, model: ModelConfig) -> None:
        await self.models.clear_default(exclude_id=model.id)
        model.is_default = True
        if not model.enabled:
            model.enabled = True
        await self.session.flush()

    # ------------------------------------------------------------------ #
    async def test_model(self, model_id: int) -> dict:
        """测试模型连通性，并记录状态与调用日志。"""
        model = await self.get_model(model_id)
        from app.llm.factory import build_runtime_config

        started = time.perf_counter()
        success = False
        message = ""
        preview: str | None = None
        try:
            llm = create_llm(build_runtime_config(model, streaming=False))
            success, message, _, preview = await probe_llm(llm)
        except Exception as exc:  # noqa: BLE001
            from app.llm.factory import _friendly_error

            message = _friendly_error(exc)
        latency = (time.perf_counter() - started) * 1000

        from datetime import datetime

        model.status = ModelStatus.OK if success else ModelStatus.ERROR
        model.status_message = message[:500]
        model.last_tested_at = datetime.now()
        await self.session.flush()

        await self.usage.log(
            provider=model.provider,
            model_name=model.model_name,
            source=UsageSource.MODEL_TEST,
            latency_ms=latency,
            success=success,
            error_message=None if success else message[:500],
        )
        return {
            "success": success,
            "message": message,
            "latency_ms": round(latency, 1),
            "model_name": model.model_name,
            "provider": model.provider,
            "reply_preview": preview,
        }

    async def ensure_unique_name(self, name: str, exclude_id: int | None = None) -> None:
        existing = await self.models.find_one(ModelConfig.name == name)
        if existing is not None and existing.id != exclude_id:
            raise ConflictError("模型名称已存在")
