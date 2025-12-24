"""
Base models and utilities for Bifrost contracts.
Includes enums, retry policies, and helper functions.
"""

import uuid
from enum import Enum
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    pass


# ==================== ENUMS ====================


class DataProviderInputMode(str, Enum):
    """Data provider input configuration modes (T005)"""
    STATIC = "static"
    FIELD_REF = "fieldRef"
    EXPRESSION = "expression"


class IntegrationType(str, Enum):
    """Supported integration types"""
    MSGRAPH = "msgraph"
    HALOPSA = "halopsa"


# ==================== MODELS ====================


class RetryPolicy(BaseModel):
    """Retry policy configuration for workflow execution"""
    max_attempts: int = Field(default=3, ge=1, le=10, description="Total attempts including initial execution")
    backoff_seconds: int = Field(default=2, ge=1, description="Initial backoff duration in seconds")
    max_backoff_seconds: int = Field(default=60, ge=1, description="Maximum backoff cap in seconds")


# ==================== HELPER FUNCTIONS ====================


def generate_entity_id() -> str:
    """
    Generate UUID for entity IDs.

    Returns:
        UUID string (e.g., "550e8400-e29b-41d4-a716-446655440000")
    """
    return str(uuid.uuid4())


