"""数据库连接 / 会话管理（SQLAlchemy 2.x AsyncSession）。

* MySQL 8.x：`mysql+aiomysql://user:pwd@host:3306/db?charset=utf8mb4`
* SQLite（本地开发）：`sqlite+aiosqlite:///./data/app.db`

SQLite 使用 `NullPool`：
  1. SQLite 文件锁与连接池组合容易出问题，NullPool 每次新建连接更稳；
  2. 规避 `pool_pre_ping` 在 aiosqlite 下的 `MissingGreenlet` 兼容性问题。
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

if settings.is_sqlite:
    engine = create_async_engine(
        settings.database_url,
        echo=settings.db_echo,
        future=True,
        poolclass=NullPool,
        connect_args={"check_same_thread": False},
    )
else:
    engine = create_async_engine(
        settings.database_url,
        echo=settings.db_echo,
        future=True,
        pool_pre_ping=True,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_recycle=settings.db_pool_recycle,
        pool_use_lifo=True,
    )

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,  # 提交后不过期，避免异步场景下的同步懒加载
    autoflush=False,
    autocommit=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI 依赖：请求级会话，异常自动回滚。"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


async def init_db() -> None:
    """建表（开发 / 首次启动用；生产建议使用 Alembic 迁移）。"""
    from app import models  # noqa: F401  确保所有模型已注册到 metadata
    from app.db.base import Base

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("数据库表结构检查完成：%s", settings.database_url.split("://")[0])


async def check_schema_ready() -> bool:
    """检查关键表是否存在；缺失时给出可执行的修复提示。"""
    from sqlalchemy import inspect

    expected = {"users", "models", "conversations", "messages", "knowledge_bases", "documents", "document_chunks", "prompts"}
    async with engine.connect() as conn:
        tables = set(await conn.run_sync(lambda sync_conn: inspect(sync_conn).get_table_names()))
    missing = sorted(expected - tables)
    if missing:
        logger.error(
            "数据库表结构不完整，缺少：%s\n"
            "  请先执行迁移（在 backend 目录下）：alembic upgrade head\n"
            "  或把 .env 中的 AUTO_CREATE_TABLES 设为 true 让应用自动建表（仅建议开发环境）",
            ", ".join(missing),
        )
        return False
    logger.info("数据库表结构检查通过，共 %s 张表", len(tables))
    return True


async def dispose_engine() -> None:
    await engine.dispose()
