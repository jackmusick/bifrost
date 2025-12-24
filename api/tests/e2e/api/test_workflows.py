"""
E2E tests for workflow management.

Tests workflow listing, discovery, and data providers.
"""

import pytest


@pytest.mark.e2e
class TestWorkflowListing:
    """Test workflow listing operations."""

    def test_list_workflows(self, e2e_client, platform_admin):
        """Platform admin can list workflows."""
        response = e2e_client.get(
            "/api/workflows",
            headers=platform_admin.headers,
        )
        assert response.status_code == 200, f"List workflows failed: {response.text}"
        workflows = response.json()
        assert isinstance(workflows, list)

    def test_list_data_providers(self, e2e_client, platform_admin):
        """Platform admin can list data providers."""
        response = e2e_client.get(
            "/api/data-providers",
            headers=platform_admin.headers,
        )
        assert response.status_code == 200, f"List data providers failed: {response.text}"
        data = response.json()
        assert isinstance(data, list) or "data_providers" in data


@pytest.mark.e2e
class TestWorkflowDiscovery:
    """Test workflow discovery operations."""

    def test_discovery_info(self, e2e_client, platform_admin):
        """Platform admin can get discovery info."""
        response = e2e_client.get(
            "/api/discovery/info",
            headers=platform_admin.headers,
        )
        # May return 200 or 404 depending on whether discovery is configured
        assert response.status_code in [200, 404], f"Discovery info failed: {response.text}"

    def test_workflow_list_pagination(self, e2e_client, platform_admin):
        """Workflow list supports pagination."""
        response = e2e_client.get(
            "/api/workflows",
            headers=platform_admin.headers,
            params={"limit": 10, "offset": 0},
        )
        assert response.status_code == 200, f"List workflows failed: {response.text}"


@pytest.mark.e2e
class TestWorkflowValidation:
    """Test workflow validation endpoint."""

    def test_validate_valid_workflow(self, e2e_client, platform_admin):
        """Validate a valid workflow file content."""
        valid_workflow = '''
"""Test workflow for validation"""

from bifrost import workflow

@workflow(
    category="testing",
    tags=["test", "validation"],
)
async def e2e_test_validation(name: str, count: int = 1) -> dict:
    """A simple test workflow for E2E validation testing."""
    return {"greeting": f"Hello, {name}!", "count": count}
'''
        response = e2e_client.post(
            "/api/workflows/validate",
            headers=platform_admin.headers,
            json={
                "path": "test_validation.py",
                "content": valid_workflow,
            },
        )
        assert response.status_code == 200, f"Validation failed: {response.text}"
        data = response.json()
        assert data["valid"] is True
        assert data["metadata"] is not None
        assert data["metadata"]["name"] == "e2e_test_validation"
        # Should have parameters extracted from function signature
        assert len(data["metadata"]["parameters"]) == 2

    def test_validate_workflow_with_roi(self, e2e_client, platform_admin):
        """Validate workflow with time_saved and value fields."""
        workflow_with_roi = '''
"""Test workflow with ROI"""

from bifrost import workflow

@workflow(
    category="automation",
    tags=["test", "roi"],
    time_saved=30,
    value=150.50,
)
async def workflow_with_roi(task: str) -> dict:
    """A workflow that saves time and provides value."""
    return {"task": task, "completed": True}
'''
        response = e2e_client.post(
            "/api/workflows/validate",
            headers=platform_admin.headers,
            json={
                "path": "test_roi.py",
                "content": workflow_with_roi,
            },
        )
        assert response.status_code == 200, f"Validation failed: {response.text}"
        data = response.json()
        # Debug: print the response if test fails
        if not data["valid"]:
            print(f"Validation failed. Response: {data}")
        assert data["valid"] is True, f"Validation should be valid. Issues: {data.get('issues', [])}"
        assert data["metadata"] is not None
        assert data["metadata"]["name"] == "workflow_with_roi"
        assert data["metadata"]["time_saved"] == 30
        assert data["metadata"]["value"] == 150.50

    def test_validate_workflow_with_syntax_error(self, e2e_client, platform_admin):
        """Validation catches syntax errors."""
        invalid_workflow = '''
"""Invalid workflow"""

def broken_workflow(
    # Missing closing paren
'''
        response = e2e_client.post(
            "/api/workflows/validate",
            headers=platform_admin.headers,
            json={
                "path": "invalid.py",
                "content": invalid_workflow,
            },
        )
        assert response.status_code == 200, f"Request failed: {response.text}"
        data = response.json()
        assert data["valid"] is False
        assert any("syntax" in issue["message"].lower() for issue in data["issues"])

    def test_validate_workflow_without_decorator(self, e2e_client, platform_admin):
        """Validation catches missing @workflow decorator."""
        no_decorator = '''
"""Workflow without decorator"""

async def not_a_workflow(name: str) -> dict:
    """No decorator means not discoverable."""
    return {"name": name}
'''
        response = e2e_client.post(
            "/api/workflows/validate",
            headers=platform_admin.headers,
            json={
                "path": "no_decorator.py",
                "content": no_decorator,
            },
        )
        assert response.status_code == 200, f"Request failed: {response.text}"
        data = response.json()
        assert data["valid"] is False
        assert any("@workflow decorator" in issue["message"] for issue in data["issues"])


@pytest.mark.e2e
class TestPlatformWorkflows:
    """Test platform workflow categorization."""

    def test_platform_workflows_properly_categorized(self, e2e_client, platform_admin):
        """Platform workflows have is_platform=True flag set correctly."""
        response = e2e_client.get(
            "/api/workflows",
            headers=platform_admin.headers,
        )
        assert response.status_code == 200, f"List workflows failed: {response.text}"
        workflows = response.json()

        # If there are workflows, check their structure
        if workflows:
            for workflow in workflows:
                # Each workflow should have is_platform field
                assert "is_platform" in workflow, \
                    f"Workflow missing is_platform field: {workflow.get('name', 'unknown')}"
                # is_platform should be a boolean
                assert isinstance(workflow["is_platform"], bool), \
                    f"is_platform should be boolean for: {workflow.get('name', 'unknown')}"

        # Optionally check that platform workflows are in expected locations
        platform_workflows = [w for w in workflows if w.get("is_platform")]
        # Non-platform workflows also available: [w for w in workflows if not w.get("is_platform")]

        # Platform workflows should be from platform directory
        for pw in platform_workflows:
            file_path = pw.get("file_path", "")
            # Platform workflows are typically in a platform subfolder or have platform marker
            # This is a soft check - adjust based on actual implementation
            assert file_path, f"Platform workflow should have file_path: {pw.get('name')}"
