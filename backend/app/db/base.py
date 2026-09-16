"""SQLAlchemy 2.x 声明式基类与公共 Mixin。

* 所有主键使用 BIGINT（SQLite 下降级为 INTEGER 以支持自增）。
* 所有业务表统一带有 `created_at` / `updated_at`。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Integer, Text, func
from sqlalchemy.dialects.mysql import MEDIUMTEXT
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# 大文本字段：SQLite 用 TEXT，MySQL 用 MEDIUMTEXT（16MB）。
# 原因：MySQL 的 TEXT 只有 64KB，而 utf8mb4 下 32000 个汉字约 96KB，
# 在 STRICT_TRANS_TABLES 模式下会直接报错；MEDIUMTEXT 可彻底避免该问题。
LongText = Text().with_variant(MEDIUMTEXT, "mysql")

# MySQL 用 BIGINT，SQLite 用 INTEGER（SQLite 只有 INTEGER PRIMARY KEY 才自增）
BigIntPK = BigInteger().with_variant(Integer, "sqlite")
BigIntFK = BigInteger().with_variant(Integer, "sqlite")


class Base(DeclarativeBase):
    """所有 ORM 模型的基类。"""

    def to_dict(self, exclude: set[str] | None = None) -> dict:
        exclude = exclude or set()
        return {c.name: getattr(self, c.name) for c in self.__table__.columns if c.name not in exclude}

    def __repr__(self) -> str:  # pragma: no cover - 调试用
        pk = getattr(self, "id", None)
        return f"<{self.__class__.__name__} id={pk}>"


class PKMixin:
    """自增主键。"""

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True, comment="主键")


class TimestampMixin:
    """创建 / 更新时间。

    注意：`updated_at` 必须使用 **Python 端** 的 `default` / `onupdate`。
    如果只写成 `onupdate=func.now()`（纯服务端表达式），SQLAlchemy 在 UPDATE 之后
    会把该属性标记为 expired，异步场景下随后访问它会触发同步懒加载，
    抛出 `MissingGreenlet`。Python 端回调可以彻底避免这个问题。
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.now,
        server_default=func.now(),
        nullable=False,
        comment="创建时间",
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.now,
        onupdate=datetime.now,
        server_default=func.now(),
        nullable=False,
        comment="更新时间",
    )
