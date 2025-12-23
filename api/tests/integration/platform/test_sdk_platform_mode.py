"""
Platform Integration Tests for Bifrost SDK.

Tests all SDK modules in platform mode with real database.
Verifies SDK methods work correctly with actual PostgreSQL database
and respect organization context.

Modules tested:
- integrations: get, list_mappings
- config: get, set, list, delete
- oauth: get
- files: read, write, list, delete, exists
- organizations: list, get, create, update, delete
- workflows: list, get
- forms: list, get
- executions: list, get
- roles: list, get, create, update, delete

Reference patterns:
- test_sdk_from_workflow.py for context setup
- test_bifrost_sdk_security.py for platform test patterns
- test_sdk_integrations.py for SDK method patterns
"""

from __future__ import annotations

import json
import pytest
from datetime import datetime
from pathlib import Path
from typing import AsyncGenerator
from unittest.mock import MagicMock, AsyncMock, patch
from uuid import uuid4, UUID

from sqlalchemy.ext.asyncio import AsyncSession
from bifrost._context import set_execution_context, clear_execution_context

# Import ORM models
from src.models.orm.integrations import Integration, IntegrationMapping, IntegrationConfigSchema
from src.models.orm.config import Config
from src.models.orm.oauth import OAuthProvider, OAuthConnection
from src.models.orm.organizations import Organization
from src.models.orm.workflows import Workflow
from src.models.orm.forms import Form
from src.models.orm.executions import Execution
from src.models.orm.users import Role
from src.models.enums import ConfigType, ExecutionStatus


@pytest.fixture
def test_org_id():
    """Generate unique test organization ID."""
    return uuid4()


@pytest.fixture
def other_org_id():
    """Generate another test organization ID."""
    return uuid4()


@pytest.fixture
async def test_org(db_session: AsyncSession, test_org_id: UUID) -> Organization:
    """Create test organization in database."""
    org = Organization(
        id=test_org_id,
        name="Test Organization",
        domain="test.example.com",
        is_active=True,
        created_by="test-user",
    )
    db_session.add(org)
    await db_session.commit()
    await db_session.refresh(org)
    return org


@pytest.fixture
async def other_org(db_session: AsyncSession, other_org_id: UUID) -> Organization:
    """Create another test organization in database."""
    org = Organization(
        id=other_org_id,
        name="Other Organization",
        domain="other.example.com",
        is_active=True,
        created_by="test-user",
    )
    db_session.add(org)
    await db_session.commit()
    await db_session.refresh(org)
    return org


@pytest.fixture
def test_context(test_org: Organization):
    """Create execution context for regular user."""
    from src.sdk.context import ExecutionContext, Organization as ContextOrg

    context_org = ContextOrg(
        id=str(test_org.id),
        name=test_org.name,
        is_active=test_org.is_active,
    )
    return ExecutionContext(
        user_id="test-user",
        email="test@example.com",
        name="Test User",
        scope=str(test_org.id),
        organization=context_org,
        is_platform_admin=False,
        is_function_key=False,
        execution_id="test-exec-123",
    )


@pytest.fixture
def admin_context(test_org: Organization):
    """Create execution context for platform admin."""
    from src.sdk.context import ExecutionContext, Organization as ContextOrg

    context_org = ContextOrg(
        id=str(test_org.id),
        name=test_org.name,
        is_active=test_org.is_active,
    )
    return ExecutionContext(
        user_id="admin-user",
        email="admin@example.com",
        name="Admin User",
        scope=str(test_org.id),
        organization=context_org,
        is_platform_admin=True,
        is_function_key=False,
        execution_id="admin-exec-456",
    )


@pytest.fixture(autouse=True)
def cleanup_context():
    """Ensure context is cleared after each test."""
    yield
    clear_execution_context()


# ==================== INTEGRATIONS SDK TESTS ====================


