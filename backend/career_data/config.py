"""Paths and conservative network defaults for career data."""

from __future__ import annotations

import os
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent
DATA_ROOT = Path(os.getenv("CAREER_DATA_ROOT", BACKEND_ROOT / "data" / "career_data"))
RAW_ROOT = DATA_ROOT / "raw"
DEFAULT_DATABASE_URL = os.getenv(
    "CAREER_DATA_DATABASE_URL", f"sqlite:///{(DATA_ROOT / 'career_data.db').as_posix()}"
)
HTTP_TIMEOUT_SECONDS = 30.0
HTTP_MAX_RETRIES = 2
HTTP_USER_AGENT = "iCampus-career-data/1.0 (public-data research; low-frequency)"


def ensure_data_directories() -> None:
    DATA_ROOT.mkdir(parents=True, exist_ok=True)
    RAW_ROOT.mkdir(parents=True, exist_ok=True)
