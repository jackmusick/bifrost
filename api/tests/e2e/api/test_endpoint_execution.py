"""
E2E tests for workflow endpoint execution.

Tests the /api/endpoints/{workflow_name} functionality including:
- Dynamic OpenAPI generation for endpoint-enabled workflows
- API key authentication via X-Bifrost-Key header
- HTTP method restrictions
- Parameter passing via query string and request body
- Sync execution and result handling
"""

import time

import pytest


# Workflow content for endpoint-enabled workflow
ENDPOINT_WORKFLOW_CONTENT = '''"""E2E Endpoint Workflow"""
from bifrost import workflow

@workflow(
    name="e2e_endpoint_workflow",
    description="E2E test workflow exposed as HTTP endpoint",
    endpoint_enabled=True,
    allowed_methods=["GET", "POST"],
    execution_mode="sync",
)
async def e2e_endpoint_workflow(message: str, count: int = 1) -> dict:
    """Returns a greeting message repeated count times."""
    messages = [message] * count
    return {
        "status": "success",
        "message": message,
        "count": count,
        "messages": messages,
    }
'''

# Workflow content for POST-only endpoint
POST_ONLY_WORKFLOW_CONTENT = '''"""E2E POST-only Endpoint Workflow"""
from bifrost import workflow

@workflow(
    name="e2e_endpoint_post_only",
    description="E2E test workflow that only accepts POST requests",
    endpoint_enabled=True,
    allowed_methods=["POST"],
    execution_mode="sync",
)
async def e2e_endpoint_post_only(data: str) -> dict:
    """Workflow that only accepts POST requests."""
    return {
        "status": "success",
        "data": data,
        "method": "POST",
    }
'''


def _wait_for_workflow(e2e_client, platform_admin, workflow_name: str, max_attempts: int = 30) -> dict | None:
    """Wait for a workflow to be discovered and return it."""
    for _ in range(max_attempts):
        response = e2e_client.get(
            "/api/workflows",
            headers=platform_admin.headers,
        )
        if response.status_code == 200:
            workflows = response.json()
            workflow = next(
                (w for w in workflows if w.get("name") == workflow_name),
                None
            )
            if workflow:
                return workflow
        time.sleep(1)
    return None


@pytest.fixture(scope="module")
def endpoint_workflow_file(e2e_client, platform_admin):
    """
    Create the endpoint-enabled workflow file via Editor API.

    This fixture creates the workflow file, waits for discovery,
    and cleans up after tests.
    """
    # Create workflow file with index=true to enable synchronous ID injection
    response = e2e_client.put(
        "/api/files/editor/content?index=true",
        headers=platform_admin.headers,
        json={
            "path": "e2e_endpoint_workflow.py",
            "content": ENDPOINT_WORKFLOW_CONTENT,
            "encoding": "utf-8",
        },
    )
    assert response.status_code == 200, f"Failed to create workflow file: {response.text}"

    # Discovery happens synchronously during file write - just fetch the workflow
    workflow = _wait_for_workflow(e2e_client, platform_admin, "e2e_endpoint_workflow")
    assert workflow is not None, "Workflow e2e_endpoint_workflow not discovered after 30s"
    assert workflow.get("endpoint_enabled"), "Workflow should have endpoint_enabled=True"

    yield workflow

    # Cleanup: delete the workflow file
    e2e_client.delete(
        "/api/files/editor?path=e2e_endpoint_workflow.py",
        headers=platform_admin.headers,
    )


@pytest.fixture(scope="module")
def post_only_workflow_file(e2e_client, platform_admin):
    """
    Create the POST-only endpoint workflow file via Editor API.
    """
    # Create workflow file with index=true to enable synchronous ID injection
    response = e2e_client.put(
        "/api/files/editor/content?index=true",
        headers=platform_admin.headers,
        json={
            "path": "e2e_endpoint_post_only.py",
            "content": POST_ONLY_WORKFLOW_CONTENT,
            "encoding": "utf-8",
        },
    )
    assert response.status_code == 200, f"Failed to create workflow file: {response.text}"

    # Discovery happens synchronously during file write - just fetch the workflow
    workflow = _wait_for_workflow(e2e_client, platform_admin, "e2e_endpoint_post_only")
    assert workflow is not None, "Workflow e2e_endpoint_post_only not discovered after 30s"

    yield workflow

    # Cleanup: delete the workflow file
    e2e_client.delete(
        "/api/files/editor?path=e2e_endpoint_post_only.py",
        headers=platform_admin.headers,
    )


