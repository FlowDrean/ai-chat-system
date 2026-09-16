"""技能注册表：类型 → 规格 / 执行器 / LangChain Tool。

这里是「技能」与业务代码之间唯一的耦合点：
* 管理后台通过 `list_specs()` 渲染动态配置表单；
* 聊天时通过 `build_tools()` 把用户启用的技能变成模型可调用的工具；
* 新增技能类型只需实现 `BaseSkill` 子类并加入 `BUILTIN_SKILLS`。
"""

from __future__ import annotations

import json
import re
from typing import Any

from langchain_core.tools import BaseTool, StructuredTool
from pydantic import BaseModel, Field, create_model

from app.core.logging import get_logger
from app.skills.base import BaseSkill, SkillArg, SkillError, SkillSpec
from app.skills.builtin import BUILTIN_SKILLS

logger = get_logger(__name__)

# 技能类型 -> 执行器类
SKILL_TYPES: dict[str, type[BaseSkill]] = {cls.spec.type: cls for cls in BUILTIN_SKILLS}

_ARG_PY_TYPES: dict[str, type] = {
    "string": str,
    "number": float,
    "integer": int,
    "boolean": bool,
}

_NAME_SAFE = re.compile(r"[^a-zA-Z0-9_-]")


# --------------------------------------------------------------------------- #
# 规格查询
# --------------------------------------------------------------------------- #
def list_specs() -> list[dict[str, Any]]:
    return [SKILL_TYPES[key].spec.to_dict() for key in sorted(SKILL_TYPES)]


def get_spec(skill_type: str) -> SkillSpec:
    cls = SKILL_TYPES.get(skill_type)
    if cls is None:
        raise SkillError(f"未知的技能类型：{skill_type}")
    return cls.spec


def is_supported(skill_type: str) -> bool:
    return skill_type in SKILL_TYPES


# --------------------------------------------------------------------------- #
# 配置 / 入参工具
# --------------------------------------------------------------------------- #
def parse_args_schema(raw: Any) -> list[dict[str, Any]]:
    """解析自定义技能的入参定义（JSON）。

    支持两种写法：
      {"keyword": {"type": "string", "description": "查询词"}}
      {"keyword": "查询词"}          # 简写，等价于 string 类型
    """
    if raw in (None, "", {}):
        return []
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except ValueError as exc:
            raise SkillError("入参定义不是合法 JSON") from exc
    else:
        parsed = raw
    if not isinstance(parsed, dict):
        raise SkillError("入参定义必须是 JSON 对象")

    args: list[dict[str, Any]] = []
    for name, definition in parsed.items():
        if isinstance(definition, str):
            args.append({"name": str(name), "type": "string", "description": definition, "required": True})
            continue
        if not isinstance(definition, dict):
            raise SkillError(f"入参 {name} 的定义必须是对象或字符串")
        arg_type = str(definition.get("type", "string")).lower()
        if arg_type not in _ARG_PY_TYPES:
            raise SkillError(f"入参 {name} 的类型 {arg_type} 不支持（可选 string/number/integer/boolean）")
        args.append(
            {
                "name": str(name),
                "type": arg_type,
                "description": str(definition.get("description", "")),
                "required": bool(definition.get("required", True)),
                "default": definition.get("default"),
            }
        )
    return args


def build_args_model(skill_type: str, config: dict[str, Any] | None, tool_name: str) -> type[BaseModel]:
    """把技能入参规格转换成 pydantic 模型（LangChain Tool 的 args_schema）。"""
    spec = get_spec(skill_type)
    args: list[dict[str, Any]] = (
        parse_args_schema((config or {}).get("args_schema")) if spec.uses_dynamic_args else [a.to_dict() for a in spec.args]
    )

    fields: dict[str, Any] = {}
    for arg in args:
        if not arg.get("name"):
            continue
        py_type = _ARG_PY_TYPES.get(str(arg.get("type", "string")), str)
        description = str(arg.get("description") or arg["name"])
        if arg.get("required") is False:
            py_type = py_type | None  # type: ignore[operator]
            fields[str(arg["name"])] = (py_type, Field(default=arg.get("default"), description=description))
        else:
            fields[str(arg["name"])] = (py_type, Field(..., description=description))

    if not fields:  # 无入参的技能
        fields["_noop"] = (str | None, Field(default=None, description="无需参数"))

    model_name = f"SkillArgs_{_NAME_SAFE.sub('_', tool_name) or 'skill'}"
    return create_model(model_name, **fields)  # type: ignore[call-overload]


def tool_name_for(skill_slug: str, skill_id: int | None = None) -> str:
    """OpenAI 的 function name 只允许字母数字与 _-，这里做一次清洗。"""
    base = _NAME_SAFE.sub("_", (skill_slug or "").strip()) or "skill"
    base = base.strip("_") or "skill"
    if skill_id is not None:
        return f"{base[:48]}_{skill_id}"[:64]
    return base[:64]


# --------------------------------------------------------------------------- #
# 执行器与工具
# --------------------------------------------------------------------------- #
def create_skill(skill_type: str, config: dict[str, Any] | None = None) -> BaseSkill:
    cls = SKILL_TYPES.get(skill_type)
    if cls is None:
        raise SkillError(f"未知的技能类型：{skill_type}")
    return cls(config or {})


def validate_config(skill_type: str, config: dict[str, Any] | None) -> None:
    """保存技能时校验必填配置。"""
    spec = get_spec(skill_type)
    data = config or {}
    missing = [
        field.label or field.key
        for field in spec.fields
        if field.required and data.get(field.key) in (None, "")
    ]
    if missing:
        raise SkillError(f"缺少必填配置：{'、'.join(missing)}")
    if spec.uses_dynamic_args:
        parse_args_schema(data.get("args_schema"))


def build_tools(skills: list[Any]) -> list[BaseTool]:
    """把技能配置行（ORM 对象或 dict）转换成 LangChain Tools。"""
    tools: list[BaseTool] = []
    for skill in skills:
        try:
            tools.append(build_tool(skill))
        except Exception as exc:  # noqa: BLE001 - 单个技能不可用不应影响其它技能
            logger.warning("构建技能工具失败 skill=%s: %s", getattr(skill, "name", skill), exc)
    return tools


def build_tool(skill: Any) -> BaseTool:
    skill_type = _attr(skill, "type")
    if not is_supported(skill_type):
        raise SkillError(f"未知的技能类型：{skill_type}")

    config = _attr(skill, "config") or {}
    skill_id = _attr(skill, "id")
    name = _attr(skill, "name") or skill_type
    slug = _attr(skill, "slug") or skill_type
    executor = create_skill(skill_type, config)
    args_model = build_args_model(skill_type, config, slug)

    description = (_attr(skill, "description") or "").strip()
    if skill_type == "http_request" and (config.get("tool_description") or "").strip():
        description = str(config["tool_description"]).strip()
    if not description:
        description = get_spec(skill_type).description
    description = f"{description}\n（技能名称：{name}）"

    async def _run(**kwargs: Any) -> str:
        logger.info("技能调用 name=%s type=%s args=%s", name, skill_type, list(kwargs))
        return await executor.safe_run(**kwargs)

    return StructuredTool.from_function(
        coroutine=_run,
        name=tool_name_for(slug, skill_id if isinstance(skill_id, int) else None),
        description=description,
        args_schema=args_model,
    )


def _attr(obj: Any, key: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)