@pytest.mark.integration
class TestIntegrationsPlatformMode:
    """Test integrations SDK with real database."""

    @pytest.mark.asyncio
    async def test_get_returns_integration_with_config(
        self,
        db_session: AsyncSession,
        test_context,
        test_org: Organization,
    ):
        """Test integrations.get() retrieves integration with merged config."""
        from bifrost import integrations

        # Create integration with config schema
        integration = Integration(
            name="TestIntegration",
            entity_id=None,
        )
        db_session.add(integration)
        await db_session.flush()

        # Add config schema
        schema_item = IntegrationConfigSchema(
            integration_id=integration.id,
            key="api_url",
            type="string",
            required=True,
            description="API URL",
            position=1,
        )
        db_session.add(schema_item)
        await db_session.flush()

        # Create mapping
        mapping = IntegrationMapping(
            integration_id=integration.id,
            organization_id=test_org.id,
            entity_id="tenant-123",
            entity_name="Test Tenant",
        )
        db_session.add(mapping)

        # Add config value
        config = Config(
            key="api_url",
            value={"value": "https://api.test.com"},
            config_type=ConfigType.STRING,
            organization_id=test_org.id,
            integration_id=integration.id,
            config_schema_id=schema_item.id,
            updated_by="test-user",
        )
        db_session.add(config)
        await db_session.commit()

        # Set context and call SDK
        set_execution_context(test_context)

        # Mock database context
        from contextlib import asynccontextmanager

        @asynccontextmanager
        async def mock_db_context():
            yield db_session

        with patch("src.core.database.get_db_context", mock_db_context):
            result = await integrations.get("TestIntegration")

        assert result is not None
        assert result["entity_id"] == "tenant-123"
        assert result["entity_name"] == "Test Tenant"
        assert result["config"]["api_url"] == "https://api.test.com"

    @pytest.mark.asyncio
    async def test_get_returns_none_when_not_found(
        self,
        db_session: AsyncSession,
        test_context,
    ):
        """Test integrations.get() returns None when integration doesn't exist."""
        from bifrost import integrations

        set_execution_context(test_context)

        from contextlib import asynccontextmanager

        @asynccontextmanager
        async def mock_db_context():
            yield db_session

        with patch("src.core.database.get_db_context", mock_db_context):
            result = await integrations.get("NonexistentIntegration")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_respects_org_context(
        self,
        db_session: AsyncSession,
        test_context,
        test_org: Organization,
        other_org: Organization,
    ):
        """Test integrations.get() only returns mapping for context org."""
        from bifrost import integrations

        # Create integration
        integration = Integration(name="MultiOrgIntegration")
        db_session.add(integration)
        await db_session.flush()

        # Create mapping for test org
        mapping1 = IntegrationMapping(
            integration_id=integration.id,
            organization_id=test_org.id,
            entity_id="test-tenant",
        )
        db_session.add(mapping1)

        # Create mapping for other org
        mapping2 = IntegrationMapping(
            integration_id=integration.id,
            organization_id=other_org.id,
            entity_id="other-tenant",
        )
        db_session.add(mapping2)
        await db_session.commit()

        # Set context for test org
        set_execution_context(test_context)

        from contextlib import asynccontextmanager

        @asynccontextmanager
        async def mock_db_context():
            yield db_session

        with patch("src.core.database.get_db_context", mock_db_context):
            result = await integrations.get("MultiOrgIntegration")

        # Should only get test org's mapping
        assert result is not None
        assert result["entity_id"] == "test-tenant"

    @pytest.mark.asyncio
    async def test_list_mappings_returns_all_org_mappings(
        self,
        db_session: AsyncSession,
        test_context,
        test_org: Organization,
        other_org: Organization,
    ):
        """Test integrations.list_mappings() returns all organization mappings."""
        from bifrost import integrations

        # Create integration
        integration = Integration(name="GlobalIntegration")
        db_session.add(integration)
        await db_session.flush()

        # Create mappings for multiple orgs
        mapping1 = IntegrationMapping(
            integration_id=integration.id,
            organization_id=test_org.id,
            entity_id="tenant-1",
            entity_name="Tenant One",
        )
        mapping2 = IntegrationMapping(
            integration_id=integration.id,
            organization_id=other_org.id,
            entity_id="tenant-2",
            entity_name="Tenant Two",
        )
        db_session.add_all([mapping1, mapping2])
        await db_session.commit()

        set_execution_context(test_context)

        from contextlib import asynccontextmanager

        @asynccontextmanager
        async def mock_db_context():
            yield db_session

        with patch("src.core.database.get_db_context", mock_db_context):
            result = await integrations.list_mappings("GlobalIntegration")

        assert result is not None
        assert len(result) == 2
        org_ids = {r["organization_id"] for r in result}
        assert str(test_org.id) in org_ids
        assert str(other_org.id) in org_ids


# ==================== CONFIG SDK TESTS ====================


