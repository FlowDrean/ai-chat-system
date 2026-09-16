"""Prompt 管理路由：/api/prompts/*"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Pagination, get_current_user, pagination
from app.core.response import Envelope, ListEnvelope, ok, page
from app.db.session import get_db
from app.models.user import User
from app.schemas.common import MessageResponse
from app.schemas.prompt import PromptCreate, PromptOut, PromptRenderRequest, PromptUpdate
from app.services.prompt_service import PromptService

router = APIRouter(prefix="/prompts", tags=["Prompt 管理"])


@router.get("", response_model=ListEnvelope[PromptOut], summary="Prompt 列表（含内置模板）")
async def list_prompts(
    keyword: str | None = Query(None),
    scene: str | None = Query(None, description="system/rag/chat"),
    enabled: bool | None = Query(None),
    page_params: Pagination = Depends(pagination),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    items, total = await PromptService(db).list_prompts(
        user.id,
        keyword=keyword,
        scene=scene,
        enabled=enabled,
        page=page_params.page,
        page_size=page_params.page_size,
    )
    return ok(page([item.model_dump() for item in items], total, page_params.page, page_params.page_size))


@router.post("", response_model=Envelope[PromptOut], summary="新建 Prompt")
async def create_prompt(
    payload: PromptCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    prompt = await PromptService(db).create_prompt(payload, user.id)
    await db.commit()
    return ok(prompt, "Prompt 创建成功")


@router.get("/{prompt_id}", response_model=Envelope[PromptOut], summary="Prompt 详情")
async def get_prompt(
    prompt_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    from app.services.prompt_service import to_prompt_out

    prompt = await PromptService(db).get_prompt(prompt_id, user.id)
    return ok(to_prompt_out(prompt))


@router.put("/{prompt_id}", response_model=Envelope[PromptOut], summary="编辑 Prompt")
async def update_prompt(
    prompt_id: int,
    payload: PromptUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    prompt = await PromptService(db).update_prompt(prompt_id, payload, user.id)
    await db.commit()
    return ok(prompt, "Prompt 已更新")


@router.delete("/{prompt_id}", response_model=Envelope[MessageResponse], summary="删除 Prompt")
async def delete_prompt(
    prompt_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    await PromptService(db).delete_prompt(prompt_id, user.id)
    await db.commit()
    return ok(MessageResponse(message="Prompt 已删除"))


@router.post("/{prompt_id}/render", response_model=Envelope[dict], summary="变量渲染预览")
async def render_prompt(
    prompt_id: int,
    payload: PromptRenderRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    result = await PromptService(db).render(prompt_id, user.id, payload.variables)
    await db.commit()
    return ok(result)


@router.post("/{prompt_id}/duplicate", response_model=Envelope[PromptOut], summary="复制为我的 Prompt")
async def duplicate_prompt(
    prompt_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    service = PromptService(db)
    source = await service.get_prompt(prompt_id, user.id)
    prompt = await service.create_prompt(
        PromptCreate(
            name=f"{source.name} 副本",
            content=source.content,
            description=source.description,
            variables=source.variables,
            tags=source.tags,
            scene=source.scene,
            enabled=source.enabled,
        ),
        user.id,
    )
    await db.commit()
    return ok(prompt, "已复制到我的 Prompt")
