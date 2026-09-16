"""技能管理路由：/api/skills/*

* `/skills`            管理列表 / 新建 / 编辑 / 删除（管理员）
* `/skills/available`  聊天页可用的技能（任意登录用户）
* `/skills/specs`      技能类型规格（前端动态表单）
* `/skills/{id}/test`  试运行
* `/skills/test-run`   未保存配置试运行
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Pagination, get_current_admin, get_current_user, pagination
from app.core.response import Envelope, ListEnvelope, ok, page
from app.db.session import get_db
from app.models.user import User
from app.schemas.common import MessageResponse
from app.schemas.skill import (
    SkillCreate,
    SkillOptionOut,
    SkillOut,
    SkillSpecOut,
    SkillTestRequest,
    SkillTestResult,
    SkillUpdate,
)
from app.services.skill_service import SkillService

router = APIRouter(prefix="/skills", tags=["技能"])


@router.get("", response_model=ListEnvelope[SkillOut], summary="技能列表（管理员）")
async def list_skills(
    keyword: str | None = Query(None, description="按名称 / 标识 / 说明搜索"),
    type: str | None = Query(None, description="按技能类型过滤"),  # noqa: A002
    enabled: bool | None = Query(None),
    page_params: Pagination = Depends(pagination),
    _: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    items, total = await SkillService(db).list_skills(
        keyword=keyword, type=type, enabled=enabled, page=page_params.page, page_size=page_params.page_size
    )
    return ok(page([item.model_dump() for item in items], total, page_params.page, page_params.page_size))


@router.get("/available", response_model=Envelope[list[SkillOptionOut]], summary="聊天可用技能")
async def list_available(
    _: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    return ok([item.model_dump() for item in await SkillService(db).list_available()])


@router.get("/specs", response_model=Envelope[list[SkillSpecOut]], summary="技能类型规格")
async def list_specs(_: User = Depends(get_current_admin)) -> dict:
    from app.skills import registry

    return ok(registry.list_specs())


@router.post("", response_model=Envelope[SkillOut], summary="新建技能（管理员）")
async def create_skill(
    payload: SkillCreate,
    user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    skill = await SkillService(db).create_skill(payload, operator_id=user.id)
    await db.commit()
    return ok(skill, "技能已创建")


@router.post("/test-run", response_model=Envelope[SkillTestResult], summary="未保存配置试运行")
async def test_draft(
    payload: SkillTestRequest,
    skill_type: str = Query(..., description="技能类型"),
    _: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    result = await SkillService(db).test_draft(skill_type, payload.config, payload.arguments)
    return ok(result, "试运行完成" if result["success"] else result["error"])


@router.get("/{skill_id}", response_model=Envelope[SkillOut], summary="技能详情（管理员）")
async def get_skill(
    skill_id: int,
    _: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    from app.services.skill_service import to_skill_out

    skill = await SkillService(db).get_skill(skill_id)
    return ok(to_skill_out(skill))


@router.put("/{skill_id}", response_model=Envelope[SkillOut], summary="编辑技能（管理员）")
async def update_skill(
    skill_id: int,
    payload: SkillUpdate,
    _: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    skill = await SkillService(db).update_skill(skill_id, payload)
    await db.commit()
    return ok(skill, "技能已更新")


@router.patch("/{skill_id}/enabled", response_model=Envelope[SkillOut], summary="启用 / 禁用技能")
async def toggle_skill(
    skill_id: int,
    enabled: bool = Query(..., description="true 启用 false 禁用"),
    _: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    skill = await SkillService(db).toggle_skill(skill_id, enabled)
    await db.commit()
    return ok(skill, "状态已更新")


@router.delete("/{skill_id}", response_model=Envelope[MessageResponse], summary="删除技能（管理员）")
async def delete_skill(
    skill_id: int,
    _: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    await SkillService(db).delete_skill(skill_id)
    await db.commit()
    return ok(MessageResponse(message="技能已删除"))


@router.post("/{skill_id}/test", response_model=Envelope[SkillTestResult], summary="试运行技能")
async def test_skill(
    skill_id: int,
    payload: SkillTestRequest | None = None,
    _: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    arguments = (payload.arguments if payload else {}) or {}
    result = await SkillService(db).test_skill(skill_id, arguments)
    return ok(result, "试运行完成" if result["success"] else (result["error"] or "试运行失败"))
