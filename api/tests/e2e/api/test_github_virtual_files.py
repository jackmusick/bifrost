"""
Virtual File Round-Trip GitHub Sync E2E Tests.

Tests that after pushing virtual files (forms, agents, apps) to GitHub,
an immediate sync preview shows no conflicts and the sync state is empty.

This test file is specifically designed to reproduce and debug the bug where:
- Forms appear as conflicts after push
- Apps appear in both incoming AND outgoing after push

Requirements:
- GITHUB_TEST_PAT environment variable with a valid GitHub PAT
- GITHUB_TEST_REPO environment variable (default: jackmusick/e2e-test-workspace)

Tests skip gracefully if environment variables are not configured.
"""

import json
import logging
import time

import pytest

from tests.e2e.fixtures.entity_setup import poll_until

logger = logging.getLogger(__name__)


def execute_sync_and_wait(e2e_client, headers, max_wait: float = 60.0):
    """
    Execute GitHub sync and wait for completion.

    Returns:
        tuple: (job_result dict, job_id)
    """
    # Get preview to find any conflicts
    preview_response = e2e_client.get("/api/github/sync", headers=headers)
    if preview_response.status_code != 200:
        logger.error(f"Preview failed: {preview_response.status_code} - {preview_response.text}")
        return None, None

    preview = preview_response.json()
    conflicts = preview.get("conflicts", [])
    to_push = preview.get("to_push", [])
    to_pull = preview.get("to_pull", [])

    # Build conflict resolutions - prefer local for all
    conflict_resolutions = {conflict["path"]: "keep_local" for conflict in conflicts}

    logger.info(
        f"Sync: to_push={len(to_push)}, to_pull={len(to_pull)}, conflicts={len(conflicts)}"
    )

    # If nothing to sync, we're done
    if not to_push and not to_pull and not conflicts:
        logger.info("Nothing to sync")
        return {"status": "completed", "message": "Nothing to sync"}, None

    # Execute sync
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

    return job_result, job_id


# =============================================================================
# Round-Trip Tests - Verify no conflicts after push
# =============================================================================


