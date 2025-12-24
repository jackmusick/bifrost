"""
Unit tests for Bifrost Forms SDK module.

Tests platform mode (inside workflows) only - forms module doesn't support external mode.
Uses mocked dependencies for fast, isolated testing.
"""

import json
import pytest
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from bifrost._context import set_execution_context, clear_execution_context


def create_mock_redis_context(mock_redis):
    """Helper to create an async context manager for mocking get_redis()."""
    @asynccontextmanager
    async def mock_get_redis():
        yield mock_redis
    return mock_get_redis


@pytest.fixture
def test_org_id():
    """Return a test organization ID."""
    return str(uuid4())


@pytest.fixture
def test_user_id():
    """Return a test user ID."""
    return "test-user-123"


@pytest.fixture
def test_context(test_org_id, test_user_id):
    """Create execution context for platform mode testing."""
    from src.sdk.context import ExecutionContext, Organization

    org = Organization(id=test_org_id, name="Test Org", is_active=True)
    return ExecutionContext(
        user_id=test_user_id,
        email="test@example.com",
        name="Test User",
        scope=test_org_id,
        organization=org,
        is_platform_admin=False,
        is_function_key=False,
        execution_id="test-exec-123",
    )


@pytest.fixture
def admin_context(test_org_id):
    """Create platform admin execution context."""
    from src.sdk.context import ExecutionContext, Organization

    org = Organization(id=test_org_id, name="Test Org", is_active=True)
    return ExecutionContext(
        user_id="admin-user",
        email="admin@example.com",
        name="Admin User",
        scope=test_org_id,
        organization=org,
        is_platform_admin=True,
        is_function_key=False,
        execution_id="admin-exec-456",
    )


@pytest.fixture
def global_context():
    """Create global scope execution context (no organization)."""
    from src.sdk.context import ExecutionContext, Organization

    org = Organization(id="", name="", is_active=False)
    return ExecutionContext(
        user_id="global-user",
        email="global@example.com",
        name="Global User",
        scope="GLOBAL",
        organization=org,
        is_platform_admin=True,
        is_function_key=False,
        execution_id="global-exec-789",
    )


