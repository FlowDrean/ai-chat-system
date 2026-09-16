"""统一响应结构。

所有接口返回 `{"code": 0, "message": "success", "data": ...}`。
这里提供 `ok()` / `fail()` 以及分页数据的封装，避免每个路由重复拼装。
"""

from __future__ import annotations

from math import ceil
from typing import Any, Generic, Sequence, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class PageMeta(BaseModel):
    page: int
    page_size: int
    total: int
    total_pages: int


class PageData(BaseModel, Generic[T]):
    items: list[T] = Field(default_factory=list)
    meta: PageMeta


class Envelope(BaseModel, Generic[T]):
    """统一响应包装（可直接用于 FastAPI `response_model`）。"""

    code: int = 0
    message: str = "success"
    data: T | None = None


class ListEnvelope(BaseModel, Generic[T]):
    """分页响应包装。"""

    code: int = 0
    message: str = "success"
    data: PageData[T] | None = None


class OkEnvelope(BaseModel):
    """data 为任意结构的响应（例如统计结果）。"""

    code: int = 0
    message: str = "success"
    data: dict | None = None


def ok(data: Any = None, message: str = "success") -> dict[str, Any]:
    """成功响应。"""
    return {"code": 0, "message": message, "data": data}


def fail(code: int, message: str, data: Any = None) -> dict[str, Any]:
    """失败响应（一般由 AppError + 全局异常处理器完成，这里用于流式等特殊场景）。"""
    return {"code": code, "message": message, "data": data}


def page(items: Sequence[Any], total: int, page_no: int, page_size: int) -> dict[str, Any]:
    """分页数据体。"""
    return {
        "items": list(items),
        "meta": {
            "page": page_no,
            "page_size": page_size,
            "total": total,
            "total_pages": ceil(total / page_size) if page_size else 0,
        },
    }
