"""
GitHub Configuration Service

Handles encrypted storage of GitHub integration configuration.
"""

import base64
import logging
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid4

from cryptography.fernet import Fernet
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import get_settings
from src.models import SystemConfig

logger = logging.getLogger(__name__)


@dataclass
class GitHubConfig:
    """GitHub configuration data."""

    repo_url: str | None
    token: str | None
    branch: str
    status: str


def _get_fernet() -> Fernet:
    """Get Fernet instance for encryption/decryption."""
    settings = get_settings()
    key_bytes = settings.secret_key.encode()[:32].ljust(32, b"0")
    return Fernet(base64.urlsafe_b64encode(key_bytes))


def _parse_org_id(org_id: str | UUID | None) -> UUID | None:
    """Parse org_id to UUID, handling GLOBAL case and UUID passthrough."""
    if not org_id or org_id == "GLOBAL":
        return None
    if isinstance(org_id, UUID):
        return org_id
    try:
        return UUID(org_id)
    except ValueError:
        return None


async def get_github_config(db: AsyncSession, org_id: str | UUID | None) -> GitHubConfig | None:
    """
    Get GitHub configuration from database.

    Args:
        db: Database session
        org_id: Organization ID (str, UUID, or None/GLOBAL for global config)

    Returns:
        GitHubConfig with decrypted token, or None if not configured
    """
    org_uuid = _parse_org_id(org_id)
    fernet = _get_fernet()

    # Look for org-specific config first
    query = select(SystemConfig).where(
        SystemConfig.category == "github",
        SystemConfig.key == "integration",
        SystemConfig.organization_id == org_uuid,
    )
    result = await db.execute(query)
    config = result.scalars().first()

    # Fallback to global config if no org-specific config
    if not config and org_uuid is not None:
        query = select(SystemConfig).where(
            SystemConfig.category == "github",
            SystemConfig.key == "integration",
            SystemConfig.organization_id.is_(None),
        )
        result = await db.execute(query)
        config = result.scalars().first()

    if not config:
        return None

    config_value = config.value_json or {}
    encrypted_token = config_value.get("encrypted_token")

    # Decrypt token if present
    token = None
    if encrypted_token:
        try:
            token = fernet.decrypt(encrypted_token.encode()).decode()
        except Exception as e:
            logger.warning(f"Failed to decrypt GitHub token: {e}")

    return GitHubConfig(
        repo_url=config_value.get("repo_url"),
        token=token,
        branch=config_value.get("branch", "main"),
        status=config_value.get("status", "connected"),
    )


async def save_github_config(
    db: AsyncSession,
    org_id: str | UUID | None,
    token: str,
    repo_url: str | None,
    branch: str,
    updated_by: str,
) -> None:
    """
    Save GitHub configuration to database.

    Args:
        db: Database session
        org_id: Organization ID (str, UUID, or None for global)
        token: GitHub personal access token (will be encrypted)
        repo_url: GitHub repository URL (can be None if just saving token)
        branch: Branch name
        updated_by: Email of user making the change
    """
    org_uuid = _parse_org_id(org_id)
    fernet = _get_fernet()

    # Encrypt token
    encrypted_token = fernet.encrypt(token.encode()).decode()

    # Check if config already exists
    query = select(SystemConfig).where(
        SystemConfig.category == "github",
        SystemConfig.key == "integration",
        SystemConfig.organization_id == org_uuid,
    )
    result = await db.execute(query)
    existing = result.scalars().first()

    config_data = {
        "repo_url": repo_url,
        "encrypted_token": encrypted_token,
        "branch": branch,
        "status": "connected",
    }

    if existing:
        existing.value_json = config_data
        existing.updated_at = datetime.utcnow()
        existing.updated_by = updated_by
    else:
        new_config = SystemConfig(
            id=uuid4(),
            category="github",
            key="integration",
            value_json=config_data,
            value_bytes=None,
            organization_id=org_uuid,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            created_by=updated_by,
            updated_by=updated_by,
        )
        db.add(new_config)

    await db.commit()
    logger.info(f"Saved GitHub config for org {org_uuid or 'GLOBAL'}")


async def delete_github_config(db: AsyncSession, org_id: str | UUID | None) -> None:
    """
    Delete GitHub configuration from database.

    Args:
        db: Database session
        org_id: Organization ID (str, UUID, or None for global)
    """
    org_uuid = _parse_org_id(org_id)

    stmt = delete(SystemConfig).where(
        SystemConfig.category == "github",
        SystemConfig.key == "integration",
        SystemConfig.organization_id == org_uuid,
    )
    await db.execute(stmt)
    await db.commit()
    logger.info(f"Deleted GitHub config for org {org_uuid or 'GLOBAL'}")