@pytest.mark.integration
class TestConfigPlatformMode:
    """Test config SDK with real Redis cache."""

    @pytest.mark.asyncio
    async def test_get_reads_from_redis_cache(
        self,
        test_context,
        test_org: Organization,
    ):
        """Test config.get() reads from Redis cache in platform mode."""
        from bifrost import config
        from src.core.cache import config_hash_key, get_redis

        set_execution_context(test_context)

        # Write test data to Redis
        cache_data = {
            "value": "https://api.example.com",
            "type": "string",
        }
        async with get_redis() as r:
            await r.hset(  # type: ignore[misc]
                config_hash_key(str(test_org.id)),
                "api_url",
                json.dumps(cache_data),
            )

        # Read via SDK
        result = await config.get("api_url")

        assert result == "https://api.example.com"

    @pytest.mark.asyncio
    async def test_get_returns_default_when_key_not_found(
        self,
        test_context,
    ):
        """Test config.get() returns default value when key doesn't exist."""
        from bifrost import config

        set_execution_context(test_context)

        result = await config.get("nonexistent_key", default="default_value")

        assert result == "default_value"

    @pytest.mark.asyncio
    async def test_get_handles_different_types(
        self,
        test_context,
        test_org: Organization,
    ):
        """Test config.get() correctly parses different data types."""
        from bifrost import config
        from src.core.cache import config_hash_key, get_redis

        set_execution_context(test_context)

        # Write different types to Redis
        async with get_redis() as r:
            hash_key = config_hash_key(str(test_org.id))
            await r.hset(hash_key, "string_val", json.dumps({"value": "text", "type": "string"}))  # type: ignore[misc]
            await r.hset(hash_key, "int_val", json.dumps({"value": 42, "type": "int"}))  # type: ignore[misc]
            await r.hset(hash_key, "bool_val", json.dumps({"value": True, "type": "bool"}))  # type: ignore[misc]
            await r.hset(hash_key, "json_val", json.dumps({"value": {"key": "val"}, "type": "json"}))  # type: ignore[misc]

        # Read via SDK
        string_val = await config.get("string_val")
        assert string_val == "text"
        int_val = await config.get("int_val")
        assert int_val == 42
        bool_val = await config.get("bool_val")
        assert bool_val is True
        result_json = await config.get("json_val")
        assert result_json == {"key": "val"}

    @pytest.mark.asyncio
    async def test_set_writes_to_buffer(
        self,
        test_context,
    ):
        """Test config.set() writes to write buffer in platform mode."""
        from bifrost import config

        set_execution_context(test_context)

        with patch("bifrost._write_buffer.get_write_buffer") as mock_get_buffer:
            mock_buffer = MagicMock()
            mock_buffer.add_config_change = AsyncMock()
            mock_get_buffer.return_value = mock_buffer

            await config.set("new_key", "new_value")

            mock_buffer.add_config_change.assert_called_once()
            call_kwargs = mock_buffer.add_config_change.call_args[1]
            assert call_kwargs["key"] == "new_key"
            assert call_kwargs["value"] == "new_value"
            assert call_kwargs["operation"] == "set"

    @pytest.mark.asyncio
    async def test_list_returns_all_config_keys(
        self,
        test_context,
        test_org: Organization,
    ):
        """Test config.list() returns all configuration key-value pairs."""
        from bifrost import config
        from src.core.cache import config_hash_key, get_redis

        set_execution_context(test_context)

        # Write multiple configs to Redis
        async with get_redis() as r:
            hash_key = config_hash_key(str(test_org.id))
            await r.hset(hash_key, "key1", json.dumps({"value": "val1", "type": "string"}))  # type: ignore[misc]
            await r.hset(hash_key, "key2", json.dumps({"value": 100, "type": "int"}))  # type: ignore[misc]
            await r.hset(hash_key, "key3", json.dumps({"value": True, "type": "bool"}))  # type: ignore[misc]

        result = await config.list()

        assert len(result) == 3
        key1_val = result["key1"]
        assert key1_val == "val1"
        key2_val = result["key2"]
        assert key2_val == 100
        key3_val = result["key3"]
        assert key3_val is True

    @pytest.mark.asyncio
    async def test_delete_writes_to_buffer(
        self,
        test_context,
        test_org: Organization,
    ):
        """Test config.delete() writes deletion to buffer."""
        from bifrost import config

        set_execution_context(test_context)

        with patch("bifrost._write_buffer.get_write_buffer") as mock_get_buffer:
            mock_buffer = MagicMock()
            mock_buffer.add_config_change = AsyncMock()
            mock_get_buffer.return_value = mock_buffer

            result = await config.delete("old_key")

            assert result is True
            mock_buffer.add_config_change.assert_called_once()
            call_kwargs = mock_buffer.add_config_change.call_args[1]
            assert call_kwargs["key"] == "old_key"
            assert call_kwargs["operation"] == "delete"

    @pytest.mark.asyncio
    async def test_get_with_explicit_org_id(
        self,
        admin_context,
        test_org: Organization,
        other_org: Organization,
    ):
        """Test config.get() can access other org's config with explicit org_id."""
        from bifrost import config
        from src.core.cache import config_hash_key, get_redis

        set_execution_context(admin_context)

        # Write config for other org
        async with get_redis() as r:
            await r.hset(  # type: ignore[misc]
                config_hash_key(str(other_org.id)),
                "other_key",
                json.dumps({"value": "other_value", "type": "string"}),
            )

        # Access other org's config
        result = await config.get("other_key", org_id=str(other_org.id))

        assert result == "other_value"


