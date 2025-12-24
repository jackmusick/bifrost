"""
Platform Integration Tests for Bifrost SDK.

Tests all SDK modules in platform mode with real database.
Verifies SDK methods work correctly with actual PostgreSQL database
and respect organization context.

Modules tested:
- integrations: get, list_mappings
- config: get, set, list, delete
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
from unittest.mock import MagicMock, AsyncMock, patch
from uuid import uuid4, UUID

from sqlalchemy.ext.asyncio import AsyncSession
from bifrost._context import set_execution_context, clear_execution_context

# Import ORM models
from src.models.orm.integrations import Integration, IntegrationMapping, IntegrationConfigSchema
from src.models.orm.config import Config
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

    user_uuid = uuid4()
    context_org = ContextOrg(
        id=str(test_org.id),
        name=test_org.name,
        is_active=test_org.is_active,
    )
    return ExecutionContext(
        user_id=str(user_uuid),
        email=f"test-{user_uuid.hex[:8]}@example.com",
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
        user_id=str(uuid4()),
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
        assert result.entity_id == "tenant-123"
        assert result.entity_name == "Test Tenant"
        assert result.config["api_url"] == "https://api.test.com"

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
        assert result.entity_id == "test-tenant"

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
        org_ids = {str(r.organization_id) for r in result}
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
            await files.write_bytes(test_path, test_content, location="workspace")

            # Read file
            result = await files.read_bytes(test_path, location="workspace")

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
            await files.write_bytes(test_path, b"test", location="workspace")

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
                await files.write_bytes(file_path, b"test", location="workspace")

            # List files
            result = await files.list(test_dir, location="workspace")

            assert len(result) >= 2
            assert "file1.txt" in result
            assert "file2.txt" in result
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
        await files.write_bytes(test_path, b"test", location="workspace")
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
            from src.core.cache import org_key

            # Delete key first to avoid WRONGTYPE error
            await r.delete(orgs_list_key())  # type: ignore[misc]

            # Add org IDs to the set
            await r.sadd(orgs_list_key(), str(test_org.id), str(other_org.id))  # type: ignore[misc]

            # Add individual org data to their keys
            test_org_data = {
                "id": str(test_org.id),
                "name": test_org.name,
                "domain": test_org.domain,
                "is_active": test_org.is_active,
                "created_by": test_org.created_by,
                "created_at": test_org.created_at.isoformat(),
                "updated_at": test_org.updated_at.isoformat(),
            }
            other_org_data = {
                "id": str(other_org.id),
                "name": other_org.name,
                "domain": other_org.domain,
                "is_active": other_org.is_active,
                "created_by": other_org.created_by,
                "created_at": other_org.created_at.isoformat(),
                "updated_at": other_org.updated_at.isoformat(),
            }
            await r.set(org_key(str(test_org.id)), json.dumps(test_org_data))  # type: ignore[misc]
            await r.set(org_key(str(other_org.id)), json.dumps(other_org_data))  # type: ignore[misc]

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
        from bifrost._write_buffer import WriteBuffer, set_write_buffer

        set_execution_context(admin_context)

        # Create actual write buffer
        buffer = WriteBuffer(
            execution_id=admin_context.execution_id,
            org_id=str(admin_context.organization.id) if admin_context.organization else None,
            user_id=admin_context.user_id,
        )
        set_write_buffer(buffer)

        try:
            result = await organizations.create("New Org", domain="neworg.com")

            assert result.name == "New Org"
            assert result.domain == "neworg.com"

            # Verify buffer has pending changes
            assert await buffer.has_pending_changes()
        finally:
            buffer.close()

    @pytest.mark.asyncio
    async def test_update_writes_to_buffer(
        self,
        admin_context,
        test_org: Organization,
    ):
        """Test organizations.update() writes to buffer."""
        from bifrost import organizations
        from bifrost._write_buffer import WriteBuffer, set_write_buffer
        from src.core.cache import org_key, get_redis

        set_execution_context(admin_context)

        # Write org to Redis cache (required for update to find it)
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
            await r.set(org_key(str(test_org.id)), json.dumps(org_data))  # type: ignore[misc]

        # Create actual write buffer
        buffer = WriteBuffer(
            execution_id=admin_context.execution_id,
            org_id=str(admin_context.organization.id) if admin_context.organization else None,
            user_id=admin_context.user_id,
        )
        set_write_buffer(buffer)

        try:
            await organizations.update(str(test_org.id), name="Updated Name")

            # Verify buffer has pending changes
            assert await buffer.has_pending_changes()
        finally:
            buffer.close()

    @pytest.mark.asyncio
    async def test_delete_writes_to_buffer(
        self,
        admin_context,
        test_org: Organization,
    ):
        """Test organizations.delete() writes to buffer."""
        from bifrost import organizations
        from bifrost._write_buffer import WriteBuffer, set_write_buffer
        from src.core.cache import org_key, get_redis

        set_execution_context(admin_context)

        # Write org to Redis cache (required for delete to find it)
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
            await r.set(org_key(str(test_org.id)), json.dumps(org_data))  # type: ignore[misc]

        # Create actual write buffer
        buffer = WriteBuffer(
            execution_id=admin_context.execution_id,
            org_id=str(admin_context.organization.id) if admin_context.organization else None,
            user_id=admin_context.user_id,
        )
        set_write_buffer(buffer)

        try:
            await organizations.delete(str(test_org.id))

            # Verify buffer has pending changes
            assert await buffer.has_pending_changes()
        finally:
            buffer.close()


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
            function_name="workflow1",
            description="First workflow",
            file_path="/workflows/workflow1.py",
            is_active=True,
            execution_mode="sync",
            endpoint_enabled=True,
        )
        wf2 = Workflow(
            name="workflow2",
            function_name="workflow2",
            description="Second workflow",
            file_path="/workflows/workflow2.py",
            is_active=True,
            execution_mode="async",
            endpoint_enabled=False,
        )
        wf3 = Workflow(
            name="inactive_workflow",
            function_name="inactive_workflow",
            description="Inactive",
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
        names = {wf.name for wf in result}
        assert "workflow1" in names
        assert "workflow2" in names
        assert "inactive_workflow" not in names

    @pytest.mark.asyncio
    async def test_get_returns_execution_details(
        self,
        db_session: AsyncSession,
        async_session_factory,
        test_context,
        test_org: Organization,
    ):
        """Test workflows.get() returns execution details."""
        from bifrost import workflows
        from uuid import UUID
        from src.models.orm.users import User

        # Create workflow and execution
        workflow = Workflow(
            name=f"test_workflow_{uuid4().hex[:8]}",
            function_name=f"test_workflow_{uuid4().hex[:8]}",
            description="Test",
            file_path=f"/workflows/test_{uuid4().hex[:8]}.py",
            is_active=True,
        )
        db_session.add(workflow)
        await db_session.flush()

        # Create user that matches context user_id
        user_uuid = UUID(test_context.user_id)
        user = User(
            id=user_uuid,
            email=test_context.email,
            name=test_context.name,
            is_active=True,
        )
        db_session.add(user)
        await db_session.flush()

        execution = Execution(
            id=uuid4(),
            workflow_name=workflow.name,
            organization_id=test_org.id,
            status=ExecutionStatus.SUCCESS,
            executed_by=user_uuid,
            executed_by_name=test_context.name,
            parameters={"key": "value"},
            result={"output": "success"},
        )
        db_session.add(execution)
        await db_session.commit()

        # Attach DB session to context
        test_context._db = db_session
        set_execution_context(test_context)

        # Use test's session factory to avoid event loop mismatch
        # workflows.get() delegates to executions.get(), so patch executions module
        with patch("bifrost.executions.get_session_factory", return_value=async_session_factory):
            result = await workflows.get(str(execution.id))

        assert result.execution_id == str(execution.id)
        assert result.status == ExecutionStatus.SUCCESS
        assert result.result == {"output": "success"}


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
        """Test forms.list() returns forms from Redis cache."""
        from bifrost import forms
        from src.core.cache import forms_hash_key, user_forms_key, get_redis

        # Create forms in database
        form1 = Form(
            id=uuid4(),
            name="Form 1",
            description="Test form 1",
            organization_id=test_org.id,
            created_by="test-user",
            is_active=True,
        )
        form2 = Form(
            id=uuid4(),
            name="Form 2",
            description="Test form 2",
            organization_id=test_org.id,
            created_by="test-user",
            is_active=True,
        )
        db_session.add_all([form1, form2])
        await db_session.commit()

        # Write to Redis cache
        async with get_redis() as r:
            # Add form IDs to user's accessible forms set
            user_key = user_forms_key(str(test_org.id), test_context.user_id)
            await r.sadd(user_key, str(form1.id), str(form2.id))  # type: ignore[misc]

            # Add form data to forms hash
            hash_key = forms_hash_key(str(test_org.id))
            form1_data = {
                "id": str(form1.id),
                "name": form1.name,
                "description": form1.description,
                "organization_id": str(form1.organization_id),
                "is_active": form1.is_active,
                "created_by": form1.created_by,
                "created_at": form1.created_at.isoformat() if form1.created_at else None,
                "updated_at": form1.updated_at.isoformat() if form1.updated_at else None,
            }
            form2_data = {
                "id": str(form2.id),
                "name": form2.name,
                "description": form2.description,
                "organization_id": str(form2.organization_id),
                "is_active": form2.is_active,
                "created_by": form2.created_by,
                "created_at": form2.created_at.isoformat() if form2.created_at else None,
                "updated_at": form2.updated_at.isoformat() if form2.updated_at else None,
            }
            await r.hset(hash_key, str(form1.id), json.dumps(form1_data))  # type: ignore[misc]
            await r.hset(hash_key, str(form2.id), json.dumps(form2_data))  # type: ignore[misc]

        # Attach DB session to context
        test_context._db = db_session
        set_execution_context(test_context)

        result = await forms.list()

        assert len(result) >= 2
        names = {f.name for f in result}
        assert "Form 1" in names
        assert "Form 2" in names

    @pytest.mark.asyncio
    async def test_get_returns_form_details(
        self,
        db_session: AsyncSession,
        test_context,
        test_org: Organization,
    ):
        """Test forms.get() returns form details from Redis cache."""
        from bifrost import forms
        from src.core.cache import forms_hash_key, user_forms_key, get_redis

        # Create form in database
        form = Form(
            id=uuid4(),
            name="Test Form",
            description="Form description",
            organization_id=test_org.id,
            created_by="test-user",
            is_active=True,
        )
        db_session.add(form)
        await db_session.commit()

        # Write to Redis cache
        async with get_redis() as r:
            # Add form ID to user's accessible forms set
            user_key = user_forms_key(str(test_org.id), test_context.user_id)
            await r.sadd(user_key, str(form.id))  # type: ignore[misc]

            # Add form data to forms hash
            hash_key = forms_hash_key(str(test_org.id))
            form_data = {
                "id": str(form.id),
                "name": form.name,
                "description": form.description,
                "organization_id": str(form.organization_id),
                "is_active": form.is_active,
                "created_by": form.created_by,
                "created_at": form.created_at.isoformat() if form.created_at else None,
                "updated_at": form.updated_at.isoformat() if form.updated_at else None,
            }
            await r.hset(hash_key, str(form.id), json.dumps(form_data))  # type: ignore[misc]

        # Attach DB session to context
        test_context._db = db_session
        set_execution_context(test_context)

        result = await forms.get(str(form.id))

        assert str(result.id) == str(form.id)
        assert result.name == "Test Form"
        assert result.description == "Form description"


# ==================== EXECUTIONS SDK TESTS ====================


@pytest.mark.integration
class TestExecutionsPlatformMode:
    """Test executions SDK with real database."""

    @pytest.mark.asyncio
    async def test_list_returns_executions(
        self,
        db_session: AsyncSession,
        async_session_factory,
        test_context,
        test_org: Organization,
    ):
        """Test executions.list() returns executions from database."""
        from bifrost import executions
        from uuid import UUID
        from src.models.orm.users import User

        # Create workflow
        workflow = Workflow(
            name=f"test_workflow_{uuid4().hex[:8]}",
            function_name=f"test_workflow_{uuid4().hex[:8]}",
            file_path=f"/workflows/test_{uuid4().hex[:8]}.py",
            is_active=True,
        )
        db_session.add(workflow)
        await db_session.flush()

        # Create user that matches context user_id
        user_uuid = UUID(test_context.user_id)
        user = User(
            id=user_uuid,
            email=test_context.email,
            name=test_context.name,
            is_active=True,
        )
        db_session.add(user)
        await db_session.flush()

        # Create executions
        exec1 = Execution(
            id=uuid4(),
            workflow_name=workflow.name,
            organization_id=test_org.id,
            status=ExecutionStatus.SUCCESS,
            executed_by=user_uuid,
            executed_by_name=test_context.name,
        )
        exec2 = Execution(
            id=uuid4(),
            workflow_name=workflow.name,
            organization_id=test_org.id,
            status=ExecutionStatus.RUNNING,
            executed_by=user_uuid,
            executed_by_name=test_context.name,
        )
        db_session.add_all([exec1, exec2])
        await db_session.commit()

        # Attach DB session to context
        test_context._db = db_session
        set_execution_context(test_context)

        # Use test's session factory to avoid event loop mismatch
        with patch("bifrost.executions.get_session_factory", return_value=async_session_factory):
            result = await executions.list()

        assert len(result) >= 2
        exec_ids = {e.execution_id for e in result}
        assert str(exec1.id) in exec_ids
        assert str(exec2.id) in exec_ids

    @pytest.mark.asyncio
    async def test_get_returns_execution_details(
        self,
        db_session: AsyncSession,
        async_session_factory,
        test_context,
        test_org: Organization,
    ):
        """Test executions.get() returns execution details."""
        from bifrost import executions
        from uuid import UUID
        from src.models.orm.users import User

        # Create workflow and execution
        workflow = Workflow(
            name=f"test_workflow_{uuid4().hex[:8]}",
            function_name=f"test_workflow_{uuid4().hex[:8]}",
            file_path=f"/workflows/test_{uuid4().hex[:8]}.py",
            is_active=True,
        )
        db_session.add(workflow)
        await db_session.flush()

        # Create user that matches context user_id
        user_uuid = UUID(test_context.user_id)
        user = User(
            id=user_uuid,
            email=test_context.email,
            name=test_context.name,
            is_active=True,
        )
        db_session.add(user)
        await db_session.flush()

        execution = Execution(
            id=uuid4(),
            workflow_name=workflow.name,
            organization_id=test_org.id,
            status=ExecutionStatus.SUCCESS,
            executed_by=user_uuid,
            executed_by_name=test_context.name,
            parameters={"input": "data"},
            result={"output": "result"},
        )
        db_session.add(execution)
        await db_session.commit()

        # Attach DB session to context
        test_context._db = db_session
        set_execution_context(test_context)

        # Use test's session factory to avoid event loop mismatch
        with patch("bifrost.executions.get_session_factory", return_value=async_session_factory):
            result = await executions.get(str(execution.id))

        assert result.execution_id == str(execution.id)
        assert result.status == ExecutionStatus.SUCCESS
        assert result.input_data == {"input": "data"}
        assert result.result == {"output": "result"}


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
        from bifrost._write_buffer import WriteBuffer, set_write_buffer

        # Attach DB session to context (needed for context validation)
        admin_context._db = MagicMock()
        set_execution_context(admin_context)

        # Create actual write buffer
        buffer = WriteBuffer(
            execution_id=admin_context.execution_id,
            org_id=str(admin_context.organization.id) if admin_context.organization else None,
            user_id=admin_context.user_id,
        )
        set_write_buffer(buffer)

        try:
            result = await roles.create(
                name="New Role",
                description="New role description",
            )

            assert result.name == "New Role"

            # Verify buffer has pending changes
            assert await buffer.has_pending_changes()
        finally:
            buffer.close()

    @pytest.mark.asyncio
    async def test_update_writes_to_buffer(
        self,
        db_session: AsyncSession,
        admin_context,
        test_org: Organization,
    ):
        """Test roles.update() writes to buffer."""
        from bifrost import roles
        from bifrost._write_buffer import WriteBuffer, set_write_buffer
        from src.core.cache import roles_hash_key, get_redis

        # Create role
        role = Role(
            id=uuid4(),
            name="Original Role",
            organization_id=test_org.id,
            is_active=True,
            created_by="test-user",
        )
        db_session.add(role)
        await db_session.commit()

        # Write role to Redis cache (required for update to find it)
        async with get_redis() as r:
            hash_key = roles_hash_key(str(test_org.id))
            role_data = {
                "id": str(role.id),
                "name": role.name,
                "description": None,
                "is_active": role.is_active,
                "created_by": role.created_by,
                "created_at": role.created_at.isoformat() if role.created_at else None,
                "updated_at": role.updated_at.isoformat() if role.updated_at else None,
            }
            await r.hset(hash_key, str(role.id), json.dumps(role_data))  # type: ignore[misc]

        # Attach DB session to context
        admin_context._db = db_session
        set_execution_context(admin_context)

        # Create actual write buffer
        buffer = WriteBuffer(
            execution_id=admin_context.execution_id,
            org_id=str(admin_context.organization.id) if admin_context.organization else None,
            user_id=admin_context.user_id,
        )
        set_write_buffer(buffer)

        try:
            await roles.update(str(role.id), name="Updated Role")

            # Verify buffer has pending changes
            assert await buffer.has_pending_changes()
        finally:
            buffer.close()

    @pytest.mark.asyncio
    async def test_delete_writes_to_buffer(
        self,
        db_session: AsyncSession,
        admin_context,
        test_org: Organization,
    ):
        """Test roles.delete() writes to buffer."""
        from bifrost import roles
        from bifrost._write_buffer import WriteBuffer, set_write_buffer
        from src.core.cache import roles_hash_key, get_redis

        # Create role
        role = Role(
            id=uuid4(),
            name="Delete Me",
            organization_id=test_org.id,
            is_active=True,
            created_by="test-user",
        )
        db_session.add(role)
        await db_session.commit()

        # Write role to Redis cache (required for delete to find it)
        async with get_redis() as r:
            hash_key = roles_hash_key(str(test_org.id))
            role_data = {
                "id": str(role.id),
                "name": role.name,
                "description": None,
                "is_active": role.is_active,
                "created_by": role.created_by,
                "created_at": role.created_at.isoformat() if role.created_at else None,
                "updated_at": role.updated_at.isoformat() if role.updated_at else None,
            }
            await r.hset(hash_key, str(role.id), json.dumps(role_data))  # type: ignore[misc]

        # Attach DB session to context
        admin_context._db = db_session
        set_execution_context(admin_context)

        # Create actual write buffer
        buffer = WriteBuffer(
            execution_id=admin_context.execution_id,
            org_id=str(admin_context.organization.id) if admin_context.organization else None,
            user_id=admin_context.user_id,
        )
        set_write_buffer(buffer)

        try:
            await roles.delete(str(role.id))

            # Verify buffer has pending changes
            assert await buffer.has_pending_changes()
        finally:
            buffer.close()
