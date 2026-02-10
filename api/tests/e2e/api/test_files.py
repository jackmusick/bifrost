"""
E2E tests for file operations (Editor API).

Tests workspace file listing, reading, writing, and folder operations.
"""

import pytest

from tests.e2e.conftest import poll_until


@pytest.mark.e2e
class TestFileOperations:
    """Test workspace file operations."""

    def test_list_files(self, e2e_client, platform_admin):
        """Platform admin can list files via editor API."""
        response = e2e_client.get(
            "/api/files/editor?path=.",
            headers=platform_admin.headers,
        )
        assert response.status_code == 200, f"List files failed: {response.text}"
        files = response.json()
        assert isinstance(files, list)

    def test_write_file(self, e2e_client, platform_admin):
        """Platform admin can write a file."""
        response = e2e_client.put(
            "/api/files/editor/content",
            headers=platform_admin.headers,
            json={
                "path": "e2e_test_file.txt",
                "content": "Hello, E2E test!",
                "encoding": "utf-8",
            },
        )
        assert response.status_code == 200, f"Write file failed: {response.text}"

        # Cleanup
        e2e_client.delete(
            "/api/files/editor?path=e2e_test_file.txt",
            headers=platform_admin.headers,
        )

    def test_read_file_content(self, e2e_client, platform_admin):
        """Platform admin can read file content."""
        # Create a file first
        e2e_client.put(
            "/api/files/editor/content",
            headers=platform_admin.headers,
            json={
                "path": "e2e_read_test.txt",
                "content": "Content to read",
                "encoding": "utf-8",
            },
        )

        # Read it back
        response = e2e_client.get(
            "/api/files/editor/content?path=e2e_read_test.txt",
            headers=platform_admin.headers,
        )
        assert response.status_code == 200, f"Read file failed: {response.text}"
        data = response.json()
        assert "Content to read" in data["content"]

        # Cleanup
        e2e_client.delete(
            "/api/files/editor?path=e2e_read_test.txt",
            headers=platform_admin.headers,
        )

    def test_create_folder(self, e2e_client, platform_admin):
        """Platform admin can create a folder."""
        response = e2e_client.post(
            "/api/files/editor/folder?path=e2e_test_folder",
            headers=platform_admin.headers,
        )
        # 201 for new, or 409 if exists from previous run
        assert response.status_code in [201, 409], f"Create folder failed: {response.text}"

        # Cleanup
        e2e_client.delete(
            "/api/files/editor?path=e2e_test_folder",
            headers=platform_admin.headers,
        )

    def test_delete_file(self, e2e_client, platform_admin):
        """Platform admin can delete a file."""
        # Create a file first
        e2e_client.put(
            "/api/files/editor/content",
            headers=platform_admin.headers,
            json={
                "path": "e2e_delete_test.txt",
                "content": "To be deleted",
                "encoding": "utf-8",
            },
        )

        # Delete it
        response = e2e_client.delete(
            "/api/files/editor?path=e2e_delete_test.txt",
            headers=platform_admin.headers,
        )
        assert response.status_code == 204, f"Delete file failed: {response.text}"

    def test_update_file_content(self, e2e_client, platform_admin):
        """Platform admin can overwrite existing file content."""
        # Create initial file
        create_response = e2e_client.put(
            "/api/files/editor/content",
            headers=platform_admin.headers,
            json={
                "path": "e2e_update_test.txt",
                "content": "Original content",
                "encoding": "utf-8",
            },
        )
        assert create_response.status_code == 200, f"Create file failed: {create_response.text}"

        # Update file with new content
        update_response = e2e_client.put(
            "/api/files/editor/content",
            headers=platform_admin.headers,
            json={
                "path": "e2e_update_test.txt",
                "content": "Updated content",
                "encoding": "utf-8",
            },
        )
        assert update_response.status_code == 200, f"Update file failed: {update_response.text}"

        # Verify content was updated
        read_response = e2e_client.get(
            "/api/files/editor/content?path=e2e_update_test.txt",
            headers=platform_admin.headers,
        )
        assert read_response.status_code == 200
        data = read_response.json()
        assert data["content"] == "Updated content", "File content was not updated"

        # Cleanup
        e2e_client.delete(
            "/api/files/editor?path=e2e_update_test.txt",
            headers=platform_admin.headers,
        )

    def test_write_file_in_subfolder(self, e2e_client, platform_admin):
        """Platform admin can write files in subdirectories."""
        # Create folder first
        folder_response = e2e_client.post(
            "/api/files/editor/folder?path=e2e_test_subfolder",
            headers=platform_admin.headers,
        )
        assert folder_response.status_code in [201, 409], \
            f"Create folder failed: {folder_response.text}"

        # Write file in subfolder
        file_response = e2e_client.put(
            "/api/files/editor/content",
            headers=platform_admin.headers,
            json={
                "path": "e2e_test_subfolder/nested_file.txt",
                "content": "File in subfolder",
                "encoding": "utf-8",
            },
        )
        assert file_response.status_code == 200, \
            f"Write file in subfolder failed: {file_response.text}"

        # Read it back to verify
        read_response = e2e_client.get(
            "/api/files/editor/content?path=e2e_test_subfolder/nested_file.txt",
            headers=platform_admin.headers,
        )
        assert read_response.status_code == 200
        data = read_response.json()
        assert data["content"] == "File in subfolder"

        # Cleanup
        e2e_client.delete(
            "/api/files/editor?path=e2e_test_subfolder",
            headers=platform_admin.headers,
        )

    def test_list_folder_contents(self, e2e_client, platform_admin):
        """Platform admin can list folder contents including files and subfolders."""
        # Create test folder
        e2e_client.post(
            "/api/files/editor/folder?path=e2e_folder_with_contents",
            headers=platform_admin.headers,
        )

        # Create multiple files in the folder
        e2e_client.put(
            "/api/files/editor/content",
            headers=platform_admin.headers,
            json={
                "path": "e2e_folder_with_contents/file1.txt",
                "content": "Content 1",
                "encoding": "utf-8",
            },
        )

        e2e_client.put(
            "/api/files/editor/content",
            headers=platform_admin.headers,
            json={
                "path": "e2e_folder_with_contents/file2.py",
                "content": "# Python file",
                "encoding": "utf-8",
            },
        )

        # List folder contents
        response = e2e_client.get(
            "/api/files/editor?path=e2e_folder_with_contents",
            headers=platform_admin.headers,
        )
        assert response.status_code == 200, f"List folder failed: {response.text}"
        files = response.json()
        assert isinstance(files, list)
        assert len(files) >= 2, "Should have at least 2 files in folder"

        # Verify we can see both files
        file_paths = [f["path"] for f in files]
        assert any("file1.txt" in path for path in file_paths), "file1.txt not found in listing"
        assert any("file2.py" in path for path in file_paths), "file2.py not found in listing"

        # Cleanup
        e2e_client.delete(
            "/api/files/editor?path=e2e_folder_with_contents",
            headers=platform_admin.headers,
        )

    def test_rename_file(self, e2e_client, platform_admin):
        """Platform admin can rename a file."""
        # Create file
        e2e_client.put(
            "/api/files/editor/content",
            headers=platform_admin.headers,
            json={
                "path": "e2e_rename_original.txt",
                "content": "Original name",
                "encoding": "utf-8",
            },
        )

        # Rename file
        rename_response = e2e_client.post(
            "/api/files/editor/rename",
            headers=platform_admin.headers,
            params={
                "old_path": "e2e_rename_original.txt",
                "new_path": "e2e_rename_new.txt",
            },
        )
        assert rename_response.status_code == 200, \
            f"Rename file failed: {rename_response.text}"

        # Verify old path doesn't exist
        old_response = e2e_client.get(
            "/api/files/editor/content?path=e2e_rename_original.txt",
            headers=platform_admin.headers,
        )
        assert old_response.status_code == 404, \
            "Old file path should not exist after rename"

        # Verify new path exists with original content
        new_response = e2e_client.get(
            "/api/files/editor/content?path=e2e_rename_new.txt",
            headers=platform_admin.headers,
        )
        assert new_response.status_code == 200
        data = new_response.json()
        assert data["content"] == "Original name", \
            "Content should be preserved after rename"

        # Cleanup
        e2e_client.delete(
            "/api/files/editor?path=e2e_rename_new.txt",
            headers=platform_admin.headers,
        )


