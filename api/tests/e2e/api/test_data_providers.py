"""
E2E tests for data providers.

Tests data provider creation, discovery, listing, and metadata extraction.
Follows the pattern of creating a data provider file via the editor API,
waiting for discovery, then verifying the results.
"""

import pytest


@pytest.mark.e2e
class TestDataProviderCreation:
    """Test data provider file creation and discovery."""

    @pytest.fixture(scope="class")
    def test_data_provider_file(self, e2e_client, platform_admin):
        """Create a test data provider file and clean up after tests."""
        data_provider_content = '''"""E2E Data Provider Test"""
from bifrost import data_provider

@data_provider(
    name="e2e_test_provider",
    description="E2E test data provider"
)
async def e2e_test_provider():
    """Returns test data."""
    return [{"id": 1, "name": "Test"}]
'''
        response = e2e_client.put(
            "/api/files/editor/content",
            headers=platform_admin.headers,
            json={
                "path": "e2e_data_provider.py",
                "content": data_provider_content,
                "encoding": "utf-8",
            },
        )
        assert response.status_code == 200, f"Create data provider failed: {response.text}"

        yield {
            "path": "e2e_data_provider.py",
            "name": "e2e_test_provider",
            "description": "E2E test data provider",
        }

        # Cleanup
        e2e_client.delete(
            "/api/files/editor?path=e2e_data_provider.py",
            headers=platform_admin.headers,
        )

    def test_create_data_provider(self, e2e_client, platform_admin):
        """Create a data provider with @data_provider decorator via editor API."""
        data_provider_content = '''"""E2E Data Provider Creation Test"""
from bifrost import data_provider

@data_provider(
    name="e2e_creation_test",
    description="Test creation of data provider"
)
async def e2e_creation_test():
    """Returns test data for creation test."""
    return [{"id": 1, "value": "created"}]
'''
        response = e2e_client.put(
            "/api/files/editor/content",
            headers=platform_admin.headers,
            json={
                "path": "e2e_creation_test_provider.py",
                "content": data_provider_content,
                "encoding": "utf-8",
            },
        )
        assert response.status_code == 200, f"Create data provider failed: {response.text}"

        # Cleanup
        e2e_client.delete(
            "/api/files/editor?path=e2e_creation_test_provider.py",
            headers=platform_admin.headers,
        )

    def test_data_provider_discovered(self, e2e_client, platform_admin, test_data_provider_file):
        """Verify data provider is discovered after file creation (discovery is synchronous)."""
        response = e2e_client.get(
            "/api/data-providers",
            headers=platform_admin.headers,
        )
        assert response.status_code == 200, f"List data providers failed: {response.text}"
        providers = response.json()
        provider_names = [p["name"] for p in providers]

        assert test_data_provider_file["name"] in provider_names, \
            f"Data provider {test_data_provider_file['name']} not discovered after file write"

    def test_data_provider_in_list(self, e2e_client, platform_admin, test_data_provider_file):
        """Verify data provider appears in /api/data-providers list."""
        response = e2e_client.get(
            "/api/data-providers",
            headers=platform_admin.headers,
        )
        assert response.status_code == 200, f"List data providers failed: {response.text}"
        providers = response.json()

        # Find the data provider
        provider = next(
            (p for p in providers if p["name"] == test_data_provider_file["name"]),
            None
        )
        assert provider is not None, \
            f"Data provider {test_data_provider_file['name']} not found in list"

    def test_data_provider_metadata_correct(self, e2e_client, platform_admin, test_data_provider_file):
        """Verify data provider metadata is correctly extracted."""
        # Discovery happens synchronously during file write - no sleep needed
        response = e2e_client.get(
            "/api/data-providers",
            headers=platform_admin.headers,
        )
        assert response.status_code == 200, f"List data providers failed: {response.text}"
        providers = response.json()

        provider = next(
            (p for p in providers if p["name"] == test_data_provider_file["name"]),
            None
        )
        assert provider is not None, \
            f"Data provider {test_data_provider_file['name']} not found in list"

        # Verify metadata fields
        assert provider["name"] == test_data_provider_file["name"], \
            f"Provider name mismatch: {provider['name']} != {test_data_provider_file['name']}"
        assert provider["description"] == test_data_provider_file["description"], \
            f"Provider description mismatch: {provider['description']} != {test_data_provider_file['description']}"
        assert "source_file_path" in provider, "Provider missing source_file_path"
        assert provider["source_file_path"] is not None, "Provider source_file_path is None"
        assert "e2e_data_provider.py" in provider["source_file_path"], \
            f"source_file_path should contain file name: {provider['source_file_path']}"

        # Verify category and cache_ttl_seconds have defaults
        assert "category" in provider, "Provider missing category"
        assert "cache_ttl_seconds" in provider, "Provider missing cache_ttl_seconds"


