"""
Unit tests for Integrations contract models.

Tests Pydantic validation for request/response models.
"""

from datetime import datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.models.contracts.integrations import (
    ConfigSchemaItem,
    IntegrationCreate,
    IntegrationUpdate,
    IntegrationMappingCreate,
    IntegrationMappingUpdate,
    IntegrationResponse,
    IntegrationMappingResponse,
    IntegrationListResponse,
    IntegrationMappingListResponse,
    IntegrationSDKResponse,
)


class TestConfigSchemaItem:
    """Tests for ConfigSchemaItem model."""

    def test_config_schema_item_valid(self):
        """Test valid config schema item."""
        item = ConfigSchemaItem(
            key="api_key",
            type="secret",
            required=True,
            description="API Key for authentication",
        )
        assert item.key == "api_key"
        assert item.type == "secret"
        assert item.required is True
        assert item.description == "API Key for authentication"
        assert item.options is None

    def test_config_schema_item_minimal(self):
        """Test config schema item with only required fields."""
        item = ConfigSchemaItem(key="setting1", type="string")
        assert item.key == "setting1"
        assert item.type == "string"
        assert item.required is False
        assert item.description is None
        assert item.options is None

    def test_config_schema_item_with_options(self):
        """Test config schema item with dropdown options."""
        item = ConfigSchemaItem(
            key="environment",
            type="string",
            options=["production", "staging", "development"],
        )
        assert item.key == "environment"
        assert item.type == "string"
        assert item.options == ["production", "staging", "development"]

    def test_config_schema_item_all_types(self):
        """Test config schema item with all supported types."""
        for config_type in ["string", "int", "bool", "json", "secret"]:
            item = ConfigSchemaItem(key="test", type=config_type)  # type: ignore
            assert item.type == config_type

    def test_config_schema_item_invalid_type(self):
        """Test config schema item with invalid type."""
        with pytest.raises(ValidationError) as exc_info:
            ConfigSchemaItem(key="test", type="invalid")  # type: ignore
        errors = exc_info.value.errors()
        assert any(e["loc"] == ("type",) for e in errors)

    def test_config_schema_item_invalid_key_empty(self):
        """Test config schema item with empty key."""
        with pytest.raises(ValidationError) as exc_info:
            ConfigSchemaItem(key="", type="string")
        errors = exc_info.value.errors()
        assert any(e["loc"] == ("key",) for e in errors)

    def test_config_schema_item_invalid_key_characters(self):
        """Test config schema item with invalid characters in key."""
        with pytest.raises(ValidationError) as exc_info:
            ConfigSchemaItem(key="api-key", type="string")
        errors = exc_info.value.errors()
        assert any(e["loc"] == ("key",) for e in errors)

    def test_config_schema_item_invalid_key_too_long(self):
        """Test config schema item with key exceeding max length."""
        with pytest.raises(ValidationError) as exc_info:
            ConfigSchemaItem(key="a" * 256, type="string")
        errors = exc_info.value.errors()
        assert any(e["loc"] == ("key",) for e in errors)

    def test_config_schema_item_valid_key_patterns(self):
        """Test valid key patterns (alphanumeric and underscores)."""
        valid_keys = ["api_key", "API_KEY", "key123", "KEY_123_VALUE"]
        for key in valid_keys:
            item = ConfigSchemaItem(key=key, type="string")
            assert item.key == key

    def test_config_schema_item_description_too_long(self):
        """Test config schema item with description exceeding max length."""
        with pytest.raises(ValidationError) as exc_info:
            ConfigSchemaItem(key="test", type="string", description="a" * 501)
        errors = exc_info.value.errors()
        assert any(e["loc"] == ("description",) for e in errors)


