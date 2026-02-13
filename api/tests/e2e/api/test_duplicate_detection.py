"""
E2E tests for duplicate detection and conflict handling.

Tests how the system handles:
- Same path + same function name (should update, not duplicate)
- Same name at different paths (allowed - names can duplicate)
- Form duplicate path handling
- App duplicate slug handling
"""

import pytest

from tests.e2e.conftest import write_and_register


@pytest.mark.e2e
class TestWorkflowDuplicateHandling:
    """Test workflow duplicate detection and handling."""

    def test_same_path_same_function_updates_not_duplicates(
        self, e2e_client, platform_admin
    ):
        """
        Writing to same path with same function name updates existing workflow.
        Should NOT create duplicate entries.
        """
        workflow_content_v1 = '''"""Version 1 Workflow"""
from bifrost import workflow

@workflow(
    name="duplicate_test_workflow",
    description="First version",
)
async def duplicate_test_workflow() -> str:
    return "v1"
'''
        # Create first version via write + register
        result = write_and_register(
            e2e_client, platform_admin.headers,
            "duplicate_test.py", workflow_content_v1,
            "duplicate_test_workflow",
        )
        v1_id = result["id"]

        # Count workflows with this name
        response = e2e_client.get(
            "/api/workflows",
            headers=platform_admin.headers,
        )
        workflows = response.json()
        matching_v1 = [w for w in workflows if w["name"] == "duplicate_test_workflow"]
        assert len(matching_v1) == 1, "Should have exactly one workflow"

        # Update with new content (same path, same function)
        workflow_content_v2 = '''"""Version 2 Workflow"""
from bifrost import workflow

@workflow(
    name="duplicate_test_workflow",
    description="Second version - updated",
)
async def duplicate_test_workflow() -> str:
    return "v2"
'''
        # Write v2 content to the same path, then attempt to register again
        resp = e2e_client.put(
            "/api/files/editor/content",
            headers=platform_admin.headers,
            json={
                "path": "duplicate_test.py",
                "content": workflow_content_v2,
                "encoding": "utf-8",
            },
        )
        assert resp.status_code in (200, 201)

        # Re-registering the same path+function should return 409 (already registered)
        resp = e2e_client.post(
            "/api/workflows/register",
            headers=platform_admin.headers,
            json={"path": "duplicate_test.py", "function_name": "duplicate_test_workflow"},
        )
        assert resp.status_code == 409, "Re-registering same path+function should be rejected as duplicate"

        # Verify still only one workflow, same ID
        response = e2e_client.get(
            "/api/workflows",
            headers=platform_admin.headers,
        )
        workflows = response.json()
        matching_v2 = [w for w in workflows if w["name"] == "duplicate_test_workflow"]
        assert len(matching_v2) == 1, \
            f"Should still have exactly one workflow, got {len(matching_v2)}"

        v2_workflow = matching_v2[0]
        assert v2_workflow["id"] == v1_id, \
            "Workflow ID should remain stable across updates"

        # Cleanup
        e2e_client.delete(
            "/api/files/editor?path=duplicate_test.py",
            headers=platform_admin.headers,
        )

    def test_same_name_different_paths_rejected(
        self, e2e_client, platform_admin
    ):
        """
        Same workflow name at different paths is rejected by unique name constraint.
        The uq_workflows_global_name index ensures one active workflow per name per scope.
        """
        workflow_content = '''"""Workflow with common name"""
from bifrost import workflow

@workflow(
    name="common_workflow_name",
    description="At path {path}",
)
async def common_workflow_name() -> str:
    return "result"
'''
        # Create at first path
        write_and_register(
            e2e_client, platform_admin.headers,
            "path1/workflow.py",
            workflow_content.replace("{path}", "path1"),
            "common_workflow_name",
        )

        # Create at second path (same name, different path) -- should fail to register
        resp = e2e_client.put(
            "/api/files/editor/content",
            headers=platform_admin.headers,
            json={
                "path": "path2/workflow.py",
                "content": workflow_content.replace("{path}", "path2"),
                "encoding": "utf-8",
            },
        )
        assert resp.status_code in (200, 201)

        # Registering the same function name at a different path should fail
        # (unique name constraint or DB-level conflict)
        resp = e2e_client.post(
            "/api/workflows/register",
            headers=platform_admin.headers,
            json={"path": "path2/workflow.py", "function_name": "common_workflow_name"},
        )
        assert resp.status_code in (409, 500), \
            f"Second registration of same name at different path should be rejected, got {resp.status_code}"

        # Only one workflow should exist (unique name constraint blocks the second)
        response = e2e_client.get(
            "/api/workflows",
            headers=platform_admin.headers,
        )
        workflows = response.json()
        matching = [w for w in workflows if w["name"] == "common_workflow_name"]

        assert len(matching) == 1, \
            f"Should have exactly one workflow (unique name constraint), got {len(matching)}"

        # Cleanup
        e2e_client.delete(
            "/api/files/editor?path=path1",
            headers=platform_admin.headers,
        )
        e2e_client.delete(
            "/api/files/editor?path=path2",
            headers=platform_admin.headers,
        )

    def test_multiple_workflows_in_same_file(
        self, e2e_client, platform_admin
    ):
        """
        Multiple @workflow decorators in same file creates multiple entries.
        """
        multi_workflow_content = '''"""Multiple Workflows in One File"""
from bifrost import workflow

@workflow(name="multi_workflow_1")
async def multi_workflow_1() -> str:
    return "first"

@workflow(name="multi_workflow_2")
async def multi_workflow_2() -> str:
    return "second"

@workflow(name="multi_workflow_3")
async def multi_workflow_3() -> str:
    return "third"
'''
        # Write the file once, then register each function separately
        resp = e2e_client.put(
            "/api/files/editor/content",
            headers=platform_admin.headers,
            json={
                "path": "multi_workflow.py",
                "content": multi_workflow_content,
                "encoding": "utf-8",
            },
        )
        assert resp.status_code in (200, 201)

        # Register each workflow function from the same file
        for func_name in ("multi_workflow_1", "multi_workflow_2", "multi_workflow_3"):
            resp = e2e_client.post(
                "/api/workflows/register",
                headers=platform_admin.headers,
                json={"path": "multi_workflow.py", "function_name": func_name},
            )
            assert resp.status_code in (200, 201, 409), \
                f"Register failed for {func_name}: {resp.status_code} {resp.text}"

        # Should create three workflow entries
        response = e2e_client.get(
            "/api/workflows",
            headers=platform_admin.headers,
        )
        workflows = response.json()
        multi_workflows = [
            w for w in workflows
            if w["name"] in ["multi_workflow_1", "multi_workflow_2", "multi_workflow_3"]
        ]

        assert len(multi_workflows) == 3, \
            f"Should have 3 workflows from multi-workflow file, got {len(multi_workflows)}"

        # All should have same source file path but different function names
        paths = [w.get("source_file_path") for w in multi_workflows]
        assert all("multi_workflow.py" in (p or "") for p in paths), \
            "All workflows should reference the same file"

        # Cleanup
        e2e_client.delete(
            "/api/files/editor?path=multi_workflow.py",
            headers=platform_admin.headers,
        )