# ==================== OAUTH SDK TESTS ====================


@pytest.mark.integration
class TestOAuthPlatformMode:
    """Test oauth SDK with real Redis cache."""

    @pytest.mark.asyncio
    async def test_get_returns_oauth_connection(
        self,
        test_context,
        test_org: Organization,
    ):
        """Test oauth.get() retrieves OAuth connection from Redis."""
        from bifrost import oauth
        from src.core.cache import oauth_hash_key, get_redis

        set_execution_context(test_context)

        # Write OAuth data to Redis
        oauth_data = {
            "provider_name": "microsoft",
            "client_id": "client-123",
            "client_secret": "secret-456",
            "authorization_url": "https://login.microsoft.com/authorize",
            "token_url": "https://login.microsoft.com/token",
            "scopes": ["openid", "profile", "email"],
            "access_token": "access-token-xyz",
            "refresh_token": "refresh-token-abc",
            "expires_at": None,
        }
        async with get_redis() as r:
            await r.hset(  # type: ignore[misc]
                oauth_hash_key(str(test_org.id)),
                "microsoft",
                json.dumps(oauth_data),
            )

        result = await oauth.get("microsoft")

        assert result is not None
        assert result["connection_name"] == "microsoft"
        assert result["client_id"] == "client-123"
        assert result["client_secret"] == "secret-456"
        assert result["access_token"] == "access-token-xyz"
        assert result["scopes"] == ["openid", "profile", "email"]

    @pytest.mark.asyncio
    async def test_get_returns_none_when_not_found(
        self,
        test_context,
    ):
        """Test oauth.get() returns None when provider not found."""
        from bifrost import oauth

        set_execution_context(test_context)

        result = await oauth.get("nonexistent_provider")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_with_explicit_org_id(
        self,
        admin_context,
        other_org: Organization,
    ):
        """Test oauth.get() can access other org's OAuth with explicit org_id."""
        from bifrost import oauth
        from src.core.cache import oauth_hash_key, get_redis

        set_execution_context(admin_context)

        # Write OAuth for other org
        oauth_data = {
            "provider_name": "partner_center",
            "client_id": "other-client",
            "client_secret": "other-secret",
            "authorization_url": None,
            "token_url": "https://login.partner.com/token",
            "scopes": ["read", "write"],
            "access_token": None,
            "refresh_token": None,
            "expires_at": None,
        }
        async with get_redis() as r:
            await r.hset(  # type: ignore[misc]
                oauth_hash_key(str(other_org.id)),
                "partner_center",
                json.dumps(oauth_data),
            )

        result = await oauth.get("partner_center", org_id=str(other_org.id))

        assert result is not None
        assert result["client_id"] == "other-client"


# ==================== FILES SDK TESTS ====================


