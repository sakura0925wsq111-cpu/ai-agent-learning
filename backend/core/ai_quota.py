"""Shared, fail-closed AI cost controls enforced at every provider call."""

from __future__ import annotations

import hashlib
import threading
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Iterator

from fastapi import HTTPException, status
from loguru import logger

from core.config import settings
from core.redis_client import get_redis_client
from core.time import business_today


_ACQUIRE_SCRIPT = r"""
local enabled = redis.call('GET', KEYS[1])
if enabled == '0' or enabled == 'false' or enabled == 'off' then return -1 end
if tonumber(ARGV[1]) > 0 and tonumber(redis.call('GET', KEYS[2]) or '0') >= tonumber(ARGV[1]) then return -2 end
if tonumber(ARGV[2]) > 0 and tonumber(redis.call('GET', KEYS[3]) or '0') >= tonumber(ARGV[2]) then return -3 end
if tonumber(ARGV[3]) > 0 and tonumber(redis.call('GET', KEYS[4]) or '0') >= tonumber(ARGV[3]) then return -4 end
if tonumber(ARGV[4]) > 0 and tonumber(redis.call('GET', KEYS[5]) or '0') >= tonumber(ARGV[4]) then return -5 end
redis.call('ZREMRANGEBYSCORE', KEYS[6], '-inf', ARGV[6])
if tonumber(ARGV[5]) > 0 and redis.call('ZCARD', KEYS[6]) >= tonumber(ARGV[5]) then return -6 end
redis.call('INCR', KEYS[2]); redis.call('EXPIRE', KEYS[2], ARGV[8])
if tonumber(ARGV[2]) > 0 then redis.call('INCR', KEYS[3]); redis.call('EXPIRE', KEYS[3], ARGV[8]) end
if tonumber(ARGV[3]) > 0 then redis.call('INCR', KEYS[4]); redis.call('EXPIRE', KEYS[4], ARGV[8]) end
redis.call('INCR', KEYS[5]); redis.call('EXPIRE', KEYS[5], ARGV[8])
redis.call('ZADD', KEYS[6], ARGV[7], ARGV[9]); redis.call('EXPIRE', KEYS[6], ARGV[8])
return 1
"""

_CHECK_SCRIPT = r"""
local enabled = redis.call('GET', KEYS[1])
if enabled == '0' or enabled == 'false' or enabled == 'off' then return -1 end
if tonumber(ARGV[1]) > 0 and tonumber(redis.call('GET', KEYS[2]) or '0') >= tonumber(ARGV[1]) then return -2 end
if tonumber(ARGV[2]) > 0 and tonumber(redis.call('GET', KEYS[3]) or '0') >= tonumber(ARGV[2]) then return -3 end
if tonumber(ARGV[3]) > 0 and tonumber(redis.call('GET', KEYS[4]) or '0') >= tonumber(ARGV[3]) then return -4 end
if tonumber(ARGV[4]) > 0 and tonumber(redis.call('GET', KEYS[5]) or '0') >= tonumber(ARGV[4]) then return -5 end
redis.call('ZREMRANGEBYSCORE', KEYS[6], '-inf', ARGV[6])
if tonumber(ARGV[5]) > 0 and redis.call('ZCARD', KEYS[6]) >= tonumber(ARGV[5]) then return -6 end
return 1
"""

_RELEASE_SCRIPT = "redis.call('ZREM', KEYS[1], ARGV[1]); return 1"


@dataclass(frozen=True)
class AIQuotaContext:
    user_id: str
    feature: str = "unknown"
    client_ip: str = "unknown"
    device_id: str = ""


def _hash(value: str) -> str:
    return hashlib.sha256((value or "unknown").encode("utf-8")).hexdigest()[:24]


