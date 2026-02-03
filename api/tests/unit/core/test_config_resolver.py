"""Tests for ConfigResolver with optional session parameter."""

import pytest
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4


class TestConfigResolverWithSession:
    """Test ConfigResolver methods with optional session."""

    @pytest.fixture
    def resolver(self):
        """Create ConfigResolver instance."""
        from src.core.config_resolver import ConfigResolver
        return ConfigResolver()

    @pytest.mark.asyncio
    async def test_get_organization_uses_provided_session(self, resolver):
        """get_organization() should use provided session on cache miss."""
        org_id = str(uuid4())

        # Mock cache miss
        resolver._get_org_from_cache = AsyncMock(return_value=None)
        resolver._set_org_cache = AsyncMock()

        mock_org = MagicMock()
        mock_org.id = uuid4()
        mock_org.name = "Test Org"
        mock_org.is_active = True
        mock_org.domain = "test.com"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_org

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        result = await resolver.get_organization(org_id, db=mock_session)

        assert result is not None
        assert result.name == "Test Org"
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_load_config_for_scope_uses_provided_session(self, resolver):
        """load_config_for_scope() should use provided session on cache miss."""
        org_id = str(uuid4())

        # Mock cache miss
        resolver._get_config_from_cache = AsyncMock(return_value=None)
        resolver._set_config_cache = AsyncMock()

        mock_config = MagicMock()
        mock_config.key = "test_key"
        mock_config.value = {"value": "test_value"}
        mock_config.config_type = MagicMock(value="string")

        # Mock scalars() to return iterable
        mock_scalars = MagicMock()
        mock_scalars.__iter__ = MagicMock(return_value=iter([mock_config]))

        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        result = await resolver.load_config_for_scope(f"ORG:{org_id}", db=mock_session)

        assert "test_key" in result
        mock_session.execute.assert_called()
