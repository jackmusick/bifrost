"""
Workflow API Key Authentication Utilities

Provides utilities for generating, validating, and managing workflow API keys.
Now uses the workflows table's api_key_* columns instead of separate workflow_keys table.
"""

import hashlib
import secrets
from datetime import datetime
from typing import Optional
from uuid import UUID


def generate_workflow_key() -> tuple[str, str]:
    """
    Generate a cryptographically secure workflow API key.

    Returns:
        Tuple of (raw_key, hashed_key) for storage in workflows.api_key_hash
    """
    # Generate a secure, URL-safe token
    raw_key = secrets.token_urlsafe(32)

    # Hash the key for secure storage
    hashed_key = hashlib.sha256(raw_key.encode()).hexdigest()

    return raw_key, hashed_key


async def validate_workflow_key(
    connection_str: str,
    api_key: str,
    workflow_name: Optional[str] = None
) -> tuple[bool, Optional[str]]:
    """
    Validate an API key against workflows table's api_key_hash column.

    Authentication flow:
    1. Hash the provided API key
    2. If workflow_name provided, look up that specific workflow
    3. Check if the workflow has api_key_enabled=True and hashed key matches
    4. Check if key is not expired
    5. Update last_used_at timestamp

    Args:
        connection_str: Database connection string (unused, kept for compatibility)
        api_key: Raw API key to validate
        workflow_name: Optional workflow name to validate against

    Returns:
        Tuple of (is_valid, workflow_id) where workflow_id is the UUID for logging
    """
    from sqlalchemy import select, or_
    from src.core.database import get_session_factory
    from src.models.orm import Workflow

    # Compute hash of provided key
    hashed_key = hashlib.sha256(api_key.encode()).hexdigest()
    now = datetime.utcnow()

    try:
        session_factory = get_session_factory()

        async with session_factory() as db:
            # Build query for workflow with matching API key
            query = select(Workflow).where(
                Workflow.api_key_hash == hashed_key,
                Workflow.api_key_enabled == True,  # noqa: E712
                or_(
                    Workflow.api_key_expires_at.is_(None),
                    Workflow.api_key_expires_at > now,
                ),
            )

            # If workflow_name provided, filter by name
            if workflow_name:
                query = query.where(Workflow.name == workflow_name)

            result = await db.execute(query)
            workflow = result.scalar_one_or_none()

            if not workflow:
                return (False, None)

            # Update last used timestamp
            workflow.api_key_last_used_at = now
            await db.commit()

            return (True, str(workflow.id))

    except Exception:
        return (False, None)


async def revoke_workflow_key(
    connection_str: str,
    workflow_id: str,
    revoked_by: str = "system"
) -> bool:
    """
    Revoke a workflow API key by disabling it on the workflow.

    Args:
        connection_str: Database connection string (unused, kept for compatibility)
        workflow_id: Workflow ID (UUID) to revoke the key for
        revoked_by: User revoking the key (for logging)

    Returns:
        True if key was successfully revoked, False otherwise
    """
    from sqlalchemy import select
    from src.core.database import get_session_factory
    from src.models.orm import Workflow

    try:
        session_factory = get_session_factory()
        workflow_uuid = UUID(workflow_id)

        async with session_factory() as db:
            result = await db.execute(
                select(Workflow).where(Workflow.id == workflow_uuid)
            )
            workflow = result.scalar_one_or_none()

            if not workflow:
                return False

            # Disable the API key
            workflow.api_key_enabled = False
            workflow.api_key_hash = None  # Clear the hash for security
            await db.commit()

            return True

    except Exception:
        return False


async def list_workflow_keys(
    connection_str: str,
    user_id: str,
    workflow_name: Optional[str] = None,
    include_disabled: bool = False
) -> list[dict]:
    """
    List workflows with API keys enabled.

    Args:
        connection_str: Database connection string (unused, kept for compatibility)
        user_id: User filter (not currently used - all workflows returned)
        workflow_name: Optional workflow name filter
        include_disabled: Include workflows with disabled API keys

    Returns:
        List of workflow API key information
    """
    from sqlalchemy import select
    from src.core.database import get_session_factory
    from src.models.orm import Workflow

    try:
        session_factory = get_session_factory()

        async with session_factory() as db:
            query = select(Workflow).where(
                Workflow.api_key_hash.isnot(None)  # Has an API key configured
            )

            if not include_disabled:
                query = query.where(Workflow.api_key_enabled == True)  # noqa: E712

            if workflow_name:
                query = query.where(Workflow.name == workflow_name)

            query = query.order_by(Workflow.created_at.desc())

            result = await db.execute(query)
            workflows = result.scalars().all()

            return [
                {
                    "id": str(wf.id),
                    "workflow_name": wf.name,
                    "hashed_key": wf.api_key_hash,
                    "description": wf.api_key_description,
                    "created_by": wf.api_key_created_by,
                    "created_at": wf.api_key_created_at.isoformat() if wf.api_key_created_at else None,
                    "last_used_at": wf.api_key_last_used_at.isoformat() if wf.api_key_last_used_at else None,
                    "expires_at": wf.api_key_expires_at.isoformat() if wf.api_key_expires_at else None,
                    "revoked": not wf.api_key_enabled,  # Disabled = revoked
                    "revoked_at": None,  # Not tracked anymore
                    "revoked_by": None,  # Not tracked anymore
                }
                for wf in workflows
            ]

    except Exception:
        return []