class AIQuotaManager:
    """Atomically enforce user/IP/device/global/concurrency limits."""

    def __init__(
        self,
        *,
        redis_client: Any | None = None,
        prefix: str | None = None,
        use_configured_redis: bool = True,
    ) -> None:
        self._redis_client = redis_client
        self._use_configured_redis = use_configured_redis
        self._prefix = prefix or f"{settings.rate_limit_key_prefix}:ai"
        self._local_counts: dict[str, int] = {}
        self._local_leases: dict[str, float] = {}
        self._local_lock = threading.Lock()

    @property
    def client(self) -> Any | None:
        if self._redis_client is not None:
            return self._redis_client
        return get_redis_client() if self._use_configured_redis else None

    def _keys(self, context: AIQuotaContext) -> list[str]:
        day = business_today().isoformat()
        device = _hash(context.device_id) if context.device_id else "unavailable"
        return [
            f"{self._prefix}:enabled",
            f"{self._prefix}:day:{day}:user:{_hash(context.user_id)}",
            f"{self._prefix}:day:{day}:ip:{_hash(context.client_ip)}",
            f"{self._prefix}:day:{day}:device:{device}",
            f"{self._prefix}:day:{day}:global",
            f"{self._prefix}:concurrency",
        ]

    @staticmethod
    def _limits(context: AIQuotaContext) -> list[int]:
        return [
            settings.ai_daily_limit,
            settings.ai_ip_daily_limit if context.client_ip not in {"", "unknown"} else 0,
            settings.ai_device_daily_limit if context.device_id else 0,
            settings.ai_global_daily_limit,
            settings.ai_global_concurrency_limit,
        ]

    @staticmethod
    def _raise_for_code(code: int) -> None:
        if code == 1:
            return
        if code == -1:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="AI 服务已暂停")
        messages = {
            -2: "今日 AI 使用次数已达上限，请明天再试",
            -3: "当前网络的 AI 使用次数已达上限",
            -4: "当前设备的 AI 使用次数已达上限",
            -5: "AI 服务今日总预算已达上限",
            -6: "AI 服务当前繁忙，请稍后再试",
        }
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=messages.get(code, "AI 使用额度不足"))

    def _redis_eval(self, script: str, keys: list[str], args: list[Any]) -> int:
        client = self.client
        if client is None:
            raise RuntimeError("Redis is not configured")
        return int(client.eval(script, len(keys), *keys, *args))

    def _local_check(self, context: AIQuotaContext, *, consume: bool, token: str = "") -> int:
        keys = self._keys(context)
        limits = self._limits(context)
        now = time.time()
        with self._local_lock:
            for lease, expiry in list(self._local_leases.items()):
                if expiry <= now:
                    self._local_leases.pop(lease, None)
            for key, limit, code in zip(keys[1:5], limits[:4], (-2, -3, -4, -5)):
                if limit > 0 and self._local_counts.get(key, 0) >= limit:
                    return code
            if limits[4] > 0 and len(self._local_leases) >= limits[4]:
                return -6
            if consume:
                for key, limit in zip(keys[1:5], limits[:4]):
                    if limit > 0:
                        self._local_counts[key] = self._local_counts.get(key, 0) + 1
                self._local_leases[token] = now + settings.ai_concurrency_lease_seconds
        return 1

    @staticmethod
    def _fail_closed(exc: Exception) -> None:
        logger.error("AI quota backend unavailable: {}", type(exc).__name__)
        if settings.is_production:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="AI 安全额度服务暂不可用") from exc

    def assert_available(self, context: AIQuotaContext) -> None:
        if not settings.ai_enabled:
            self._raise_for_code(-1)
        keys, limits, now = self._keys(context), self._limits(context), time.time()
        try:
            code = self._redis_eval(_CHECK_SCRIPT, keys, [*limits, now]) if self.client is not None else self._local_check(context, consume=False)
        except HTTPException:
            raise
        except Exception as exc:
            self._fail_closed(exc)
            code = self._local_check(context, consume=False)
        self._raise_for_code(code)

    @contextmanager
    def lease(self, context: AIQuotaContext) -> Iterator[None]:
        """Charge one provider attempt and hold one global concurrency slot."""
        if not settings.ai_enabled:
            self._raise_for_code(-1)
        token = uuid.uuid4().hex
        keys, limits, now = self._keys(context), self._limits(context), time.time()
        expiry = now + settings.ai_concurrency_lease_seconds
        using_redis = False
        try:
            if self.client is not None:
                code = self._redis_eval(_ACQUIRE_SCRIPT, keys, [*limits, now, expiry, 2 * 24 * 60 * 60, token])
                using_redis = True
            else:
                code = self._local_check(context, consume=True, token=token)
        except HTTPException:
            raise
        except Exception as exc:
            self._fail_closed(exc)
            code = self._local_check(context, consume=True, token=token)
        self._raise_for_code(code)
        try:
            yield
        finally:
            if using_redis:
                try:
                    self._redis_eval(_RELEASE_SCRIPT, [keys[5]], [token])
                except Exception as exc:
                    logger.warning("AI concurrency lease release failed: {}", type(exc).__name__)
            else:
                with self._local_lock:
                    self._local_leases.pop(token, None)


_manager: AIQuotaManager | None = None
_manager_lock = threading.Lock()


def get_ai_quota_manager() -> AIQuotaManager:
    global _manager
    if _manager is None:
        with _manager_lock:
            if _manager is None:
                _manager = AIQuotaManager()
    return _manager


def reset_ai_quota_manager() -> None:
    global _manager
    with _manager_lock:
        _manager = None
