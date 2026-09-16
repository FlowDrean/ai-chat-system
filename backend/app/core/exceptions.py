"""统一异常体系 + 全局异常处理器。

约定：所有接口返回
    { "code": 0, "message": "success", "data": {...} }
失败：
    { "code": 40001, "message": "模型连接失败", "data": null }

任何情况下都**不会**把 traceback / SQL / 文件路径 / API Key 返回给前端。
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logging import get_logger

logger = get_logger(__name__)


class ErrorCode:
    """业务错误码。"""

    SUCCESS = 0

    # 4xxxx 客户端错误
    BAD_REQUEST = 40000
    VALIDATION_ERROR = 40001
    UNAUTHORIZED = 40100
    TOKEN_EXPIRED = 40101
    TOKEN_INVALID = 40102
    PERMISSION_DENIED = 40300
    ACCOUNT_DISABLED = 40301
    NOT_FOUND = 40400
    CONFLICT = 40900

    # 5xxxx 服务端 / 依赖错误
    INTERNAL_ERROR = 50000
    CONFIGURATION_ERROR = 50001
    DATABASE_ERROR = 50002

    MODEL_CALL_FAILED = 50101
    MODEL_NOT_FOUND = 50102
    MODEL_DISABLED = 50103
    EMBEDDING_FAILED = 50104
    RETRIEVAL_FAILED = 50105

    FILE_TYPE_UNSUPPORTED = 50201
    FILE_TOO_LARGE = 50202
    FILE_PARSE_FAILED = 50203
    STORAGE_ERROR = 50204

    UPSTREAM_ERROR = 50301


class AppError(Exception):
    """业务异常基类。"""

    code: int = ErrorCode.INTERNAL_ERROR
    http_status: int = 400
    message: str = "请求处理失败"

    def __init__(self, message: str | None = None, *, code: int | None = None, data: Any = None) -> None:
        self.message = message or self.message
        if code is not None:
            self.code = code
        self.data = data
        super().__init__(self.message)

    def to_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, "data": self.data}


class BadRequestError(AppError):
    code = ErrorCode.BAD_REQUEST
    http_status = 400
    message = "请求参数不正确"


class ValidationError(BadRequestError):
    code = ErrorCode.VALIDATION_ERROR
    message = "参数校验失败"


class UnauthorizedError(AppError):
    code = ErrorCode.UNAUTHORIZED
    http_status = 401
    message = "请先登录"


class TokenExpiredError(UnauthorizedError):
    code = ErrorCode.TOKEN_EXPIRED
    message = "登录已过期，请重新登录"


class TokenInvalidError(UnauthorizedError):
    code = ErrorCode.TOKEN_INVALID
    message = "登录凭证无效"


class PermissionDeniedError(AppError):
    code = ErrorCode.PERMISSION_DENIED
    http_status = 403
    message = "没有操作权限"


class AccountDisabledError(AppError):
    code = ErrorCode.ACCOUNT_DISABLED
    http_status = 403
    message = "账号已被禁用"


class NotFoundError(AppError):
    code = ErrorCode.NOT_FOUND
    http_status = 404
    message = "资源不存在"


class ConflictError(AppError):
    code = ErrorCode.CONFLICT
    http_status = 409
    message = "资源已存在或状态冲突"


class ConfigurationError(AppError):
    code = ErrorCode.CONFIGURATION_ERROR
    http_status = 500
    message = "服务配置缺失或不正确"


class DatabaseError(AppError):
    code = ErrorCode.DATABASE_ERROR
    http_status = 500
    message = "数据库操作失败"


class ModelCallError(AppError):
    code = ErrorCode.MODEL_CALL_FAILED
    http_status = 502
    message = "模型调用失败，请检查模型配置或 API Key"


class ModelNotFoundError(NotFoundError):
    code = ErrorCode.MODEL_NOT_FOUND
    message = "模型不存在"


class ModelDisabledError(AppError):
    code = ErrorCode.MODEL_DISABLED
    http_status = 400
    message = "该模型已被禁用"


class EmbeddingError(AppError):
    code = ErrorCode.EMBEDDING_FAILED
    http_status = 502
    message = "Embedding 调用失败"


class RetrievalError(AppError):
    code = ErrorCode.RETRIEVAL_FAILED
    http_status = 502
    message = "知识库检索失败"


class FileTypeUnsupportedError(AppError):
    code = ErrorCode.FILE_TYPE_UNSUPPORTED
    http_status = 400
    message = "不支持的文件类型"


class FileTooLargeError(AppError):
    code = ErrorCode.FILE_TOO_LARGE
    http_status = 413  # HTTP_413_CONTENT_TOO_LARGE
    message = "文件大小超出限制"


class FileParseError(AppError):
    code = ErrorCode.FILE_PARSE_FAILED
    http_status = 400
    message = "文件解析失败"


class StorageError(AppError):
    code = ErrorCode.STORAGE_ERROR
    http_status = 500
    message = "文件存储失败"


class UpstreamError(AppError):
    code = ErrorCode.UPSTREAM_ERROR
    http_status = 502
    message = "上游服务调用失败"


# --------------------------------------------------------------------------- #
# 异常处理器注册
# --------------------------------------------------------------------------- #
def _payload(code: int, message: str, data: Any = None, *, request_id: str = "-") -> dict[str, Any]:
    return {"code": code, "message": message, "data": data, "request_id": request_id}


def _current_request_id() -> str:
    from app.core.logging import request_id_ctx

    return request_id_ctx.get()


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error_handler(request: Request, exc: AppError) -> JSONResponse:  # noqa: ARG001
        if exc.http_status >= 500:
            logger.error("业务异常 [%s] %s: %s", exc.code, request.url.path, exc.message, exc_info=False)
        else:
            logger.warning("业务异常 [%s] %s: %s", exc.code, request.url.path, exc.message)
        return JSONResponse(
            status_code=exc.http_status,
            content=_payload(exc.code, exc.message, exc.data, request_id=_current_request_id()),
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:  # noqa: ARG001
        first = exc.errors()[0] if exc.errors() else {}
        loc = ".".join(str(x) for x in first.get("loc", []) if x not in ("body", "query", "path"))
        message = f"参数校验失败：{loc} {first.get('msg', '')}".strip()
        logger.warning("参数校验失败 %s: %s", request.url.path, message)
        return JSONResponse(
            status_code=422,
            content=_payload(ErrorCode.VALIDATION_ERROR, message, None, request_id=_current_request_id()),
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:  # noqa: ARG001
        code_map = {401: ErrorCode.UNAUTHORIZED, 403: ErrorCode.PERMISSION_DENIED, 404: ErrorCode.NOT_FOUND}
        code = code_map.get(exc.status_code, ErrorCode.BAD_REQUEST)
        message = str(exc.detail) if exc.detail else "请求失败"
        return JSONResponse(
            status_code=exc.status_code,
            content=_payload(code, message, None, request_id=_current_request_id()),
        )

    @app.exception_handler(IntegrityError)
    async def _integrity_handler(request: Request, exc: IntegrityError) -> JSONResponse:  # noqa: ARG001
        logger.error("数据库约束冲突 %s: %s", request.url.path, exc.orig)
        return JSONResponse(
            status_code=409,
            content=_payload(ErrorCode.CONFLICT, "数据已存在或违反唯一约束", None, request_id=_current_request_id()),
        )

    @app.exception_handler(SQLAlchemyError)
    async def _sqlalchemy_handler(request: Request, exc: SQLAlchemyError) -> JSONResponse:  # noqa: ARG001
        logger.exception("数据库错误 %s: %s", request.url.path, exc)
        return JSONResponse(
            status_code=500,
            content=_payload(ErrorCode.DATABASE_ERROR, "数据库操作失败", None, request_id=_current_request_id()),
        )

    @app.exception_handler(Exception)
    async def _unhandled_handler(request: Request, exc: Exception) -> JSONResponse:  # noqa: ARG001
        logger.exception("未捕获异常 %s: %s", request.url.path, exc)
        # 生产环境绝不返回 traceback
        return JSONResponse(
            status_code=500,
            content=_payload(ErrorCode.INTERNAL_ERROR, "服务器内部错误，请稍后重试", None, request_id=_current_request_id()),
        )
