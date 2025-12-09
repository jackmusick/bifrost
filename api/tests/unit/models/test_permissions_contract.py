"""
Contract tests for Permissions API models
Tests Pydantic validation rules for request/response models
"""

from datetime import datetime

import pytest
from pydantic import ValidationError

from src.models.models import GrantPermissionsRequest, PermissionsData, User, UserPermission


# Note: Models use snake_case (e.g., user_id, org_id, can_execute_workflows)
# This matches the OpenAPI/TypeScript schema


class TestGrantPermissionsRequest:
    """Test validation for GrantPermissionsRequest model"""

    def test_valid_grant_permissions_request(self):
        """Test valid grant permissions request"""
        request = GrantPermissionsRequest(
            user_id="user-123",
            org_id="org-456",
            permissions=PermissionsData(
                can_execute_workflows=True,
                can_manage_config=True,
                can_manage_forms=True,
                can_view_history=True
            )
        )
        assert request.user_id == "user-123"
        assert request.org_id == "org-456"
        assert request.permissions.can_execute_workflows is True
        assert request.permissions.can_manage_config is True
        assert request.permissions.can_manage_forms is True
        assert request.permissions.can_view_history is True

    def test_grant_permissions_with_mixed_flags(self):
        """Test granting some permissions but not others"""
        request = GrantPermissionsRequest(
            user_id="user-123",
            org_id="org-456",
            permissions=PermissionsData(
                can_execute_workflows=True,
                can_manage_config=False,
                can_manage_forms=True,
                can_view_history=False
            )
        )
        assert request.permissions.can_execute_workflows is True
        assert request.permissions.can_manage_config is False
        assert request.permissions.can_manage_forms is True
        assert request.permissions.can_view_history is False

    def test_grant_permissions_with_all_false(self):
        """Test granting no permissions (all false)"""
        request = GrantPermissionsRequest(
            user_id="user-123",
            org_id="org-456",
            permissions=PermissionsData(
                can_execute_workflows=False,
                can_manage_config=False,
                can_manage_forms=False,
                can_view_history=False
            )
        )
        assert request.permissions.can_execute_workflows is False
        assert request.permissions.can_manage_config is False
        assert request.permissions.can_manage_forms is False
        assert request.permissions.can_view_history is False

    def test_missing_required_user_id(self):
        """Test that user_id is required"""
        with pytest.raises(ValidationError) as exc_info:
            GrantPermissionsRequest(
                org_id="org-456",
                permissions=PermissionsData(
                    can_execute_workflows=True,
                    can_manage_config=True,
                    can_manage_forms=True,
                    can_view_history=True
                )
            )

        errors = exc_info.value.errors()
        assert any(e["loc"] == ("user_id",) and e["type"] == "missing" for e in errors)

    def test_missing_required_org_id(self):
        """Test that org_id is required"""
        with pytest.raises(ValidationError) as exc_info:
            GrantPermissionsRequest(
                user_id="user-123",
                permissions=PermissionsData(
                    can_execute_workflows=True,
                    can_manage_config=True,
                    can_manage_forms=True,
                    can_view_history=True
                )
            )

        errors = exc_info.value.errors()
        assert any(e["loc"] == ("org_id",) and e["type"] == "missing" for e in errors)

    def test_missing_required_permissions(self):
        """Test that permissions object is required"""
        with pytest.raises(ValidationError) as exc_info:
            GrantPermissionsRequest(
                user_id="user-123",
                org_id="org-456"
            )

        errors = exc_info.value.errors()
        assert any(e["loc"] == ("permissions",) and e["type"] == "missing" for e in errors)


class TestPermissionsData:
    """Test validation for PermissionsData model"""

    def test_valid_permissions_data(self):
        """Test valid permissions data"""
        permissions = PermissionsData(
            can_execute_workflows=True,
            can_manage_config=False,
            can_manage_forms=True,
            can_view_history=False
        )
        assert permissions.can_execute_workflows is True
        assert permissions.can_manage_config is False
        assert permissions.can_manage_forms is True
        assert permissions.can_view_history is False

    def test_missing_can_execute_workflows(self):
        """Test that can_execute_workflows is required"""
        with pytest.raises(ValidationError) as exc_info:
            PermissionsData(
                can_manage_config=True,
                can_manage_forms=True,
                can_view_history=True
            )

        errors = exc_info.value.errors()
        assert any(e["loc"] == ("can_execute_workflows",) and e["type"] == "missing" for e in errors)

    def test_missing_can_manage_config(self):
        """Test that can_manage_config is required"""
        with pytest.raises(ValidationError) as exc_info:
            PermissionsData(
                can_execute_workflows=True,
                can_manage_forms=True,
                can_view_history=True
            )

        errors = exc_info.value.errors()
        assert any(e["loc"] == ("can_manage_config",) and e["type"] == "missing" for e in errors)

    def test_missing_can_manage_forms(self):
        """Test that can_manage_forms is required"""
        with pytest.raises(ValidationError) as exc_info:
            PermissionsData(
                can_execute_workflows=True,
                can_manage_config=True,
                can_view_history=True
            )

        errors = exc_info.value.errors()
        assert any(e["loc"] == ("can_manage_forms",) and e["type"] == "missing" for e in errors)

    def test_missing_can_view_history(self):
        """Test that can_view_history is required"""
        with pytest.raises(ValidationError) as exc_info:
            PermissionsData(
                can_execute_workflows=True,
                can_manage_config=True,
                can_manage_forms=True
            )

        errors = exc_info.value.errors()
        assert any(e["loc"] == ("can_view_history",) and e["type"] == "missing" for e in errors)


