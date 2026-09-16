"""技能服务：管理后台配置 + 聊天时解析可用技能 + 试运行。

安全设计：
* 敏感配置（API Key 等）在出参里脱敏，只回传掩码；
* 更新时如果敏感字段传空字符串，表示「保持原值不变」，避免前端回显掩码时把密钥覆盖掉；
* 内置技能不可删除，只能禁用或改配置。
"""

from __future__ import annotations

import re
import time
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BadRequestError, PermissionDeniedError
from app.core.logging import get_logger
from app.core.security import mask_secret
from app.models.skill import Skill
from app.repositories.skill_repo import SkillRepository
from app.schemas.skill import SkillCreate, SkillOptionOut, SkillOut, SkillUpdate
from app.skills import registry
from app.skills.base import SkillError

logger = get_logger(__name__)

_SLUG_SAFE = re.compile(r"[^a-z0-9_-]")


def _slugify(text: str) -> str:
    base = _SLUG_SAFE.sub("-", (text or "").strip().lower())
    base = re.sub(r"-{2,}", "-", base).strip("-")
    return base or "skill"


def _secret_keys(skill_type: str, config: dict[str, Any] | None) -> list[str]:
    """该技能类型里哪些配置项属于敏感项。"""
    if not registry.is_supported(skill_type):
        return []
    spec = registry.get_spec(skill_type)
    keys = [field.key for field in spec.fields if field.secret or field.type == "password"]
    if config:
        # 兜底：key 名里带 key/secret/token/password 的也脱敏
        for key in config:
            if re.search(r"(api[_-]?key|secret|token|password)", key, re.I) and key not in keys:
                keys.append(key)
    return keys


def mask_config(skill_type: str, config: dict[str, Any] | None) -> tuple[dict[str, Any] | None, list[str]]:
    """出参脱敏：只保留掩码，不返回明文。"""
    if not config:
        return None, []
    keys = _secret_keys(skill_type, config)
    masked: dict[str, Any] = {}
    for key, value in config.items():
        if key in keys and isinstance(value, str) and value:
            masked[key] = mask_secret(value)
        else:
            masked[key] = value
    return masked, keys


def to_skill_out(skill: Skill) -> SkillOut:
    config, masked_keys = mask_config(skill.type, skill.config)
    spec = None
    type_label = skill.type
    category = "general"
    if registry.is_supported(skill.type):
        raw_spec = registry.get_spec(skill.type).to_dict()
        spec = raw_spec
        type_label = raw_spec["name"]
        category = raw_spec["category"]
    data = skill.to_dict()
    data.update(
        {
            "type_label": type_label,
            "category": category,
            "config": config,
            "config_masked_keys": masked_keys,
            "spec": spec,
        }
    )
    return SkillOut.model_validate(data)


def is_configured(skill: Skill) -> bool:
    """技能是否已完成必填配置。"""
    if not registry.is_supported(skill.type):
        return False
    spec = registry.get_spec(skill.type)
    config = skill.config or {}
    for field in spec.fields:
        if field.required and config.get(field.key) in (None, ""):
            return False
    if spec.uses_dynamic_args:
        try:
            registry.parse_args_schema(config.get("args_schema"))
        except SkillError:
            return False
    return True


