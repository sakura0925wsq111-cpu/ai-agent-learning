"""Small process-local rate limiter with a stable dependency boundary.

This is suitable for a single test instance. Production multi-worker deployments
should replace the storage behind this module with Redis without changing routes.
"""

from __future__ import annotations

import hashlib
import threading
import time
from collections import defaultdict, deque
from datetime import date

from fastapi import Depends, HTTPException, Request, status

from core.config import settings
from utils.auth import get_current_user_id


class SlidingWindowLimiter:
    def __init__(self) -> None:
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str, *, limit: int, window_seconds: int) -> bool:
        if limit <= 0:
            return True
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


_limiter = SlidingWindowLimiter()


def enforce_login_rate_limit(request: Request, student_id: str) -> None:
    client_ip = request.client.host if request.client else "unknown"
    identity = hashlib.sha256(student_id.encode("utf-8")).hexdigest()[:16]
    if not _limiter.allow(
        f"login:{client_ip}:{identity}",
        limit=settings.login_rate_limit,
        window_seconds=settings.login_rate_window_seconds,
    ):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="登录尝试过于频繁，请稍后再试",
        )


def enforce_ai_daily_limit(
    current_user_id: str = Depends(get_current_user_id),
) -> str:
    if not _limiter.allow(
        f"ai:{date.today().isoformat()}:{current_user_id}",
        limit=settings.ai_daily_limit,
        window_seconds=24 * 60 * 60,
    ):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="今日 AI 使用次数已达上限，请明天再试",
        )
    return current_user_id