@pytest.mark.integration
class TestFilesPlatformMode:
    """Test files SDK with real filesystem."""

    @pytest.mark.asyncio
    async def test_write_and_read_workspace_file(
        self,
        test_context,
    ):
        """Test files.write() and files.read() for workspace files."""
        from bifrost import files

        set_execution_context(test_context)

        test_content = b"Hello, workspace!"
        test_path = f"test-{uuid4()}.txt"

        try:
            # Write file
            await files.write(test_path, test_content, location="workspace")

            # Read file
            result = await files.read(test_path, location="workspace")

            assert result == test_content
        finally:
            # Cleanup
            try:
                await files.delete(test_path, location="workspace")
            except Exception:
                pass

    @pytest.mark.asyncio
    async def test_exists_returns_true_for_existing_file(
        self,
        test_context,
    ):
        """Test files.exists() returns True for existing file."""
        from bifrost import files

        set_execution_context(test_context)

        test_path = f"exists-test-{uuid4()}.txt"

        try:
            await files.write(test_path, b"test", location="workspace")

            result = await files.exists(test_path, location="workspace")

            assert result is True
        finally:
            try:
                await files.delete(test_path, location="workspace")
            except Exception:
                pass

    @pytest.mark.asyncio
    async def test_exists_returns_false_for_nonexistent_file(
        self,
        test_context,
    ):
        """Test files.exists() returns False for nonexistent file."""
        from bifrost import files

        set_execution_context(test_context)

        result = await files.exists(f"nonexistent-{uuid4()}.txt", location="workspace")

        assert result is False

    @pytest.mark.asyncio
    async def test_list_returns_files_in_directory(
        self,
        test_context,
    ):
        """Test files.list() returns files in directory."""
        from bifrost import files

        set_execution_context(test_context)

        test_dir = f"list-test-{uuid4()}"
        test_files = [f"{test_dir}/file1.txt", f"{test_dir}/file2.txt"]

        try:
            # Create test files
            for file_path in test_files:
                await files.write(file_path, b"test", location="workspace")

            # List files
            result = await files.list(test_dir, location="workspace")

            assert len(result) >= 2
            file_names = [f["name"] for f in result]
            assert "file1.txt" in file_names
            assert "file2.txt" in file_names
        finally:
            # Cleanup
            for file_path in test_files:
                try:
                    await files.delete(file_path, location="workspace")
                except Exception:
                    pass

    @pytest.mark.asyncio
    async def test_delete_removes_file(
        self,
        test_context,
    ):
        """Test files.delete() removes file."""
        from bifrost import files

        set_execution_context(test_context)

        test_path = f"delete-test-{uuid4()}.txt"

        # Create file
        await files.write(test_path, b"test", location="workspace")
        assert await files.exists(test_path, location="workspace")

        # Delete file
        await files.delete(test_path, location="workspace")

        # Verify deleted
        assert not await files.exists(test_path, location="workspace")


# ==================== ORGANIZATIONS SDK TESTS ====================


@pytest.mark.integration
class TestOrganizationsPlatformMode:
    """Test organizations SDK with real database and Redis."""

    @pytest.mark.asyncio
    async def test_list_returns_organizations_from_cache(
        self,
        admin_context,
        test_org: Organization,
        other_org: Organization,
    ):
        """Test organizations.list() returns orgs from Redis cache."""
        from bifrost import organizations
        from src.core.cache import orgs_list_key, get_redis

        set_execution_context(admin_context)

        # Write orgs to Redis cache
        async with get_redis() as r:
            org_data = [
                {
                    "id": str(test_org.id),
                    "name": test_org.name,
                    "domain": test_org.domain,
                    "is_active": test_org.is_active,
                    "created_by": test_org.created_by,
                    "created_at": test_org.created_at.isoformat(),
                    "updated_at": test_org.updated_at.isoformat(),
                },
                {
                    "id": str(other_org.id),
                    "name": other_org.name,
                    "domain": other_org.domain,
                    "is_active": other_org.is_active,
                    "created_by": other_org.created_by,
                    "created_at": other_org.created_at.isoformat(),
                    "updated_at": other_org.updated_at.isoformat(),
                },
            ]
            await r.set(orgs_list_key(), json.dumps(org_data))

        result = await organizations.list()

        assert len(result) >= 2
        org_ids = {org.id for org in result}
        assert str(test_org.id) in org_ids
        assert str(other_org.id) in org_ids

    @pytest.mark.asyncio
    async def test_get_returns_organization_from_cache(
        self,
        admin_context,
        test_org: Organization,
    ):
        """Test organizations.get() returns org from Redis cache."""
        from bifrost import organizations
        from src.core.cache import org_key, get_redis

        set_execution_context(admin_context)

        # Write org to Redis cache
        async with get_redis() as r:
            org_data = {
                "id": str(test_org.id),
                "name": test_org.name,
                "domain": test_org.domain,
                "is_active": test_org.is_active,
                "created_by": test_org.created_by,
                "created_at": test_org.created_at.isoformat(),
                "updated_at": test_org.updated_at.isoformat(),
            }
            await r.set(org_key(str(test_org.id)), json.dumps(org_data))

        result = await organizations.get(str(test_org.id))

        assert result.id == str(test_org.id)
        assert result.name == test_org.name
        assert result.domain == test_org.domain

    @pytest.mark.asyncio
    async def test_create_writes_to_buffer(
        self,
        admin_context,
    ):
        """Test organizations.create() writes to buffer."""
        from bifrost import organizations

        set_execution_context(admin_context)

        with patch("bifrost._write_buffer.get_write_buffer") as mock_get_buffer:
            mock_buffer = MagicMock()
            mock_buffer.add_org_change = AsyncMock(return_value=str(uuid4()))
            mock_get_buffer.return_value = mock_buffer

            result = await organizations.create("New Org", domain="neworg.com")

            assert result.name == "New Org"
            assert result.domain == "neworg.com"
            mock_buffer.add_org_change.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_writes_to_buffer(
        self,
        admin_context,
        test_org: Organization,
    ):
        """Test organizations.update() writes to buffer."""
        from bifrost import organizations

        set_execution_context(admin_context)

        with patch("bifrost._write_buffer.get_write_buffer") as mock_get_buffer:
            mock_buffer = MagicMock()
            mock_buffer.add_org_change = AsyncMock()
            mock_get_buffer.return_value = mock_buffer

            await organizations.update(str(test_org.id), name="Updated Name")

            mock_buffer.add_org_change.assert_called_once()
            call_kwargs = mock_buffer.add_org_change.call_args[1]
            assert call_kwargs["operation"] == "update"
            assert call_kwargs["data"]["name"] == "Updated Name"

    @pytest.mark.asyncio
    async def test_delete_writes_to_buffer(
        self,
        admin_context,
        test_org: Organization,
    ):
        """Test organizations.delete() writes to buffer."""
        from bifrost import organizations

        set_execution_context(admin_context)

        with patch("bifrost._write_buffer.get_write_buffer") as mock_get_buffer:
            mock_buffer = MagicMock()
            mock_buffer.add_org_change = AsyncMock()
            mock_get_buffer.return_value = mock_buffer

            await organizations.delete(str(test_org.id))

            mock_buffer.add_org_change.assert_called_once()
            call_kwargs = mock_buffer.add_org_change.call_args[1]
            assert call_kwargs["operation"] == "delete"


