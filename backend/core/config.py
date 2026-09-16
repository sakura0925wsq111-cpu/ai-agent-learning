"""Typed application configuration for development, test, and production."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parent.parent
_DEV_SECRET = "icampus-dev-secret-change-in-production"


class Settings(BaseSettings):
    """Load settings from ``backend/.env`` and process environment variables."""

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "iCampus"
    app_version: str = "0.2.0"
    app_env: Literal["dev", "test", "prod"] = "dev"
    debug: bool = False

    host: str = "127.0.0.1"
    port: int = 8000

    database_url: str = "sqlite:///./data/icampus.db"
    redis_url: str = ""
    redis_socket_timeout_seconds: float = 1.0
    rate_limit_key_prefix: str = "icampus"

    jwt_secret_key: str = _DEV_SECRET
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 1440

    llm_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("DEEPSEEK_API_KEY", "LLM_API_KEY"),
    )
    llm_base_url: str = "https://api.deepseek.com"
    llm_model: str = "deepseek-chat"
    llm_timeout: float = 30.0
    # Hidden SDK retries bypass per-provider-call accounting; retry explicitly
    # through LLMService so every attempt acquires a fresh quota lease.
    llm_max_retries: int = 0

    # Comma-separated origins. An empty value disables browser CORS.
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    login_rate_limit: int = 10
    login_rate_window_seconds: int = 300
    registration_enabled: bool = True
    registration_rate_limit: int = 5
    registration_rate_window_seconds: int = 60 * 60
    registration_global_daily_limit: int = 200
    ai_daily_limit: int = 50
    ai_ip_daily_limit: int = 250
    ai_device_daily_limit: int = 100
    ai_global_daily_limit: int = 2000
    ai_global_concurrency_limit: int = 8
    ai_concurrency_lease_seconds: int = 120
    ai_enabled: bool = True
    upload_max_bytes: int = 10 * 1024 * 1024
    upload_rate_limit: int = 10
    upload_rate_window_seconds: int = 10 * 60
    upload_pdf_max_pages: int = 50
    upload_excel_max_rows: int = 2000
    upload_excel_max_columns: int = 100
    upload_xlsx_max_entries: int = 1000
    upload_xlsx_max_uncompressed_bytes: int = 50 * 1024 * 1024
    upload_xlsx_max_entry_bytes: int = 10 * 1024 * 1024
    upload_xlsx_max_compression_ratio: float = 100.0
    upload_max_extracted_chars: int = 200_000
    upload_parser_timeout_seconds: float = 15.0
    upload_parser_workers: int = 2
    import_preview_ttl_seconds: int = 30 * 60
    demo_account_enabled: bool = True
    demo_student_id: str = "demo2026"
    demo_password: str = "DemoPass123!"

    log_level: str = "INFO"
    log_dir: str = "logs"
    log_rotation: str = "10 MB"
    log_retention: str = "7 days"
    memory_max_per_user: int = 50

    @property
    def cors_allowed_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def is_production(self) -> bool:
        return self.app_env == "prod"

    @model_validator(mode="after")
    def validate_environment(self) -> "Settings":
        if self.is_production:
            if not self.database_url.startswith("postgresql"):
                raise ValueError("prod requires a PostgreSQL DATABASE_URL")
            if not self.redis_url.startswith(("redis://", "rediss://")):
                raise ValueError("prod requires a Redis REDIS_URL")
            if not self.jwt_secret_key or self.jwt_secret_key == _DEV_SECRET or len(self.jwt_secret_key) < 32:
                raise ValueError("prod requires JWT_SECRET_KEY with at least 32 non-default characters")
            if not self.llm_api_key:
                raise ValueError("prod requires DEEPSEEK_API_KEY (or legacy LLM_API_KEY)")
            if self.llm_max_retries != 0:
                raise ValueError("prod requires LLM_MAX_RETRIES=0 so every provider attempt is quota charged")
            if self.debug:
                raise ValueError("DEBUG must be false in prod")
            if not self.cors_allowed_origins or "*" in self.cors_allowed_origins:
                raise ValueError("prod requires an explicit CORS_ORIGINS whitelist")
            if self.demo_account_enabled:
                raise ValueError("DEMO_ACCOUNT_ENABLED must be false in prod")
            positive_limits = {
                "AI_DAILY_LIMIT": self.ai_daily_limit,
                "AI_IP_DAILY_LIMIT": self.ai_ip_daily_limit,
                "AI_DEVICE_DAILY_LIMIT": self.ai_device_daily_limit,
                "AI_GLOBAL_DAILY_LIMIT": self.ai_global_daily_limit,
                "AI_GLOBAL_CONCURRENCY_LIMIT": self.ai_global_concurrency_limit,
                "REGISTRATION_RATE_LIMIT": self.registration_rate_limit,
                "REGISTRATION_GLOBAL_DAILY_LIMIT": self.registration_global_daily_limit,
                "UPLOAD_RATE_LIMIT": self.upload_rate_limit,
            }
            invalid = [name for name, value in positive_limits.items() if value <= 0]
            if invalid:
                raise ValueError("prod requires positive safety limits: " + ", ".join(invalid))
        return self


settings = Settings()
