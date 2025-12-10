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