@pytest.mark.e2e
class TestVirtualFileRoundTrip:
    """Test that after pushing virtual files, immediate sync shows clean state."""

    def test_form_push_then_sync_no_conflicts(
        self,
        e2e_client,
        platform_admin,
        github_configured,  # noqa: ARG002 - required for GitHub setup
        test_form_with_workflow,
        get_github_file_content,
    ):
        """
        After pushing a form, immediate sync should show no conflicts.

        This test verifies:
        1. Form is in to_push before sync
        2. After sync completes, preview is empty (no conflicts, no to_push, no to_pull)
        """
        form_info = test_form_with_workflow
        form = form_info["form"]
        form_id = form["id"]

        # 1. Get sync preview - form should be in to_push
        preview1 = e2e_client.get("/api/github/sync", headers=platform_admin.headers)
        assert preview1.status_code == 200, f"Preview failed: {preview1.text}"
        preview_data = preview1.json()

        to_push_paths = [a["path"] for a in preview_data.get("to_push", [])]
        form_in_push = any(f"{form_id}.form.json" in p for p in to_push_paths)
        logger.info(f"Form {form_id} in to_push: {form_in_push}")
        logger.info(f"All to_push paths: {to_push_paths}")

        assert form_in_push, f"Form {form_id} should be in to_push before sync"

        # 2. Execute sync (push the form)
        job_result, job_id = execute_sync_and_wait(e2e_client, platform_admin.headers)
        assert job_result, "Sync job did not complete"
        assert job_result.get("status") == "success", f"Sync failed: {job_result}"
        logger.info(f"Sync job {job_id} completed successfully")

        # 3. Verify form was actually pushed to GitHub
        form_file_path = f"forms/{form_id}.form.json"
        github_content = get_github_file_content(form_file_path)
        assert github_content is not None, f"Form file not found on GitHub: {form_file_path}"
        logger.info(f"Form file verified on GitHub: {form_file_path}")

        # Log what GitHub has for debugging
        logger.info(f"GitHub form content keys: {list(github_content.keys())}")
        if "_export" in github_content:
            logger.info(f"GitHub form _export: {github_content['_export']}")

        # 4. Get sync preview again - should be empty, NO conflicts
        preview2 = e2e_client.get("/api/github/sync", headers=platform_admin.headers)
        assert preview2.status_code == 200, f"Second preview failed: {preview2.text}"
        data = preview2.json()

        to_pull = data.get("to_pull", [])
        to_push = data.get("to_push", [])
        conflicts = data.get("conflicts", [])

        # Log details for debugging
        logger.info(f"After sync - to_pull: {len(to_pull)}, to_push: {len(to_push)}, conflicts: {len(conflicts)}")
        if conflicts:
            for c in conflicts:
                logger.error(f"CONFLICT: {c.get('path')}")
                logger.error(f"  local_sha: {c.get('local_sha')}")
                logger.error(f"  remote_sha: {c.get('remote_sha')}")
        if to_push:
            for p in to_push:
                logger.warning(f"TO_PUSH: {p.get('path')}")
        if to_pull:
            for p in to_pull:
                logger.warning(f"TO_PULL: {p.get('path')}")

        # Check for form specifically
        form_in_conflicts = any(f"{form_id}.form.json" in c.get("path", "") for c in conflicts)
        form_in_push = any(f"{form_id}.form.json" in p.get("path", "") for p in to_push)
        form_in_pull = any(f"{form_id}.form.json" in p.get("path", "") for p in to_pull)

        assert not form_in_conflicts, "Form should NOT be in conflicts after push"
        assert not form_in_push, "Form should NOT be in to_push after push"
        assert not form_in_pull, "Form should NOT be in to_pull after push"

    def test_agent_push_then_sync_no_conflicts(
        self,
        e2e_client,
        platform_admin,
        github_configured,  # noqa: ARG002 - required for GitHub setup
        test_agent_with_tools,
        get_github_file_content,
    ):
        """
        After pushing an agent, immediate sync should show no conflicts.

        This test verifies:
        1. Agent is in to_push before sync
        2. After sync completes, preview shows agent is not in conflicts or to_push
        """
        agent_info = test_agent_with_tools
        agent = agent_info["agent"]
        agent_id = agent["id"]

        # 1. Get sync preview - agent should be in to_push
        preview1 = e2e_client.get("/api/github/sync", headers=platform_admin.headers)
        assert preview1.status_code == 200, f"Preview failed: {preview1.text}"
        preview_data = preview1.json()

        to_push_paths = [a["path"] for a in preview_data.get("to_push", [])]
        agent_in_push = any(f"{agent_id}.agent.json" in p for p in to_push_paths)
        logger.info(f"Agent {agent_id} in to_push: {agent_in_push}")
        logger.info(f"All to_push paths: {to_push_paths}")

        assert agent_in_push, f"Agent {agent_id} should be in to_push before sync"

        # 2. Execute sync (push the agent)
        job_result, job_id = execute_sync_and_wait(e2e_client, platform_admin.headers)
        assert job_result, "Sync job did not complete"
        assert job_result.get("status") == "success", f"Sync failed: {job_result}"
        logger.info(f"Sync job {job_id} completed successfully")

        # 3. Verify agent was actually pushed to GitHub
        agent_file_path = f"agents/{agent_id}.agent.json"
        github_content = get_github_file_content(agent_file_path)
        assert github_content is not None, f"Agent file not found on GitHub: {agent_file_path}"
        logger.info(f"Agent file verified on GitHub: {agent_file_path}")

        # Log what GitHub has for debugging
        logger.info(f"GitHub agent content keys: {list(github_content.keys())}")
        if "_export" in github_content:
            logger.info(f"GitHub agent _export: {github_content['_export']}")

        # 4. Get sync preview again - should show no conflicts for agent
        preview2 = e2e_client.get("/api/github/sync", headers=platform_admin.headers)
        assert preview2.status_code == 200, f"Second preview failed: {preview2.text}"
        data = preview2.json()

        to_pull = data.get("to_pull", [])
        to_push = data.get("to_push", [])
        conflicts = data.get("conflicts", [])

        # Log details for debugging
        logger.info(f"After sync - to_pull: {len(to_pull)}, to_push: {len(to_push)}, conflicts: {len(conflicts)}")
        if conflicts:
            for c in conflicts:
                logger.error(f"CONFLICT: {c.get('path')}")
        if to_push:
            for p in to_push:
                logger.warning(f"TO_PUSH: {p.get('path')}")
        if to_pull:
            for p in to_pull:
                logger.warning(f"TO_PULL: {p.get('path')}")

        # Check for agent specifically
        agent_in_conflicts = any(f"{agent_id}.agent.json" in c.get("path", "") for c in conflicts)
        agent_in_push = any(f"{agent_id}.agent.json" in p.get("path", "") for p in to_push)
        agent_in_pull = any(f"{agent_id}.agent.json" in p.get("path", "") for p in to_pull)

        assert not agent_in_conflicts, "Agent should NOT be in conflicts after push"
        assert not agent_in_push, "Agent should NOT be in to_push after push"
        assert not agent_in_pull, "Agent should NOT be in to_pull after push"

    def test_app_push_then_sync_no_conflicts(
        self,
        e2e_client,
        platform_admin,
        github_configured,  # noqa: ARG002 - required for GitHub setup
        get_github_file_content,
    ):
        """
        After pushing an app, immediate sync should show no conflicts.

        This test verifies:
        1. App is in to_push before sync
        2. After sync, app should NOT appear in both incoming AND outgoing
        """
        # Create a unique app for this test
        unique_id = int(time.time() * 1000) % 1000000
        app_slug = f"e2e-roundtrip-{unique_id}"

        app_response = e2e_client.post(
            "/api/applications",
            headers=platform_admin.headers,
            json={
                "name": f"E2E Round Trip Test {unique_id}",
                "slug": app_slug,
                "description": "App for round-trip sync testing",
                "access_level": "authenticated",
            },
        )
        assert app_response.status_code == 201, f"Create app failed: {app_response.text}"
        app = app_response.json()
        app_id = app["id"]
        logger.info(f"Created app: {app_id} (slug: {app_slug})")

        try:
            # 1. Get sync preview - app should be in to_push
            preview1 = e2e_client.get("/api/github/sync", headers=platform_admin.headers)
            assert preview1.status_code == 200, f"Preview failed: {preview1.text}"
            preview_data = preview1.json()

            to_push_paths = [a["path"] for a in preview_data.get("to_push", [])]
            app_in_push = any(app_slug in p for p in to_push_paths)
            logger.info(f"App {app_slug} in to_push: {app_in_push}")
            logger.info(f"All to_push paths containing app: {[p for p in to_push_paths if app_slug in p]}")

            assert app_in_push, f"App {app_slug} should be in to_push before sync"

            # 2. Execute sync
            job_result, job_id = execute_sync_and_wait(e2e_client, platform_admin.headers)
            assert job_result, "Sync job did not complete"
            assert job_result.get("status") == "success", f"Sync failed: {job_result}"
            logger.info(f"Sync job {job_id} completed successfully")

            # 3. Verify app was actually pushed to GitHub
            # Note: Apps use directory structure: apps/{slug}/app.json
            app_file_path = f"apps/{app_slug}/app.json"
            github_content = get_github_file_content(app_file_path)
            assert github_content is not None, f"App file not found on GitHub: {app_file_path}"
            logger.info(f"App file verified on GitHub: {app_file_path}")

            # 4. Get sync preview again
            preview2 = e2e_client.get("/api/github/sync", headers=platform_admin.headers)
            assert preview2.status_code == 200, f"Second preview failed: {preview2.text}"
            data = preview2.json()

            to_pull = data.get("to_pull", [])
            to_push = data.get("to_push", [])
            conflicts = data.get("conflicts", [])

            # Log details for debugging
            logger.info(f"After sync - to_pull: {len(to_pull)}, to_push: {len(to_push)}, conflicts: {len(conflicts)}")

            # Check for app specifically
            to_pull_paths = [p.get("path", "") for p in to_pull]
            to_push_paths = [p.get("path", "") for p in to_push]
            conflict_paths = [c.get("path", "") for c in conflicts]

            app_in_pull = any(app_slug in p for p in to_pull_paths)
            app_in_push = any(app_slug in p for p in to_push_paths)
            app_in_conflicts = any(app_slug in p for p in conflict_paths)

            if app_in_pull:
                logger.warning(f"App in TO_PULL: {[p for p in to_pull_paths if app_slug in p]}")
            if app_in_push:
                logger.warning(f"App in TO_PUSH: {[p for p in to_push_paths if app_slug in p]}")
            if app_in_conflicts:
                logger.error(f"App in CONFLICTS: {[p for p in conflict_paths if app_slug in p]}")

            # The critical check: app should NOT appear in both incoming and outgoing
            assert not (app_in_pull and app_in_push), (
                f"BUG: App {app_slug} appears in BOTH to_pull AND to_push! "
                f"to_pull: {[p for p in to_pull_paths if app_slug in p]}, "
                f"to_push: {[p for p in to_push_paths if app_slug in p]}"
            )

            # Also check it's not in conflicts
            assert not app_in_conflicts, f"App {app_slug} should NOT be in conflicts after push"

            # Ideally, it should be in neither (clean state)
            if app_in_pull or app_in_push:
                logger.warning(
                    f"App still in sync state after push (not a critical failure but unexpected): "
                    f"pull={app_in_pull}, push={app_in_push}"
                )

        finally:
            # Cleanup: delete app
            try:
                e2e_client.delete(
                    f"/api/applications/{app_id}",
                    headers=platform_admin.headers,
                )
                logger.info(f"Cleaned up app: {app_id}")
            except Exception as e:
                logger.warning(f"Failed to cleanup app: {e}")


