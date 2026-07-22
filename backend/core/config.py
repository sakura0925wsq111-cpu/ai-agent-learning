"""Centralized configuration using Pydantic Settings.

Reads from .env file and environment variables.
Values are validated at startup — if something is missing, the app won't start.
"""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


# ── Project paths ──────────────────────────────────────────────
# backend/core/config.py  →  backend/  →  project root
PROJECT_ROOT = Path(__file__).resolve().parent.parent  # backend/


class Settings(BaseSettings):
    """Application settings loaded from .env and environment variables."""

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # ── App ──
    app_name: str = "CampusPal"
    app_version: str = "0.1.0"
    debug: bool = False

    # ── Server ──
    host: str = "127.0.0.1"
    port: int = 8000

    # ── Database ──
    database_url: str = "sqlite:///./data/campuspal.db"

    # ── LLM ──
    llm_api_key: str = ""
    llm_base_url: str = "https://api.deepseek.com"
    llm_model: str = "deepseek-chat"

    # ── Logging ──
    log_level: str = "DEBUG"
    log_dir: str = "logs"
    log_rotation: str = "10 MB"
    log_retention: str = "7 days"

    # ── Memory ──
    memory_max_per_user: int = 50


# Singleton — import this everywhere
settings = Settings()
