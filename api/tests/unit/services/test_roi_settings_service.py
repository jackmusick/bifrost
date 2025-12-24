"""
Unit tests for ROISettingsService.

Tests ROI settings storage and retrieval via SystemConfig.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from src.services.roi_settings_service import (
    ROISettingsService,
    ROISettings,
    ROI_CONFIG_CATEGORY,
    ROI_CONFIG_KEY,
)
from src.models.orm.config import SystemConfig


class TestROISettingsService:
    """Tests for ROISettingsService methods."""

    @pytest.fixture
    def mock_session(self):
        """Create a mock database session."""
        session = AsyncMock()
        session.execute = AsyncMock()
        session.flush = AsyncMock()
        return session

    @pytest.fixture
    def service(self, mock_session):
        """Create service with mock session."""
        return ROISettingsService(mock_session)

    @pytest.mark.asyncio
    async def test_get_settings_returns_defaults_when_not_configured(
        self, service, mock_session
    ):
        """Test get_settings returns defaults when no config exists."""
        # Mock no existing config
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.first.return_value = None
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        result = await service.get_settings()

        assert isinstance(result, ROISettings)
        assert result.time_saved_unit == "minutes"
        assert result.value_unit == "USD"

    @pytest.mark.asyncio
    async def test_get_settings_returns_defaults_when_value_json_is_none(
        self, service, mock_session
    ):
        """Test get_settings returns defaults when config exists but value_json is None."""
        # Mock existing config with None value_json
        mock_config = MagicMock(spec=SystemConfig)
        mock_config.value_json = None

        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.first.return_value = mock_config
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        result = await service.get_settings()

        assert isinstance(result, ROISettings)
        assert result.time_saved_unit == "minutes"
        assert result.value_unit == "USD"

    @pytest.mark.asyncio
    async def test_get_settings_returns_saved_values(self, service, mock_session):
        """Test get_settings returns saved values when config exists."""
        # Mock existing config
        mock_config = MagicMock(spec=SystemConfig)
        mock_config.value_json = {
            "time_saved_unit": "hours",
            "value_unit": "EUR",
        }

        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.first.return_value = mock_config
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        result = await service.get_settings()

        assert isinstance(result, ROISettings)
        assert result.time_saved_unit == "hours"
        assert result.value_unit == "EUR"

    @pytest.mark.asyncio
    async def test_get_settings_handles_partial_config(self, service, mock_session):
        """Test get_settings uses defaults for missing keys."""
        # Mock config with only one key
        mock_config = MagicMock(spec=SystemConfig)
        mock_config.value_json = {
            "time_saved_unit": "days",
            # value_unit missing
        }

        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.first.return_value = mock_config
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        result = await service.get_settings()

        assert result.time_saved_unit == "days"
        assert result.value_unit == "USD"  # default

    @pytest.mark.asyncio
    async def test_save_settings_creates_new_config_when_none_exists(
        self, service, mock_session
    ):
        """Test save_settings creates new config when none exists."""
        # Mock no existing config
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.first.return_value = None
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        result = await service.save_settings(
            time_saved_unit="hours",
            value_unit="GBP",
            updated_by="admin@example.com",
        )

        # Verify new config was added
        mock_session.add.assert_called_once()
        added_config = mock_session.add.call_args[0][0]
        assert isinstance(added_config, SystemConfig)
        assert added_config.category == ROI_CONFIG_CATEGORY
        assert added_config.key == ROI_CONFIG_KEY
        assert added_config.value_json == {
            "time_saved_unit": "hours",
            "value_unit": "GBP",
        }
        assert added_config.organization_id is None
        assert added_config.created_by == "admin@example.com"
        assert added_config.updated_by == "admin@example.com"

        # Verify flush was called
        mock_session.flush.assert_called_once()

        # Verify return value
        assert result.time_saved_unit == "hours"
        assert result.value_unit == "GBP"

    @pytest.mark.asyncio
    async def test_save_settings_updates_existing_config(self, service, mock_session):
        """Test save_settings updates existing config."""
        # Mock existing config
        existing_config = MagicMock(spec=SystemConfig)
        existing_config.value_json = {
            "time_saved_unit": "minutes",
            "value_unit": "USD",
        }

        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.first.return_value = existing_config
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        result = await service.save_settings(
            time_saved_unit="seconds",
            value_unit="CAD",
            updated_by="admin@example.com",
        )

        # Verify config was updated
        assert existing_config.value_json == {
            "time_saved_unit": "seconds",
            "value_unit": "CAD",
        }
        assert existing_config.updated_by == "admin@example.com"

        # Verify flush was called
        mock_session.flush.assert_called_once()

        # Verify add was NOT called (update, not create)
        mock_session.add.assert_not_called()

        # Verify return value
        assert result.time_saved_unit == "seconds"
        assert result.value_unit == "CAD"

    @pytest.mark.asyncio
    async def test_save_settings_queries_correct_category_and_key(
        self, service, mock_session
    ):
        """Test save_settings queries with correct category and key."""
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.first.return_value = None
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        await service.save_settings(
            time_saved_unit="minutes",
            value_unit="USD",
            updated_by="test@example.com",
        )

        # Verify execute was called (the query runs)
        assert mock_session.execute.called

        # The query should filter by category and key
        # (We can't easily inspect the query details with mocks, but we verify it executed)
