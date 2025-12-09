"""
Contract tests for Organizations API models
Tests Pydantic validation rules for request/response models
"""

from datetime import datetime

import pytest
from pydantic import ValidationError

from src.models.models import CreateOrganizationRequest, ErrorResponse, Organization, UpdateOrganizationRequest


# Note: Models use snake_case (e.g., is_active, created_at, created_by, updated_at)
# This matches the OpenAPI/TypeScript schema


class TestCreateOrganizationRequest:
    """Test validation for CreateOrganizationRequest model"""

    def test_valid_request_with_name_only(self):
        """Test valid request with required name field"""
        request = CreateOrganizationRequest(name="Test Organization")
        assert request.name == "Test Organization"
        assert request.domain is None

    def test_valid_request_with_domain(self):
        """Test valid request with optional domain"""
        request = CreateOrganizationRequest(
            name="Test Organization",
            domain="acme.com"
        )
        assert request.name == "Test Organization"
        assert request.domain == "acme.com"

    def test_valid_request_with_null_domain(self):
        """Test valid request with explicit null domain"""
        request = CreateOrganizationRequest(
            name="Test Organization",
            domain=None
        )
        assert request.name == "Test Organization"
        assert request.domain is None

    def test_invalid_empty_name(self):
        """Test that empty name is rejected"""
        with pytest.raises(ValidationError) as exc_info:
            CreateOrganizationRequest(name="")

        errors = exc_info.value.errors()
        assert any(e["loc"] == ("name",) for e in errors)
        assert any("at least 1 character" in str(e["msg"]).lower() for e in errors)

    def test_invalid_name_too_long(self):
        """Test that name exceeding 200 characters is rejected"""
        long_name = "A" * 201
        with pytest.raises(ValidationError) as exc_info:
            CreateOrganizationRequest(name=long_name)

        errors = exc_info.value.errors()
        assert any(e["loc"] == ("name",) for e in errors)

    def test_missing_required_name(self):
        """Test that name is required"""
        with pytest.raises(ValidationError) as exc_info:
            CreateOrganizationRequest()

        errors = exc_info.value.errors()
        assert any(e["loc"] == ("name",) and e["type"] == "missing" for e in errors)


class TestOrganizationResponse:
    """Test Organization response model structure"""

    def test_valid_organization_response(self):
        """Test that valid organization response is accepted"""
        org = Organization(
            id="org-123",
            name="Test Organization",
            is_active=True,
            created_at=datetime.utcnow(),
            created_by="user-123",
            updated_at=datetime.utcnow()
        )
        assert org.id == "org-123"
        assert org.name == "Test Organization"
        assert org.is_active is True

    def test_organization_missing_required_fields(self):
        """Test that all required fields must be present"""
        with pytest.raises(ValidationError) as exc_info:
            Organization(
                id="org-123",
                name="Test Organization"
                # Missing: created_at, created_by, updated_at (is_active has default=True)
            )

        errors = exc_info.value.errors()
        required_fields = {"created_at", "created_by", "updated_at"}
        missing_fields = {e["loc"][0] for e in errors if e["type"] == "missing"}
        assert required_fields.issubset(missing_fields)

    def test_organization_serialization(self):
        """Test that organization can be serialized to dict/JSON"""
        org = Organization(
            id="org-123",
            name="Test Organization",
            is_active=True,
            created_at=datetime.utcnow(),
            created_by="user-123",
            updated_at=datetime.utcnow()
        )

        org_dict = org.model_dump()
        assert "id" in org_dict
        assert "name" in org_dict
        assert "is_active" in org_dict
        assert "created_at" in org_dict
        assert "created_by" in org_dict
        assert "updated_at" in org_dict


class TestUpdateOrganizationRequest:
    """Test validation for UpdateOrganizationRequest model"""

    def test_valid_update_name_only(self):
        """Test updating only the name"""
        request = UpdateOrganizationRequest(name="Updated Name")
        assert request.name == "Updated Name"
        assert request.is_active is None

    def test_valid_update_is_active_only(self):
        """Test updating only the is_active flag"""
        request = UpdateOrganizationRequest(is_active=False)
        assert request.name is None
        assert request.is_active is False

    def test_valid_update_all_fields(self):
        """Test updating all fields at once"""
        request = UpdateOrganizationRequest(
            name="Updated Name",
            is_active=False
        )
        assert request.name == "Updated Name"
        assert request.is_active is False

    def test_valid_update_with_no_fields(self):
        """Test that update request with no fields is valid (no-op)"""
        request = UpdateOrganizationRequest()
        assert request.name is None
        assert request.is_active is None

    def test_invalid_empty_name(self):
        """Test that empty name is rejected in updates"""
        with pytest.raises(ValidationError) as exc_info:
            UpdateOrganizationRequest(name="")

        errors = exc_info.value.errors()
        assert any(e["loc"] == ("name",) for e in errors)

    def test_invalid_name_too_long(self):
        """Test that name exceeding 200 characters is rejected"""
        long_name = "A" * 201
        with pytest.raises(ValidationError) as exc_info:
            UpdateOrganizationRequest(name=long_name)

        errors = exc_info.value.errors()
        assert any(e["loc"] == ("name",) for e in errors)


class TestErrorResponse:
    """Test ErrorResponse model for API errors"""

    def test_valid_error_response(self):
        """Test valid error response structure"""
        error = ErrorResponse(
            error="ValidationError",
            message="Invalid request data",
            details={"field": "name", "issue": "too short"}
        )
        assert error.error == "ValidationError"
        assert error.message == "Invalid request data"
        assert error.details is not None

    def test_error_response_without_details(self):
        """Test error response without optional details"""
        error = ErrorResponse(
            error="NotFound",
            message="Organization not found"
        )
        assert error.error == "NotFound"
        assert error.message == "Organization not found"
        assert error.details is None

    def test_error_response_serialization(self):
        """Test error response can be serialized"""
        error = ErrorResponse(
            error="Unauthorized",
            message="Authentication required"
        )
        error_dict = error.model_dump()
        assert "error" in error_dict
        assert "message" in error_dict
        assert "details" in error_dict
