"""
Unit tests for scoped entity lookups.

Tests the prioritized lookup pattern (org-specific > global) for:
- TableRepository.get_by_name()
- ConfigRepository.get_config()
- WorkflowRepository.get_by_name()
- DataProviderRepository.get_by_name()

These tests verify that when the same name/key exists in both org scope
and global scope, the org-specific entity is returned (not MultipleResultsFound).
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from src.models.orm.tables import Table
from src.models.orm.config import Config
from src.models.orm.workflows import Workflow
from src.models.enums import ConfigType


def make_table(name: str, org_id=None) -> Table:
    """Create a Table instance for testing."""
    return Table(
        id=uuid4(),
        name=name,
        organization_id=org_id,
        application_id=None,
        schema=None,
        description=None,
    )


def make_config(key: str, org_id=None, value: str = "test") -> Config:
    """Create a Config instance for testing."""
    return Config(
        id=uuid4(),
        key=key,
        organization_id=org_id,
        value={"value": value},
        config_type=ConfigType.STRING,
        description=None,
        updated_by="test@example.com",
    )


def make_workflow(name: str, org_id=None, workflow_type: str = "workflow") -> Workflow:
    """Create a Workflow instance for testing."""
    return Workflow(
        id=uuid4(),
        name=name,
        organization_id=org_id,
        type=workflow_type,
        is_active=True,
        function_name=name.lower().replace(" ", "_"),
        path=f"/workflows/{name.lower().replace(' ', '_')}.py",
    )


class TestTableRepositoryScopedLookup:
    """Tests for TableRepository.get_by_name() prioritized lookup."""

    @pytest.fixture
    def mock_session(self):
        """Create a mock database session."""
        session = AsyncMock()
        session.execute = AsyncMock()
        return session

    @pytest.fixture
    def org_id(self):
        """Create a test organization ID."""
        return uuid4()

    async def test_same_name_in_org_and_global_returns_org_specific(
        self, mock_session, org_id
    ):
        """When same name exists in org AND global, return org-specific."""
        from src.routers.tables import TableRepository

        org_table = make_table("shared_table", org_id)

        # First query (org-specific) returns the org table
        mock_result_org = MagicMock()
        mock_result_org.scalar_one_or_none.return_value = org_table
        mock_session.execute.return_value = mock_result_org

        repo = TableRepository(mock_session, org_id)
        result = await repo.get_by_name("shared_table")

        assert result is not None
        assert result.id == org_table.id
        assert result.organization_id == org_id
        # Should only execute one query (org-specific found, no fallback needed)
        assert mock_session.execute.call_count == 1

    async def test_name_only_in_global_returns_global(self, mock_session, org_id):
        """When name only exists in global scope, return global."""
        from src.routers.tables import TableRepository

        global_table = make_table("shared_table", None)

        # First query (org-specific) returns None
        mock_result_org = MagicMock()
        mock_result_org.scalar_one_or_none.return_value = None

        # Second query (global) returns the global table
        mock_result_global = MagicMock()
        mock_result_global.scalar_one_or_none.return_value = global_table

        mock_session.execute.side_effect = [mock_result_org, mock_result_global]

        repo = TableRepository(mock_session, org_id)
        result = await repo.get_by_name("shared_table")

        assert result is not None
        assert result.id == global_table.id
        assert result.organization_id is None
        # Should execute two queries (org-specific not found, then global)
        assert mock_session.execute.call_count == 2

    async def test_name_only_in_org_returns_org_specific(self, mock_session, org_id):
        """When name only exists in org scope, return org-specific."""
        from src.routers.tables import TableRepository

        org_table = make_table("shared_table", org_id)

        # First query (org-specific) returns the org table
        mock_result_org = MagicMock()
        mock_result_org.scalar_one_or_none.return_value = org_table
        mock_session.execute.return_value = mock_result_org

        repo = TableRepository(mock_session, org_id)
        result = await repo.get_by_name("shared_table")

        assert result is not None
        assert result.id == org_table.id
        assert result.organization_id == org_id
        # Should only execute one query (org-specific found)
        assert mock_session.execute.call_count == 1

    async def test_no_org_id_only_checks_global(self, mock_session):
        """When no org_id, only check global scope."""
        from src.routers.tables import TableRepository

        global_table = make_table("shared_table", None)

        # Only global query should be executed
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = global_table
        mock_session.execute.return_value = mock_result

        repo = TableRepository(mock_session, None)  # No org_id
        result = await repo.get_by_name("shared_table")

        assert result is not None
        assert result.id == global_table.id
        # Should only execute one query (global only)
        assert mock_session.execute.call_count == 1

    async def test_name_not_found_returns_none(self, mock_session, org_id):
        """When name doesn't exist anywhere, return None."""
        from src.routers.tables import TableRepository

        # Both queries return None
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        repo = TableRepository(mock_session, org_id)
        result = await repo.get_by_name("nonexistent")

        assert result is None


