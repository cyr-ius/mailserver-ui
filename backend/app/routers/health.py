"""Health and readiness endpoints."""

from fastapi import APIRouter

from app.config import settings

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/healthz")
async def healthz() -> dict[str, str]:
    """Lightweight liveness probe."""
    return {"status": "healthy", "version": settings.app_version}
