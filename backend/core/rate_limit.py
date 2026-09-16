"""Shared abuse controls for login, registration, upload, and AI routes."""

from __future__ import annotations

import hashlib
import threading
import time
from collections import defaultdict, deque

from fastapi import Depends, HTTPException, Request, status
from loguru import logger

from core.ai_quota import AIQuotaContext, get_ai_quota_manager
from core.config import settings
from core.redis_client import get_redis_client
from core.time import business_today
from utils.auth import get_current_user_id


_FIXED_WINDOW_SCRIPT = r"""
local current = redis.call('INCR', KEYS[1])
if current == 1 then redis.call('EXPIRE', KEYS[1], ARGV[1]) end
return current
"""


class SlidingWindowLimiter:
    """Process-local fallback used only when Redis is absent outside production."""

    def __init__(self) -> None:
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str, *, limit: int, window_seconds: int) -> bool:
        now = time.monotonic()
        cutoff = now - window_seconds
        with self._lock:
            events = self._events[key]
            while events and events[0] <= cutoff:
                events.popleft()
            if len(events) >= limit:
                return False
            events.append(now)
            return True

    def reset(self) -> None:
        with self._lock:
            self._events.clear()


_local_limiter = SlidingWindowLimiter()


def reset_rate_limit_state() -> None:
    """Clear only the non-production in-memory fallback (test helper)."""
    _local_limiter.reset()


def _hash(value: str) -> str:
    return hashlib.sha256((value or "unknown").encode("utf-8")).hexdigest()[:24]


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _device_id(request: Request) -> str:
    return request.headers.get("x-device-id", "").strip()[:128]


def _allow(key: str, *, limit: int, window_seconds: int) -> bool:
    if limit <= 0:
        return True
    full_key = f"{settings.rate_limit_key_prefix}:rate:{key}"
    client = get_redis_client()
    if client is not None:
        try:
            current = int(client.eval(_FIXED_WINDOW_SCRIPT, 1, full_key, window_seconds))
            return current <= limit
        except Exception as exc:
            logger.error("Rate-limit backend unavailable: {}", type(exc).__name__)
            if settings.is_production:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="安全限流服务暂不可用",
                ) from exc
    return _local_limiter.allow(full_key, limit=limit, window_seconds=window_seconds)


def _reject(message: str) -> None:
    raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=message)


def enforce_login_rate_limit(request: Request, student_id: str) -> None:
    ip = _hash(_client_ip(request))
    identity = _hash(student_id)
    for key in (f"login:ip:{ip}", f"login:identity:{identity}"):
        if not _allow(key, limit=settings.login_rate_limit, window_seconds=settings.login_rate_window_seconds):
            _reject("登录尝试过于频繁，请稍后再试")


def enforce_registration_rate_limit(request: Request, student_id: str) -> None:
    if not settings.registration_enabled:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="当前暂未开放注册")
    dimensions = [
        f"register:ip:{_hash(_client_ip(request))}",
        f"register:identity:{_hash(student_id)}",
    ]
    device = _device_id(request)
    if device:
        dimensions.append(f"register:device:{_hash(device)}")
    for key in dimensions:
        if not _allow(
            key,
            limit=settings.registration_rate_limit,
            window_seconds=settings.registration_rate_window_seconds,
        ):
            _reject("注册操作过于频繁，请稍后再试")
    day = business_today().isoformat()
    if not _allow(
        f"register:day:{day}:global",
        limit=settings.registration_global_daily_limit,
        window_seconds=24 * 60 * 60,
    ):
        _reject("今日注册名额已满，请明天再试")


def enforce_upload_rate_limit(request: Request, user_id: str) -> None:
    dimensions = [
        f"upload:user:{_hash(user_id)}",
        f"upload:ip:{_hash(_client_ip(request))}",
    ]
    device = _device_id(request)
    if device:
        dimensions.append(f"upload:device:{_hash(device)}")
    for key in dimensions:
        if not _allow(
            key,
            limit=settings.upload_rate_limit,
            window_seconds=settings.upload_rate_window_seconds,
        ):
            _reject("上传操作过于频繁，请稍后再试")


def enforce_ai_daily_limit(
    request: Request,
    current_user_id: str = Depends(get_current_user_id),
) -> str:
    """Preflight AI availability; charging happens inside ``LLMService``."""
    get_ai_quota_manager().assert_available(
        AIQuotaContext(
            user_id=current_user_id,
            feature=request.url.path,
            client_ip=_client_ip(request),
            device_id=_device_id(request),
        )
    )
    return current_user_id
