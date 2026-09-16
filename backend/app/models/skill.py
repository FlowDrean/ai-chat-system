"""技能（Skills）模型。

一个技能 = 一种能力的**一份配置实例**。例如 `http_request` 类型可以创建多个技能：
「公司员工查询」「订单查询接口」…… 每个都有自己的 URL / 请求头 / 入参定义。

* 系统预置技能（`is_builtin=True`）由 seed 写入，可编辑配置、可禁用，但不允许删除；
* 自定义技能可由管理员自由增删；
* `visible_to_users` 控制是否在聊天页的技能选择器里出现。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import BigIntFK, Base, LongText, PKMixin, TimestampMixin


class Skill(Base, PKMixin, TimestampMixin):
    __tablename__ = "skills"

    name: Mapped[str] = mapped_column(String(64), comment="技能名称（展示名）")
    slug: Mapped[str] = mapped_column(String(64), unique=True, index=True, comment="唯一标识，用作工具名")
    type: Mapped[str] = mapped_column(String(32), index=True, comment="技能类型，见 app/skills/registry.py")
    description: Mapped[str | None] = mapped_column(
        LongText, default=None, comment="用途说明（会作为工具描述告诉模型何时调用）"
    )
    icon: Mapped[str | None] = mapped_column(String(64), default=None, comment="前端图标名")
    config: Mapped[dict | None] = mapped_column(JSON, default=None, comment="技能配置（敏感项加密/脱敏输出）")

    enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True, comment="是否启用")
    is_builtin: Mapped[bool] = mapped_column(Boolean, default=False, comment="系统预置，不可删除")
    visible_to_users: Mapped[bool] = mapped_column(
        Boolean, default=True, comment="是否允许在聊天页选择使用"
    )
    sort_order: Mapped[int] = mapped_column(Integer, default=0, comment="排序")

    usage_count: Mapped[int] = mapped_column(Integer, default=0, comment="累计调用次数")
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime, default=None, comment="最近调用时间")
    created_by: Mapped[int | None] = mapped_column(BigIntFK, default=None)

    # ------------------------------------------------------------------ #
    def tool_name(self) -> str:
        from app.skills.registry import tool_name_for

        return tool_name_for(self.slug, self.id)
