"""日志配置。

日志格式包含：时间 / 级别 / 模块 / 请求 ID / 用户 ID / 内容。
并且会过滤掉 API Key、Authorization、密码等敏感信息（见 `_SENSITIVE_PATTERNS`）。
"""

from __future__ import annotations

import logging
import logging.handlers
import re
import sys
from contextvars import ContextVar
from typing import Any

from app.core.config import settings

# 请求上下文（由中间件写入，日志过滤器读取）
request_id_ctx: ContextVar[str] = ContextVar("request_id", default="-")
user_id_ctx: ContextVar[str] = ContextVar("user_id", default="-")

_LOG_FORMAT = "%(asctime)s | %(levelname)-7s | %(name)-28s | rid=%(request_id)s uid=%(user_id)s | %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# 命中以下模式的内容在落日志前会被脱敏
_SENSITIVE_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"(sk-[A-Za-z0-9_\-]{6})[A-Za-z0-9_\-]+"), r"\1***"),
    (re.compile(r"(?i)(api[_-]?key\"?\s*[:=]\s*\"?)([^\"\s,}]+)"), r"\1***"),
    (re.compile(r"(?i)(authorization\"?\s*[:=]\s*\"?)([^\"\s,}]+)"), r"\1***"),
    (re.compile(r"(?i)(password\"?\s*[:=]\s*\"?)([^\"\s,}]+)"), r"\1***"),
    (re.compile(r"(?i)bearer\s+[A-Za-z0-9._\-]+"), "Bearer ***"),
)


def mask_sensitive(text: str) -> str:
    for pattern, repl in _SENSITIVE_PATTERNS:
        text = pattern.sub(repl, text)
    return text


class ContextFilter(logging.Filter):
    """把 contextvar 中的请求上下文注入日志记录，并对敏感内容脱敏。

    注意：当 `record.args` 存在时必须保留 `record.msg` 的原始模板，
    否则 `msg % args` 会因为占位符被脱敏改写而抛 ValueError。
    """

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: A003
        record.request_id = request_id_ctx.get()
        record.user_id = user_id_ctx.get()
        if record.args:
            if isinstance(record.args, tuple):
                record.args = tuple(
                    mask_sensitive(a) if isinstance(a, str) else a for a in record.args
                )
            elif isinstance(record.args, dict):
                record.args = {
                    k: (mask_sensitive(v) if isinstance(v, str) else v) for k, v in record.args.items()
                }
        elif isinstance(record.msg, str):
            record.msg = mask_sensitive(record.msg)
        return True


class SensitiveFilter(logging.Filter):
    """兜底：对最终输出格式化后的字符串再次脱敏。"""

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: A003
        try:
            message = record.getMessage()
        except Exception:  # pragma: no cover - 极端情况下的格式化失败
            return True
        if mask_sensitive(message) != message:
            record.msg = mask_sensitive(message)
            record.args = ()
        return True


def setup_logging(level: str | None = None) -> None:
    """初始化 root logger（重复调用是幂等的）。"""
    log_level = (level or settings.log_level).upper()
    root = logging.getLogger()
    if getattr(root, "_ai_chat_configured", False):
        root.setLevel(log_level)
        return

    settings.log_path.mkdir(parents=True, exist_ok=True)

    formatter = logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT)
    context_filter = ContextFilter()
    sensitive_filter = SensitiveFilter()

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(formatter)
    console.addFilter(context_filter)
    console.addFilter(sensitive_filter)

    handlers: list[logging.Handler] = [console]

    if settings.log_to_file:
        file_handler = logging.handlers.RotatingFileHandler(
            settings.log_path / "app.log", maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8"
        )
        file_handler.setFormatter(formatter)
        file_handler.addFilter(context_filter)
        file_handler.addFilter(sensitive_filter)
        handlers.append(file_handler)

        error_handler = logging.handlers.RotatingFileHandler(
            settings.log_path / "error.log", maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8"
        )
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(formatter)
        error_handler.addFilter(context_filter)
        error_handler.addFilter(sensitive_filter)
        handlers.append(error_handler)

    root.handlers.clear()
    root.setLevel(log_level)
    for handler in handlers:
        root.addHandler(handler)

    # 第三方库降噪
    for noisy in ("httpx", "httpcore", "urllib3", "aiosqlite", "asyncio", "openai", "urllib3.connectionpool"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    if not settings.log_sql:
        logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.pool").setLevel(logging.WARNING)

    root._ai_chat_configured = True  # type: ignore[attr-defined]


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


def log_extra(**kwargs: Any) -> dict[str, Any]:
    """保留扩展位：附加结构化字段。"""
    return kwargs
