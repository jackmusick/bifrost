"""E2E tests for workflow registration."""

import pytest


@pytest.mark.e2e
class TestRegisterWorkflow:
    """Test POST /api/workflows/register endpoint."""

    def test_register_workflow_from_existing_file(self, e2e_client, platform_admin):
        """Register a workflow function from an existing .py file."""
        file_content = '''
from bifrost import workflow

@workflow(name="Test Registration Workflow")
def test_reg_wf(message: str):
    """A test workflow for registration."""
    return {"message": message}
'''
        # Write file via editor API
        write_resp = e2e_client.put(
            "/api/files/editor/content",
            headers=platform_admin.headers,
            json={
                "path": "workflows/test_reg.py",
                "content": file_content,
                "encoding": "utf-8",
            },
        )
        assert write_resp.status_code == 200, f"Write failed: {write_resp.text}"

        # Verify workflow was NOT auto-registered
        list_resp = e2e_client.get(
            "/api/workflows",
            headers=platform_admin.headers,
        )
        assert list_resp.status_code == 200
        workflows = list_resp.json()
        auto_registered = [w for w in workflows if w.get("name") == "Test Registration Workflow"]
        assert len(auto_registered) == 0, "Workflow should NOT be auto-registered"

        # Register explicitly
        reg_resp = e2e_client.post(
            "/api/workflows/register",
            headers=platform_admin.headers,
            json={"path": "workflows/test_reg.py", "function_name": "test_reg_wf"},
        )
        assert reg_resp.status_code == 201, f"Register failed: {reg_resp.text}"
        data = reg_resp.json()
        assert data["name"] == "Test Registration Workflow"
        assert data["function_name"] == "test_reg_wf"
        assert data["type"] == "workflow"
        assert "id" in data

        # Cleanup
        e2e_client.delete(
            "/api/files/editor?path=workflows/test_reg.py",
            headers=platform_admin.headers,
        )

    def test_register_nonexistent_file_fails(self, e2e_client, platform_admin):
        """Registration fails if .py file doesn't exist."""
        resp = e2e_client.post(
            "/api/workflows/register",
            headers=platform_admin.headers,
            json={"path": "workflows/nonexistent.py", "function_name": "foo"},
        )
        assert resp.status_code == 404

    def test_register_nonexistent_function_fails(self, e2e_client, platform_admin):
        """Registration fails if function doesn't exist in file."""
        # Write a file without any decorated functions
        e2e_client.put(
            "/api/files/editor/content",
            headers=platform_admin.headers,
            json={
                "path": "workflows/test_reg2.py",
                "content": "x = 1\n",
                "encoding": "utf-8",
            },
        )

        resp = e2e_client.post(
            "/api/workflows/register",
            headers=platform_admin.headers,
            json={"path": "workflows/test_reg2.py", "function_name": "missing_fn"},
        )
        assert resp.status_code == 404

        # Cleanup
        e2e_client.delete(
            "/api/files/editor?path=workflows/test_reg2.py",
            headers=platform_admin.headers,
        )

    def test_register_duplicate_fails(self, e2e_client, platform_admin):
        """Registration fails if workflow is already registered."""
        file_content = '''
from bifrost import workflow

@workflow(name="Duplicate Registration Test")
def test_dup_wf(message: str):
    """A test workflow for duplicate registration."""
    return {"message": message}
'''
        # Write file
        e2e_client.put(
            "/api/files/editor/content",
            headers=platform_admin.headers,
            json={
                "path": "workflows/test_dup.py",
                "content": file_content,
                "encoding": "utf-8",
            },
        )

        # Register first time
        reg_resp = e2e_client.post(
            "/api/workflows/register",
            headers=platform_admin.headers,
            json={"path": "workflows/test_dup.py", "function_name": "test_dup_wf"},
        )
        assert reg_resp.status_code == 201, f"First register failed: {reg_resp.text}"

        # Register again - should fail with 409
        dup_resp = e2e_client.post(
            "/api/workflows/register",
            headers=platform_admin.headers,
            json={"path": "workflows/test_dup.py", "function_name": "test_dup_wf"},
        )
        assert dup_resp.status_code == 409

        # Cleanup
        e2e_client.delete(
            "/api/files/editor?path=workflows/test_dup.py",
            headers=platform_admin.headers,
        )

    def test_register_non_python_file_fails(self, e2e_client, platform_admin):
        """Registration fails for non-.py files."""
        # Write a non-Python file first so the endpoint finds it and
        # rejects it based on file extension (400) rather than returning
        # 404 for a missing file.
        e2e_client.put(
            "/api/files/editor/content",
            headers=platform_admin.headers,
            json={
                "path": "workflows/readme.md",
                "content": "# Readme\n",
                "encoding": "utf-8",
            },
        )

        resp = e2e_client.post(
            "/api/workflows/register",
            headers=platform_admin.headers,
            json={"path": "workflows/readme.md", "function_name": "foo"},
        )
        assert resp.status_code == 400

        # Cleanup
        e2e_client.delete(
            "/api/files/editor?path=workflows/readme.md",
            headers=platform_admin.headers,
        )
