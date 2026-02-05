"""
Contract tests for OrgConfig API models
Tests Pydantic validation rules for request/response models
"""

import pytest
from pydantic import ValidationError

from src.models import ConfigType, SetConfigRequest, ConfigResponse


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