# ==================== WORKFLOWS SDK TESTS ====================


@pytest.mark.integration
class TestWorkflowsPlatformMode:
    """Test workflows SDK with real database."""

    @pytest.mark.asyncio
    async def test_list_returns_active_workflows(
        self,
        db_session: AsyncSession,
        test_context,
        test_org: Organization,
    ):
        """Test workflows.list() returns active workflows from database."""
        from bifrost import workflows

        # Create workflows
        wf1 = Workflow(
            name="workflow1",
            description="First workflow",
            organization_id=test_org.id,
            file_path="/workflows/workflow1.py",
            is_active=True,
            execution_mode="sync",
            endpoint_enabled=True,
        )
        wf2 = Workflow(
            name="workflow2",
            description="Second workflow",
            organization_id=test_org.id,
            file_path="/workflows/workflow2.py",
            is_active=True,
            execution_mode="async",
            endpoint_enabled=False,
        )
        wf3 = Workflow(
            name="inactive_workflow",
            description="Inactive",
            organization_id=test_org.id,
            file_path="/workflows/inactive.py",
            is_active=False,
        )
        db_session.add_all([wf1, wf2, wf3])
        await db_session.commit()

        # Attach DB session to context
        test_context._db = db_session
        set_execution_context(test_context)

        result = await workflows.list()

        # Should return only active workflows
        assert len(result) == 2
        names = {wf["name"] for wf in result}
        assert "workflow1" in names
        assert "workflow2" in names
        assert "inactive_workflow" not in names

    @pytest.mark.asyncio
    async def test_get_returns_execution_details(
        self,
        db_session: AsyncSession,
        test_context,
        test_org: Organization,
    ):
        """Test workflows.get() returns execution details."""
        from bifrost import workflows

        # Create workflow and execution
        workflow = Workflow(
            name="test_workflow",
            description="Test",
            organization_id=test_org.id,
            file_path="/workflows/test.py",
            is_active=True,
        )
        db_session.add(workflow)
        await db_session.flush()

        execution = Execution(
            id="exec-123",
            workflow_id=workflow.id,
            organization_id=test_org.id,
            status=ExecutionStatus.COMPLETED,
            triggered_by="test-user",
            parameters={"key": "value"},
            result={"output": "success"},
        )
        db_session.add(execution)
        await db_session.commit()

        # Attach DB session to context
        test_context._db = db_session
        set_execution_context(test_context)

        result = await workflows.get("exec-123")

        assert result["id"] == "exec-123"
        assert result["status"] == "completed"
        assert result["result"] == {"output": "success"}


# ==================== FORMS SDK TESTS ====================