@pytest.mark.e2e
class TestFormDuplicateHandling:
    """Test form duplicate detection and handling."""

    def test_form_names_can_duplicate(
        self, e2e_client, platform_admin
    ):
        """
        Multiple forms with same name are allowed (IDs are unique).
        """
        # Create first form
        response1 = e2e_client.post(
            "/api/forms",
            headers=platform_admin.headers,
            json={
                "name": "Duplicate Name Form",
                "workflow_id": None,
                "form_schema": {"fields": []},
                "access_level": "authenticated",
            },
        )
        assert response1.status_code == 201
        form1 = response1.json()

        # Create second form with same name
        response2 = e2e_client.post(
            "/api/forms",
            headers=platform_admin.headers,
            json={
                "name": "Duplicate Name Form",
                "workflow_id": None,
                "form_schema": {"fields": []},
                "access_level": "authenticated",
            },
        )
        assert response2.status_code == 201
        form2 = response2.json()

        # Should have different IDs
        assert form1["id"] != form2["id"], \
            "Forms with same name should have different IDs"

        # List should show both
        response = e2e_client.get(
            "/api/forms",
            headers=platform_admin.headers,
        )
        forms = response.json()
        matching = [f for f in forms if f["name"] == "Duplicate Name Form"]
        assert len(matching) >= 2, \
            "Should have at least 2 forms with same name"

        # Cleanup
        e2e_client.delete(f"/api/forms/{form1['id']}", headers=platform_admin.headers)
        e2e_client.delete(f"/api/forms/{form2['id']}", headers=platform_admin.headers)


@pytest.mark.e2e
class TestDataProviderDuplicateHandling:
    """Test data provider duplicate detection."""

    def test_same_path_same_function_updates_provider(
        self, e2e_client, platform_admin
    ):
        """
        Same path + function name updates existing data provider.
        """
        dp_v1 = '''"""DP Version 1"""
from bifrost import data_provider

@data_provider(
    name="dup_test_provider",
    description="Version 1",
)
async def dup_test_provider():
    return [{"v": 1}]
'''
        # Register first version
        result = write_and_register(
            e2e_client, platform_admin.headers,
            "dup_test_provider.py", dp_v1,
            "dup_test_provider",
        )
        v1_id = result["id"]

        # Update with new content
        dp_v2 = '''"""DP Version 2"""
from bifrost import data_provider

@data_provider(
    name="dup_test_provider",
    description="Version 2 - updated",
)
async def dup_test_provider():
    return [{"v": 2}]
'''
        # Write v2 content to the same path, then attempt to register again
        resp = e2e_client.put(
            "/api/files/editor/content",
            headers=platform_admin.headers,
            json={
                "path": "dup_test_provider.py",
                "content": dp_v2,
                "encoding": "utf-8",
            },
        )
        assert resp.status_code in (200, 201)

        # Re-registering same path+function should return 409
        resp = e2e_client.post(
            "/api/workflows/register",
            headers=platform_admin.headers,
            json={"path": "dup_test_provider.py", "function_name": "dup_test_provider"},
        )
        assert resp.status_code == 409, "Re-registering same path+function should be rejected as duplicate"

        # Should still be one provider with same ID
        response = e2e_client.get(
            "/api/workflows?type=data_provider",
            headers=platform_admin.headers,
        )
        providers = response.json()
        matching = [p for p in providers if p["name"] == "dup_test_provider"]
        assert len(matching) == 1, \
            f"Should have exactly one provider, got {len(matching)}"
        assert matching[0]["id"] == v1_id, \
            "Provider ID should remain stable"

        # Cleanup
        e2e_client.delete(
            "/api/files/editor?path=dup_test_provider.py",
            headers=platform_admin.headers,
        )


