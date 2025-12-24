"""Service for managing ROI settings via SystemConfig."""

import logging
from dataclasses import dataclass
from datetime import datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.orm.config import SystemConfig

logger = logging.getLogger(__name__)

ROI_CONFIG_CATEGORY = "roi"
ROI_CONFIG_KEY = "settings"


@dataclass
class ROISettings:
    """ROI settings for the platform."""

    time_saved_unit: str = "minutes"  # Display label
    value_unit: str = "USD"  # Display label (ISP defines meaning)


class ROISettingsService:
    """Service for managing ROI settings."""

    def __init__(self, session: AsyncSession):
        """Initialize the service with a database session."""
        self.session = session

    async def get_settings(self) -> ROISettings:
        """
        Get current ROI settings.

        Returns:
            ROISettings with current settings, or defaults if not configured
        """
        result = await self.session.execute(
            select(SystemConfig).where(
                SystemConfig.category == ROI_CONFIG_CATEGORY,
                SystemConfig.key == ROI_CONFIG_KEY,
                SystemConfig.organization_id.is_(None),
            )
        )
        config = result.scalars().first()

        if not config or not config.value_json:
            # Return defaults if not configured
            return ROISettings()

        config_data = config.value_json

        return ROISettings(
            time_saved_unit=config_data.get("time_saved_unit", "minutes"),
            value_unit=config_data.get("value_unit", "USD"),
        )

    async def save_settings(
        self,
        time_saved_unit: str,
        value_unit: str,
        updated_by: str,
    ) -> ROISettings:
        """
        Save ROI settings.

        Args:
            time_saved_unit: Display label for time saved
            value_unit: Display label for value
            updated_by: Email/ID of user making the change

        Returns:
            Updated ROISettings
        """
        # Check if config already exists
        result = await self.session.execute(
            select(SystemConfig).where(
                SystemConfig.category == ROI_CONFIG_CATEGORY,
                SystemConfig.key == ROI_CONFIG_KEY,
                SystemConfig.organization_id.is_(None),
            )
        )
        existing = result.scalars().first()

        config_data = {
            "time_saved_unit": time_saved_unit,
            "value_unit": value_unit,
        }

        if existing:
            # Update existing config
            existing.value_json = config_data
            existing.updated_at = datetime.utcnow()
            existing.updated_by = updated_by
            logger.info(
                f"Updated ROI settings: time_saved_unit={time_saved_unit}, value_unit={value_unit}"
            )
        else:
            # Create new config
            new_config = SystemConfig(
                id=uuid4(),
                category=ROI_CONFIG_CATEGORY,
                key=ROI_CONFIG_KEY,
                value_json=config_data,
                value_bytes=None,
                organization_id=None,
                created_by=updated_by,
                updated_by=updated_by,
            )
            self.session.add(new_config)
            logger.info(
                f"Created ROI settings: time_saved_unit={time_saved_unit}, value_unit={value_unit}"
            )

        await self.session.flush()

        return ROISettings(
            time_saved_unit=time_saved_unit,
            value_unit=value_unit,
        )
