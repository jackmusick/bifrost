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
    max_attempts: int = Field(3, ge=1, le=10, description="Total attempts including initial execution")
    backoff_seconds: int = Field(2, ge=1, description="Initial backoff duration in seconds")
    max_backoff_seconds: int = Field(60, ge=1, description="Maximum backoff cap in seconds")


# ==================== HELPER FUNCTIONS ====================


def generate_entity_id() -> str:
    """
    Generate UUID for entity IDs.

    Returns:
        UUID string (e.g., "550e8400-e29b-41d4-a716-446655440000")
    """
    return str(uuid.uuid4())


def parse_row_key(row_key: str) -> tuple[str, str]:
    """
    Parse 'type:id' row keys.

    Examples:
        "form:7c9e6679-7425-40de-944b-e07fc1f90ae7" → ("form", "7c9e6679-7425-40de-944b-e07fc1f90ae7")
        "config:workflow_key" → ("config", "workflow_key")
        "execution:9999999999999_uuid" → ("execution", "9999999999999_uuid")

    Args:
        row_key: Row key string

    Returns:
        Tuple of (entity_type, entity_id)
    """
    parts = row_key.split(':', 1)
    return parts[0], parts[1] if len(parts) > 1 else ""


def parse_composite_row_key(row_key: str, expected_parts: int) -> list[str]:
    """
    Parse multi-part row keys like 'assignedrole:role_uuid:user_id'.

    Examples:
        "assignedrole:a3b2c1d4-...:user-456" → ["assignedrole", "a3b2c1d4-...", "user-456"]
        "formrole:7c9e6679-...:a3b2c1d4-..." → ["formrole", "7c9e6679-...", "a3b2c1d4-..."]

    Args:
        row_key: Row key string
        expected_parts: Expected number of parts

    Returns:
        List of row key parts

    Raises:
        ValueError: If row key doesn't have expected number of parts
    """
    parts = row_key.split(':')
    if len(parts) != expected_parts:
        raise ValueError(f"Expected {expected_parts} parts in row key, got {len(parts)}: {row_key}")
    return parts


def entity_to_model(entity: dict, model_class: type[BaseModel]) -> BaseModel:
    """
    Convert Table Storage entity to Pydantic model.
    Handles composite row keys (type:uuid or type:id1:id2).

    Args:
        entity: Entity dictionary from Table Storage
        model_class: Pydantic model class to convert to

    Returns:
        Instance of the Pydantic model
    """
    # Remove Azure Table Storage metadata fields
    clean_entity = {k: v for k, v in entity.items() if not k.startswith(
        'odata') and k not in ['PartitionKey', 'RowKey', 'Timestamp', 'etag']}

    # Extract ID from row key (e.g., "form:7c9e6679-..." → "7c9e6679-...")
    if 'id' in model_class.model_fields and 'RowKey' in entity:
        row_key = entity['RowKey']
        entity_type, entity_id = parse_row_key(row_key)
        clean_entity['id'] = entity_id

    # Handle composite keys for junction tables (UserRole, FormRole, etc.)
    if 'user_id' in model_class.model_fields and 'role_id' in model_class.model_fields:
        # e.g., "userrole:user-123:a3b2c1d4-5678-90ab-cdef-1234567890ab"
        parts = parse_composite_row_key(entity['RowKey'], 3)
        clean_entity['user_id'] = parts[1]
        clean_entity['role_id'] = parts[2]  # UUID

    if 'form_id' in model_class.model_fields and 'role_id' in model_class.model_fields:
        # e.g., "formrole:form_uuid:role_uuid"
        parts = parse_composite_row_key(entity['RowKey'], 3)
        clean_entity['form_id'] = parts[1]  # UUID
        clean_entity['role_id'] = parts[2]  # UUID

    return model_class(**clean_entity)


def model_to_entity(
    model: BaseModel,
    partition_key: str,
    row_key: str,
    entity_type: str | None = None,
    generate_id: bool = False
) -> dict:
    """
    Convert Pydantic model to Table Storage entity.
    Constructs row key like 'type:uuid' if entity_type provided.
    Generates UUID if generate_id=True and model has no id.

    Args:
        model: Pydantic model instance
        partition_key: Partition key for the entity
        row_key: Row key for the entity (ignored if entity_type provided)
        entity_type: Optional entity type for composite row key construction
        generate_id: Whether to generate UUID if model has no id

    Returns:
        Entity dictionary ready for Table Storage
    """
    entity = model.model_dump()
    entity['PartitionKey'] = partition_key

    # Generate UUID if needed
    if generate_id and 'id' not in entity:
        entity['id'] = generate_entity_id()

    # Construct composite row key if entity_type provided
    if entity_type and 'id' in entity:
        entity['RowKey'] = f"{entity_type}:{entity['id']}"
        del entity['id']  # Remove id field, RowKey contains the UUID
    else:
        entity['RowKey'] = row_key

    return entity
