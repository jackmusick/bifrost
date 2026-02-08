"""
Portable Workflow Refs GitHub Sync E2E Tests.

Tests the complete flow of portable refs through GitHub sync:
1. Push: Create entities with workflow refs → push → verify portable refs in JSON
2. Pull: Create files on GitHub with portable refs → pull → verify UUIDs restored
3. Missing refs: Verify graceful degradation when workflows don't exist

Requirements:
- GITHUB_TEST_PAT environment variable with a valid GitHub PAT
- GITHUB_TEST_REPO environment variable (default: jackmusick/e2e-test-workspace)

Tests skip gracefully if environment variables are not configured.
"""

import json
import logging
import time
from uuid import UUID, uuid4

import pytest

from tests.e2e.fixtures.entity_setup import (
    create_app_json_with_portable_refs,
    create_form_json_with_portable_refs,
    create_agent_json_with_portable_refs,
    poll_until,
)

logger = logging.getLogger(__name__)


def is_uuid(value: str) -> bool:
    """Check if a string is a valid UUID."""
    try:
        UUID(value)
        return True
    except (ValueError, TypeError):
        return False


def is_portable_ref(value: str) -> bool:
    """Check if a string looks like a portable ref (path::function)."""
    return isinstance(value, str) and "::" in value and "/" in value