@pytest.mark.e2e
class TestDataProviderAccess:
    """Test data provider access control."""

    def test_org_user_can_list_data_providers(self, e2e_client, org1_user):
        """Org user can list data providers."""
        response = e2e_client.get(
            "/api/data-providers",
            headers=org1_user.headers,
        )
        assert response.status_code == 200, \
            f"Org user should list data providers: {response.status_code}"
        providers = response.json()
        assert isinstance(providers, list), "Response should be a list of providers"


@pytest.mark.e2e
class TestDataProviderParametrization:
    """Test data provider with parameters."""

    @pytest.fixture(scope="class")
    def parametrized_provider_file(self, e2e_client, platform_admin):
        """Create a parametrized data provider file."""
        data_provider_content = '''"""E2E Parametrized Data Provider"""
from bifrost import data_provider

@data_provider(
    name="e2e_parametrized_provider",
    description="Data provider with parameters"
)
async def e2e_parametrized_provider(category: str = "default"):
    """Returns dynamic data based on category."""
    data = {
        "default": [
            {"value": "opt_a", "label": "Option A"},
            {"value": "opt_b", "label": "Option B"},
        ],
        "advanced": [
            {"value": "opt_x", "label": "Advanced X"},
            {"value": "opt_y", "label": "Advanced Y"},
        ],
    }
    return data.get(category, data["default"])
'''
        response = e2e_client.put(
            "/api/files/editor/content",
            headers=platform_admin.headers,
            json={
                "path": "e2e_parametrized_provider.py",
                "content": data_provider_content,
                "encoding": "utf-8",
            },
        )
        assert response.status_code == 200, f"Create data provider failed: {response.text}"

        yield {
            "path": "e2e_parametrized_provider.py",
            "name": "e2e_parametrized_provider",
            "description": "Data provider with parameters",
        }

        # Cleanup
        e2e_client.delete(
            "/api/files/editor?path=e2e_parametrized_provider.py",
            headers=platform_admin.headers,
        )

    def test_parametrized_provider_discovered(self, e2e_client, platform_admin, parametrized_provider_file):
        """Parametrized data provider is discovered (discovery is synchronous)."""
        response = e2e_client.get(
            "/api/data-providers",
            headers=platform_admin.headers,
        )
        assert response.status_code == 200
        providers = response.json()
        provider_names = [p["name"] for p in providers]

        assert parametrized_provider_file["name"] in provider_names, \
            "Parametrized provider not discovered after file write"

    def test_parametrized_provider_has_parameters(self, e2e_client, platform_admin, parametrized_provider_file):
        """Parametrized data provider includes parameter metadata."""
        # Discovery happens synchronously during file write - no sleep needed
        response = e2e_client.get(
            "/api/data-providers",
            headers=platform_admin.headers,
        )
        assert response.status_code == 200
        providers = response.json()

        provider = next(
            (p for p in providers if p["name"] == parametrized_provider_file["name"]),
            None
        )
        assert provider is not None, "Parametrized provider not found"

        # Verify parameters field exists
        assert "parameters" in provider, "Provider missing parameters field"
        parameters = provider["parameters"]
        assert isinstance(parameters, list), "Parameters should be a list"
        # Note: Parameter discovery depends on @param decorators; may be empty without them


@pytest.mark.e2e
class TestMultipleDataProviders:
    """Test listing multiple data providers together."""

    def test_list_returns_multiple_providers(self, e2e_client, platform_admin):
        """Listing data providers returns multiple providers."""
        response = e2e_client.get(
            "/api/data-providers",
            headers=platform_admin.headers,
        )
        assert response.status_code == 200, f"List data providers failed: {response.text}"
        providers = response.json()

        # Should be a list
        assert isinstance(providers, list), "Response should be a list"

        # Verify each provider has required fields
        for provider in providers:
            assert "name" in provider, "Provider missing name"
            assert "description" in provider, "Provider missing description"
            assert isinstance(provider["name"], str), "Provider name should be string"
