"""Health check and version endpoints."""

from fastapi import APIRouter

from core.config import settings
from schemas.response import APIResponse

router = APIRouter(tags=["system"])


@router.get("/health", response_model=APIResponse[dict])
async def health_check():
    """Liveness probe — returns OK if the server is running."""
    return APIResponse.ok(data={"status": "healthy"})


@router.get("/version", response_model=APIResponse[dict])
async def version():
    """Return application version info."""
    return APIResponse.ok(
        data={
            "app": settings.app_name,
            "version": settings.app_version,
        }
    )