class TestFormsPlatformMode:
    """Test forms SDK methods in platform mode (inside workflows)."""

    @pytest.fixture(autouse=True)
    def cleanup_context(self):
        """Ensure context is cleared after each test."""
        yield
        clear_execution_context()

    @pytest.mark.asyncio
    async def test_list_returns_forms_from_redis(self, test_context, test_org_id, test_user_id):
        """Test that forms.list() returns forms from Redis cache."""
        from bifrost import forms

        set_execution_context(test_context)

        # Mock form data
        form1_id = str(uuid4())
        form2_id = str(uuid4())
        form1_data = {
            "id": form1_id,
            "name": "Contact Form",
            "description": "Contact us",
            "workflow_id": "contact_workflow",
            "is_active": True,
        }
        form2_data = {
            "id": form2_id,
            "name": "Survey Form",
            "description": "User survey",
            "workflow_id": "survey_workflow",
            "is_active": True,
        }

        # Mock Redis client
        mock_redis = MagicMock()
        mock_redis.smembers = AsyncMock(return_value={form1_id, form2_id})
        mock_redis.hget = AsyncMock(
            side_effect=lambda hash_key, form_id: (
                json.dumps(form1_data) if form_id == form1_id else json.dumps(form2_data)
            )
        )

        with patch("bifrost.forms.get_redis", create_mock_redis_context(mock_redis)):
            result = await forms.list()

        assert result is not None
        assert len(result) == 2

        # Forms should be sorted by name
        assert result[0].name == "Contact Form"
        assert result[1].name == "Survey Form"
        assert str(result[0].id) == form1_id
        assert str(result[1].id) == form2_id

    @pytest.mark.asyncio
    async def test_list_returns_empty_list_when_no_forms(self, test_context, test_org_id, test_user_id):
        """Test that forms.list() returns empty list when no forms accessible."""
        from bifrost import forms

        set_execution_context(test_context)

        # Mock Redis client with no form IDs
        mock_redis = MagicMock()
        mock_redis.smembers = AsyncMock(return_value=set())

        with patch("bifrost.forms.get_redis", create_mock_redis_context(mock_redis)):
            result = await forms.list()

        assert result == []
        mock_redis.smembers.assert_called_once()

    @pytest.mark.asyncio
    async def test_list_uses_context_org_id(self, test_context, test_org_id, test_user_id):
        """Test that forms.list() uses context.org_id when available."""
        from bifrost import forms

        set_execution_context(test_context)

        # Mock Redis client
        mock_redis = MagicMock()
        mock_redis.smembers = AsyncMock(return_value=set())

        with patch("bifrost.forms.get_redis", create_mock_redis_context(mock_redis)):
            with patch("bifrost.forms.user_forms_key") as mock_user_forms_key:
                mock_user_forms_key.return_value = f"user:{test_user_id}:forms"
                await forms.list()

                # Verify user_forms_key was called with org_id and user_id
                mock_user_forms_key.assert_called_once_with(test_org_id, test_user_id)

    @pytest.mark.asyncio
    async def test_list_uses_none_for_global_scope(self, global_context):
        """Test that forms.list() uses None for org_id in GLOBAL scope."""
        from bifrost import forms

        set_execution_context(global_context)

        # Mock Redis client
        mock_redis = MagicMock()
        mock_redis.smembers = AsyncMock(return_value=set())

        with patch("bifrost.forms.get_redis", create_mock_redis_context(mock_redis)):
            with patch("bifrost.forms.user_forms_key") as mock_user_forms_key:
                mock_user_forms_key.return_value = "user:global-user:forms"
                await forms.list()

                # Verify user_forms_key was called with None for org_id
                mock_user_forms_key.assert_called_once_with(None, "global-user")

    @pytest.mark.asyncio
    async def test_list_skips_invalid_json_data(self, test_context, test_org_id, test_user_id):
        """Test that forms.list() skips forms with invalid JSON data."""
        from bifrost import forms

        set_execution_context(test_context)

        form1_id = str(uuid4())
        form2_id = str(uuid4())
        form1_data = {"id": form1_id, "name": "Valid Form", "is_active": True}

        # Mock Redis client
        mock_redis = MagicMock()
        mock_redis.smembers = AsyncMock(return_value={form1_id, form2_id})
        mock_redis.hget = AsyncMock(
            side_effect=lambda hash_key, form_id: (
                json.dumps(form1_data) if form_id == form1_id else "invalid json {{{{"
            )
        )

        with patch("bifrost.forms.get_redis", create_mock_redis_context(mock_redis)):
            result = await forms.list()

        # Should only return the valid form
        assert len(result) == 1
        assert str(result[0].id) == form1_id

    @pytest.mark.asyncio
    async def test_list_sorts_by_name(self, test_context, test_org_id, test_user_id):
        """Test that forms.list() returns forms sorted alphabetically by name."""
        from bifrost import forms

        set_execution_context(test_context)

        form1_id = str(uuid4())
        form2_id = str(uuid4())
        form3_id = str(uuid4())

        # Create forms with names out of order
        zebra_form = {"id": form1_id, "name": "Zebra Form", "is_active": True}
        apple_form = {"id": form2_id, "name": "Apple Form", "is_active": True}
        banana_form = {"id": form3_id, "name": "Banana Form", "is_active": True}

        mock_redis = MagicMock()
        mock_redis.smembers = AsyncMock(return_value={form1_id, form2_id, form3_id})
        mock_redis.hget = AsyncMock(
            side_effect=lambda hash_key, form_id: (
                json.dumps(zebra_form) if form_id == form1_id
                else json.dumps(apple_form) if form_id == form2_id
                else json.dumps(banana_form)
            )
        )

        with patch("bifrost.forms.get_redis", create_mock_redis_context(mock_redis)):
            result = await forms.list()

        # Should be sorted alphabetically
        assert len(result) == 3
        assert result[0].name == "Apple Form"
        assert result[1].name == "Banana Form"
        assert result[2].name == "Zebra Form"

    @pytest.mark.asyncio
    async def test_get_returns_form_data(self, test_context, test_org_id, test_user_id):
        """Test that forms.get() returns complete form data."""
        from bifrost import forms

        set_execution_context(test_context)

        form_id = str(uuid4())
        form_data = {
            "id": form_id,
            "name": "Test Form",
            "description": "A test form",
            "workflow_id": "test_workflow",
            "launch_workflow_id": "launch_test",
            "is_active": True,
            "form_schema": {
                "fields": [
                    {
                        "id": str(uuid4()),
                        "name": "email",
                        "label": "Email Address",
                        "type": "email",
                        "required": True,
                        "position": 0,
                    }
                ]
            },
        }

        # Mock Redis client
        mock_redis = MagicMock()
        mock_redis.smembers = AsyncMock(return_value={form_id})
        mock_redis.hget = AsyncMock(return_value=json.dumps(form_data))

        with patch("bifrost.forms.get_redis", create_mock_redis_context(mock_redis)):
            result = await forms.get(form_id)

        assert result is not None
        assert str(result.id) == form_id
        assert result.name == "Test Form"
        assert result.description == "A test form"
        assert result.workflow_id == "test_workflow"
        assert result.form_schema is not None
        # form_schema is either dict or FormSchema
        if isinstance(result.form_schema, dict):
            assert len(result.form_schema["fields"]) == 1
            assert result.form_schema["fields"][0]["name"] == "email"
        else:
            assert len(result.form_schema.fields) == 1
            assert result.form_schema.fields[0].name == "email"

    @pytest.mark.asyncio
    async def test_get_raises_value_error_when_form_not_found(self, test_context, test_org_id, test_user_id):
        """Test that forms.get() raises ValueError when form doesn't exist in Redis."""
        from bifrost import forms

        set_execution_context(test_context)

        form_id = str(uuid4())

        # Mock Redis client returning None (form not found)
        mock_redis = MagicMock()
        mock_redis.smembers = AsyncMock(return_value={form_id})
        mock_redis.hget = AsyncMock(return_value=None)

        with patch("bifrost.forms.get_redis", create_mock_redis_context(mock_redis)):
            with pytest.raises(ValueError, match=f"Form not found: {form_id}"):
                await forms.get(form_id)

    @pytest.mark.asyncio
    async def test_get_raises_permission_error_when_user_lacks_access(
        self, test_context, test_org_id, test_user_id
    ):
        """Test that forms.get() raises PermissionError when user doesn't have access."""
        from bifrost import forms

        set_execution_context(test_context)

        form_id = str(uuid4())
        accessible_form_id = str(uuid4())

        # Mock Redis client - user has access to different form
        mock_redis = MagicMock()
        mock_redis.smembers = AsyncMock(return_value={accessible_form_id})

        with patch("bifrost.forms.get_redis", create_mock_redis_context(mock_redis)):
            with pytest.raises(PermissionError, match=f"Access denied to form: {form_id}"):
                await forms.get(form_id)

    @pytest.mark.asyncio
    async def test_get_skips_permission_check_for_platform_admin(
        self, admin_context, test_org_id
    ):
        """Test that forms.get() skips permission check for platform admins."""
        from bifrost import forms

        set_execution_context(admin_context)

        form_id = str(uuid4())
        form_data = {"id": form_id, "name": "Admin Form", "is_active": True}

        # Mock Redis client - admin has no forms in access list
        mock_redis = MagicMock()
        mock_redis.smembers = AsyncMock(return_value=set())  # Empty set
        mock_redis.hget = AsyncMock(return_value=json.dumps(form_data))

        with patch("bifrost.forms.get_redis", create_mock_redis_context(mock_redis)):
            result = await forms.get(form_id)

        # Should return form even though not in access list
        assert str(result.id) == form_id
        assert result.name == "Admin Form"

    @pytest.mark.asyncio
    async def test_get_raises_value_error_on_invalid_json(
        self, test_context, test_org_id, test_user_id
    ):
        """Test that forms.get() raises ValueError when Redis data is invalid JSON."""
        from bifrost import forms

        set_execution_context(test_context)

        form_id = str(uuid4())

        # Mock Redis client returning invalid JSON
        mock_redis = MagicMock()
        mock_redis.smembers = AsyncMock(return_value={form_id})
        mock_redis.hget = AsyncMock(return_value="invalid json {{{")

        with patch("bifrost.forms.get_redis", create_mock_redis_context(mock_redis)):
            with pytest.raises(ValueError, match=f"Invalid form data: {form_id}"):
                await forms.get(form_id)

    @pytest.mark.asyncio
    async def test_get_uses_correct_redis_keys(self, test_context, test_org_id, test_user_id):
        """Test that forms.get() uses correct Redis keys for org-scoped forms."""
        from bifrost import forms

        set_execution_context(test_context)

        form_id = str(uuid4())
        form_data = {"id": form_id, "name": "Test Form", "is_active": True}

        mock_redis = MagicMock()
        mock_redis.smembers = AsyncMock(return_value={form_id})
        mock_redis.hget = AsyncMock(return_value=json.dumps(form_data))

        with patch("bifrost.forms.get_redis", create_mock_redis_context(mock_redis)):
            with patch("bifrost.forms.user_forms_key") as mock_user_forms_key:
                with patch("bifrost.forms.forms_hash_key") as mock_forms_hash_key:
                    mock_user_forms_key.return_value = "user:test:forms"
                    mock_forms_hash_key.return_value = "forms:test-org"

                    await forms.get(form_id)

                    # Verify Redis keys were created correctly
                    mock_user_forms_key.assert_called_once_with(test_org_id, test_user_id)
                    mock_forms_hash_key.assert_called_once_with(test_org_id)

    @pytest.mark.asyncio
    async def test_list_requires_execution_context(self):
        """Test that forms.list() requires execution context."""
        from bifrost import forms

        clear_execution_context()

        with pytest.raises(RuntimeError, match="execution context"):
            await forms.list()

    @pytest.mark.asyncio
    async def test_get_requires_execution_context(self):
        """Test that forms.get() requires execution context."""
        from bifrost import forms

        clear_execution_context()

        with pytest.raises(RuntimeError, match="execution context"):
            await forms.get("form-123")
