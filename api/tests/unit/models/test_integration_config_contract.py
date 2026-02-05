"""
Contract tests for IntegrationConfig API models
Tests Pydantic validation rules for request/response models
"""

from datetime import datetime

import pytest
from pydantic import ValidationError

from src.models import IntegrationConfig, IntegrationType, SetIntegrationConfigRequest


# Note: Models use snake_case (e.g., updated_at, updated_by)
# Settings require: client_secret_config_key (not client_secret_ref)
#                   api_key_config_key (not api_key_ref)


class TestSetIntegrationConfigRequest:
    """Test validation for SetIntegrationConfigRequest model"""

    def test_invalid_type_enum(self):
        """Test that invalid integration type is rejected"""
        with pytest.raises(ValidationError) as exc_info:
            SetIntegrationConfigRequest(
                type="invalid_type",
                settings={}
            )

        errors = exc_info.value.errors()
        assert any(e["loc"] == ("type",) for e in errors)

    def test_msgraph_missing_tenant_id(self):
        """Test that msgraph integration requires tenant_id"""
        with pytest.raises(ValidationError) as exc_info:
            SetIntegrationConfigRequest(
                type=IntegrationType.MSGRAPH,
                settings={
                    "client_id": "87654321-4321-4321-4321-210987654321",
                    "client_secret_config_key": "org-123-msgraph-secret"
                }
            )

        errors = exc_info.value.errors()
        assert any("tenant_id" in str(e) for e in errors)

    def test_msgraph_missing_client_id(self):
        """Test that msgraph integration requires client_id"""
        with pytest.raises(ValidationError) as exc_info:
            SetIntegrationConfigRequest(
                type=IntegrationType.MSGRAPH,
                settings={
                    "tenant_id": "12345678-1234-1234-1234-123456789012",
                    "client_secret_config_key": "org-123-msgraph-secret"
                }
            )

        errors = exc_info.value.errors()
        assert any("client_id" in str(e) for e in errors)

    def test_msgraph_missing_client_secret_config_key(self):
        """Test that msgraph integration requires client_secret_config_key"""
        with pytest.raises(ValidationError) as exc_info:
            SetIntegrationConfigRequest(
                type=IntegrationType.MSGRAPH,
                settings={
                    "tenant_id": "12345678-1234-1234-1234-123456789012",
                    "client_id": "87654321-4321-4321-4321-210987654321"
                }
            )

        errors = exc_info.value.errors()
        assert any("client_secret_config_key" in str(e) for e in errors)

    def test_halopsa_missing_api_url(self):
        """Test that halopsa integration requires api_url"""
        with pytest.raises(ValidationError) as exc_info:
            SetIntegrationConfigRequest(
                type=IntegrationType.HALOPSA,
                settings={
                    "client_id": "halopsa-client-123",
                    "api_key_config_key": "org-123-halopsa-key"
                }
            )

        errors = exc_info.value.errors()
        assert any("api_url" in str(e) for e in errors)

    def test_halopsa_missing_client_id(self):
        """Test that halopsa integration requires client_id"""
        with pytest.raises(ValidationError) as exc_info:
            SetIntegrationConfigRequest(
                type=IntegrationType.HALOPSA,
                settings={
                    "api_url": "https://tenant.halopsa.com",
                    "api_key_config_key": "org-123-halopsa-key"
                }
            )

        errors = exc_info.value.errors()
        assert any("client_id" in str(e) for e in errors)

    def test_halopsa_missing_api_key_config_key(self):
        """Test that halopsa integration requires api_key_config_key"""
        with pytest.raises(ValidationError) as exc_info:
            SetIntegrationConfigRequest(
                type=IntegrationType.HALOPSA,
                settings={
                    "api_url": "https://tenant.halopsa.com",
                    "client_id": "halopsa-client-123"
                }
            )

        errors = exc_info.value.errors()
        assert any("api_key_config_key" in str(e) for e in errors)

    def test_missing_required_type(self):
        """Test that type is required"""
        with pytest.raises(ValidationError) as exc_info:
            SetIntegrationConfigRequest(
                settings={
                    "tenant_id": "12345678-1234-1234-1234-123456789012",
                    "client_id": "87654321-4321-4321-4321-210987654321",
                    "client_secret_config_key": "org-123-msgraph-secret"
                }
            )

        errors = exc_info.value.errors()
        assert any(e["loc"] == ("type",) and e["type"] == "missing" for e in errors)

    def test_missing_required_settings(self):
        """Test that settings is required"""
        with pytest.raises(ValidationError) as exc_info:
            SetIntegrationConfigRequest(
                type=IntegrationType.MSGRAPH
            )

        errors = exc_info.value.errors()
        assert any(e["loc"] == ("settings",) and e["type"] == "missing" for e in errors)


class TestIntegrationConfigResponse:
    """Test IntegrationConfig response model structure"""

    def test_integration_config_missing_required_fields(self):
        """Test that all required fields must be present"""
        with pytest.raises(ValidationError) as exc_info:
            IntegrationConfig(
                type=IntegrationType.MSGRAPH,
                enabled=True,
                settings={"test": "value"}
                # Missing: updated_at, updated_by
            )

        errors = exc_info.value.errors()
        required_fields = {"updated_at", "updated_by"}
        missing_fields = {e["loc"][0] for e in errors if e["type"] == "missing"}
        assert required_fields.issubset(missing_fields)

    def test_integration_config_json_serialization(self):
        """Test that integration config can be serialized to JSON mode"""
        config = IntegrationConfig(
            type=IntegrationType.MSGRAPH,
            enabled=True,
            settings={
                "tenant_id": "12345678-1234-1234-1234-123456789012",
                "client_id": "87654321-4321-4321-4321-210987654321",
                "client_secret_config_key": "org-123-msgraph-secret"
            },
            updated_at=datetime.utcnow(),
            updated_by="user-123"
        )

        config_dict = config.model_dump(mode="json")
        assert isinstance(config_dict["updated_at"], str)  # datetime -> ISO string
        assert config_dict["type"] == "msgraph"  # Enum -> string value


