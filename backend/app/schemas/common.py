"""Schema 公共基类与分页结构。"""

from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class BaseSchema(BaseModel):
    """所有出入参 Schema 的基类。

    * `from_attributes=True`：支持直接从 ORM 对象转换。
    * `protected_namespaces=()`：允许 `model_name` / `model_id` 等字段名（避免 pydantic 警告）。
    """

    model_config = ConfigDict(from_attributes=True, protected_namespaces=(), populate_by_name=True)


class PageQuery(BaseSchema):
    page: int = Field(default=1, ge=1, description="页码，从 1 开始")
    page_size: int = Field(default=20, ge=1, le=200, description="每页条数")

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


class PageResult(BaseSchema, Generic[T]):
    items: list[T] = Field(default_factory=list)
    total: int = 0
    page: int = 1
    page_size: int = 20
    total_pages: int = 0


class IdResponse(BaseSchema):
    id: int


class MessageResponse(BaseSchema):
    message: str = "success"


class OptionItem(BaseSchema):
    value: str
    label: str
    description: str | None = None
    meta: dict | None = None