class TestUserPermissionResponse:
    """Test UserPermission response model structure"""

    def test_valid_user_permission_response(self):
        """Test valid user permission response"""
        permission = UserPermission(
            user_id="user-123",
            org_id="org-456",
            can_execute_workflows=True,
            can_manage_config=False,
            can_manage_forms=True,
            can_view_history=False,
            granted_by="admin-user",
            granted_at=datetime.utcnow()
        )
        assert permission.user_id == "user-123"
        assert permission.org_id == "org-456"
        assert permission.can_execute_workflows is True
        assert permission.can_manage_config is False
        assert permission.granted_by == "admin-user"
        assert isinstance(permission.granted_at, datetime)

    def test_user_permission_defaults_to_false(self):
        """Test that permission flags default to False"""
        permission = UserPermission(
            user_id="user-123",
            org_id="org-456",
            granted_by="admin-user",
            granted_at=datetime.utcnow()
        )
        assert permission.can_execute_workflows is False
        assert permission.can_manage_config is False
        assert permission.can_manage_forms is False
        assert permission.can_view_history is False

    def test_user_permission_missing_required_fields(self):
        """Test that all required fields must be present"""
        with pytest.raises(ValidationError) as exc_info:
            UserPermission(
                user_id="user-123",
                org_id="org-456"
                # Missing: granted_by, granted_at
            )

        errors = exc_info.value.errors()
        required_fields = {"granted_by", "granted_at"}
        missing_fields = {e["loc"][0] for e in errors if e["type"] == "missing"}
        assert required_fields.issubset(missing_fields)

    def test_user_permission_serialization(self):
        """Test that user permission can be serialized to dict/JSON"""
        permission = UserPermission(
            user_id="user-123",
            org_id="org-456",
            can_execute_workflows=True,
            can_manage_config=True,
            can_manage_forms=True,
            can_view_history=True,
            granted_by="admin-user",
            granted_at=datetime.utcnow()
        )

        perm_dict = permission.model_dump()
        assert "user_id" in perm_dict
        assert "org_id" in perm_dict
        assert "can_execute_workflows" in perm_dict
        assert "can_manage_config" in perm_dict
        assert "can_manage_forms" in perm_dict
        assert "can_view_history" in perm_dict
        assert "granted_by" in perm_dict
        assert "granted_at" in perm_dict

    def test_user_permission_json_serialization(self):
        """Test that user permission can be serialized to JSON mode"""
        permission = UserPermission(
            user_id="user-123",
            org_id="org-456",
            can_execute_workflows=True,
            can_manage_config=False,
            can_manage_forms=True,
            can_view_history=False,
            granted_by="admin-user",
            granted_at=datetime.utcnow()
        )

        perm_dict = permission.model_dump(mode="json")
        assert isinstance(perm_dict["granted_at"], str)  # datetime -> ISO string


class TestUserResponse:
    """Test User response model structure"""

    def test_valid_user_response(self):
        """Test valid user response"""
        user = User(
            id="user-123",
            email="user@example.com",
            display_name="Test User",
            is_active=True,
            last_login=datetime.utcnow(),
            created_at=datetime.utcnow()
        )
        assert user.id == "user-123"
        assert user.email == "user@example.com"
        assert user.display_name == "Test User"
        assert user.is_active is True
        assert isinstance(user.last_login, datetime)
        assert isinstance(user.created_at, datetime)

    def test_user_without_last_login(self):
        """Test user without last_login (new user)"""
        user = User(
            id="user-123",
            email="user@example.com",
            display_name="Test User",
            is_active=True,
            last_login=None,
            created_at=datetime.utcnow()
        )
        assert user.last_login is None

    def test_user_is_active_defaults_to_true(self):
        """Test that is_active defaults to True"""
        user = User(
            id="user-123",
            email="user@example.com",
            display_name="Test User",
            created_at=datetime.utcnow()
        )
        assert user.is_active is True

    def test_user_missing_required_fields(self):
        """Test that all required fields must be present"""
        with pytest.raises(ValidationError) as exc_info:
            User(
                id="user-123",
                email="user@example.com"
                # Missing: display_name, created_at
            )

        errors = exc_info.value.errors()
        required_fields = {"display_name", "created_at"}
        missing_fields = {e["loc"][0] for e in errors if e["type"] == "missing"}
        assert required_fields.issubset(missing_fields)

    def test_user_serialization(self):
        """Test that user can be serialized to dict/JSON"""
        user = User(
            id="user-123",
            email="user@example.com",
            display_name="Test User",
            is_active=True,
            last_login=datetime.utcnow(),
            created_at=datetime.utcnow()
        )

        user_dict = user.model_dump()
        assert "id" in user_dict
        assert "email" in user_dict
        assert "display_name" in user_dict
        assert "is_active" in user_dict
        assert "last_login" in user_dict
        assert "created_at" in user_dict
