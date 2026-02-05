"""
Contract tests for Organizations API models
Tests Pydantic validation rules for request/response models
"""

import pytest
from pydantic import ValidationError

from src.models import CreateOrganizationRequest, UpdateOrganizationRequest
from src.models.contracts.organizations import Organization


# Note: Models use snake_case (e.g., is_active, created_at, created_by, updated_at)
# This matches the OpenAPI/TypeScript schema


class TestCreateOrganizationRequest:
    """Test validation for CreateOrganizationRequest model"""

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



class TestUpdateOrganizationRequest:
    """Test validation for UpdateOrganizationRequest model"""

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


