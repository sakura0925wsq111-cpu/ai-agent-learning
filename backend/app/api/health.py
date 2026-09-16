"""Health check and version endpoints."""

import asyncio

from fastapi import APIRouter, Response, status
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from core.config import settings
from core.redis_client import get_redis_client
from database.session import engine
from schemas.response import APIResponse

router = APIRouter(tags=["system"])


@router.get("/health", response_model=APIResponse[dict])
async def health_check():
    """Liveness probe — returns OK if the server is running."""
    return APIResponse.ok(data={"status": "healthy"})


@router.get("/ready", response_model=APIResponse[dict])
async def readiness_check(response: Response):
    """Readiness probe: validate database access and required runtime config."""
    checks: dict[str, dict[str, object]] = {}
    ready = True

    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        checks["database"] = {"ok": True}
    except SQLAlchemyError as exc:
        ready = False
        checks["database"] = {"ok": False, "error": type(exc).__name__}

    config_ok = bool(settings.jwt_secret_key) and (
        settings.app_env == "dev" or bool(settings.llm_api_key)
    )
    ready = ready and config_ok
    checks["configuration"] = {"ok": config_ok}
    redis_required = settings.is_production
    redis_ok = not redis_required and not settings.redis_url
    if settings.redis_url:
        try:
            client = get_redis_client()
            redis_ok = bool(client and await asyncio.to_thread(client.ping))
        except Exception as exc:
            checks["redis"] = {
                "ok": False,
                "configured": True,
                "required": redis_required,
                "error": type(exc).__name__,
            }
        else:
            checks["redis"] = {
                "ok": redis_ok,
                "configured": True,
                "required": redis_required,
            }
    else:
        checks["redis"] = {
            "ok": redis_ok,
            "configured": False,
            "required": redis_required,
        }
    ready = ready and (redis_ok or not redis_required)

    if not ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return APIResponse.ok(data={"status": "ready" if ready else "not_ready", "checks": checks})


@router.get("/version", response_model=APIResponse[dict])
async def version():
    """Return application version info."""
    return APIResponse.ok(
        data={
            "app": settings.app_name,
            "version": settings.app_version,
        }
    )
