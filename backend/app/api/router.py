"""API 路由汇总（统一前缀 /api）。"""

from fastapi import APIRouter

from app.api.auth import router as auth_router
from app.api.chat import router as chat_router
from app.api.dashboard import router as dashboard_router
from app.api.documents import router as documents_router
from app.api.knowledge import router as knowledge_router
from app.api.mcp import router as mcp_router
from app.api.models import router as models_router
from app.api.prompts import router as prompts_router
from app.api.skills import router as skills_router
from app.api.users import profile_router, router as users_router

api_router = APIRouter()

api_router.include_router(auth_router)
api_router.include_router(chat_router)
api_router.include_router(models_router)
api_router.include_router(knowledge_router)
api_router.include_router(mcp_router)
api_router.include_router(documents_router)
api_router.include_router(prompts_router)
api_router.include_router(skills_router)
api_router.include_router(users_router)
api_router.include_router(profile_router)
api_router.include_router(dashboard_router)

__all__ = ["api_router"]