class TestIntegrationCreate:
    """Tests for IntegrationCreate model."""

    def test_integration_create_minimal(self):
        """Test creating integration with only required fields."""
        data = IntegrationCreate(name="Test Integration")
        assert data.name == "Test Integration"
        assert data.config_schema is None
        assert data.entity_id is None
        assert data.entity_id_name is None
        assert data.default_entity_id is None

    def test_integration_create_full(self):
        """Test creating integration with all fields."""
        schema = [
            ConfigSchemaItem(key="api_key", type="secret", required=True),
            ConfigSchemaItem(key="timeout", type="int", required=False),
        ]

        data = IntegrationCreate(
            name="Full Integration",
            config_schema=schema,
            entity_id="tenant-123",
            entity_id_name="Tenant ID",
            default_entity_id="common",
        )

        assert data.name == "Full Integration"
        assert data.config_schema is not None
        assert len(data.config_schema) == 2
        assert data.config_schema[0].key == "api_key"
        assert data.entity_id == "tenant-123"
        assert data.entity_id_name == "Tenant ID"
        assert data.default_entity_id == "common"

    def test_integration_create_invalid_name_empty(self):
        """Test creating integration with empty name."""
        with pytest.raises(ValidationError) as exc_info:
            IntegrationCreate(name="")
        errors = exc_info.value.errors()
        assert any(e["loc"] == ("name",) for e in errors)

    def test_integration_create_invalid_name_too_long(self):
        """Test creating integration with name exceeding max length."""
        with pytest.raises(ValidationError) as exc_info:
            IntegrationCreate(name="a" * 256)
        errors = exc_info.value.errors()
        assert any(e["loc"] == ("name",) for e in errors)

    def test_integration_create_missing_name(self):
        """Test creating integration without required name."""
        with pytest.raises(ValidationError) as exc_info:
            IntegrationCreate()  # type: ignore
        errors = exc_info.value.errors()
        assert any(e["type"] == "missing" and e["loc"] == ("name",) for e in errors)

    def test_integration_create_with_config_schema(self):
        """Test creating integration with config schema."""
        schema = [
            ConfigSchemaItem(
                key="api_key",
                type="secret",
                required=True,
                description="API Key",
            ),
            ConfigSchemaItem(
                key="environment",
                type="string",
                options=["prod", "staging"],
            ),
        ]

        data = IntegrationCreate(name="Integration", config_schema=schema)

        assert data.config_schema is not None
        assert len(data.config_schema) == 2
        assert data.config_schema[0].type == "secret"
        assert data.config_schema[1].options == ["prod", "staging"]


class TestIntegrationUpdate:
    """Tests for IntegrationUpdate model."""

    def test_integration_update_empty(self):
        """Test update with no fields (all optional)."""
        data = IntegrationUpdate(name=None)
        assert data.name is None
        assert data.list_entities_data_provider_id is None
        assert data.config_schema is None
        assert data.entity_id is None
        assert data.entity_id_name is None
        assert data.default_entity_id is None

    def test_integration_update_name_only(self):
        """Test update with only name."""
        data = IntegrationUpdate(name="Updated Name")
        assert data.name == "Updated Name"
        assert data.list_entities_data_provider_id is None

    def test_integration_update_config_schema_only(self):
        """Test update with only config schema."""
        schema = [ConfigSchemaItem(key="new_key", type="string")]
        data = IntegrationUpdate(config_schema=schema)
        assert data.config_schema == schema
        assert data.name is None

    def test_integration_update_invalid_name_empty(self):
        """Test update with empty name fails validation."""
        with pytest.raises(ValidationError) as exc_info:
            IntegrationUpdate(name="")
        errors = exc_info.value.errors()
        assert any(e["loc"] == ("name",) for e in errors)


