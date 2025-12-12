"""
GitHub E2E test fixtures.

Uses branch-per-run strategy:
1. Create unique branch for test run
2. Run all tests against that branch
3. Clean up branch after tests

This ensures test isolation and prevents state conflicts between runs.

Environment variables required:
- GITHUB_TEST_PAT: GitHub Personal Access Token with repo access
- GITHUB_TEST_REPO: Repository to test against (default: jackmusick/e2e-test-workspace)
"""

import logging
import os
import time
from collections.abc import Generator
from typing import Any

import pytest

logger = logging.getLogger(__name__)


def _get_github_client():
    """
    Lazily import and create GitHub client.

    This avoids import errors if PyGithub is not installed
    (tests will skip gracefully).
    """
    try:
        from github import Github, Auth

        return Github, Auth
    except ImportError:
        return None, None


@pytest.fixture(scope="session")
def github_test_config() -> dict[str, Any]:
    """
    Get GitHub test configuration from environment.

    Skips all GitHub tests if GITHUB_TEST_PAT is not set.

    Returns:
        dict with pat, repo, and base_branch
    """
    pat = os.environ.get("GITHUB_TEST_PAT")
    repo = os.environ.get("GITHUB_TEST_REPO", "jackmusick/e2e-test-workspace")

    if not pat:
        pytest.skip(
            "GitHub E2E tests require GITHUB_TEST_PAT environment variable. "
            "Set it to a GitHub PAT with repo access to run these tests."
        )

    Github, Auth = _get_github_client()
    if Github is None:
        pytest.skip(
            "GitHub E2E tests require PyGithub package. "
            "Install with: pip install PyGithub"
        )

    return {
        "pat": pat,
        "repo": repo,
        "base_branch": "main",
    }


@pytest.fixture(scope="session")
def github_test_branch(
    github_test_config: dict[str, Any],
) -> Generator[dict[str, Any], None, None]:
    """
    Create a unique branch for this test run.

    Branch naming: e2e-test-{timestamp}

    This fixture:
    1. Creates a new branch from main
    2. Yields config dict with branch name and repo object
    3. Cleans up (deletes) the branch after all tests complete

    Args:
        github_test_config: Configuration from github_test_config fixture

    Yields:
        dict with pat, repo, branch, base_branch, and repo_obj
    """
    Github, Auth = _get_github_client()
    if Github is None:
        pytest.skip("PyGithub not available")

    g = Github(auth=Auth.Token(github_test_config["pat"]))
    repo = g.get_repo(github_test_config["repo"])

    # Create unique branch name with timestamp
    branch_name = f"e2e-test-{int(time.time())}"

    try:
        # Get main branch SHA
        main_ref = repo.get_git_ref(f"heads/{github_test_config['base_branch']}")
        main_sha = main_ref.object.sha

        # Create new branch from main
        repo.create_git_ref(f"refs/heads/{branch_name}", main_sha)
        logger.info(f"Created test branch: {branch_name}")

    except Exception as e:
        pytest.skip(f"Failed to create test branch: {e}")

    yield {
        **github_test_config,
        "branch": branch_name,
        "repo_obj": repo,
        "github_client": g,
    }

    # Cleanup: delete the test branch
    try:
        ref = repo.get_git_ref(f"heads/{branch_name}")
        ref.delete()
        logger.info(f"Cleaned up test branch: {branch_name}")
    except Exception as e:
        logger.warning(f"Failed to cleanup test branch {branch_name}: {e}")
        # Don't fail - branch may already be deleted or cleanup isn't critical


def _wait_for_notification_completion(
    e2e_client,
    headers: dict,
    notification_id: str,
    timeout_seconds: int = 120,
    poll_interval: float = 2.0,
) -> dict[str, Any]:
    """
    Poll notification status until completion or timeout.

    Args:
        e2e_client: HTTP client
        headers: Auth headers
        notification_id: Notification ID to poll
        timeout_seconds: Max time to wait
        poll_interval: Time between polls

    Returns:
        Final notification data

    Raises:
        TimeoutError: If notification doesn't complete in time
        AssertionError: If notification fails
    """
    import time as time_module

    start = time_module.time()
    while (time_module.time() - start) < timeout_seconds:
        response = e2e_client.get(
            f"/api/notifications/{notification_id}",
            headers=headers,
        )

        if response.status_code == 404:
            # Notification may have been cleaned up, treat as completed
            logger.info(f"Notification {notification_id} not found (may have expired)")
            return {"status": "completed"}

        if response.status_code != 200:
            logger.warning(f"Notification poll failed: {response.status_code}")
            time_module.sleep(poll_interval)
            continue

        data = response.json()
        status = data.get("status")

        if status == "completed":
            logger.info(f"Notification {notification_id} completed successfully")
            return data
        elif status == "failed":
            error = data.get("error", "Unknown error")
            raise AssertionError(f"GitHub setup failed: {error}")
        elif status == "cancelled":
            raise AssertionError("GitHub setup was cancelled")

        # Still pending or running
        logger.debug(f"Notification {notification_id} status: {status}")
        time_module.sleep(poll_interval)

    raise TimeoutError(
        f"Notification {notification_id} did not complete within {timeout_seconds}s"
    )


