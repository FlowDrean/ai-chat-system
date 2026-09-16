"""安全工具：密码哈希、JWT、API Key 加密与脱敏。

设计要点：
* 密码使用 PBKDF2-HMAC-SHA256（标准库实现，无第三方兼容性风险），
  同时兼容校验 `$2b$` 开头的 bcrypt 历史哈希。
* JWT 使用 HS256 + `SECRET_KEY`。
* 模型 API Key 在数据库中 **加密存储**（Fernet / AES-128-CBC + HMAC），
  接口返回时统一调用 `mask_secret()` 脱敏。
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings
from app.core.exceptions import TokenExpiredError, TokenInvalidError
from app.core.logging import get_logger

logger = get_logger(__name__)

_PBKDF2_ITERATIONS = 260_000
_PBKDF2_ALGORITHM = "pbkdf2_sha256"


# --------------------------------------------------------------------------- #
# 密码
# --------------------------------------------------------------------------- #
def hash_password(password: str) -> str:
    """使用 PBKDF2-HMAC-SHA256 生成密码哈希。"""
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _PBKDF2_ITERATIONS)
    return "${}${}${}${}".format(
        _PBKDF2_ALGORITHM,
        _PBKDF2_ITERATIONS,
        base64.b64encode(salt).decode(),
        base64.b64encode(digest).decode(),
    )


def _verify_pbkdf2(password: str, hashed: str) -> bool:
    try:
        _, algorithm, iterations, salt_b64, digest_b64 = hashed.split("$")
        if algorithm != _PBKDF2_ALGORITHM:
            return False
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(digest_b64)
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, int(iterations))
        return hmac.compare_digest(expected, actual)
    except Exception:  # noqa: BLE001
        return False


def verify_password(password: str, hashed: str | None) -> bool:
    if not hashed:
        return False
    if hashed.startswith("$pbkdf2"):
        return _verify_pbkdf2(password, hashed)
    if hashed.startswith(("$2a$", "$2b$", "$2y$")):
        try:  # 可选依赖：如果安装了 bcrypt 则兼容旧数据
            import bcrypt  # type: ignore

            return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
        except Exception:  # noqa: BLE001
            logger.warning("检测到 bcrypt 哈希但未安装 bcrypt，无法校验")
            return False
    return False


# --------------------------------------------------------------------------- #
# JWT
# --------------------------------------------------------------------------- #
def create_access_token(
    subject: str | int,
    *,
    expires_minutes: int | None = None,
    extra: dict[str, Any] | None = None,
) -> str:
    expires_delta = timedelta(minutes=expires_minutes or settings.access_token_expire_minutes)
    now = datetime.now(tz=timezone.utc)
    payload: dict[str, Any] = {
        "sub": str(subject),
        "iat": int(now.timestamp()),
        "exp": int((now + expires_delta).timestamp()),
        "type": "access",
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict[str, Any]:
    try:
        return jwt.decode(token, settings.secret_key, algorithms=[settings.jwt_algorithm])
    except jwt.ExpiredSignatureError as exc:
        raise TokenExpiredError() from exc
    except jwt.PyJWTError as exc:
        raise TokenInvalidError() from exc


# --------------------------------------------------------------------------- #
# API Key 加密 / 脱敏
# --------------------------------------------------------------------------- #
def _fernet() -> Fernet:
    key = settings.api_key_encryption_key.strip()
    if not key:
        # 由 SECRET_KEY 派生一个稳定的 Fernet key（生产环境建议显式配置）
        digest = hashlib.sha256(settings.secret_key.encode("utf-8")).digest()
        key = base64.urlsafe_b64encode(digest).decode()
    return Fernet(key.encode("utf-8") if isinstance(key, str) else key)


def encrypt_secret(plain: str | None) -> str | None:
    """加密 API Key 等敏感字段。"""
    if not plain:
        return None
    return _fernet().encrypt(plain.encode("utf-8")).decode("utf-8")


def decrypt_secret(cipher: str | None) -> str | None:
    """解密；兼容历史明文数据（解密失败时按明文返回，并给出告警）。"""
    if not cipher:
        return None
    try:
        return _fernet().decrypt(cipher.encode("utf-8")).decode("utf-8")
    except (InvalidToken, ValueError):
        logger.warning("API Key 解密失败，按明文处理（建议重新保存模型配置以完成加密）")
        return cipher


def mask_secret(plain: str | None, *, head: int = 4, tail: int = 4) -> str | None:
    """脱敏展示：`sk-a**********1234`。"""
    if not plain:
        return None
    if len(plain) <= head + tail:
        return "*" * len(plain)
    return f"{plain[:head]}{'*' * 8}{plain[-tail:]}"


def mask_stored_secret(cipher: str | None) -> str | None:
    """对数据库中的密文做脱敏展示（无需先解密再回传明文）。"""
    if not cipher:
        return None
    return "••••••••" + (cipher[-6:] if len(cipher) >= 6 else "")


def generate_secret_key() -> str:
    return secrets.token_hex(32)


__all__ = [
    "create_access_token",
    "decode_access_token",
    "decrypt_secret",
    "encrypt_secret",
    "generate_secret_key",
    "hash_password",
    "mask_secret",
    "mask_stored_secret",
    "verify_password",
]
