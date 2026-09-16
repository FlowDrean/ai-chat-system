"""HTTP 中间件：请求 ID 注入 + 访问日志 + 耗时统计。"""

from __future__ import annotations

import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from app.core.logging import get_logger, request_id_ctx, user_id_ctx

logger = get_logger("app.access")


class RequestContextMiddleware(BaseHTTPMiddleware):
    """为每个请求生成 request_id，写入 contextvar，供日志与响应头使用。"""

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:16]
        token_rid = request_id_ctx.set(request_id)
        token_uid = user_id_ctx.set(request.headers.get("X-User-ID", "-"))
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            elapsed = (time.perf_counter() - started) * 1000
            logger.exception("请求异常 %s %s (%.1fms)", request.method, request.url.path, elapsed)
            raise
        else:
            elapsed = (time.perf_counter() - started) * 1000
            response.headers["X-Request-ID"] = request_id
            response.headers["X-Process-Time"] = f"{elapsed:.1f}ms"
            if not request.url.path.startswith(("/api/chat/stream", "/docs", "/openapi")):
                logger.info(
                    "%s %s -> %s (%.1fms)",
                    request.method,
                    request.url.path,
                    response.status_code,
                    elapsed,
                )
            return response
        finally:
            request_id_ctx.reset(token_rid)
            user_id_ctx.reset(token_uid)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """补充基础安全响应头。"""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        return response