@pytest.mark.e2e
class TestFileAccess:
    """Test file access control."""

    def test_org_user_cannot_access_files(self, e2e_client, org1_user):
        """Org user cannot access file operations (403)."""
        response = e2e_client.get(
            "/api/files/editor?path=.",
            headers=org1_user.headers,
        )
        assert response.status_code == 403, \
            f"Org user should not access files: {response.status_code}"


@pytest.mark.e2e
class TestWorkflowFileDiscovery:
    """Test workflow file creation and discovery."""

    @pytest.fixture(scope="class")
    def test_workflow_file(self, e2e_client, platform_admin):
        """Create a test workflow file and clean up after tests."""
        workflow_content = '''"""E2E Test Workflow - Discovery"""
from bifrost import workflow, context

@workflow(
    name="e2e_discovery_test_workflow",
    description="Test workflow for discovery",
    execution_mode="sync"
)
async def e2e_discovery_test_workflow(value: str):
    return {"value": value, "user": context.email}
'''
        # Use index=true to inject workflow ID into decorator
        response = e2e_client.put(
            "/api/files/editor/content?index=true",
            headers=platform_admin.headers,
            json={
                "path": "e2e_discovery_test.py",
                "content": workflow_content,
                "encoding": "utf-8",
            },
        )
        assert response.status_code == 200, f"Create workflow file failed: {response.text}"

        yield {"path": "e2e_discovery_test.py", "name": "e2e_discovery_test_workflow"}

        # Cleanup
        e2e_client.delete(
            "/api/files/editor?path=e2e_discovery_test.py",
            headers=platform_admin.headers,
        )

    def test_workflow_file_creates_workflow(self, e2e_client, platform_admin, test_workflow_file):
        """Workflow is discoverable after file creation."""

        def check_workflow():
            response = e2e_client.get(
                "/api/workflows",
                headers=platform_admin.headers,
            )
            if response.status_code != 200:
                return None
            workflows = response.json()
            workflow_names = [w["name"] for w in workflows]
            if test_workflow_file["name"] in workflow_names:
                return True
            return None

        workflow_found = poll_until(check_workflow, max_wait=30.0, interval=0.2)

        assert workflow_found, \
            f"Workflow {test_workflow_file['name']} not discovered after 30s"

    def test_workflow_has_parameters(self, e2e_client, platform_admin, test_workflow_file):
        """Discovered workflow includes parameters."""

        def check_workflow_with_params():
            response = e2e_client.get(
                "/api/workflows",
                headers=platform_admin.headers,
            )
            if response.status_code != 200:
                return None
            workflows = response.json()
            workflow = next(
                (w for w in workflows if w["name"] == test_workflow_file["name"]), None
            )
            if workflow and "parameters" in workflow:
                return workflow
            return None

        workflow = poll_until(check_workflow_with_params, max_wait=10.0, interval=0.2)

        assert workflow, f"Workflow {test_workflow_file['name']} with parameters not found"
        param_names = [p["name"] for p in workflow["parameters"]]
        assert "value" in param_names, "Missing 'value' parameter"