class SkillService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.skills = SkillRepository(session)

    # ------------------------------------------------------------------ #
    # 查询
    # ------------------------------------------------------------------ #
    async def list_skills(
        self,
        *,
        keyword: str | None = None,
        type: str | None = None,  # noqa: A002
        enabled: bool | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[SkillOut], int]:
        items, total = await self.skills.list_skills(
            keyword=keyword,
            type=type,
            enabled=enabled,
            offset=(page - 1) * page_size,
            limit=page_size,
        )
        return [to_skill_out(item) for item in items], total

    async def get_skill(self, skill_id: int) -> Skill:
        return await self.skills.get_or_404(skill_id)

    async def list_available(self) -> list[SkillOptionOut]:
        """聊天页可用技能：已启用 + 允许用户使用。"""
        rows = await self.skills.list_active(visible_only=True)
        return [
            SkillOptionOut(
                id=row.id,
                name=row.name,
                slug=row.slug,
                type=row.type,
                description=row.description,
                icon=row.icon,
                configured=is_configured(row),
            )
            for row in rows
        ]

    def list_specs(self) -> list[dict[str, Any]]:
        return registry.list_specs()

    async def resolve_for_chat(self, skill_ids: list[int] | None) -> list[Skill]:
        """把会话/请求里的技能 id 解析成可用的技能（自动过滤已删除 / 已禁用 / 未配置的）。"""
        if not skill_ids:
            return []
        rows = await self.skills.list_by_ids([int(i) for i in skill_ids if i])
        usable: list[Skill] = []
        for row in rows:
            if not row.visible_to_users:
                continue
            if not is_configured(row):
                logger.info("技能 %s（%s）未完成配置，已跳过", row.name, row.type)
                continue
            usable.append(row)
        return usable

    # ------------------------------------------------------------------ #
    # 写入
    # ------------------------------------------------------------------ #
    async def create_skill(self, data: SkillCreate, operator_id: int | None = None) -> SkillOut:
        if not registry.is_supported(data.type):
            raise BadRequestError(f"不支持的技能类型：{data.type}")
        spec = registry.get_spec(data.type)
        if not spec.configurable:
            raise BadRequestError(f"技能类型「{spec.name}」不支持新建实例")

        slug = data.slug or _slugify(data.name)
        if await self.skills.get_by_slug(slug) is not None:
            raise BadRequestError(f"标识「{slug}」已被占用，请换一个")
        if not data.slug:
            slug = await self._unique_slug(slug)

        try:
            registry.validate_config(data.type, data.config)
        except SkillError as exc:
            raise BadRequestError(str(exc)) from exc

        skill = Skill(
            name=data.name.strip(),
            slug=slug,
            type=data.type,
            description=(data.description or spec.description).strip(),
            icon=data.icon or spec.icon,
            config=data.config or {},
            enabled=data.enabled,
            is_builtin=False,
            visible_to_users=data.visible_to_users,
            sort_order=data.sort_order,
            created_by=operator_id,
        )
        self.session.add(skill)
        await self.session.flush()
        logger.info("新建技能 id=%s name=%s type=%s", skill.id, skill.name, skill.type)
        return to_skill_out(skill)

    async def update_skill(self, skill_id: int, data: SkillUpdate) -> SkillOut:
        skill = await self.get_skill(skill_id)
        payload = data.model_dump(exclude_unset=True)

        config = payload.pop("config", None)
        if config is not None:
            merged = {**(skill.config or {})}
            secret_keys = _secret_keys(skill.type, merged)
            for key, value in config.items():
                # 敏感项传空字符串 = 保持原值（前端回显的是掩码，不能覆盖真实密钥）
                if key in secret_keys and value in ("", None):
                    continue
                merged[key] = value
            try:
                registry.validate_config(skill.type, merged)
            except SkillError as exc:
                raise BadRequestError(str(exc)) from exc
            skill.config = merged

        for key in ("name", "description", "icon", "enabled", "visible_to_users", "sort_order"):
            if key in payload and payload[key] is not None:
                setattr(skill, key, payload[key])

        await self.session.flush()
        logger.info("更新技能 id=%s name=%s enabled=%s", skill.id, skill.name, skill.enabled)
        return to_skill_out(skill)

    async def delete_skill(self, skill_id: int) -> None:
        skill = await self.get_skill(skill_id)
        if skill.is_builtin:
            raise PermissionDeniedError("系统预置技能不可删除，可将其禁用")
        await self.skills.delete(skill)
        logger.info("删除技能 id=%s name=%s", skill_id, skill.name)

    async def toggle_skill(self, skill_id: int, enabled: bool) -> SkillOut:
        skill = await self.get_skill(skill_id)
        skill.enabled = enabled
        await self.session.flush()
        return to_skill_out(skill)

    # ------------------------------------------------------------------ #
    # 试运行
    # ------------------------------------------------------------------ #
    async def test_skill(
        self, skill_id: int, arguments: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        skill = await self.get_skill(skill_id)
        return await self._run(skill.type, skill.config, arguments or {}, skill.name)

    async def test_draft(
        self,
        skill_type: str,
        config: dict[str, Any] | None,
        arguments: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """未保存的配置也能试运行（配置表单里的「试运行」按钮）。"""
        if not registry.is_supported(skill_type):
            raise BadRequestError(f"不支持的技能类型：{skill_type}")
        return await self._run(skill_type, config or {}, arguments or {}, skill_type)

    async def _run(
        self,
        skill_type: str,
        config: dict[str, Any] | None,
        arguments: dict[str, Any],
        label: str,
    ) -> dict[str, Any]:
        started = time.perf_counter()
        try:
            registry.validate_config(skill_type, config)
            executor = registry.create_skill(skill_type, config)
        except SkillError as exc:
            return {
                "success": False,
                "output": "",
                "error": str(exc),
                "latency_ms": round((time.perf_counter() - started) * 1000, 1),
                "tool_name": label,
                "arguments": arguments,
            }

        output = await executor.safe_run(**arguments)
        latency = (time.perf_counter() - started) * 1000
        failed = output.startswith("[技能执行失败]")
        return {
            "success": not failed,
            "output": output,
            "error": output if failed else None,
            "latency_ms": round(latency, 1),
            "tool_name": registry.tool_name_for(_slugify(label)),
            "arguments": arguments,
        }

    # ------------------------------------------------------------------ #
    async def _unique_slug(self, base: str) -> str:
        slug = base
        index = 2
        while await self.skills.get_by_slug(slug) is not None:
            slug = f"{base}-{index}"
            index += 1
        return slug

    async def mark_used(self, skill_ids: list[int]) -> None:
        """记录技能调用次数（由聊天流程调用）。"""
        if not skill_ids:
            return
        from datetime import datetime

        from sqlalchemy import update

        await self.session.execute(
            update(Skill)
            .where(Skill.id.in_(skill_ids))
            .values(usage_count=Skill.usage_count + 1, last_used_at=datetime.now())
        )
        await self.session.flush()

    # ------------------------------------------------------------------ #
    async def seed_builtin_skills(self) -> None:
        """首次启动写入内置技能。"""
        presets: list[dict[str, Any]] = [
            {
                "slug": "calculator",
                "type": "calculator",
                "name": "计算器",
                "description": "执行数学计算。当用户给出算术表达式、需要精确计算（加减乘除、幂、开方、三角函数、百分比）时使用。",
                "icon": "CalculatorOutlined",
                "config": {"precision": 10},
                "enabled": True,
                "sort_order": 10,
            },
            {
                "slug": "current-time",
                "type": "current_time",
                "name": "当前时间",
                "description": "获取当前日期、时间与星期。当用户询问今天几号、现在几点、星期几，或需要以当前时间为基准推理时使用。",
                "icon": "ClockCircleOutlined",
                "config": {"timezone": "Asia/Shanghai", "format": "%Y-%m-%d %H:%M:%S"},
                "enabled": True,
                "sort_order": 20,
            },
            {
                "slug": "web-fetch",
                "type": "web_fetch",
                "name": "网页抓取",
                "description": "抓取一个网页或接口地址的文本内容。当用户给出具体 URL，或需要阅读某个已知链接的正文时使用。",
                "icon": "GlobalOutlined",
                "config": {"max_chars": 4000, "timeout": 20, "allow_private": False},
                "enabled": True,
                "sort_order": 30,
            },
            {
                "slug": "web-search",
                "type": "web_search",
                "name": "联网搜索",
                "description": "在互联网上搜索最新信息。当问题涉及实时新闻、最新版本、近期事件，或需要模型知识之外的外部资料时使用。",
                "icon": "SearchOutlined",
                "config": {
                    "api_key": "",
                    "base_url": "https://api.tavily.com",
                    "max_results": 5,
                    "search_depth": "basic",
                    "timeout": 20,
                },
                "enabled": False,  # 需要先填 API Key
                "sort_order": 40,
            },
        ]

        created = 0
        for preset in presets:
            if await self.skills.get_by_slug(preset["slug"]) is not None:
                continue
            self.session.add(
                Skill(
                    name=preset["name"],
                    slug=preset["slug"],
                    type=preset["type"],
                    description=preset["description"],
                    icon=preset["icon"],
                    config=preset["config"],
                    enabled=preset["enabled"],
                    is_builtin=True,
                    visible_to_users=True,
                    sort_order=preset["sort_order"],
                )
            )
            created += 1
        if created:
            await self.session.flush()
            logger.info("初始化内置技能 %s 个", created)
