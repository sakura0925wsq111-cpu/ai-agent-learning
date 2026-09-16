"""Lazy Redis client shared by rate limits, AI quotas, and readiness checks."""

from __future__ import annotations

import threading
from typing import Any

from core.config import settings


_client: Any | None = None
_client_lock = threading.Lock()


def get_redis_client() -> Any | None:
    """Return one lazy synchronous Redis client, or ``None`` when unconfigured."""
    global _client
    if not settings.redis_url:
        return None
    if _client is not None:
        return _client
    with _client_lock:
        if _client is None:
            from redis import Redis

            _client = Redis.from_url(
                settings.redis_url,
                decode_responses=True,
                socket_connect_timeout=settings.redis_socket_timeout_seconds,
                socket_timeout=settings.redis_socket_timeout_seconds,
                health_check_interval=30,
            )
    return _client


def reset_redis_client() -> None:
    """Close and clear the cached client (used during shutdown and tests)."""
    global _client
    with _client_lock:
        client, _client = _client, None
    if client is not None:
        try:
            client.close()
        except Exception:
            pass