@pytest.fixture(scope="module")
def endpoint_api_key(e2e_client, platform_admin, endpoint_workflow_file):
    """
    Create an API key for the endpoint workflow.

    Returns the raw API key (only available on creation).
    """
    # Revoke existing key if present
    list_response = e2e_client.get(
        "/api/workflow-keys",
        headers=platform_admin.headers,
    )

    if list_response.status_code == 200:
        keys = list_response.json()
        existing_key = next(
            (k for k in keys if k.get("workflow_name") == "e2e_endpoint_workflow"),
            None
        )
        if existing_key:
            e2e_client.delete(
                f"/api/workflow-keys/{existing_key['id']}",
                headers=platform_admin.headers,
            )

    # Create new API key
    response = e2e_client.post(
        "/api/workflow-keys",
        headers=platform_admin.headers,
        json={
            "workflow_name": "e2e_endpoint_workflow",
            "description": "E2E test API key",
        },
    )
    assert response.status_code == 201, f"Failed to create API key: {response.text}"

    key_data = response.json()
    assert "raw_key" in key_data, "Response should include raw_key"

    yield key_data["raw_key"]

    # Cleanup: revoke the key
    if "id" in key_data:
        e2e_client.delete(
            f"/api/workflow-keys/{key_data['id']}",
            headers=platform_admin.headers,
        )


@pytest.fixture(scope="module")
def post_only_api_key(e2e_client, platform_admin, post_only_workflow_file):
    """Create an API key for the POST-only workflow."""
    # Revoke existing key if present
    list_response = e2e_client.get(
        "/api/workflow-keys",
        headers=platform_admin.headers,
    )

    if list_response.status_code == 200:
        keys = list_response.json()
        existing_key = next(
            (k for k in keys if k.get("workflow_name") == "e2e_endpoint_post_only"),
            None
        )
        if existing_key:
            e2e_client.delete(
                f"/api/workflow-keys/{existing_key['id']}",
                headers=platform_admin.headers,
            )

    # Create new key
    response = e2e_client.post(
        "/api/workflow-keys",
        headers=platform_admin.headers,
        json={
            "workflow_name": "e2e_endpoint_post_only",
            "description": "E2E test POST-only key",
        },
    )
    assert response.status_code == 201, f"Failed to create API key: {response.text}"

    key_data = response.json()

    yield key_data["raw_key"]

    # Cleanup
    if "id" in key_data:
        e2e_client.delete(
            f"/api/workflow-keys/{key_data['id']}",
            headers=platform_admin.headers,
        )


@pytest.mark.e2e
class TestWorkflowEndpointOpenAPI:
    """Test dynamic OpenAPI generation for workflow endpoints."""

    def test_openapi_spec_available(self, e2e_client):
        """OpenAPI spec is available at /openapi.json."""
        response = e2e_client.get("/openapi.json")
        assert response.status_code == 200, f"OpenAPI spec not available: {response.text}"
        spec = response.json()
        assert "openapi" in spec
        assert "paths" in spec

    def test_openapi_has_endpoint_security_scheme(self, e2e_client):
        """OpenAPI spec includes BifrostApiKey security scheme."""
        response = e2e_client.get("/openapi.json")
        assert response.status_code == 200
        spec = response.json()

        # Check security scheme exists
        schemes = spec.get("components", {}).get("securitySchemes", {})
        assert "BifrostApiKey" in schemes, "Missing BifrostApiKey security scheme"

        api_key_scheme = schemes["BifrostApiKey"]
        assert api_key_scheme["type"] == "apiKey"
        assert api_key_scheme["in"] == "header"
        assert api_key_scheme["name"] == "X-Bifrost-Key"

    def test_openapi_has_execute_response_schema(self, e2e_client):
        """OpenAPI spec includes EndpointExecuteResponse schema."""
        response = e2e_client.get("/openapi.json")
        assert response.status_code == 200
        spec = response.json()

        schemas = spec.get("components", {}).get("schemas", {})
        assert "EndpointExecuteResponse" in schemas, "Missing EndpointExecuteResponse schema"

        response_schema = schemas["EndpointExecuteResponse"]
        assert "execution_id" in response_schema.get("properties", {})
        assert "status" in response_schema.get("properties", {})


@pytest.mark.e2e
class TestWorkflowEndpointAuthentication:
    """Test API key authentication for workflow endpoints."""

    def test_endpoint_requires_api_key(self, e2e_client):
        """Endpoint returns 422 without X-Bifrost-Key header."""
        response = e2e_client.post("/api/endpoints/any_workflow")
        assert response.status_code == 422, f"Expected 422, got: {response.status_code}"

    def test_invalid_api_key_returns_401(self, e2e_client):
        """Endpoint returns 401 for invalid API key."""
        response = e2e_client.post(
            "/api/endpoints/any_workflow",
            headers={"X-Bifrost-Key": "invalid_key_12345"},
        )
        assert response.status_code == 401, f"Expected 401, got: {response.status_code}"
        assert "Invalid" in response.json().get("detail", "")


