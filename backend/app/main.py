"""FastAPI 应用入口。

启动流程：
    初始化日志 → 建表（开发环境）/ Alembic 迁移 → 初始化数据 → 恢复未完成的文档任务
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.router import api_router
from app.core.config import settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import get_logger, setup_logging
from app.core.middleware import RequestContextMiddleware, SecurityHeadersMiddleware
from app.core.response import ok
from app.db.session import check_schema_ready, dispose_engine, init_db
from app.seed import seed_initial_data

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):  # noqa: ARG001
    setup_logging()
    settings.ensure_directories()
    logger.info("=" * 78)
    logger.info("%s v%s 启动中 (env=%s)", settings.app_name, settings.app_version, settings.app_env)
    logger.info("数据库：%s", settings.database_url.split("@")[-1])
    logger.info("向量库：%s", settings.vector_store)
    logger.info("上传目录：%s", settings.upload_path)

    # SQLite / 开发环境可自动建表；MySQL 等长期环境建议 `alembic upgrade head` 并把
    # AUTO_CREATE_TABLES 设为 false，避免 create_all 绕过迁移管理。
    if settings.auto_create_tables and (settings.is_sqlite or settings.debug):
        await init_db()
    else:
        await check_schema_ready()

    try:
        await seed_initial_data()
    except Exception as exc:  # noqa: BLE001
        logger.exception("初始化数据失败：%s", exc)

    try:
        from app.services.document_service import DocumentService
        from app.db.session import AsyncSessionLocal

        async with AsyncSessionLocal() as session:
            await DocumentService(session).recover_unfinished()
    except Exception as exc:  # noqa: BLE001
        logger.warning("恢复未完成文档任务失败：%s", exc)

    logger.info("API 文档：http://127.0.0.1:%s/docs", settings.port)
    logger.info("=" * 78)
    yield
    await dispose_engine()
    logger.info("%s 已关闭", settings.app_name)


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description=(
        "AI 问答聊天助手平台：多模型配置 · AI 对话（SSE 流式）· RAG 知识库 · "
        "文档解析与向量化 · Prompt 管理 · LangChain / LangGraph 工作流"
    ),
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

# --------------------------------------------------------------------------- #
# 中间件（注意：先注册 CORS，再注册自定义中间件）
# --------------------------------------------------------------------------- #
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID", "X-Process-Time"],
)
app.add_middleware(RequestContextMiddleware)
app.add_middleware(SecurityHeadersMiddleware)

register_exception_handlers(app)
app.include_router(api_router, prefix=settings.api_prefix)


# --------------------------------------------------------------------------- #
# 根路径
# --------------------------------------------------------------------------- #
@app.get("/", include_in_schema=False)
async def index() -> JSONResponse:
    return JSONResponse(
        ok(
            {
                "name": settings.app_name,
                "version": settings.app_version,
                "docs": "/docs",
                "api_prefix": settings.api_prefix,
            },
            "AI Chat Assistant API is running",
        )
    )
