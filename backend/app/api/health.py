"""Health check and version endpoints."""

from fastapi import APIRouter, Response, status
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from core.config import settings
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
    checks["redis"] = {
        "ok": True,
        "configured": bool(settings.redis_url),
        "required": False,
    }

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
