"""
Contract tests for OrgConfig API models
Tests Pydantic validation rules for request/response models
"""

from datetime import datetime

import pytest
from pydantic import ValidationError

from src.models.models import Config, ConfigType, SetConfigRequest


# Note: Models use snake_case (e.g., updated_at, updated_by, org_id)
# ConfigType has: STRING, INT, BOOL, JSON, SECRET


class TestSetConfigRequest:
    """Test validation for SetConfigRequest model"""

    def test_valid_request_string_type(self):
        """Test valid request with string type"""
        request = SetConfigRequest(
            key="api_timeout",
            value="30",
            type=ConfigType.STRING,
            description="API timeout in seconds"
        )
        assert request.key == "api_timeout"
        assert request.value == "30"
        assert request.type == ConfigType.STRING
        assert request.description == "API timeout in seconds"

    def test_valid_request_int_type(self):
        """Test valid request with int type"""
        request = SetConfigRequest(
            key="max_retries",
            value="3",
            type=ConfigType.INT
        )
        assert request.key == "max_retries"
        assert request.value == "3"
        assert request.type == ConfigType.INT
        assert request.description is None

    def test_valid_request_bool_type(self):
        """Test valid request with bool type"""
        request = SetConfigRequest(
            key="enable_notifications",
            value="true",
            type=ConfigType.BOOL
        )
        assert request.type == ConfigType.BOOL

    def test_valid_request_json_type(self):
        """Test valid request with json type"""
        request = SetConfigRequest(
            key="workflow_defaults",
            value='{"timeout": 300, "retry": true}',
            type=ConfigType.JSON
        )
        assert request.type == ConfigType.JSON

    def test_valid_request_secret_type(self):
        """Test valid request with secret type (encrypted value)"""
        request = SetConfigRequest(
            key="api_key",
            value="my-secret-api-key",
            type=ConfigType.SECRET
        )
        assert request.type == ConfigType.SECRET
        assert request.value == "my-secret-api-key"

    def test_valid_request_without_description(self):
        """Test valid request without description"""
        request = SetConfigRequest(
            key="test_key",
            value="test_value",
            type=ConfigType.STRING
        )
        assert request.description is None

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

    def test_valid_key_with_underscores(self):
        """Test that keys with underscores are allowed"""
        request = SetConfigRequest(
            key="valid_key_123",
            value="value",
            type=ConfigType.STRING
        )
        assert request.key == "valid_key_123"

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

    def test_valid_config_response(self):
        """Test that valid config response is accepted"""
        config = Config(
            key="api_timeout",
            value="30",
            type=ConfigType.INT,
            scope="GLOBAL",
            description="API timeout in seconds",
            updated_at=datetime.utcnow(),
            updated_by="user-123"
        )
        assert config.key == "api_timeout"
        assert config.value == "30"
        assert config.type == ConfigType.INT
        assert config.scope == "GLOBAL"
        assert config.description == "API timeout in seconds"
        assert isinstance(config.updated_at, datetime)
        assert config.updated_by == "user-123"

    def test_config_without_description(self):
        """Test config with null description"""
        config = Config(
            key="test_key",
            value="test_value",
            type=ConfigType.STRING,
            scope="org",
            org_id="test-org-123",
            description=None,
            updated_at=datetime.utcnow(),
            updated_by="user-123"
        )
        assert config.description is None
        assert config.scope == "org"
        assert config.org_id == "test-org-123"

    def test_config_missing_required_fields(self):
        """Test that key and value are required"""
        with pytest.raises(ValidationError) as exc_info:
            Config(
                type=ConfigType.STRING
                # Missing: key, value
            )

        errors = exc_info.value.errors()
        required_fields = {"key", "value"}
        missing_fields = {e["loc"][0] for e in errors if e["type"] == "missing"}
        assert required_fields.issubset(missing_fields)

    def test_config_serialization(self):
        """Test that config can be serialized to dict/JSON"""
        config = Config(
            key="test_key",
            value="test_value",
            type=ConfigType.STRING,
            scope="GLOBAL",
            description="Test description",
            updated_at=datetime.utcnow(),
            updated_by="user-123"
        )

        config_dict = config.model_dump()
        assert "key" in config_dict
        assert "value" in config_dict
        assert "type" in config_dict
        assert "scope" in config_dict
        assert "description" in config_dict
        assert "updated_at" in config_dict
        assert "updated_by" in config_dict

    def test_config_json_serialization(self):
        """Test that config can be serialized to JSON mode"""
        config = Config(
            key="test_key",
            value="test_value",
            type=ConfigType.STRING,
            scope="GLOBAL",
            description="Test description",
            updated_at=datetime.utcnow(),
            updated_by="user-123"
        )

        config_dict = config.model_dump(mode="json")
        assert isinstance(config_dict["updated_at"], str)  # datetime -> ISO string


class TestConfigTypeEnum:
    """Test ConfigType enum values"""

    def test_all_config_types(self):
        """Test that all expected config types are available"""
        assert ConfigType.STRING == "string"
        assert ConfigType.INT == "int"
        assert ConfigType.BOOL == "bool"
        assert ConfigType.JSON == "json"
        assert ConfigType.SECRET == "secret"

    def test_config_type_in_request(self):
        """Test using enum in request"""
        for config_type in [ConfigType.STRING, ConfigType.INT, ConfigType.BOOL,
                           ConfigType.JSON, ConfigType.SECRET]:
            request = SetConfigRequest(
                key="test_key",
                value="test_value",
                type=config_type
            )
            assert request.type == config_type
