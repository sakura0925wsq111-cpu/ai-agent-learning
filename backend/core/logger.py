"""Logging setup with Loguru.

Provides:
- Console logging (colored, for development)
- File logging (rotated, for production debugging)
- Error-only file logging (for alerting)
"""

import sys
from pathlib import Path

from loguru import logger

from core.config import PROJECT_ROOT, settings


def setup_logging() -> None:
    """Configure Loguru with console and file sinks.

    Called once at application startup.
    Existing handlers are removed first to avoid duplicates on hot-reload.
    """
    logger.remove()  # Remove default handler

    log_dir = PROJECT_ROOT / settings.log_dir
    log_dir.mkdir(parents=True, exist_ok=True)

    # ── Console: human-readable, colored ──
    logger.add(
        sys.stderr,
        level=settings.log_level,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
            "<level>{message}</level>"
        ),
        colorize=True,
    )

    # ── File: all logs, rotated ──
    logger.add(
        log_dir / "app_{time:YYYY-MM-DD}.log",
        level="DEBUG",
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} | {message}",
        rotation=settings.log_rotation,
        retention=settings.log_retention,
        encoding="utf-8",
    )

    # ── File: errors only ──
    logger.add(
        log_dir / "error_{time:YYYY-MM-DD}.log",
        level="ERROR",
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} | {message}",
        rotation=settings.log_rotation,
        retention=settings.log_retention,
        encoding="utf-8",
    )

    logger.info(f"Logging initialized. level={settings.log_level}, dir={log_dir}")


# Re-export logger for convenience:  from core.logger import logger
__all__ = ["logger", "setup_logging"]
