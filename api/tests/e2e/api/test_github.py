"""
GitHub Integration E2E Tests.

Tests the complete GitHub integration workflow including:
- Token validation and storage
- Repository listing and configuration
- Branch listing
- Commit history
- Sync preview

Requirements:
- GITHUB_TEST_PAT environment variable with a valid GitHub PAT
- GITHUB_TEST_REPO environment variable (default: jackmusick/e2e-test-workspace)

Tests skip gracefully if environment variables are not configured.
"""

import logging

import pytest

logger = logging.getLogger(__name__)


# =============================================================================
# Configuration Tests
# =============================================================================


class TestGitHubConfiguration:
    """Test GitHub token validation and repository configuration."""

    def test_validate_token_success(
        self,
        e2e_client,
        platform_admin,
        require_github_config,
    ):
        """Test that a valid GitHub token can be validated and saved."""
        response = e2e_client.post(
            "/api/github/validate",
            json={"token": require_github_config["pat"]},
            headers=platform_admin.headers,
        )
        assert response.status_code == 200, f"Token validation failed: {response.text}"

        data = response.json()
        assert "repositories" in data
        assert isinstance(data["repositories"], list)
        assert len(data["repositories"]) > 0

    def test_validate_token_invalid(
        self,
        e2e_client,
        platform_admin,
    ):
        """Test that an invalid token returns an error."""
        response = e2e_client.post(
            "/api/github/validate",
            json={"token": "invalid_token_12345"},
            headers=platform_admin.headers,
        )
        assert response.status_code in [400, 401, 500]

    def test_get_config_unconfigured(
        self,
        e2e_client,
        platform_admin,
    ):
        """Test getting config when GitHub is not configured."""
        # Ensure disconnected first
        e2e_client.post(
            "/api/github/disconnect",
            headers=platform_admin.headers,
        )

        response = e2e_client.get(
            "/api/github/config",
            headers=platform_admin.headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["configured"] is False
        assert data["token_saved"] is False

    def test_configure_repository(
        self,
        e2e_client,
        platform_admin,
        github_token_only,
        github_test_branch,
    ):
        """Test configuring a GitHub repository."""
        response = e2e_client.post(
            "/api/github/configure",
            json={
                "repo_url": github_test_branch["repo"],
                "branch": github_test_branch["branch"],
            },
            headers=platform_admin.headers,
        )
        assert response.status_code == 200, f"Configure failed: {response.text}"

        data = response.json()
        assert data["status"] == "configured"

    def test_get_config_after_configure(
        self,
        e2e_client,
        platform_admin,
        github_configured,
    ):
        """Test getting config after GitHub is configured."""
        response = e2e_client.get(
            "/api/github/config",
            headers=platform_admin.headers,
        )
        assert response.status_code == 200

        data = response.json()
        assert data["configured"] is True
        assert data["token_saved"] is True
        assert data["repo_url"] is not None

    def test_list_repositories(
        self,
        e2e_client,
        platform_admin,
        github_token_only,
    ):
        """Test listing repositories with saved token."""
        response = e2e_client.get(
            "/api/github/repositories",
            headers=platform_admin.headers,
        )
        assert response.status_code == 200

        data = response.json()
        assert "repositories" in data
        assert isinstance(data["repositories"], list)
        assert len(data["repositories"]) > 0

    def test_list_branches(
        self,
        e2e_client,
        platform_admin,
        github_token_only,
    ):
        """Test listing branches for a repository."""
        response = e2e_client.get(
            "/api/github/branches",
            params={"repo": github_token_only["repo"]},
            headers=platform_admin.headers,
        )
        assert response.status_code == 200

        data = response.json()
        assert "branches" in data
        assert isinstance(data["branches"], list)
        assert len(data["branches"]) > 0

        # Should have at least a main branch
        branch_names = [b["name"] for b in data["branches"]]
        assert "main" in branch_names or "master" in branch_names

    def test_disconnect(
        self,
        e2e_client,
        platform_admin,
        github_configured,
    ):
        """Test disconnecting GitHub integration."""
        response = e2e_client.post(
            "/api/github/disconnect",
            headers=platform_admin.headers,
        )
        assert response.status_code == 200

        data = response.json()
        assert data["success"] is True

        # Verify disconnected
        response = e2e_client.get(
            "/api/github/config",
            headers=platform_admin.headers,
        )
        assert response.status_code == 200
        assert response.json()["configured"] is False


# =============================================================================
# Commit History Tests
# =============================================================================


class TestGitHubCommits:
    """Test commit history functionality."""

    def test_get_commit_history(
        self,
        e2e_client,
        platform_admin,
        github_configured,
    ):
        """Test retrieving commit history."""
        response = e2e_client.get(
            "/api/github/commits",
            params={"limit": 10},
            headers=platform_admin.headers,
        )
        assert response.status_code == 200

        data = response.json()
        assert "commits" in data
        assert isinstance(data["commits"], list)

    def test_get_commit_history_pagination(
        self,
        e2e_client,
        platform_admin,
        github_configured,
    ):
        """Test paginating through commit history."""
        # First page
        response = e2e_client.get(
            "/api/github/commits",
            params={"limit": 5, "offset": 0},
            headers=platform_admin.headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["commits"]) <= 5


# =============================================================================
# Sync Tests
# =============================================================================


class TestGitHubSync:
    """Test sync preview and execution."""

    def test_sync_preview(
        self,
        e2e_client,
        platform_admin,
        github_configured,
    ):
        """Test getting sync preview."""
        response = e2e_client.get(
            "/api/github/sync",
            headers=platform_admin.headers,
        )
        assert response.status_code == 200, f"Sync preview failed: {response.text}"

        data = response.json()
        assert "to_pull" in data
        assert "to_push" in data
        assert "conflicts" in data
        assert "will_orphan" in data
        assert "is_empty" in data

    def test_sync_execute_no_changes(
        self,
        e2e_client,
        platform_admin,
        github_configured,
    ):
        """Test executing sync with no changes."""
        response = e2e_client.post(
            "/api/github/sync",
            json={
                "conflict_resolutions": {},
                "confirm_orphans": True,
            },
            headers=platform_admin.headers,
        )
        assert response.status_code == 200, f"Sync execute failed: {response.text}"

        data = response.json()
        assert "job_id" in data
        assert data["status"] == "queued"


# =============================================================================
# Access Control Tests
# =============================================================================


class TestGitHubAccessControl:
    """Test that GitHub endpoints require proper authorization."""

    def test_unauthenticated_cannot_access(
        self,
        e2e_client,
    ):
        """Test that unauthenticated requests are rejected."""
        # Use a fresh client to ensure no cookies/headers are carried over
        import httpx
        with httpx.Client(base_url=e2e_client.base_url, timeout=30.0) as fresh_client:
            response = fresh_client.get("/api/github/config")
        assert response.status_code in [401, 403, 422], f"Expected 401/403/422 but got {response.status_code}: {response.text}"

    def test_validate_requires_token(
        self,
        e2e_client,
        platform_admin,
    ):
        """Test that validate endpoint requires a token in the body."""
        response = e2e_client.post(
            "/api/github/validate",
            json={},
            headers=platform_admin.headers,
        )
        assert response.status_code in [400, 422]


# =============================================================================
# Create Repository Tests
# =============================================================================


class TestGitHubCreateRepository:
    """Test repository creation (skipped by default as it creates real repos)."""

    @pytest.mark.skip(reason="Creates real GitHub repository - run manually")
    def test_create_repository(
        self,
        e2e_client,
        platform_admin,
        github_token_only,  # noqa: ARG002 - fixture sets up test state
    ):
        """Test creating a new GitHub repository."""
        import uuid

        unique_name = f"test-repo-{uuid.uuid4().hex[:8]}"

        response = e2e_client.post(
            "/api/github/create-repository",
            json={
                "name": unique_name,
                "description": "Test repository created by E2E tests",
                "private": True,
            },
            headers=platform_admin.headers,
        )
        assert response.status_code == 200

        data = response.json()
        assert "full_name" in data
        assert "url" in data
        assert unique_name in data["full_name"]
