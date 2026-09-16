"""技能（Skills）：让大模型可以调用外部能力的统一抽象。

    app/skills/base.py      技能规格（配置项 / 入参）与执行器基类
    app/skills/builtin.py   内置技能实现（计算器 / 时间 / 网页抓取 / 联网搜索 / 自定义 HTTP）
    app/skills/registry.py  类型注册表：规格查询、执行器创建、LangChain Tool 构建

前端「技能管理」页面的动态表单由 `SkillSpec.fields` 驱动，
聊天时的 tool-calling 由 `build_tools()` 生成的 LangChain Tool 驱动。
新增一种技能 = 写一个 `BaseSkill` 子类 + 在 `registry.BUILTIN_SKILLS` 注册，其它代码无需改动。
"""

from app.skills.base import BaseSkill, SkillArg, SkillField, SkillSpec

__all__ = ["BaseSkill", "SkillArg", "SkillField", "SkillSpec"]