class TestIntegrationMappingCreate:
    """Tests for IntegrationMappingCreate model."""

    def test_mapping_create_minimal(self):
        """Test creating mapping with required fields only."""
        org_id = uuid4()
        data = IntegrationMappingCreate(
            organization_id=org_id,
            entity_id="tenant-123",
        )
        assert data.organization_id == org_id
        assert data.entity_id == "tenant-123"
        assert data.entity_name is None
        assert data.oauth_token_id is None
        assert data.config is None

    def test_mapping_create_full(self):
        """Test creating mapping with all fields."""
        org_id = uuid4()
        token_id = uuid4()
        data = IntegrationMappingCreate(
            organization_id=org_id,
            entity_id="tenant-456",
            entity_name="Test Tenant",
            oauth_token_id=token_id,
            config={"setting1": "value1"},
        )
        assert data.organization_id == org_id
        assert data.entity_id == "tenant-456"
        assert data.entity_name == "Test Tenant"
        assert data.oauth_token_id == token_id
        assert data.config == {"setting1": "value1"}

    def test_mapping_create_missing_organization_id(self):
        """Test creating mapping without organization_id."""
        with pytest.raises(ValidationError) as exc_info:
            IntegrationMappingCreate(entity_id="tenant-123")  # type: ignore
        errors = exc_info.value.errors()
        assert any(
            e["type"] == "missing" and e["loc"] == ("organization_id",)
            for e in errors
        )

    def test_mapping_create_missing_entity_id(self):
        """Test creating mapping without entity_id."""
        with pytest.raises(ValidationError) as exc_info:
            IntegrationMappingCreate(organization_id=uuid4())  # type: ignore
        errors = exc_info.value.errors()
        assert any(
            e["type"] == "missing" and e["loc"] == ("entity_id",)
            for e in errors
        )

    def test_mapping_create_invalid_entity_id_empty(self):
        """Test creating mapping with empty entity_id."""
        with pytest.raises(ValidationError) as exc_info:
            IntegrationMappingCreate(
                organization_id=uuid4(),
                entity_id="",
            )
        errors = exc_info.value.errors()
        assert any(e["loc"] == ("entity_id",) for e in errors)

    def test_mapping_create_invalid_entity_id_too_long(self):
        """Test creating mapping with entity_id exceeding max length."""
        with pytest.raises(ValidationError) as exc_info:
            IntegrationMappingCreate(
                organization_id=uuid4(),
                entity_id="a" * 256,
            )
        errors = exc_info.value.errors()
        assert any(e["loc"] == ("entity_id",) for e in errors)

    def test_mapping_create_invalid_entity_name_too_long(self):
        """Test creating mapping with entity_name exceeding max length."""
        with pytest.raises(ValidationError) as exc_info:
            IntegrationMappingCreate(
                organization_id=uuid4(),
                entity_id="tenant-123",
                entity_name="a" * 256,
            )
        errors = exc_info.value.errors()
        assert any(e["loc"] == ("entity_name",) for e in errors)


class TestIntegrationMappingUpdate:
    """Tests for IntegrationMappingUpdate model."""

    def test_mapping_update_empty(self):
        """Test update with no fields (all optional)."""
        data = IntegrationMappingUpdate(entity_id=None)
        assert data.entity_id is None
        assert data.entity_name is None
        assert data.oauth_token_id is None
        assert data.config is None

    def test_mapping_update_entity_id(self):
        """Test update with only entity_id."""
        data = IntegrationMappingUpdate(entity_id="tenant-new")
        assert data.entity_id == "tenant-new"
        assert data.entity_name is None

    def test_mapping_update_entity_name(self):
        """Test update with only entity_name."""
        data = IntegrationMappingUpdate(entity_name="Updated Name")
        assert data.entity_name == "Updated Name"
        assert data.entity_id is None

    def test_mapping_update_oauth_token(self):
        """Test update with only oauth_token_id."""
        token_id = uuid4()
        data = IntegrationMappingUpdate(oauth_token_id=token_id)
        assert data.oauth_token_id == token_id

    def test_mapping_update_config(self):
        """Test update with only config."""
        config = {"key1": "value1"}
        data = IntegrationMappingUpdate(config=config)
        assert data.config == config

    def test_mapping_update_invalid_entity_id_empty(self):
        """Test update with empty entity_id fails validation."""
        with pytest.raises(ValidationError) as exc_info:
            IntegrationMappingUpdate(entity_id="")
        errors = exc_info.value.errors()
        assert any(e["loc"] == ("entity_id",) for e in errors)