@pytest.fixture(scope="function")
def github_configured(e2e_client, platform_admin, github_test_branch):
    """
    Configure GitHub integration for a single test.

    This fixture:
    1. Validates and saves the GitHub token
    2. Dispatches async repository configuration job
    3. Waits for the job to complete via notification polling
    4. Yields the config for test use
    5. Disconnects GitHub after the test

    Args:
        e2e_client: HTTP client fixture
        platform_admin: Authenticated platform admin fixture
        github_test_branch: Branch configuration from github_test_branch

    Yields:
        dict with GitHub config including branch name and repo object
    """
    config = github_test_branch

    # Step 1: Validate and save token
    response = e2e_client.post(
        "/api/github/validate",
        json={"token": config["pat"]},
        headers=platform_admin.headers,
    )
    assert response.status_code == 200, f"Token validation failed: {response.text}"

    # Step 2: Configure repository (now async - dispatches job)
    repo_url = f"https://github.com/{config['repo']}.git"
    response = e2e_client.post(
        "/api/github/configure",
        json={
            "repo_url": repo_url,
            "branch": config["branch"],
            "auth_token": config["pat"],
        },
        headers=platform_admin.headers,
    )
    assert response.status_code == 200, f"Repository configuration failed: {response.text}"

    data = response.json()

    # Check if response is async (new flow) or sync (old flow for backwards compat)
    if "notification_id" in data:
        # New async flow - wait for job completion
        notification_id = data["notification_id"]
        logger.info(f"GitHub setup job dispatched: {data.get('job_id')}, notification: {notification_id}")

        _wait_for_notification_completion(
            e2e_client,
            platform_admin.headers,
            notification_id,
            timeout_seconds=120,
        )
        logger.info(f"GitHub setup completed: {repo_url} @ {config['branch']}")
    else:
        # Old sync flow (backwards compatibility)
        logger.info(f"Configured GitHub (sync): {repo_url} @ {config['branch']}")

    yield config

    # Cleanup: Disconnect GitHub integration
    try:
        e2e_client.post(
            "/api/github/disconnect",
            headers=platform_admin.headers,
        )
        logger.info("Disconnected GitHub integration")
    except Exception as e:
        logger.warning(f"Failed to disconnect GitHub: {e}")


@pytest.fixture(scope="function")
def github_token_only(e2e_client, platform_admin, github_test_config):
    """
    Configure only the GitHub token (not the full repository).

    Use this fixture for tests that need to validate tokens or list
    repositories before configuring a specific repo.

    Args:
        e2e_client: HTTP client fixture
        platform_admin: Authenticated platform admin fixture
        github_test_config: Base configuration from github_test_config

    Yields:
        dict with GitHub config (token only, no repo configured)
    """
    config = github_test_config

    # Validate and save token only
    response = e2e_client.post(
        "/api/github/validate",
        json={"token": config["pat"]},
        headers=platform_admin.headers,
    )
    assert response.status_code == 200, f"Token validation failed: {response.text}"

    yield config

    # Cleanup: Disconnect to clear token
    try:
        e2e_client.post(
            "/api/github/disconnect",
            headers=platform_admin.headers,
        )
    except Exception:
        pass  # Ignore cleanup failures


@pytest.fixture(scope="function")
def create_remote_file(github_test_branch):
    """
    Factory fixture to create files directly on GitHub.

    This is useful for testing pull operations - create a file on GitHub,
    then verify it can be pulled to the local workspace.

    Usage:
        def test_pull(create_remote_file):
            file_info = create_remote_file("test.txt", "content", "commit message")
            # Now pull and verify...

    Returns:
        Factory function that creates files on GitHub
    """
    config = github_test_branch
    repo = config["repo_obj"]
    branch = config["branch"]
    created_files = []

    def _create_file(
        path: str,
        content: str,
        message: str = "E2E test file",
    ) -> dict[str, Any]:
        """
        Create a file on GitHub.

        Args:
            path: File path in repository
            content: File content
            message: Commit message

        Returns:
            dict with path, sha, and commit info
        """
        result = repo.create_file(
            path=path,
            message=message,
            content=content,
            branch=branch,
        )
        created_files.append(path)
        logger.info(f"Created remote file: {path}")
        return {
            "path": path,
            "sha": result["content"].sha,
            "commit_sha": result["commit"].sha,
        }

    yield _create_file

    # Cleanup: delete created files
    for file_path in created_files:
        try:
            contents = repo.get_contents(file_path, ref=branch)
            if not isinstance(contents, list):
                repo.delete_file(
                    path=file_path,
                    message=f"E2E cleanup: {file_path}",
                    sha=contents.sha,
                    branch=branch,
                )
                logger.info(f"Cleaned up remote file: {file_path}")
        except Exception as e:
            logger.warning(f"Failed to cleanup remote file {file_path}: {e}")


@pytest.fixture(scope="function")
def update_remote_file(github_test_branch):
    """
    Factory fixture to update existing files on GitHub.

    This is useful for testing conflict scenarios - update a file on GitHub
    while it's also modified locally.

    Usage:
        def test_conflict(update_remote_file):
            update_remote_file("existing.txt", "new content", "Update for conflict")
            # Now try to push local changes and verify conflict...

    Returns:
        Factory function that updates files on GitHub
    """
    config = github_test_branch
    repo = config["repo_obj"]
    branch = config["branch"]

    def _update_file(
        path: str,
        new_content: str,
        message: str = "E2E test update",
    ) -> dict[str, Any]:
        """
        Update an existing file on GitHub.

        Args:
            path: File path in repository
            new_content: New file content
            message: Commit message

        Returns:
            dict with path, sha, and commit info
        """
        # Get current file to get its SHA
        contents = repo.get_contents(path, ref=branch)
        if isinstance(contents, list):
            raise ValueError(f"Path {path} is a directory, not a file")

        result = repo.update_file(
            path=path,
            message=message,
            content=new_content,
            sha=contents.sha,
            branch=branch,
        )
        logger.info(f"Updated remote file: {path}")
        return {
            "path": path,
            "sha": result["content"].sha,
            "commit_sha": result["commit"].sha,
        }

    return _update_file