@pytest.mark.integration
class TestFormsPlatformMode:
    """Test forms SDK with real database."""

    @pytest.mark.asyncio
    async def test_list_returns_forms(
        self,
        db_session: AsyncSession,
        test_context,
        test_org: Organization,
    ):
        """Test forms.list() returns forms from database."""
        from bifrost import forms

        # Create forms
        form1 = Form(
            name="Form 1",
            description="Test form 1",
            organization_id=test_org.id,
            form_schema={"fields": []},
            is_public=False,
            is_active=True,
        )
        form2 = Form(
            name="Form 2",
            description="Test form 2",
            organization_id=test_org.id,
            form_schema={"fields": []},
            is_public=True,
            is_active=True,
        )
        db_session.add_all([form1, form2])
        await db_session.commit()

        # Attach DB session to context
        test_context._db = db_session
        set_execution_context(test_context)

        result = await forms.list()

        assert len(result) >= 2
        names = {f["name"] for f in result}
        assert "Form 1" in names
        assert "Form 2" in names

    @pytest.mark.asyncio
    async def test_get_returns_form_details(
        self,
        db_session: AsyncSession,
        test_context,
        test_org: Organization,
    ):
        """Test forms.get() returns form details."""
        from bifrost import forms

        # Create form
        form = Form(
            id=uuid4(),
            name="Test Form",
            description="Form description",
            organization_id=test_org.id,
            form_schema={"fields": [{"name": "email", "type": "text"}]},
            is_public=False,
            is_active=True,
        )
        db_session.add(form)
        await db_session.commit()

        # Attach DB session to context
        test_context._db = db_session
        set_execution_context(test_context)

        result = await forms.get(str(form.id))

        assert result["id"] == str(form.id)
        assert result["name"] == "Test Form"
        assert result["description"] == "Form description"


# ==================== EXECUTIONS SDK TESTS ====================


@pytest.mark.integration
class TestExecutionsPlatformMode:
    """Test executions SDK with real database."""

    @pytest.mark.asyncio
    async def test_list_returns_executions(
        self,
        db_session: AsyncSession,
        test_context,
        test_org: Organization,
    ):
        """Test executions.list() returns executions from database."""
        from bifrost import executions

        # Create workflow
        workflow = Workflow(
            name="test_workflow",
            organization_id=test_org.id,
            file_path="/workflows/test.py",
            is_active=True,
        )
        db_session.add(workflow)
        await db_session.flush()

        # Create executions
        exec1 = Execution(
            id="exec-1",
            workflow_id=workflow.id,
            organization_id=test_org.id,
            status=ExecutionStatus.COMPLETED,
            triggered_by="test-user",
        )
        exec2 = Execution(
            id="exec-2",
            workflow_id=workflow.id,
            organization_id=test_org.id,
            status=ExecutionStatus.RUNNING,
            triggered_by="test-user",
        )
        db_session.add_all([exec1, exec2])
        await db_session.commit()

        # Attach DB session to context
        test_context._db = db_session
        set_execution_context(test_context)

        result = await executions.list()

        assert len(result) >= 2
        exec_ids = {e["id"] for e in result}
        assert "exec-1" in exec_ids
        assert "exec-2" in exec_ids

    @pytest.mark.asyncio
    async def test_get_returns_execution_details(
        self,
        db_session: AsyncSession,
        test_context,
        test_org: Organization,
    ):
        """Test executions.get() returns execution details."""
        from bifrost import executions

        # Create workflow and execution
        workflow = Workflow(
            name="test_workflow",
            organization_id=test_org.id,
            file_path="/workflows/test.py",
            is_active=True,
        )
        db_session.add(workflow)
        await db_session.flush()

        execution = Execution(
            id="exec-detail",
            workflow_id=workflow.id,
            organization_id=test_org.id,
            status=ExecutionStatus.COMPLETED,
            triggered_by="test-user",
            parameters={"input": "data"},
            result={"output": "result"},
        )
        db_session.add(execution)
        await db_session.commit()

        # Attach DB session to context
        test_context._db = db_session
        set_execution_context(test_context)

        result = await executions.get("exec-detail")

        assert result["id"] == "exec-detail"
        assert result["status"] == "completed"
        assert result["parameters"] == {"input": "data"}
        assert result["result"] == {"output": "result"}


# ==================== ROLES SDK TESTS ====================


