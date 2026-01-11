"""Service for managing worker pool configuration via SystemConfig.

Persists pool min/max workers settings so they survive container restarts.
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.orm.config import SystemConfig

logger = logging.getLogger(__name__)

WORKER_POOL_CONFIG_CATEGORY = "worker_pool"
WORKER_POOL_CONFIG_KEY = "config"


@dataclass
class WorkerPoolConfig:
    """Worker pool configuration settings."""

    min_workers: int = 2  # Minimum processes to maintain (warm pool)
    max_workers: int = 10  # Maximum processes for scaling


class WorkerPoolConfigService:
    """Service for managing worker pool configuration."""

    def __init__(self, session: AsyncSession):
        """Initialize the service with a database session."""
        self.session = session

    async def get_config(self) -> WorkerPoolConfig:
        """
        Get current worker pool configuration.

        Returns:
            WorkerPoolConfig with current settings, or defaults if not configured
        """
        result = await self.session.execute(
            select(SystemConfig).where(
                SystemConfig.category == WORKER_POOL_CONFIG_CATEGORY,
                SystemConfig.key == WORKER_POOL_CONFIG_KEY,
                SystemConfig.organization_id.is_(None),
            )
        )
        config = result.scalars().first()

        if not config or not config.value_json:
            # Return defaults if not configured
            return WorkerPoolConfig()

        config_data = config.value_json

        return WorkerPoolConfig(
            min_workers=config_data.get("min_workers", 2),
            max_workers=config_data.get("max_workers", 10),
        )

    async def save_config(
        self,
        min_workers: int,
        max_workers: int,
        updated_by: str,
    ) -> WorkerPoolConfig:
        """
        Save worker pool configuration.

        Args:
            min_workers: Minimum worker processes to maintain
            max_workers: Maximum worker processes for scaling
            updated_by: Email/ID of user making the change

        Returns:
            Updated WorkerPoolConfig

        Raises:
            ValueError: If min_workers < 2 or min_workers > max_workers
        """
        # Validate
        if min_workers < 2:
            raise ValueError(f"min_workers must be >= 2, got {min_workers}")
        if min_workers > max_workers:
            raise ValueError(
                f"min_workers ({min_workers}) cannot be greater than max_workers ({max_workers})"
            )

        # Check if config already exists
        result = await self.session.execute(
            select(SystemConfig).where(
                SystemConfig.category == WORKER_POOL_CONFIG_CATEGORY,
                SystemConfig.key == WORKER_POOL_CONFIG_KEY,
                SystemConfig.organization_id.is_(None),
            )
        )
        existing = result.scalars().first()

        config_data = {
            "min_workers": min_workers,
            "max_workers": max_workers,
        }

        if existing:
            # Update existing config
            existing.value_json = config_data
            existing.updated_at = datetime.utcnow()
            existing.updated_by = updated_by
            logger.info(
                f"Updated worker pool config: min_workers={min_workers}, max_workers={max_workers}"
            )
        else:
            # Create new config
            new_config = SystemConfig(
                id=uuid4(),
                category=WORKER_POOL_CONFIG_CATEGORY,
                key=WORKER_POOL_CONFIG_KEY,
                value_json=config_data,
                value_bytes=None,
                organization_id=None,
                created_by=updated_by,
                updated_by=updated_by,
            )
            self.session.add(new_config)
            logger.info(
                f"Created worker pool config: min_workers={min_workers}, max_workers={max_workers}"
            )

        await self.session.flush()

        return WorkerPoolConfig(
            min_workers=min_workers,
            max_workers=max_workers,
        )


async def get_pool_config(session: AsyncSession) -> WorkerPoolConfig:
    """
    Convenience function to get worker pool config.

    Args:
        session: Database session

    Returns:
        WorkerPoolConfig with current settings
    """
    service = WorkerPoolConfigService(session)
    return await service.get_config()


async def save_pool_config(
    session: AsyncSession,
    min_workers: int,
    max_workers: int,
    updated_by: str,
) -> WorkerPoolConfig:
    """
    Convenience function to save worker pool config.

    Args:
        session: Database session
        min_workers: Minimum worker processes
        max_workers: Maximum worker processes
        updated_by: User who made the change

    Returns:
        Updated WorkerPoolConfig
    """
    service = WorkerPoolConfigService(session)
    return await service.save_config(min_workers, max_workers, updated_by)