class TestConfigRepositoryScopedLookup:
    """Tests for ConfigRepository.get_config() prioritized lookup."""

    @pytest.fixture
    def mock_session(self):
        """Create a mock database session."""
        session = AsyncMock()
        session.execute = AsyncMock()
        return session

    @pytest.fixture
    def org_id(self):
        """Create a test organization ID."""
        return uuid4()

    async def test_same_key_in_org_and_global_returns_org_specific(
        self, mock_session, org_id
    ):
        """When same key exists in org AND global, return org-specific."""
        from src.routers.config import ConfigRepository

        org_config = make_config("shared_key", org_id, "org_value")

        # First query (org-specific) returns the org config
        mock_result_org = MagicMock()
        mock_result_org.scalar_one_or_none.return_value = org_config
        mock_session.execute.return_value = mock_result_org

        repo = ConfigRepository(mock_session, org_id)
        result = await repo.get_config("shared_key")

        assert result is not None
        assert result.id == org_config.id
        assert result.organization_id == org_id
        # Should only execute one query (org-specific found)
        assert mock_session.execute.call_count == 1

    async def test_key_only_in_global_returns_global(self, mock_session, org_id):
        """When key only exists in global scope, return global."""
        from src.routers.config import ConfigRepository

        global_config = make_config("shared_key", None, "global_value")

        # First query (org-specific) returns None
        mock_result_org = MagicMock()
        mock_result_org.scalar_one_or_none.return_value = None

        # Second query (global) returns the global config
        mock_result_global = MagicMock()
        mock_result_global.scalar_one_or_none.return_value = global_config

        mock_session.execute.side_effect = [mock_result_org, mock_result_global]

        repo = ConfigRepository(mock_session, org_id)
        result = await repo.get_config("shared_key")

        assert result is not None
        assert result.id == global_config.id
        assert result.organization_id is None
        # Should execute two queries (org-specific not found, then global)
        assert mock_session.execute.call_count == 2

    async def test_key_only_in_org_returns_org_specific(self, mock_session, org_id):
        """When key only exists in org scope, return org-specific."""
        from src.routers.config import ConfigRepository

        org_config = make_config("shared_key", org_id, "org_value")

        # First query (org-specific) returns the org config
        mock_result_org = MagicMock()
        mock_result_org.scalar_one_or_none.return_value = org_config
        mock_session.execute.return_value = mock_result_org

        repo = ConfigRepository(mock_session, org_id)
        result = await repo.get_config("shared_key")

        assert result is not None
        assert result.id == org_config.id
        assert result.organization_id == org_id


class TestWorkflowRepositoryScopedLookup:
    """Tests for WorkflowRepository.get_by_name() prioritized lookup."""

    @pytest.fixture
    def mock_session(self):
        """Create a mock database session."""
        session = AsyncMock()
        session.execute = AsyncMock()
        return session

    @pytest.fixture
    def org_id(self):
        """Create a test organization ID."""
        return uuid4()

    async def test_same_name_in_org_and_global_returns_org_specific(
        self, mock_session, org_id
    ):
        """When same name exists in org AND global, return org-specific."""
        from src.repositories.workflows import WorkflowRepository

        org_workflow = make_workflow("shared_workflow", org_id)

        # First query (org-specific) returns the org workflow
        mock_result_org = MagicMock()
        mock_result_org.scalar_one_or_none.return_value = org_workflow
        mock_session.execute.return_value = mock_result_org

        # OrgScopedRepository takes org_id in constructor, not method
        repo = WorkflowRepository(mock_session, org_id=org_id, is_superuser=True)
        result = await repo.get_by_name("shared_workflow")

        assert result is not None
        assert result.id == org_workflow.id
        assert result.organization_id == org_id
        # Should only execute one query (org-specific found)
        assert mock_session.execute.call_count == 1

    async def test_name_only_in_global_returns_global(self, mock_session, org_id):
        """When name only exists in global scope, return global."""
        from src.repositories.workflows import WorkflowRepository

        global_workflow = make_workflow("shared_workflow", None)

        # First query (org-specific) returns None
        mock_result_org = MagicMock()
        mock_result_org.scalar_one_or_none.return_value = None

        # Second query (global) returns the global workflow
        mock_result_global = MagicMock()
        mock_result_global.scalar_one_or_none.return_value = global_workflow

        mock_session.execute.side_effect = [mock_result_org, mock_result_global]

        # OrgScopedRepository takes org_id in constructor, not method
        repo = WorkflowRepository(mock_session, org_id=org_id, is_superuser=True)
        result = await repo.get_by_name("shared_workflow")

        assert result is not None
        assert result.id == global_workflow.id
        assert result.organization_id is None
        # Should execute two queries (org-specific not found, then global)
        assert mock_session.execute.call_count == 2

    async def test_name_only_in_org_returns_org_specific(self, mock_session, org_id):
        """When name only exists in org scope, return org-specific."""
        from src.repositories.workflows import WorkflowRepository

        org_workflow = make_workflow("shared_workflow", org_id)

        # First query (org-specific) returns the org workflow
        mock_result_org = MagicMock()
        mock_result_org.scalar_one_or_none.return_value = org_workflow
        mock_session.execute.return_value = mock_result_org

        # OrgScopedRepository takes org_id in constructor, not method
        repo = WorkflowRepository(mock_session, org_id=org_id, is_superuser=True)
        result = await repo.get_by_name("shared_workflow")

        assert result is not None
        assert result.id == org_workflow.id
        assert result.organization_id == org_id

    async def test_no_org_id_only_checks_global(self, mock_session):
        """When no org_id provided, only check global scope."""
        from src.repositories.workflows import WorkflowRepository

        global_workflow = make_workflow("shared_workflow", None)

        # Only global query should be executed
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = global_workflow
        mock_session.execute.return_value = mock_result

        # OrgScopedRepository with org_id=None means global-only scope
        repo = WorkflowRepository(mock_session, org_id=None, is_superuser=True)
        result = await repo.get_by_name("shared_workflow")

        assert result is not None
        assert result.id == global_workflow.id
        # Should only execute one query (global only)
        assert mock_session.execute.call_count == 1


