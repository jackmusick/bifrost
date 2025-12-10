"""
Health check contract models for Bifrost.
"""

from datetime import datetime
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    pass


# ==================== HEALTH MODELS ====================


class HealthCheck(BaseModel):
    """Individual health check result"""
    service: str = Field(..., description="Display name of the service (e.g., 'API', 'Key Vault')")
    healthy: bool = Field(..., description="Whether the service is healthy")
    message: str = Field(..., description="Health check message")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional service-specific metadata")


class BasicHealthResponse(BaseModel):
    """Basic health check response (liveness check)"""
    status: Literal["healthy"] = Field(default="healthy", description="Health status (always healthy if API responds)")
    service: str = Field(default="Bifrost Integrations API", description="Service name")
    timestamp: str = Field(..., description="Health check timestamp (ISO 8601)")


class GeneralHealthResponse(BaseModel):
    """General health check response with multiple service checks"""
    status: Literal["healthy", "degraded", "unhealthy"] = Field(..., description="Overall system health status")
    service: str = Field(default="Bifrost Integrations API", description="Service name")
    timestamp: datetime = Field(..., description="Health check timestamp")
    checks: list[HealthCheck] = Field(..., description="Individual service health checks")