class TestIntegrationResponse:
    """Tests for IntegrationResponse model."""

    def test_integration_response_valid(self):
        """Test valid integration response."""
        now = datetime.utcnow()
        integration_id = uuid4()

        response = IntegrationResponse(
            id=integration_id,
            name="Test Integration",
            list_entities_data_provider_id=None,
            config_schema=[
                ConfigSchemaItem(key="api_key", type="secret", required=True)
            ],
            entity_id="tenant-123",
            entity_id_name="Tenant ID",
            default_entity_id="common",
            has_oauth_config=True,
            is_deleted=False,
            created_at=now,
            updated_at=now,
        )

        assert response.id == integration_id
        assert response.name == "Test Integration"
        assert response.entity_id == "tenant-123"
        assert response.entity_id_name == "Tenant ID"
        assert response.default_entity_id == "common"
        assert response.has_oauth_config is True
        assert response.is_deleted is False
        assert response.config_schema is not None
        assert len(response.config_schema) == 1

    def test_integration_response_minimal(self):
        """Test integration response with minimal fields."""
        now = datetime.utcnow()
        response = IntegrationResponse(
            id=uuid4(),
            name="Simple",
            created_at=now,
            updated_at=now,
        )
        assert response.id is not None
        assert response.name == "Simple"
        assert response.is_deleted is False
        assert response.config_schema is None


class TestIntegrationMappingResponse:
    """Tests for IntegrationMappingResponse model."""

    def test_mapping_response_valid(self):
        """Test valid mapping response."""
        now = datetime.utcnow()
        mapping_id = uuid4()
        integration_id = uuid4()
        org_id = uuid4()
        token_id = uuid4()

        response = IntegrationMappingResponse(
            id=mapping_id,
            integration_id=integration_id,
            organization_id=org_id,
            entity_id="tenant-123",
            entity_name="Test Tenant",
            oauth_token_id=token_id,
            config={"setting": "value"},
            created_at=now,
            updated_at=now,
        )

        assert response.id == mapping_id
        assert response.integration_id == integration_id
        assert response.entity_id == "tenant-123"
        assert response.config == {"setting": "value"}

    def test_mapping_response_minimal(self):
        """Test mapping response with minimal fields."""
        now = datetime.utcnow()
        response = IntegrationMappingResponse(
            id=uuid4(),
            integration_id=uuid4(),
            organization_id=uuid4(),
            entity_id="entity-1",
            created_at=now,
            updated_at=now,
        )
        assert response.entity_name is None
        assert response.oauth_token_id is None
        assert response.config is None


class TestIntegrationListResponse:
    """Tests for IntegrationListResponse model."""

    def test_integration_list_response_valid(self):
        """Test valid integration list response."""
        now = datetime.utcnow()
        items = [
            IntegrationResponse(
                id=uuid4(),
                name="Integration 1",
                created_at=now,
                updated_at=now,
            ),
            IntegrationResponse(
                id=uuid4(),
                name="Integration 2",
                created_at=now,
                updated_at=now,
            ),
        ]

        response = IntegrationListResponse(items=items, total=2)

        assert len(response.items) == 2
        assert response.total == 2

    def test_integration_list_response_empty(self):
        """Test empty integration list response."""
        response = IntegrationListResponse(items=[], total=0)
        assert len(response.items) == 0
        assert response.total == 0


