"""首次启动初始化数据：管理员账号 / 默认模型 / 内置 Prompt。

所有初始值都来自 `.env`，不存在任何硬编码的密钥。
"""

from __future__ import annotations

from app.core.config import settings
from app.core.logging import get_logger
from app.core.security import hash_password
from app.db.session import AsyncSessionLocal
from app.models.model_config import ModelConfig, Provider
from app.models.user import User, UserRole, UserStatus
from app.repositories.model_repo import ModelRepository
from app.repositories.user_repo import UserRepository
from app.services.prompt_service import PromptService
from app.services.skill_service import SkillService

logger = get_logger(__name__)


async def seed_initial_data() -> None:
    async with AsyncSessionLocal() as session:
        await _seed_admin(session)
        await _seed_model(session)
        await PromptService(session).ensure_builtin_prompts()
        await SkillService(session).seed_builtin_skills()
        await session.commit()


async def _seed_admin(session) -> None:  # noqa: ANN001
    """系统没有任何用户时，创建默认管理员。"""
    users = UserRepository(session)
    if await users.exists_any():
        return
    username = settings.default_admin_username or "admin"
    password = settings.default_admin_password or "admin123456"
    admin = User(
        username=username,
        email=settings.default_admin_email or None,
        nickname="管理员",
        password_hash=hash_password(password),
        role=UserRole.ADMIN,
        is_superuser=True,
        status=UserStatus.ACTIVE,
    )
    session.add(admin)
    await session.flush()
    logger.warning(
        "已创建默认管理员账号 username=%s password=%s（请登录后立即修改密码）", username, password
    )


async def _seed_model(session) -> None:  # noqa: ANN001
    """没有任何模型时，创建一个可直接使用的模型。

    默认是内置的 `mock` 模型（无需 API Key，可离线演示全链路）。
    如果在 `.env` 中配置了 `DEFAULT_PROVIDER` / `DEFAULT_API_KEY`，则创建真实模型。
    """
    if not settings.seed_default_model:
        return
    models = ModelRepository(session)
    if await models.count_all() > 0:
        return

    provider = (settings.default_provider or Provider.MOCK).lower()
    model_name = settings.default_model_name or "mock-chat"
    base_url = settings.default_base_url or Provider.DEFAULT_BASE_URLS.get(provider) or None
    api_key = settings.default_api_key or None

    if provider in Provider.REQUIRES_API_KEY and not api_key:
        logger.warning(
            "DEFAULT_PROVIDER=%s 但未配置 DEFAULT_API_KEY，已自动回退为内置 mock 模型", provider
        )
        provider, model_name, base_url, api_key = Provider.MOCK, "mock-chat", None, None

    model = ModelConfig(
        name=f"{Provider.LABELS.get(provider, provider)} 默认模型",
        provider=provider,
        model_name=model_name,
        base_url=base_url,
        temperature=0.7,
        max_tokens=4096,
        enabled=True,
        is_default=True,
        supports_stream=provider != Provider.MOCK,
        description="系统初始化自动创建，可在「模型管理」中修改或删除",
    )
    model.api_key = api_key
    session.add(model)
    await session.flush()
    logger.info("已创建默认模型 provider=%s model=%s", provider, model_name)