@pytest.mark.integration
class TestRolesPlatformMode:
    """Test roles SDK with real database."""

    @pytest.mark.asyncio
    async def test_list_returns_roles(
        self,
        db_session: AsyncSession,
        test_context,
        test_org: Organization,
    ):
        """Test roles.list() returns roles from Redis cache."""
        from bifrost import roles
        from src.core.cache import roles_hash_key, get_redis

        # Attach DB session to context
        test_context._db = db_session
        set_execution_context(test_context)

        # Write roles to Redis cache
        async with get_redis() as r:
            hash_key = roles_hash_key(str(test_org.id))
            role1_id = str(uuid4())
            role2_id = str(uuid4())
            await r.hset(hash_key, role1_id, json.dumps({  # type: ignore[misc]
                "id": role1_id,
                "name": "Admin",
                "description": "Admin role",
                "is_active": True,
                "created_by": "test-user",
                "created_at": datetime.utcnow().isoformat(),
                "updated_at": datetime.utcnow().isoformat(),
            }))
            await r.hset(hash_key, role2_id, json.dumps({  # type: ignore[misc]
                "id": role2_id,
                "name": "User",
                "description": "User role",
                "is_active": True,
                "created_by": "test-user",
                "created_at": datetime.utcnow().isoformat(),
                "updated_at": datetime.utcnow().isoformat(),
            }))

        result = await roles.list()

        assert len(result) >= 2
        role_names = {r.name for r in result}
        assert "Admin" in role_names
        assert "User" in role_names

    @pytest.mark.asyncio
    async def test_get_returns_role_details(
        self,
        db_session: AsyncSession,
        test_context,
        test_org: Organization,
    ):
        """Test roles.get() returns role details from Redis cache."""
        from bifrost import roles
        from src.core.cache import roles_hash_key, get_redis

        # Attach DB session to context
        test_context._db = db_session
        set_execution_context(test_context)

        # Write role to Redis cache
        role_id = str(uuid4())
        async with get_redis() as r:
            hash_key = roles_hash_key(str(test_org.id))
            await r.hset(hash_key, role_id, json.dumps({  # type: ignore[misc]
                "id": role_id,
                "name": "Manager",
                "description": "Manager role",
                "is_active": True,
                "created_by": "test-user",
                "created_at": datetime.utcnow().isoformat(),
                "updated_at": datetime.utcnow().isoformat(),
            }))

        result = await roles.get(role_id)

        assert result.id == role_id
        assert result.name == "Manager"
        assert result.description == "Manager role"

    @pytest.mark.asyncio
    async def test_create_writes_to_buffer(
        self,
        admin_context,
        test_org: Organization,
    ):
        """Test roles.create() writes to buffer."""
        from bifrost import roles

        # Attach DB session to context (needed for context validation)
        admin_context._db = MagicMock()
        set_execution_context(admin_context)

        with patch("bifrost._write_buffer.get_write_buffer") as mock_get_buffer:
            mock_buffer = MagicMock()
            mock_buffer.add_role_change = AsyncMock(return_value=str(uuid4()))
            mock_get_buffer.return_value = mock_buffer

            result = await roles.create(
                name="New Role",
                description="New role description",
            )

            assert result.name == "New Role"
            mock_buffer.add_role_change.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_writes_to_buffer(
        self,
        db_session: AsyncSession,
        admin_context,
        test_org: Organization,
    ):
        """Test roles.update() writes to buffer."""
        from bifrost import roles

        # Create role
        role = Role(
            id=uuid4(),
            name="Original Role",
            organization_id=test_org.id,
            is_active=True,
        )
        db_session.add(role)
        await db_session.commit()

        # Attach DB session to context
        admin_context._db = db_session
        set_execution_context(admin_context)

        with patch("bifrost._write_buffer.get_write_buffer") as mock_get_buffer:
            mock_buffer = MagicMock()
            mock_buffer.add_role_change = AsyncMock()
            mock_get_buffer.return_value = mock_buffer

            await roles.update(str(role.id), name="Updated Role")

            mock_buffer.add_role_change.assert_called_once()
            call_kwargs = mock_buffer.add_role_change.call_args[1]
            assert call_kwargs["operation"] == "update"

    @pytest.mark.asyncio
    async def test_delete_writes_to_buffer(
        self,
        db_session: AsyncSession,
        admin_context,
        test_org: Organization,
    ):
        """Test roles.delete() writes to buffer."""
        from bifrost import roles

        # Create role
        role = Role(
            id=uuid4(),
            name="Delete Me",
            organization_id=test_org.id,
            is_active=True,
        )
        db_session.add(role)
        await db_session.commit()

        # Attach DB session to context
        admin_context._db = db_session
        set_execution_context(admin_context)

        with patch("bifrost._write_buffer.get_write_buffer") as mock_get_buffer:
            mock_buffer = MagicMock()
            mock_buffer.add_role_change = AsyncMock()
            mock_get_buffer.return_value = mock_buffer

            await roles.delete(str(role.id))

            mock_buffer.add_role_change.assert_called_once()
            call_kwargs = mock_buffer.add_role_change.call_args[1]
            assert call_kwargs["operation"] == "delete"
