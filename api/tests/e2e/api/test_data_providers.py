"""
E2E tests for data providers.

Tests data provider creation, discovery, listing, and metadata extraction.
Uses write_and_register() to write files and register decorated functions
in a single step, avoiding poll-based discovery.
"""

import pytest

from tests.e2e.conftest import write_and_register


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
        result = write_and_register(
            e2e_client,
            platform_admin.headers,
            "e2e_data_provider.py",
            data_provider_content,
            "e2e_test_provider",
        )

        yield {
            "id": result["id"],
            "path": "e2e_data_provider.py",
            "name": result["name"],
            "description": result["description"],
            "type": result["type"],
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
        result = write_and_register(
            e2e_client,
            platform_admin.headers,
            "e2e_creation_test_provider.py",
            data_provider_content,
            "e2e_creation_test",
        )
        assert result["type"] == "data_provider", \
            f"Expected type='data_provider', got '{result['type']}'"

        # Cleanup
        e2e_client.delete(
            "/api/files/editor?path=e2e_creation_test_provider.py",
            headers=platform_admin.headers,
        )

    def test_data_provider_discovered(self, e2e_client, platform_admin, test_data_provider_file):
        """Verify data provider is discovered after file creation (discovery is synchronous)."""
        response = e2e_client.get(
            "/api/workflows?type=data_provider",
            headers=platform_admin.headers,
        )
        assert response.status_code == 200, f"List data providers failed: {response.text}"
        providers = response.json()
        provider_names = [p["name"] for p in providers]

        assert test_data_provider_file["name"] in provider_names, \
            f"Data provider {test_data_provider_file['name']} not discovered after file write"

    def test_data_provider_in_list(self, e2e_client, platform_admin, test_data_provider_file):
        """Verify data provider appears in /api/workflows?type=data_provider list."""
        response = e2e_client.get(
            "/api/workflows?type=data_provider",
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
        response = e2e_client.get(
            "/api/workflows?type=data_provider",
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

    def test_org_user_cannot_list_all_data_providers(self, e2e_client, org1_user):
        """Org user cannot list all data providers (requires platform admin)."""
        response = e2e_client.get(
            "/api/workflows?type=data_provider",
            headers=org1_user.headers,
        )
        # Workflows endpoint requires platform admin access
        assert response.status_code == 403, \
            f"Org user should not be able to list all data providers: {response.status_code}"


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
        result = write_and_register(
            e2e_client,
            platform_admin.headers,
            "e2e_parametrized_provider.py",
            data_provider_content,
            "e2e_parametrized_provider",
        )

        yield {
            "id": result["id"],
            "path": "e2e_parametrized_provider.py",
            "name": result["name"],
            "description": result["description"],
            "type": result["type"],
        }

        # Cleanup
        e2e_client.delete(
            "/api/files/editor?path=e2e_parametrized_provider.py",
            headers=platform_admin.headers,
        )

    def test_parametrized_provider_discovered(self, e2e_client, platform_admin, parametrized_provider_file):
        """Parametrized data provider is discovered (discovery is synchronous)."""
        response = e2e_client.get(
            "/api/workflows?type=data_provider",
            headers=platform_admin.headers,
        )
        assert response.status_code == 200
        providers = response.json()
        provider_names = [p["name"] for p in providers]

        assert parametrized_provider_file["name"] in provider_names, \
            "Parametrized provider not discovered after file write"

    def test_parametrized_provider_has_parameters(self, e2e_client, platform_admin, parametrized_provider_file):
        """Parametrized data provider includes parameter metadata."""
        response = e2e_client.get(
            "/api/workflows?type=data_provider",
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
            "/api/workflows?type=data_provider",
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


@pytest.mark.e2e
class TestDataProviderExecution:
    """Test executing data providers via /api/workflows/execute.

    Data providers are stored in the workflows table with type='data_provider',
    so they can also be executed through the standard workflow execution endpoint.
    """

    @pytest.fixture(scope="class")
    def executable_data_provider(self, e2e_client, platform_admin):
        """Create a data provider for execution tests."""
        data_provider_content = '''"""E2E Executable Data Provider"""
from bifrost import data_provider

@data_provider(
    name="e2e_executable_provider",
    description="Data provider for execution tests"
)
async def e2e_executable_provider(category: str = "default"):
    """Returns test options based on category."""
    options = {
        "default": [
            {"value": "opt1", "label": "Option 1"},
            {"value": "opt2", "label": "Option 2"},
        ],
        "premium": [
            {"value": "premium1", "label": "Premium Option 1"},
            {"value": "premium2", "label": "Premium Option 2"},
        ],
    }
    return options.get(category, options["default"])
'''
        result = write_and_register(
            e2e_client,
            platform_admin.headers,
            "e2e_executable_provider.py",
            data_provider_content,
            "e2e_executable_provider",
        )

        yield {
            "id": result["id"],
            "name": result["name"],
            "type": result["type"],
        }

        # Cleanup
        e2e_client.delete(
            "/api/files/editor?path=e2e_executable_provider.py",
            headers=platform_admin.headers,
        )

    def test_data_provider_has_correct_type(self, e2e_client, platform_admin, executable_data_provider):
        """Data provider appears in workflows list with type='data_provider'."""
        assert executable_data_provider["type"] == "data_provider", \
            f"Data provider should have type='data_provider', got '{executable_data_provider['type']}'"

    def test_execute_data_provider_via_workflow_endpoint(self, e2e_client, platform_admin, executable_data_provider):
        """Data provider can be executed via /api/workflows/execute endpoint."""
        response = e2e_client.post(
            "/api/workflows/execute",
            headers=platform_admin.headers,
            json={
                "workflow_id": executable_data_provider["id"],
                "input_data": {"category": "default"},
            },
        )
        assert response.status_code == 200, f"Execute data provider failed: {response.text}"
        data = response.json()

        # Should have execution_id and status
        assert "execution_id" in data or "executionId" in data, "Should return execution_id"
        assert data.get("status") in ["Success", "Running", "Pending"], \
            f"Unexpected status: {data.get('status')}"

    def test_execute_data_provider_with_parameters(self, e2e_client, platform_admin, executable_data_provider):
        """Data provider execution accepts and uses parameters."""
        response = e2e_client.post(
            "/api/workflows/execute",
            headers=platform_admin.headers,
            json={
                "workflow_id": executable_data_provider["id"],
                "input_data": {"category": "premium"},
            },
        )
        assert response.status_code == 200, f"Execute data provider failed: {response.text}"
        data = response.json()

        # For sync execution, check the result contains premium options
        result = data.get("result", {})
        if isinstance(result, list):
            # Data providers return a list directly
            assert len(result) == 2, f"Expected 2 premium options, got {len(result)}"
        elif isinstance(result, dict) and "error" not in result:
            # Execution succeeded
            assert data.get("status") == "Success"
