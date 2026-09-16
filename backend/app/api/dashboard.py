"""Dashboard / 系统信息路由。"""

from __future__ import annotations

import platform
import sys

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_admin, get_current_user
from app.core.config import settings
from app.core.response import Envelope, ok
from app.db.session import get_db
from app.models.user import User
from app.schemas.prompt import DashboardOut
from app.services.dashboard_service import DashboardService

router = APIRouter(tags=["统计与系统"])


@router.get("/dashboard", response_model=Envelope[DashboardOut], summary="Dashboard 统计")
async def dashboard(
    days: int = Query(14, ge=7, le=90, description="趋势天数"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    data = await DashboardService(db, user_id=user.id, is_admin=user.is_admin).overview(days=days)
    return ok(data)


@router.get("/system/info", response_model=Envelope[dict], summary="系统信息（管理员）")
async def system_info(_: User = Depends(get_current_admin)) -> dict:
    return ok(
        {
            "app_name": settings.app_name,
            "app_version": settings.app_version,
            "app_env": settings.app_env,
            "debug": settings.debug,
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "database": settings.database_url.split("://")[0],
            "vector_store": settings.vector_store,
            "default_embedding": f"{settings.default_embedding_provider}:{settings.default_embedding_model}",
            "max_upload_size_mb": settings.max_upload_size_mb,
            "allowed_extensions": sorted(settings.allowed_extension_set),
            "llm_request_timeout": settings.llm_request_timeout,
            "max_context_messages": settings.max_context_messages,
        }
    )


@router.get("/health", summary="健康检查")
async def health() -> dict:
    return ok({"status": "ok", "version": settings.app_version})
