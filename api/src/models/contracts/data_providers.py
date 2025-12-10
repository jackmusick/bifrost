"""
Data provider contract models for Bifrost.
"""

from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    pass


# ==================== DATA PROVIDER MODELS ====================


class DataProviderRequest(BaseModel):
    """Request model for data provider endpoint (T009)"""
    org_id: str | None = Field(None, description="Organization ID for org-scoped providers")
    inputs: dict[str, Any] | None = Field(None, description="Input parameter values for data provider")
    no_cache: bool = Field(False, description="Bypass cache and fetch fresh data")


class DataProviderOption(BaseModel):
    """Data provider option item"""
    label: str
    value: str
    metadata: dict[str, Any] | None = None


class DataProviderResponse(BaseModel):
    """Response model for data provider endpoint"""
    provider: str = Field(..., description="Name of the data provider")
    options: list[DataProviderOption] = Field(..., description="List of options returned by the provider")
    cached: bool = Field(..., description="Whether this result was served from cache")
    cache_expires_at: str = Field(..., description="Cache expiration timestamp")
