"""
Health Check Router

Provides endpoints for monitoring application health.
"""

from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import get_settings
from src.core.database import get_db

router = APIRouter(prefix="/health", tags=["health"])


class HealthCheck(BaseModel):
    """Health check response model."""
    status: str
    timestamp: datetime
    version: str = "2.0.0"
    environment: str


class DetailedHealthCheck(BaseModel):
    """Detailed health check with component status."""
    status: str
    timestamp: datetime
    version: str = "2.0.0"
    environment: str
    components: dict[str, dict]


@router.get("", response_model=HealthCheck)
async def health_check() -> HealthCheck:
    """
    Basic health check endpoint.

    Returns:
        Basic health status
    """
    settings = get_settings()
    return HealthCheck(
        status="healthy",
        timestamp=datetime.utcnow(),
        environment=settings.environment,
    )


@router.get("/detailed", response_model=DetailedHealthCheck)
async def detailed_health_check(
    db: AsyncSession = Depends(get_db),
) -> DetailedHealthCheck:
    """
    Detailed health check with component status.

    Checks:
    - Database connectivity

    Returns:
        Detailed health status with component information
    """
    settings = get_settings()
    components: dict[str, dict] = {}

    # Check database
    try:
        await db.execute(text("SELECT 1"))
        components["database"] = {
            "status": "healthy",
            "type": "postgresql",
        }
    except Exception as e:
        components["database"] = {
            "status": "unhealthy",
            "type": "postgresql",
            "error": str(e),
        }

    components["redis"] = {
        "status": "not_configured",
        "type": "redis",
    }

    components["rabbitmq"] = {
        "status": "not_configured",
        "type": "rabbitmq",
    }

    # Determine overall status
    unhealthy = any(c.get("status") == "unhealthy" for c in components.values())
    overall_status = "unhealthy" if unhealthy else "healthy"

    return DetailedHealthCheck(
        status=overall_status,
        timestamp=datetime.utcnow(),
        environment=settings.environment,
        components=components,
    )