@pytest.mark.e2e
class TestMixedEntityDuplicates:
    """Test handling of same name across different entity types."""

    def test_same_name_workflow_and_data_provider_rejected(
        self, e2e_client, platform_admin
    ):
        """
        Same name for workflow and data provider is rejected.
        The unique name constraint applies across all types in the workflows table.
        """
        # Create workflow
        workflow_content = '''"""Workflow with shared name"""
from bifrost import workflow

@workflow(name="shared_name_entity")
async def shared_name_entity() -> str:
    return "workflow"
'''
        write_and_register(
            e2e_client, platform_admin.headers,
            "shared_name_workflow.py", workflow_content,
            "shared_name_entity",
        )

        # Create data provider with same name -- should fail to register
        dp_content = '''"""Data Provider with shared name"""
from bifrost import data_provider

@data_provider(name="shared_name_entity")
async def shared_name_entity():
    return [{"type": "dp"}]
'''
        # Write the file
        resp = e2e_client.put(
            "/api/files/editor/content",
            headers=platform_admin.headers,
            json={
                "path": "shared_name_dp.py",
                "content": dp_content,
                "encoding": "utf-8",
            },
        )
        assert resp.status_code in (200, 201)

        # Registering a data provider with the same function name should fail
        # (unique name constraint blocks it)
        resp = e2e_client.post(
            "/api/workflows/register",
            headers=platform_admin.headers,
            json={"path": "shared_name_dp.py", "function_name": "shared_name_entity"},
        )
        assert resp.status_code in (409, 500), \
            f"Registering duplicate name across types should be rejected, got {resp.status_code}"

        # Only the workflow should exist
        response = e2e_client.get(
            "/api/workflows",
            headers=platform_admin.headers,
        )
        workflows = response.json()
        wf = next((w for w in workflows if w["name"] == "shared_name_entity"), None)
        assert wf is not None, "Workflow should exist"
        assert wf["type"] == "workflow", "First registered entity should be the workflow"

        response = e2e_client.get(
            "/api/workflows?type=data_provider",
            headers=platform_admin.headers,
        )
        providers = response.json()
        dp = next((p for p in providers if p["name"] == "shared_name_entity"), None)
        assert dp is None, "Data provider should not exist (blocked by unique name constraint)"

        # Cleanup
        e2e_client.delete(
            "/api/files/editor?path=shared_name_workflow.py",
            headers=platform_admin.headers,
        )
        e2e_client.delete(
            "/api/files/editor?path=shared_name_dp.py",
            headers=platform_admin.headers,
        )


@pytest.mark.e2e
class TestIdempotentWrites:
    """Test that repeated writes are idempotent."""

    def test_repeated_writes_same_content_idempotent(
        self, e2e_client, platform_admin
    ):
        """
        Writing same content multiple times doesn't create duplicates.
        """
        workflow_content = '''"""Idempotent Workflow"""
from bifrost import workflow

@workflow(name="idempotent_workflow")
async def idempotent_workflow() -> str:
    return "stable"
'''
        # Register the workflow once
        write_and_register(
            e2e_client, platform_admin.headers,
            "idempotent_test.py", workflow_content,
            "idempotent_workflow",
        )

        # Write the same content 2 more times (file writes only, no register)
        for _ in range(2):
            response = e2e_client.put(
                "/api/files/editor/content",
                headers=platform_admin.headers,
                json={
                    "path": "idempotent_test.py",
                    "content": workflow_content,
                    "encoding": "utf-8",
                },
            )
            assert response.status_code == 200

        # Attempting to re-register should return 409
        resp = e2e_client.post(
            "/api/workflows/register",
            headers=platform_admin.headers,
            json={"path": "idempotent_test.py", "function_name": "idempotent_workflow"},
        )
        assert resp.status_code == 409, "Re-registering should confirm it already exists"

        # Should have exactly one workflow
        response = e2e_client.get(
            "/api/workflows",
            headers=platform_admin.headers,
        )
        workflows = response.json()
        matching = [w for w in workflows if w["name"] == "idempotent_workflow"]
        assert len(matching) == 1, \
            f"Repeated writes should be idempotent, got {len(matching)} entries"

        # Cleanup
        e2e_client.delete(
            "/api/files/editor?path=idempotent_test.py",
            headers=platform_admin.headers,
        )
