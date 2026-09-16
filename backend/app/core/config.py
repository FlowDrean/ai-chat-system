"""全局配置。

所有可配置项均通过环境变量 / `.env` 文件注入，代码里不出现任何硬编码密钥。
参见 `backend/.env.example`。
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# .../backend
BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """应用配置（env 变量名与字段名大小写不敏感地一一对应）。"""

    model_config = SettingsConfigDict(
        env_file=str(BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ------------------------------------------------------------------ 应用
    app_name: str = "AI Chat Assistant"
    app_version: str = "1.0.0"
    app_env: Literal["dev", "test", "prod"] = "dev"
    debug: bool = True
    host: str = "0.0.0.0"
    port: int = 8000
    api_prefix: str = "/api"

    # ------------------------------------------------------------------ 数据库
    # MySQL:  mysql+aiomysql://user:password@127.0.0.1:3306/ai_chat?charset=utf8mb4
    # SQLite: sqlite+aiosqlite:///./data/app.db   （本地开发默认，零依赖启动）
    database_url: str = "sqlite+aiosqlite:///./data/app.db"
    db_echo: bool = False
    db_pool_size: int = 10
    db_max_overflow: int = 20
    db_pool_recycle: int = 1800
    # 启动时自动 create_all（仅建议 SQLite / 开发环境使用）。
    # 使用 MySQL 的生产/长期环境请设为 false，并通过 `alembic upgrade head` 管理表结构。
    auto_create_tables: bool = True

    # ------------------------------------------------------------------ 安全
    secret_key: str = "please-change-me-with-openssl-rand-hex-32"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24 * 7
    # 留空时由 secret_key 派生（Fernet key）。生产环境请显式配置。
    api_key_encryption_key: str = ""
    password_min_length: int = 6

    # ------------------------------------------------------------------ CORS
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # ------------------------------------------------------------------ 文件存储
    storage_dir: str = "storage"
    upload_dir: str = "storage/uploads"
    max_upload_size_mb: int = 50
    allowed_extensions: str = ".pdf,.docx,.txt,.md,.markdown,.csv,.xlsx"

    # ------------------------------------------------------------------ 向量存储
    vector_store: Literal["sql", "chroma"] = "sql"
    vector_dir: str = "storage/vectors"
    default_embedding_provider: str = "local"
    default_embedding_model: str = "local-hash-512"
    embedding_dimension: int = 512
    embedding_batch_size: int = 32

    # ------------------------------------------------------------------ RAG 默认参数
    default_chunk_size: int = 800
    default_chunk_overlap: int = 120
    default_top_k: int = 4
    default_similarity_threshold: float = 0.2

    # ------------------------------------------------------------------ LLM
    llm_request_timeout: int = 180
    llm_max_retries: int = 2
    max_context_messages: int = 20
    max_context_chars: int = 24000
    # 首次启动时是否自动创建一个可直接使用的模型（mock 本地模型 / 或 .env 指定的真实模型）
    seed_default_model: bool = True
    default_provider: str = "mock"
    default_model_name: str = "mock-chat"
    default_base_url: str = ""
    default_api_key: str = ""

    # 首次启动创建的管理员账号（生产环境请务必修改）
    default_admin_username: str = "admin"
    default_admin_password: str = "admin123456"
    default_admin_email: str = ""

    # ------------------------------------------------------------------ 日志
    log_level: str = "INFO"
    log_dir: str = "logs"
    log_to_file: bool = True
    log_sql: bool = False

    # ------------------------------------------------------------------ 派生属性
    @field_validator("database_url")
    @classmethod
    def _normalize_sqlite_path(cls, v: str) -> str:
        """把相对路径的 sqlite 文件锚定到 backend/ 目录，避免受启动目录影响。"""
        prefix = "sqlite+aiosqlite:///"
        if v.startswith(prefix):
            raw = v[len(prefix) :]
            if raw and not raw.startswith(":memory:") and not Path(raw).is_absolute():
                abs_path = (BACKEND_DIR / raw).resolve()
                abs_path.parent.mkdir(parents=True, exist_ok=True)
                return f"{prefix}{abs_path.as_posix()}"
        return v

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def allowed_extension_set(self) -> set[str]:
        return {e.strip().lower() for e in self.allowed_extensions.split(",") if e.strip()}

    @property
    def upload_path(self) -> Path:
        p = Path(self.upload_dir)
        return p if p.is_absolute() else (BACKEND_DIR / p)

    @property
    def vector_path(self) -> Path:
        p = Path(self.vector_dir)
        return p if p.is_absolute() else (BACKEND_DIR / p)

    @property
    def log_path(self) -> Path:
        p = Path(self.log_dir)
        return p if p.is_absolute() else (BACKEND_DIR / p)

    @property
    def max_upload_size(self) -> int:
        return self.max_upload_size_mb * 1024 * 1024

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    def ensure_directories(self) -> None:
        for path in (self.upload_path, self.vector_path, self.log_path):
            path.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
