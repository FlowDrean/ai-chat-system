"""模型管理路由：/api/models/*"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Pagination, get_current_admin, get_current_user, pagination
from app.core.exceptions import NotFoundError
from app.core.response import Envelope, ListEnvelope, ok, page
from app.db.session import get_db
from app.llm.embeddings import list_embedding_providers
from app.llm.factory import list_provider_infos
from app.models.user import User
from app.schemas.common import MessageResponse
from app.schemas.model_config import (
    ModelCreate,
    ModelOut,
    ModelTestResult,
    ModelUpdate,
    ProviderInfo,
)
from app.services.model_service import ModelService

router = APIRouter(prefix="/models", tags=["模型管理"])


@router.get("/providers", response_model=Envelope[list[ProviderInfo]], summary="供应商列表")
async def list_providers(_: User = Depends(get_current_user)) -> dict:
    return ok(list_provider_infos())


@router.get("/embedding-options", response_model=Envelope[list[dict]], summary="Embedding 供应商与预置模型")
async def embedding_options(_: User = Depends(get_current_user)) -> dict:
    return ok(list_embedding_providers())


@router.get("", response_model=ListEnvelope[ModelOut], summary="模型列表")
async def list_models(
    keyword: str | None = Query(None, description="按名称 / 模型 ID 搜索"),
    provider: str | None = Query(None),
    enabled: bool | None = Query(None),
    page_params: Pagination = Depends(pagination),
    _: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    items, total = await ModelService(db).list_models(
        keyword=keyword,
        provider=provider,
        enabled=enabled,
        page=page_params.page,
        page_size=page_params.page_size,
    )
    return ok(page([item.model_dump() for item in items], total, page_params.page, page_params.page_size))


@router.post("", response_model=Envelope[ModelOut], summary="新增模型")
async def create_model(
    payload: ModelCreate,
    user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    model = await ModelService(db).create_model(payload, operator_id=user.id)
    await db.commit()
    return ok(model, "模型创建成功")


@router.get("/{model_id}", response_model=Envelope[ModelOut], summary="模型详情")
async def get_model(
    model_id: int, _: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> dict:
    from app.services.model_service import to_model_out

    service = ModelService(db)
    model = await service.get_model(model_id)
    return ok(to_model_out(model))


@router.put("/{model_id}", response_model=Envelope[ModelOut], summary="编辑模型")
async def update_model(
    model_id: int,
    payload: ModelUpdate,
    _: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    model = await ModelService(db).update_model(model_id, payload)
    await db.commit()
    return ok(model, "模型更新成功")


@router.delete("/{model_id}", response_model=Envelope[MessageResponse], summary="删除模型")
async def delete_model(
    model_id: int,
    _: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    await ModelService(db).delete_model(model_id)
    await db.commit()
    return ok(MessageResponse(message="模型已删除"))


@router.post("/{model_id}/default", response_model=Envelope[ModelOut], summary="设为默认模型")
async def set_default_model(
    model_id: int,
    _: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    model = await ModelService(db).set_default(model_id)
    await db.commit()
    return ok(model, "已设为默认模型")


@router.patch("/{model_id}/enabled", response_model=Envelope[ModelOut], summary="启用 / 禁用模型")
async def toggle_model(
    model_id: int,
    enabled: bool = Query(..., description="true 启用 false 禁用"),
    _: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    model = await ModelService(db).toggle_model(model_id, enabled)
    await db.commit()
    return ok(model, "状态已更新")


@router.post("/{model_id}/test", response_model=Envelope[ModelTestResult], summary="测试模型连接")
async def test_model(
    model_id: int,
    _: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    result = await ModelService(db).test_model(model_id)
    await db.commit()
    return ok(result, result["message"])


@router.post("/{model_id}/duplicate", response_model=Envelope[ModelOut], summary="复制模型配置")
async def duplicate_model(
    model_id: int,
    _: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    service = ModelService(db)
    source = await service.get_model(model_id)
    if source is None:
        raise NotFoundError("模型不存在")
    payload = ModelCreate(
        name=f"{source.name} 副本",
        provider=source.provider,
        model_name=source.model_name,
        base_url=source.base_url,
        temperature=source.temperature,
        top_p=source.top_p,
        max_tokens=source.max_tokens,
        frequency_penalty=source.frequency_penalty,
        presence_penalty=source.presence_penalty,
        enabled=source.enabled,
        is_default=False,
        supports_stream=source.supports_stream,
        supports_vision=source.supports_vision,
        extra_params=source.extra_params,
        description=source.description,
        api_key=source.api_key,
    )
    model = await service.create_model(payload)
    await db.commit()
    return ok(model, "已复制模型配置")
