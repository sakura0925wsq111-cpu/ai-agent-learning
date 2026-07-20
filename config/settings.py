"""Centralized configuration loaded from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

# Project root: ai-agent-learning/
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Load .env from project root (does nothing harmful if file is missing).
load_dotenv(PROJECT_ROOT / ".env")


@dataclass(frozen=True)
class Settings:
    """Runtime settings for LLM and data paths."""

    deepseek_api_key: str
    deepseek_base_url: str
    deepseek_model: str
    data_dir: Path

    @classmethod
    def from_env(cls) -> Settings:
        api_key = os.getenv("DEEPSEEK_API_KEY", "").strip()
        if not api_key:
            raise ValueError(
                "DEEPSEEK_API_KEY is not set. "
                "Copy .env.example to .env and add your API key."
            )

        return cls(
            deepseek_api_key=api_key,
            deepseek_base_url=os.getenv(
                "DEEPSEEK_BASE_URL", "https://api.deepseek.com"
            ).strip(),
            deepseek_model=os.getenv("DEEPSEEK_MODEL", "deepseek-chat").strip(),
            data_dir=PROJECT_ROOT / "data",
        )


@lru_cache
def get_settings() -> Settings:
    """Return cached settings instance."""
    return Settings.from_env()