class TestDataProviderRepositoryScopedLookup:
    """Tests for DataProviderRepository.get_by_name() prioritized lookup."""

    @pytest.fixture
    def mock_session(self):
        """Create a mock database session."""
        session = AsyncMock()
        session.execute = AsyncMock()
        return session

    @pytest.fixture
    def org_id(self):
        """Create a test organization ID."""
        return uuid4()

    async def test_same_name_in_org_and_global_returns_org_specific(
        self, mock_session, org_id
    ):
        """When same name exists in org AND global, return org-specific."""
        from src.repositories.data_providers import DataProviderRepository

        org_provider = make_workflow("shared_provider", org_id, "data_provider")

        # First query (org-specific) returns the org provider
        mock_result_org = MagicMock()
        mock_result_org.scalar_one_or_none.return_value = org_provider
        mock_session.execute.return_value = mock_result_org

        # OrgScopedRepository takes org_id in constructor
        repo = DataProviderRepository(mock_session, org_id=org_id, is_superuser=True)
        result = await repo.get_by_name("shared_provider")

        assert result is not None
        assert result.id == org_provider.id
        assert result.organization_id == org_id
        # Should only execute one query (org-specific found)
        assert mock_session.execute.call_count == 1

    async def test_name_only_in_global_returns_global(self, mock_session, org_id):
        """When name only exists in global scope, return global."""
        from src.repositories.data_providers import DataProviderRepository

        global_provider = make_workflow("shared_provider", None, "data_provider")

        # First query (org-specific) returns None
        mock_result_org = MagicMock()
        mock_result_org.scalar_one_or_none.return_value = None

        # Second query (global) returns the global provider
        mock_result_global = MagicMock()
        mock_result_global.scalar_one_or_none.return_value = global_provider

        mock_session.execute.side_effect = [mock_result_org, mock_result_global]

        # OrgScopedRepository takes org_id in constructor
        repo = DataProviderRepository(mock_session, org_id=org_id, is_superuser=True)
        result = await repo.get_by_name("shared_provider")

        assert result is not None
        assert result.id == global_provider.id
        assert result.organization_id is None
        # Should execute two queries (org-specific not found, then global)
        assert mock_session.execute.call_count == 2

    async def test_name_only_in_org_returns_org_specific(self, mock_session, org_id):
        """When name only exists in org scope, return org-specific."""
        from src.repositories.data_providers import DataProviderRepository

        org_provider = make_workflow("shared_provider", org_id, "data_provider")

        # First query (org-specific) returns the org provider
        mock_result_org = MagicMock()
        mock_result_org.scalar_one_or_none.return_value = org_provider
        mock_session.execute.return_value = mock_result_org

        # OrgScopedRepository takes org_id in constructor
        repo = DataProviderRepository(mock_session, org_id=org_id, is_superuser=True)
        result = await repo.get_by_name("shared_provider")

        assert result is not None
        assert result.id == org_provider.id
        assert result.organization_id == org_id

    async def test_no_org_id_only_checks_global(self, mock_session):
        """When no org_id provided, only check global scope."""
        from src.repositories.data_providers import DataProviderRepository

        global_provider = make_workflow("shared_provider", None, "data_provider")

        # Only global query should be executed
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = global_provider
        mock_session.execute.return_value = mock_result

        # OrgScopedRepository with org_id=None means global-only scope
        repo = DataProviderRepository(mock_session, org_id=None, is_superuser=True)
        result = await repo.get_by_name("shared_provider")

        assert result is not None
        assert result.id == global_provider.id
        # Should only execute one query (global only)
        assert mock_session.execute.call_count == 1