class TestIntegrationMappingListResponse:
    """Tests for IntegrationMappingListResponse model."""

    def test_mapping_list_response_valid(self):
        """Test valid mapping list response."""
        now = datetime.utcnow()
        items = [
            IntegrationMappingResponse(
                id=uuid4(),
                integration_id=uuid4(),
                organization_id=uuid4(),
                entity_id="entity-1",
                created_at=now,
                updated_at=now,
            ),
            IntegrationMappingResponse(
                id=uuid4(),
                integration_id=uuid4(),
                organization_id=uuid4(),
                entity_id="entity-2",
                created_at=now,
                updated_at=now,
            ),
        ]

        response = IntegrationMappingListResponse(items=items, total=2)

        assert len(response.items) == 2
        assert response.total == 2

    def test_mapping_list_response_empty(self):
        """Test empty mapping list response."""
        response = IntegrationMappingListResponse(items=[], total=0)
        assert len(response.items) == 0
        assert response.total == 0


class TestIntegrationSDKResponse:
    """Tests for IntegrationSDKResponse model (SDK response)."""

    def test_integration_data_valid(self):
        """Test valid integration data."""
        integration_id = uuid4()
        data = IntegrationSDKResponse(
            integration_id=integration_id,
            entity_id="tenant-123",
            entity_name="Test Tenant",
            config={"api_key": "secret"},
            oauth_client_id="client-id",
            oauth_token_url="https://oauth.example.com/token?entity_id={entity_id}",
            oauth_scopes="read write",
        )

        assert data.integration_id == integration_id
        assert data.entity_id == "tenant-123"
        assert data.entity_name == "Test Tenant"
        assert data.config == {"api_key": "secret"}
        assert data.oauth_client_id == "client-id"
        assert data.oauth_token_url is not None
        assert "{entity_id}" in data.oauth_token_url
        assert data.oauth_scopes == "read write"

    def test_integration_data_minimal(self):
        """Test integration data with minimal fields."""
        integration_id = uuid4()
        data = IntegrationSDKResponse(
            integration_id=integration_id,
            entity_id="tenant-123",
        )

        assert data.integration_id == integration_id
        assert data.entity_id == "tenant-123"
        assert data.entity_name is None
        assert data.config == {}
        assert data.oauth_client_id is None
        assert data.oauth_token_url is None
        assert data.oauth_scopes is None

    def test_integration_data_default_config(self):
        """Test that config defaults to empty dict."""
        data = IntegrationSDKResponse(
            integration_id=uuid4(),
            entity_id="entity-1",
        )
        assert isinstance(data.config, dict)
        assert len(data.config) == 0

    def test_integration_data_missing_integration_id(self):
        """Test that integration_id is required and cannot be None."""
        with pytest.raises(ValidationError) as exc_info:
            IntegrationSDKResponse(integration_id=None, entity_id="entity-1")  # type: ignore
        errors = exc_info.value.errors()
        # Passing None to a UUID field raises uuid_type error
        assert any(
            e["type"] == "uuid_type" and e["loc"] == ("integration_id",)
            for e in errors
        )

    def test_integration_data_missing_entity_id(self):
        """Test that entity_id is required and cannot be None."""
        with pytest.raises(ValidationError) as exc_info:
            IntegrationSDKResponse(integration_id=uuid4(), entity_id=None)  # type: ignore
        errors = exc_info.value.errors()
        # Passing None to a str field raises string_type error
        assert any(
            e["type"] == "string_type" and e["loc"] == ("entity_id",)
            for e in errors
        )

    def test_integration_data_with_oauth_fields(self):
        """Test integration data with OAuth configuration."""
        data = IntegrationSDKResponse(
            integration_id=uuid4(),
            entity_id="tenant-123",
            oauth_client_id="client-123",
            oauth_token_url="https://oauth.example.com/token",
            oauth_scopes="read write delete",
        )

        assert data.oauth_client_id == "client-123"
        assert data.oauth_token_url == "https://oauth.example.com/token"
        assert data.oauth_scopes == "read write delete"
