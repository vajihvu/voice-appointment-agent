"""Health check and status API routes."""

from fastapi import APIRouter

from app.core.config import get_settings

router = APIRouter(tags=["health"])
settings = get_settings()


@router.get("/health")
async def health_check():
    """Returns application health and configuration metadata."""
    return {
        "status": "ok",
        "business": settings.business.get("name", "Dental Clinic"),
        "environment": settings.ENVIRONMENT,
    }