# =============================================================================
# Debug Tests - Detailed SHA Comparison
# =============================================================================


@pytest.mark.e2e
class TestVirtualFileSHAComparison:
    """Debug tests to understand exactly what differs between local and remote content."""

    def test_form_sha_comparison_debug(
        self,
        e2e_client,
        platform_admin,
        github_configured,  # noqa: ARG002 - required for GitHub setup
        test_form_with_workflow,
        get_github_file_content,
    ):
        """
        Debug test to see exactly what's different between local and remote content.

        This test:
        1. Creates and pushes a form
        2. Fetches what GitHub has
        3. Gets sync preview with detailed conflict information
        4. Logs exact differences to help diagnose the issue
        """
        form_info = test_form_with_workflow
        form = form_info["form"]
        form_id = form["id"]
        form_file_path = f"forms/{form_id}.form.json"

        # 1. Execute sync to push the form
        job_result, _ = execute_sync_and_wait(e2e_client, platform_admin.headers)
        assert job_result, "Sync job did not complete"
        assert job_result.get("status") == "success", f"Sync failed: {job_result}"

        # 2. Get what GitHub has
        github_content = get_github_file_content(form_file_path)
        if github_content:
            logger.info("=== GITHUB CONTENT ===")
            logger.info(f"Keys: {list(github_content.keys())}")
            logger.info(f"ID: {github_content.get('id')}")
            logger.info(f"Name: {github_content.get('name')}")
            if "_export" in github_content:
                logger.info(f"_export: {json.dumps(github_content['_export'], indent=2)}")
            logger.info(f"Full content:\n{json.dumps(github_content, indent=2)}")
        else:
            logger.warning(f"GitHub content not found for {form_file_path}")

        # 3. Get sync preview with conflict details
        preview = e2e_client.get("/api/github/sync", headers=platform_admin.headers)
        assert preview.status_code == 200
        data = preview.json()

        conflicts = data.get("conflicts", [])
        to_push = data.get("to_push", [])
        to_pull = data.get("to_pull", [])

        logger.info("=== SYNC PREVIEW ===")
        logger.info(f"Total conflicts: {len(conflicts)}")
        logger.info(f"Total to_push: {len(to_push)}")
        logger.info(f"Total to_pull: {len(to_pull)}")

        # Find our form in conflicts
        form_conflict = None
        for c in conflicts:
            if form_id in c.get("path", ""):
                form_conflict = c
                break

        if form_conflict:
            logger.error("=== FORM CONFLICT FOUND ===")
            logger.error(f"PATH: {form_conflict.get('path')}")
            logger.error(f"LOCAL SHA: {form_conflict.get('local_sha')}")
            logger.error(f"REMOTE SHA: {form_conflict.get('remote_sha')}")
            if "local_content" in form_conflict:
                logger.error(f"LOCAL CONTENT:\n{form_conflict.get('local_content')}")
            if "remote_content" in form_conflict:
                logger.error(f"REMOTE CONTENT:\n{form_conflict.get('remote_content')}")

            # This test is designed to fail when there's a conflict so we can see the output
            pytest.fail(
                f"Form {form_id} is in conflicts after push. "
                f"Check test output for SHA comparison details."
            )
        else:
            # Check if form is in to_push or to_pull
            form_in_push = any(form_id in p.get("path", "") for p in to_push)
            form_in_pull = any(form_id in p.get("path", "") for p in to_pull)

            if form_in_push or form_in_pull:
                logger.warning(f"Form in push: {form_in_push}, in pull: {form_in_pull}")
                for p in to_push:
                    if form_id in p.get("path", ""):
                        logger.warning(f"Form in TO_PUSH: {json.dumps(p, indent=2)}")
                for p in to_pull:
                    if form_id in p.get("path", ""):
                        logger.warning(f"Form in TO_PULL: {json.dumps(p, indent=2)}")
            else:
                logger.info("Form is NOT in conflicts, to_push, or to_pull - CLEAN STATE")

    def test_agent_sha_comparison_debug(
        self,
        e2e_client,
        platform_admin,
        github_configured,  # noqa: ARG002 - required for GitHub setup
        test_agent_with_tools,
        get_github_file_content,
    ):
        """
        Debug test to see exactly what differs for agents.
        """
        agent_info = test_agent_with_tools
        agent = agent_info["agent"]
        agent_id = agent["id"]
        agent_file_path = f"agents/{agent_id}.agent.json"

        # 1. Execute sync to push the agent
        job_result, _ = execute_sync_and_wait(e2e_client, platform_admin.headers)
        assert job_result, "Sync job did not complete"
        assert job_result.get("status") == "success", f"Sync failed: {job_result}"

        # 2. Get what GitHub has
        github_content = get_github_file_content(agent_file_path)
        if github_content:
            logger.info("=== GITHUB CONTENT ===")
            logger.info(f"Keys: {list(github_content.keys())}")
            logger.info(f"ID: {github_content.get('id')}")
            logger.info(f"Name: {github_content.get('name')}")
            logger.info(f"tool_ids: {github_content.get('tool_ids')}")
            if "_export" in github_content:
                logger.info(f"_export: {json.dumps(github_content['_export'], indent=2)}")
        else:
            logger.warning(f"GitHub content not found for {agent_file_path}")

        # 3. Get sync preview
        preview = e2e_client.get("/api/github/sync", headers=platform_admin.headers)
        assert preview.status_code == 200
        data = preview.json()

        conflicts = data.get("conflicts", [])
        to_push = data.get("to_push", [])
        to_pull = data.get("to_pull", [])

        logger.info("=== SYNC PREVIEW ===")
        logger.info(f"Total conflicts: {len(conflicts)}")
        logger.info(f"Total to_push: {len(to_push)}")
        logger.info(f"Total to_pull: {len(to_pull)}")

        # Find our agent
        agent_conflict = None
        for c in conflicts:
            if agent_id in c.get("path", ""):
                agent_conflict = c
                break

        if agent_conflict:
            logger.error("=== AGENT CONFLICT FOUND ===")
            logger.error(f"PATH: {agent_conflict.get('path')}")
            logger.error(f"LOCAL SHA: {agent_conflict.get('local_sha')}")
            logger.error(f"REMOTE SHA: {agent_conflict.get('remote_sha')}")

            pytest.fail(
                f"Agent {agent_id} is in conflicts after push. "
                f"Check test output for SHA comparison details."
            )
        else:
            agent_in_push = any(agent_id in p.get("path", "") for p in to_push)
            agent_in_pull = any(agent_id in p.get("path", "") for p in to_pull)

            if agent_in_push or agent_in_pull:
                logger.warning(f"Agent in push: {agent_in_push}, in pull: {agent_in_pull}")
            else:
                logger.info("Agent is NOT in conflicts, to_push, or to_pull - CLEAN STATE")