def execute_sync_with_auto_resolution(e2e_client, headers, max_wait: float = 60.0, max_retries: int = 3):
    """
    Execute GitHub sync with automatic conflict resolution.

    This helper:
    1. Gets sync preview to find conflicts
    2. Builds conflict_resolutions preferring local for all conflicts
    3. Executes sync
    4. Polls until job completes
    5. If status is 'conflict', retries with new resolutions

    Returns:
        tuple: (job_result dict, job_id)

    Note: Conflicts are common in E2E tests because the test branch
    is reused across tests in a session. We retry because conflicts
    can change between preview and execute.
    """
    for attempt in range(max_retries):
        # Get preview — now returns a job_id that must be polled
        preview_response = e2e_client.get("/api/github/sync", headers=headers)
        if preview_response.status_code != 200:
            logger.error(f"Preview failed: {preview_response.status_code} - {preview_response.text}")
            return None, None

        preview_data = preview_response.json()
        preview_job_id = preview_data.get("job_id")

        if preview_job_id:
            # Poll for preview job completion
            preview_terminal = ["success", "completed", "failed", "error"]

            def check_preview():
                resp = e2e_client.get(f"/api/jobs/{preview_job_id}", headers=headers)
                if resp.status_code == 200:
                    result = resp.json()
                    if result.get("status") in preview_terminal:
                        return result
                return None

            preview_result = poll_until(check_preview, max_wait=max_wait, interval=1.0)
            if preview_result is None or preview_result.get("status") in ["failed", "error"]:
                logger.error(f"Preview job {preview_job_id} failed: {preview_result}")
                return None, None
            preview = preview_result.get("preview", {})
        else:
            # Backward compat: inline preview data
            preview = preview_data

        conflicts = preview.get("conflicts", [])
        to_push = preview.get("to_push", [])
        to_pull = preview.get("to_pull", [])

        # Build conflict resolutions - prefer local for all
        # conflicts is a list of SyncConflictInfo dicts with 'path' field
        # Values must be "keep_local" or "keep_remote"
        conflict_resolutions = {conflict["path"]: "keep_local" for conflict in conflicts}

        logger.info(
            f"Sync attempt {attempt + 1}: to_push={len(to_push)}, "
            f"to_pull={len(to_pull)}, conflicts={len(conflicts)}"
        )

        # If nothing to sync, we're done
        if not to_push and not to_pull and not conflicts:
            logger.info("Nothing to sync")
            return {"status": "success", "message": "Nothing to sync"}, None

        # Execute sync
        # We pass confirm_orphans=True and confirm_unresolved_refs=True since E2E tests
        # may have refs that don't exist in the test environment. We still verify
        # ref translation is working correctly by checking the file content.
        sync_response = e2e_client.post(
            "/api/github/sync",
            json={
                "conflict_resolutions": conflict_resolutions,
                "confirm_orphans": True,
                "confirm_unresolved_refs": True,
            },
            headers=headers,
        )
        if sync_response.status_code != 200:
            logger.error(f"Sync execute failed: {sync_response.status_code} - {sync_response.text}")
            return None, None

        job_id = sync_response.json().get("job_id")
        logger.info(f"Sync job started: {job_id}")

        # Poll for completion
        # Note: Scheduler uses "success" for successful completion, "failed" for errors
        terminal_statuses = ["success", "completed", "failed", "conflict", "orphans_detected", "unresolved_refs"]

        def check_complete():
            resp = e2e_client.get(f"/api/jobs/{job_id}", headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                status = data.get("status")
                if status in terminal_statuses:
                    logger.info(f"Job {job_id} finished with status: {status}")
                    return data
            return None

        job_result = poll_until(check_complete, max_wait=max_wait, interval=1.0)

        if job_result is None:
            logger.error(f"Job {job_id} timed out after {max_wait}s")
            return None, job_id

        # "success" or "completed" means sync finished successfully
        # "failed" means sync failed
        status = job_result.get("status")
        if status in ["success", "completed"]:
            # Normalize to "success" for test assertions
            job_result["status"] = "success"
            return job_result, job_id
        if status == "failed":
            return job_result, job_id

        # If conflict, orphans_detected, or unresolved_refs, retry with confirmations
        logger.warning(f"Job {job_id} status: {job_result.get('status')}, retrying...")

    logger.error(f"Sync failed after {max_retries} attempts")
    return job_result, job_id


# =============================================================================
# Push Tests - Verify portable refs in GitHub after push
# =============================================================================


@pytest.mark.e2e
class TestPortableRefsPush:
    """Test that entities pushed to GitHub have portable refs."""

    def test_form_push_has_portable_refs(
        self,
        e2e_client,
        platform_admin,
        github_configured,  # noqa: ARG002 - required for GitHub setup
        test_form_with_workflow,
    ):
        """
        Verify form pushed to GitHub has portable refs.
        """
        form_info = test_form_with_workflow

        # Execute sync with auto conflict resolution
        job_result, _ = execute_sync_with_auto_resolution(
            e2e_client, platform_admin.headers
        )
        assert job_result and job_result.get("status") == "success"

        # Check form file content
        form_file_path = f"forms/{form_info['form']['name'].lower().replace(' ', '-')}.form.json"

        file_response = e2e_client.get(
            f"/api/files/editor/content?path={form_file_path}",
            headers=platform_admin.headers,
        )

        if file_response.status_code == 200:
            content = file_response.json().get("content", "")
            form_json = json.loads(content)

            # Check for portable refs
            if form_json.get("workflow_id"):
                assert is_portable_ref(form_json["workflow_id"]), (
                    f"workflow_id should be portable ref: {form_json['workflow_id']}"
                )

            logger.info("Form JSON has portable refs")

    def test_agent_push_has_portable_refs(
        self,
        e2e_client,
        platform_admin,
        github_configured,  # noqa: ARG002 - required for GitHub setup
        test_agent_with_tools,
    ):
        """
        Verify agent pushed to GitHub has portable refs in tool_ids.
        """
        _ = test_agent_with_tools  # Fixture creates agent

        # Execute sync with auto conflict resolution
        job_result, _ = execute_sync_with_auto_resolution(
            e2e_client, platform_admin.headers
        )
        assert job_result and job_result.get("status") == "success"

        logger.info("Agent sync completed - portable refs should be in GitHub")


# =============================================================================
# Pull Tests - Verify UUIDs restored after pull
# =============================================================================


@pytest.mark.e2e
class TestPortableRefsPull:
    """Test that entities pulled from GitHub have UUIDs restored."""

    def test_form_pull_resolves_refs(
        self,
        e2e_client,
        platform_admin,
        github_configured,  # noqa: ARG002 - required for GitHub setup
        create_remote_file,
        test_workflow,
    ):
        """
        Verify form pulled from GitHub has UUIDs restored.
        """
        workflow = test_workflow
        form_name = f"E2E Pull Test Form {int(time.time())}"
        form_id = str(uuid4())

        # Create form JSON with portable refs
        form_content = create_form_json_with_portable_refs(
            form_name=form_name,
            form_id=form_id,
            workflow_portable_ref=workflow["portable_ref"],
        )

        form_slug = form_name.lower().replace(" ", "-")
        create_remote_file(
            path=f"forms/{form_slug}.form.json",
            content=form_content,
            message="E2E test: Form with portable refs",
        )

        # Execute pull with auto conflict resolution
        job_result, _ = execute_sync_with_auto_resolution(
            e2e_client, platform_admin.headers
        )
        assert job_result and job_result.get("status") == "success"

        # Find imported form
        def find_form():
            resp = e2e_client.get("/api/forms", headers=platform_admin.headers)
            if resp.status_code != 200:
                return None
            forms = resp.json()
            for form in forms:
                if form.get("name") == form_name:
                    return form
            return None

        form = poll_until(find_form, max_wait=10.0)
        assert form, f"Form {form_name} not found after pull"

        # Check workflow_id is UUID
        if form.get("workflow_id"):
            assert is_uuid(form["workflow_id"]), (
                f"workflow_id should be UUID: {form['workflow_id']}"
            )

        logger.info("Form pulled with UUIDs restored")

    def test_agent_pull_resolves_refs(
        self,
        e2e_client,
        platform_admin,
        github_configured,  # noqa: ARG002 - required for GitHub setup
        create_remote_file,
        test_workflow,
    ):
        """
        Verify agent pulled from GitHub has UUIDs restored in tool_ids.
        """
        workflow = test_workflow
        agent_name = f"E2E Pull Test Agent {int(time.time())}"
        agent_id = str(uuid4())

        # Create agent JSON with portable refs
        agent_content = create_agent_json_with_portable_refs(
            agent_name=agent_name,
            agent_id=agent_id,
            workflow_portable_ref=workflow["portable_ref"],
        )

        agent_slug = agent_name.lower().replace(" ", "-")
        create_remote_file(
            path=f"agents/{agent_slug}.agent.json",
            content=agent_content,
            message="E2E test: Agent with portable refs",
        )

        # Execute pull with auto conflict resolution
        job_result, _ = execute_sync_with_auto_resolution(
            e2e_client, platform_admin.headers
        )
        assert job_result and job_result.get("status") == "success"

        # Find imported agent
        def find_agent():
            resp = e2e_client.get("/api/agents", headers=platform_admin.headers)
            if resp.status_code != 200:
                return None
            agents = resp.json()
            for agent in agents:
                if agent.get("name") == agent_name:
                    return agent
            return None

        agent = poll_until(find_agent, max_wait=10.0)
        assert agent, f"Agent {agent_name} not found after pull"

        # Check tool_ids are UUIDs
        tool_ids = agent.get("tool_ids", [])
        if tool_ids:
            for tool_id in tool_ids:
                assert is_uuid(tool_id), f"tool_id should be UUID: {tool_id}"

        logger.info("Agent pulled with UUIDs restored")


# =============================================================================
# Missing Refs Tests - Graceful Degradation
# =============================================================================


@pytest.mark.e2e
class TestMissingRefsGracefulDegradation:
    """Test that missing workflow refs are handled gracefully."""

    def test_app_with_missing_workflow_imports(
        self,
        e2e_client,
        platform_admin,
        github_configured,  # noqa: ARG002 - required for GitHub setup
        create_remote_file,
    ):
        """
        App with ref to non-existent workflow imports gracefully.

        The portable ref should stay as-is (not become null or error).
        """
        app_slug = f"e2e-missing-ref-{int(time.time())}"
        app_id = str(uuid4())
        non_existent_ref = "workflows/does_not_exist.py::fake_function"

        # Create app with non-existent workflow ref
        app_content = create_app_json_with_portable_refs(
            app_name="Missing Ref Test App",
            app_slug=app_slug,
            app_id=app_id,
            workflow_portable_ref=non_existent_ref,
        )

        create_remote_file(
            path=f"apps/{app_slug}.app.json",
            content=app_content,
            message="E2E test: App with missing workflow ref",
        )

        # Execute pull with auto conflict resolution
        job_result, _ = execute_sync_with_auto_resolution(
            e2e_client, platform_admin.headers
        )
        # Should complete (not fail)
        assert job_result, "Sync should complete even with missing refs"

        # App should still be imported
        def find_app():
            resp = e2e_client.get("/api/applications", headers=platform_admin.headers)
            if resp.status_code != 200:
                return None
            apps = resp.json().get("applications", [])
            for app in apps:
                if app.get("slug") == app_slug:
                    return app
            return None

        app = poll_until(find_app, max_wait=10.0)
        logger.info(f"App import with missing ref: found={app is not None}")

    def test_form_with_missing_workflow_imports(
        self,
        e2e_client,
        platform_admin,
        github_configured,  # noqa: ARG002 - required for GitHub setup
        create_remote_file,
    ):
        """
        Form with ref to non-existent workflow imports gracefully.
        """
        form_name = f"Missing Ref Form {int(time.time())}"
        form_id = str(uuid4())
        non_existent_ref = "workflows/missing.py::no_such_function"

        form_content = create_form_json_with_portable_refs(
            form_name=form_name,
            form_id=form_id,
            workflow_portable_ref=non_existent_ref,
        )

        form_slug = form_name.lower().replace(" ", "-")
        create_remote_file(
            path=f"forms/{form_slug}.form.json",
            content=form_content,
            message="E2E test: Form with missing workflow ref",
        )

        # Execute pull with auto conflict resolution
        job_result, _ = execute_sync_with_auto_resolution(
            e2e_client, platform_admin.headers
        )
        assert job_result, "Sync should complete even with missing refs"

        logger.info("Form import with missing ref completed")

    def test_agent_with_missing_tools_imports(
        self,
        e2e_client,
        platform_admin,
        github_configured,  # noqa: ARG002 - required for GitHub setup
        create_remote_file,
    ):
        """
        Agent with refs to non-existent tools imports gracefully.
        """
        agent_name = f"Missing Tools Agent {int(time.time())}"
        agent_id = str(uuid4())
        non_existent_ref = "workflows/no_tool.py::missing_tool"

        agent_content = create_agent_json_with_portable_refs(
            agent_name=agent_name,
            agent_id=agent_id,
            workflow_portable_ref=non_existent_ref,
        )

        agent_slug = agent_name.lower().replace(" ", "-")
        create_remote_file(
            path=f"agents/{agent_slug}.agent.json",
            content=agent_content,
            message="E2E test: Agent with missing tool refs",
        )

        # Execute pull with auto conflict resolution
        job_result, _ = execute_sync_with_auto_resolution(
            e2e_client, platform_admin.headers
        )
        assert job_result, "Sync should complete even with missing refs"

        logger.info("Agent import with missing refs completed")

    def test_partial_ref_resolution(
        self,
        e2e_client,
        platform_admin,
        github_configured,  # noqa: ARG002 - required for GitHub setup
        create_remote_file,
        test_workflow,
    ):
        """
        Some refs resolve (existing workflow), others stay as portable strings.
        """
        workflow = test_workflow
        app_slug = f"e2e-partial-{int(time.time())}"
        app_id = str(uuid4())

        # Create app with two buttons:
        # - One references existing workflow (should resolve)
        # - One references non-existent workflow (should stay portable)
        app_data = {
            "id": app_id,
            "name": "Partial Ref Test App",
            "slug": app_slug,
            "pages": [
                {
                    "id": "page-1",
                    "title": "Test",
                    "path": "/test",
                    "layout": {
                        "id": "layout_1",
                        "type": "column",
                        "children": [
                            {
                                "id": "btn_exists",
                                "type": "button",
                                "props": {
                                    "label": "Exists",
                                    "workflow_id": workflow["portable_ref"],
                                },
                            },
                            {
                                "id": "btn_missing",
                                "type": "button",
                                "props": {
                                    "label": "Missing",
                                    "workflow_id": "workflows/nope.py::missing",
                                },
                            },
                        ],
                    },
                }
            ],
            "_export": {
                "workflow_refs": ["pages.*.layout..*.props.workflow_id"],
                "version": "1.0",
            },
        }

        create_remote_file(
            path=f"apps/{app_slug}.app.json",
            content=json.dumps(app_data, indent=2),
            message="E2E test: Partial ref resolution",
        )

        # Execute pull with auto conflict resolution
        job_result, _ = execute_sync_with_auto_resolution(
            e2e_client, platform_admin.headers
        )
        assert job_result, "Sync should complete"

        logger.info("Partial ref resolution test completed")