@pytest.mark.e2e
class TestWorkflowEndpointExecution:
    """Test workflow execution via endpoints with API keys."""

    def test_execute_endpoint_via_post(
        self,
        e2e_client,
        endpoint_workflow_file,
        endpoint_api_key,
    ):
        """Execute workflow endpoint via POST with JSON body."""
        response = e2e_client.post(
            "/api/endpoints/e2e_endpoint_workflow",
            headers={"X-Bifrost-Key": endpoint_api_key},
            json={"message": "Hello E2E", "count": 3},
            timeout=60.0,
        )

        assert response.status_code == 200, f"Endpoint execution failed: {response.text}"

        result = response.json()
        assert "execution_id" in result
        assert result["status"] in ["Success", "Completed", "success", "completed"], \
            f"Unexpected status: {result.get('status')}"

        # Check result contains expected data
        if result.get("result"):
            assert result["result"].get("message") == "Hello E2E"
            assert result["result"].get("count") == 3
            assert len(result["result"].get("messages", [])) == 3

    def test_execute_endpoint_via_get(
        self,
        e2e_client,
        endpoint_workflow_file,
        endpoint_api_key,
    ):
        """Execute workflow endpoint via GET with query parameters."""
        response = e2e_client.get(
            "/api/endpoints/e2e_endpoint_workflow",
            headers={"X-Bifrost-Key": endpoint_api_key},
            params={"message": "Hello GET", "count": "2"},
            timeout=60.0,
        )

        assert response.status_code == 200, f"Endpoint execution failed: {response.text}"

        result = response.json()
        assert "execution_id" in result
        assert result["status"] in ["Success", "Completed", "success", "completed"]

    def test_method_not_allowed(
        self,
        e2e_client,
        endpoint_workflow_file,
        endpoint_api_key,
    ):
        """Endpoint returns 405 for disallowed HTTP methods."""
        response = e2e_client.delete(
            "/api/endpoints/e2e_endpoint_workflow",
            headers={"X-Bifrost-Key": endpoint_api_key},
        )

        assert response.status_code == 405, f"Expected 405, got: {response.status_code}"
        assert "not allowed" in response.json().get("detail", "").lower()

    def test_workflow_not_found(self, e2e_client, endpoint_api_key):
        """Endpoint returns 401/404 for non-existent workflow."""
        response = e2e_client.post(
            "/api/endpoints/nonexistent_workflow",
            headers={"X-Bifrost-Key": endpoint_api_key},
        )

        # Could be 401 (key invalid for this workflow) or 404 (workflow not found)
        assert response.status_code in [401, 404], \
            f"Expected 401 or 404, got: {response.status_code}"


@pytest.mark.e2e
class TestPostOnlyEndpoint:
    """Test workflows that only allow POST method."""

    def test_post_only_rejects_get(
        self,
        e2e_client,
        post_only_workflow_file,
        post_only_api_key,
    ):
        """POST-only workflow rejects GET requests with 405."""
        response = e2e_client.get(
            "/api/endpoints/e2e_endpoint_post_only",
            headers={"X-Bifrost-Key": post_only_api_key},
        )

        assert response.status_code == 405, f"Expected 405, got: {response.status_code}"

    def test_post_only_accepts_post(
        self,
        e2e_client,
        post_only_workflow_file,
        post_only_api_key,
    ):
        """POST-only workflow accepts POST requests."""
        response = e2e_client.post(
            "/api/endpoints/e2e_endpoint_post_only",
            headers={"X-Bifrost-Key": post_only_api_key},
            json={"data": "test data"},
            timeout=60.0,
        )

        assert response.status_code == 200, f"POST failed: {response.text}"
        result = response.json()
        assert result["status"] in ["Success", "Completed", "success", "completed"]


@pytest.mark.e2e
class TestEndpointExecutionResult:
    """Test execution result structure and content."""

    def test_result_has_execution_id(
        self,
        e2e_client,
        endpoint_workflow_file,
        endpoint_api_key,
    ):
        """Result includes execution_id."""
        response = e2e_client.post(
            "/api/endpoints/e2e_endpoint_workflow",
            headers={"X-Bifrost-Key": endpoint_api_key},
            json={"message": "Result test", "count": 1},
            timeout=60.0,
        )

        result = response.json()
        assert "execution_id" in result
        assert result["execution_id"]  # Not empty

    def test_result_has_status(
        self,
        e2e_client,
        endpoint_workflow_file,
        endpoint_api_key,
    ):
        """Result includes status field."""
        response = e2e_client.post(
            "/api/endpoints/e2e_endpoint_workflow",
            headers={"X-Bifrost-Key": endpoint_api_key},
            json={"message": "Status test", "count": 1},
            timeout=60.0,
        )

        result = response.json()
        assert "status" in result

    def test_result_contains_workflow_output(
        self,
        e2e_client,
        endpoint_workflow_file,
        endpoint_api_key,
    ):
        """Result contains the workflow's return value."""
        response = e2e_client.post(
            "/api/endpoints/e2e_endpoint_workflow",
            headers={"X-Bifrost-Key": endpoint_api_key},
            json={"message": "Output test", "count": 2},
            timeout=60.0,
        )

        result = response.json()
        if result.get("status") in ["Success", "Completed", "success", "completed"]:
            assert "result" in result
            result_data = result.get("result", {})
            if result_data:
                assert result_data.get("message") == "Output test"
                assert result_data.get("count") == 2
                assert len(result_data.get("messages", [])) == 2
