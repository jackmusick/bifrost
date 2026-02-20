"""
Contract tests for OrgConfig API models
Tests Pydantic validation rules for request/response models
"""

import pytest
from pydantic import ValidationError

from src.models import ConfigType, SetConfigRequest, UpdateConfigRequest, ConfigResponse


# Note: Models use snake_case (e.g., updated_at, updated_by, org_id)
# ConfigType has: STRING, INT, BOOL, JSON, SECRET


class TestSetConfigRequest:
    """Test validation for SetConfigRequest model"""

    def test_invalid_key_with_spaces(self):
        """Test that keys with spaces are rejected"""
        with pytest.raises(ValidationError) as exc_info:
            SetConfigRequest(
                key="invalid key",
                value="value",
                type=ConfigType.STRING
            )

        errors = exc_info.value.errors()
        assert any(e["loc"] == ("key",) for e in errors)
        assert any("string_pattern_mismatch" in e["type"] for e in errors)

    def test_invalid_key_with_special_chars(self):
        """Test that keys with special characters are rejected"""
        with pytest.raises(ValidationError) as exc_info:
            SetConfigRequest(
                key="invalid-key!",
                value="value",
                type=ConfigType.STRING
            )

        errors = exc_info.value.errors()
        assert any(e["loc"] == ("key",) for e in errors)

    def test_invalid_key_with_dots(self):
        """Test that keys with dots are rejected"""
        with pytest.raises(ValidationError) as exc_info:
            SetConfigRequest(
                key="invalid.key",
                value="value",
                type=ConfigType.STRING
            )

        errors = exc_info.value.errors()
        assert any(e["loc"] == ("key",) for e in errors)

    def test_missing_required_key(self):
        """Test that key is required"""
        with pytest.raises(ValidationError) as exc_info:
            SetConfigRequest(
                value="value",
                type=ConfigType.STRING
            )

        errors = exc_info.value.errors()
        assert any(e["loc"] == ("key",) and e["type"] == "missing" for e in errors)

    def test_missing_required_value(self):
        """Test that value is required"""
        with pytest.raises(ValidationError) as exc_info:
            SetConfigRequest(
                key="test_key",
                type=ConfigType.STRING
            )

        errors = exc_info.value.errors()
        assert any(e["loc"] == ("value",) and e["type"] == "missing" for e in errors)

    def test_missing_required_type(self):
        """Test that type is required"""
        with pytest.raises(ValidationError) as exc_info:
            SetConfigRequest(
                key="test_key",
                value="value"
            )

        errors = exc_info.value.errors()
        assert any(e["loc"] == ("type",) and e["type"] == "missing" for e in errors)

    def test_invalid_type_enum(self):
        """Test that invalid type is rejected"""
        with pytest.raises(ValidationError) as exc_info:
            SetConfigRequest(
                key="test_key",
                value="value",
                type="invalid_type"
            )

        errors = exc_info.value.errors()
        assert any(e["loc"] == ("type",) for e in errors)


class TestUpdateConfigRequest:
    """Test validation for UpdateConfigRequest model (partial updates)"""

    def test_all_fields_optional(self):
        """Test that all fields can be omitted."""
        req = UpdateConfigRequest()
        assert req.key is None
        assert req.value is None
        assert req.type is None
        assert req.description is None
        assert req.organization_id is None

    def test_partial_update_only_value(self):
        """Test sending only value field."""
        req = UpdateConfigRequest(value="new-value")
        assert req.value == "new-value"
        assert req.key is None
        assert req.type is None

    def test_partial_update_only_description(self):
        """Test sending only description field."""
        req = UpdateConfigRequest(description="updated desc")
        assert req.description == "updated desc"
        assert req.value is None

    def test_empty_string_value_accepted(self):
        """Test that empty string value is accepted (used to signal keep-existing for secrets)."""
        req = UpdateConfigRequest(value="")
        assert req.value == ""

    def test_null_value_accepted(self):
        """Test that None value is the default (signals no change)."""
        req = UpdateConfigRequest(type=ConfigType.SECRET)
        assert req.value is None

    def test_key_pattern_still_enforced(self):
        """Test that key pattern validation still applies when key is provided."""
        with pytest.raises(ValidationError) as exc_info:
            UpdateConfigRequest(key="invalid key!")
        errors = exc_info.value.errors()
        assert any(e["loc"] == ("key",) for e in errors)

    def test_valid_key_accepted(self):
        """Test valid key is accepted."""
        req = UpdateConfigRequest(key="valid_key_123")
        assert req.key == "valid_key_123"

    def test_model_fields_set_tracks_explicit_fields(self):
        """Test that model_fields_set correctly tracks which fields were explicitly set."""
        req = UpdateConfigRequest(description=None)
        assert "description" in req.model_fields_set
        # organization_id was NOT explicitly set
        assert "organization_id" not in req.model_fields_set


class TestConfigResponse:
    """Test Config response model structure"""

    def test_config_missing_required_fields(self):
        """Test that key and value are required"""
        with pytest.raises(ValidationError) as exc_info:
            ConfigResponse(
                type=ConfigType.STRING
                # Missing: key, value
            )

        errors = exc_info.value.errors()
        required_fields = {"key", "value"}
        missing_fields = {e["loc"][0] for e in errors if e["type"] == "missing"}
        assert required_fields.issubset(missing_fields)

