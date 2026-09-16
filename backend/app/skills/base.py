"""技能规格与执行器基类。

一个「技能」由三部分组成：

1. **配置（config）**：存在 `skills.config` 里的 JSON，例如联网搜索的 API Key、
   HTTP 技能的 URL / 请求头。由 `SkillSpec.fields` 描述，前端据此渲染动态表单。
2. **入参（args）**：大模型调用技能时传的参数，由 `SkillSpec.args` 描述，
   会被转换成 pydantic 模型作为 LangChain Tool 的 `args_schema`。
3. **执行（run）**：`BaseSkill.run(**kwargs) -> str`，返回值会作为工具结果回喂给模型。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Literal

FieldType = Literal["string", "password", "text", "number", "integer", "boolean", "json", "select"]
ArgType = Literal["string", "number", "integer", "boolean"]


class SkillError(Exception):
    """技能执行异常（会被转换为工具错误信息返回给模型）。"""


@dataclass(slots=True)
class SkillField:
    """技能的一项配置（前端动态表单字段）。"""

    key: str
    label: str
    type: FieldType = "string"
    required: bool = False
    default: Any = None
    placeholder: str = ""
    help: str = ""
    options: list[dict[str, str]] = field(default_factory=list)
    secret: bool = False
    """敏感配置（如 API Key）：出参脱敏、日志不打印。"""

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "label": self.label,
            "type": self.type,
            "required": self.required,
            "default": self.default,
            "placeholder": self.placeholder,
            "help": self.help,
            "options": self.options,
            "secret": self.secret,
        }


@dataclass(slots=True)
class SkillArg:
    """大模型调用技能时的一个入参（用于生成 Tool 的 args_schema）。"""

    name: str
    type: ArgType = "string"
    description: str = ""
    required: bool = True
    default: Any = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "type": self.type,
            "description": self.description,
            "required": self.required,
            "default": self.default,
        }


@dataclass(slots=True)
class SkillSpec:
    """技能类型规格（同一种类型可以被实例化出多个技能）。"""

    type: str
    name: str
    description: str
    """默认用途说明，会作为工具描述告诉模型「什么时候该用它」。"""
    icon: str = "ApiOutlined"
    category: str = "general"
    fields: list[SkillField] = field(default_factory=list)
    args: list[SkillArg] = field(default_factory=list)
    uses_dynamic_args: bool = False
    """为 True 时入参来自配置里的 `args_schema`（用于自定义 HTTP 技能）。"""
    configurable: bool = True
    """是否允许用户新建该类型的技能（内置能力也可以新建多份，例如多个 HTTP 接口）。"""

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "name": self.name,
            "description": self.description,
            "icon": self.icon,
            "category": self.category,
            "fields": [f.to_dict() for f in self.fields],
            "args": [a.to_dict() for a in self.args],
            "uses_dynamic_args": self.uses_dynamic_args,
            "configurable": self.configurable,
        }


class BaseSkill(ABC):
    """技能执行器基类。

    子类只需实现 `run()`；`spec` 描述这个技能的类型规格。
    构造函数拿到的 `config` 是用户在「技能管理」里保存的配置字典。
    """

    spec: SkillSpec

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self.config: dict[str, Any] = dict(config or {})

    # ------------------------------------------------------------------ #
    # 配置工具
    # ------------------------------------------------------------------ #
    def cfg(self, key: str, default: Any = None) -> Any:
        value = self.config.get(key)
        return default if value in (None, "") else value

    def cfg_int(self, key: str, default: int) -> int:
        try:
            return int(self.cfg(key, default))
        except (TypeError, ValueError):
            return default

    def cfg_float(self, key: str, default: float) -> float:
        try:
            return float(self.cfg(key, default))
        except (TypeError, ValueError):
            return default

    def cfg_bool(self, key: str, default: bool = False) -> bool:
        value = self.cfg(key, default)
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in {"1", "true", "yes", "on"}

    def require(self, key: str, label: str | None = None) -> str:
        """必填配置校验：缺失时抛出可读错误（而不是 500）。"""
        value = self.cfg(key)
        if value in (None, ""):
            raise SkillError(f"技能「{self.spec.name}」缺少必填配置：{label or key}")
        return str(value)

    # ------------------------------------------------------------------ #
    # 执行
    # ------------------------------------------------------------------ #
    @abstractmethod
    async def run(self, **kwargs: Any) -> str:
        """执行技能，返回给模型的文本结果。"""

    async def safe_run(self, **kwargs: Any) -> str:
        """包装执行过程：把异常转成模型可理解的错误文本，避免中断整轮对话。"""
        try:
            return await self.run(**kwargs)
        except SkillError as exc:
            return f"[技能执行失败] {exc}"
        except Exception as exc:  # noqa: BLE001
            return f"[技能执行失败] {type(exc).__name__}: {exc}"

    # ------------------------------------------------------------------ #
    def test_arguments(self) -> dict[str, Any]:
        """「试运行」按钮用的默认入参（可由子类覆盖）。"""
        return {arg.name: (arg.default if arg.default is not None else "") for arg in self.spec.args}
