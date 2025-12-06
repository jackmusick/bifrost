"""
Integration tests for editor file operations.

Tests the file_operations.py module with actual file system operations.
"""

import pytest
import tempfile
import shutil
from pathlib import Path
from shared.editor.file_operations import (
    validate_and_resolve_path,
    list_directory,
    read_file,
    write_file,
)
from shared.models import FileType


class TestFileOperations:
    """Integration tests for file operations module"""

    @pytest.fixture
    def temp_home(self, monkeypatch):
        """Create a temporary /home directory for testing"""
        # Create temp directory to act as /home
        temp_dir = tempfile.mkdtemp(prefix="test_editor_home_")
        home_path = Path(temp_dir)

        # Monkeypatch get_base_path to use temp directory
        def mock_get_base_path() -> Path:
            return home_path

        monkeypatch.setattr(
            "shared.editor.file_operations.get_base_path",
            mock_get_base_path,
        )

        # Create some test files and folders
        (home_path / "workflows").mkdir(exist_ok=True)
        (home_path / "data_providers").mkdir(exist_ok=True)
        (home_path / "workflows" / "sync_users.py").write_text(
            "import bifrost\n\ndef run(context):\n    pass"
        )
        (home_path / "workflows" / "sync_orders.py").write_text(
            "import bifrost\n\ndef run(context):\n    pass"
        )
        (home_path / "data_providers" / "get_users.py").write_text(
            "import bifrost\n\ndef run(context, parameters):\n    return []"
        )

        yield {
            "temp_dir": temp_dir,
            "home_path": home_path,
        }

        # Cleanup
        shutil.rmtree(temp_dir, ignore_errors=True)

    def test_validate_and_resolve_path_valid(self, temp_home):
        """Test path validation with valid paths"""
        # Valid paths
        path = validate_and_resolve_path("workflows/sync_users.py")
        assert path.exists()
        assert path.name == "sync_users.py"

        # Root directory
        path = validate_and_resolve_path("")
        assert path.exists()
        assert path.is_dir()

    def test_validate_and_resolve_path_directory_traversal(self, temp_home):
        """Test path validation rejects directory traversal attempts"""
        # Attempt directory traversal
        with pytest.raises(ValueError, match="Path outside repository"):
            validate_and_resolve_path("../../../etc/passwd")

        with pytest.raises(ValueError, match="Path outside repository"):
            validate_and_resolve_path("workflows/../../etc/passwd")

    def test_list_directory_root(self, temp_home):
        """Test listing root directory"""
        files = list_directory("")

        # Should have 2 folders
        assert len(files) == 2
        folder_names = {f.name for f in files if f.type == FileType.FOLDER}
        assert "workflows" in folder_names
        assert "data_providers" in folder_names

        # Check folder properties
        workflows = [f for f in files if f.name == "workflows"][0]
        assert workflows.type == FileType.FOLDER
        assert workflows.size is None
        assert workflows.extension is None

    def test_list_directory_workflows(self, temp_home):
        """Test listing workflows directory"""
        files = list_directory("workflows")

        # Should have 2 Python files
        assert len(files) == 2
        file_names = {f.name for f in files}
        assert "sync_users.py" in file_names
        assert "sync_orders.py" in file_names

        # Check file properties
        sync_users = [f for f in files if f.name == "sync_users.py"][0]
        assert sync_users.type == FileType.FILE
        assert sync_users.extension == ".py"
        assert sync_users.size is not None
        assert sync_users.size > 0
        assert "workflows/sync_users.py" in sync_users.path

    def test_list_directory_not_found(self, temp_home):
        """Test listing non-existent directory"""
        with pytest.raises(FileNotFoundError):
            list_directory("non_existent_folder")

    def test_list_directory_file_not_dir(self, temp_home):
        """Test listing a file (not a directory) raises error"""
        with pytest.raises(ValueError, match="Not a directory"):
            list_directory("workflows/sync_users.py")

    async def test_read_file_success(self, temp_home):
        """Test reading file content"""
        response = await read_file("workflows/sync_users.py")

        assert response.path == "workflows/sync_users.py"
        assert "import bifrost" in response.content
        assert response.encoding == "utf-8"
        assert response.size > 0
        assert response.etag is not None
        assert len(response.etag) > 0
        assert response.modified is not None

    async def test_read_file_not_found(self, temp_home):
        """Test reading non-existent file"""
        with pytest.raises(FileNotFoundError):
            await read_file("workflows/non_existent.py")

    async def test_read_file_directory(self, temp_home):
        """Test reading a directory (not a file) raises error"""
        with pytest.raises(ValueError, match="Not a file"):
            await read_file("workflows")

    async def test_write_file_new(self, temp_home):
        """Test writing a new file"""
        home_path = temp_home["home_path"]

        content = "import bifrost\n\ndef run(context):\n    context.info('New workflow')"
        response = await write_file("workflows/new_workflow.py", content)

        assert response.path == "workflows/new_workflow.py"
        assert response.content == content
        assert response.encoding == "utf-8"
        assert response.size == len(content.encode("utf-8"))
        assert response.etag is not None

        # Verify file actually exists
        file_path = home_path / "workflows" / "new_workflow.py"
        assert file_path.exists()
        assert file_path.read_text() == content

    async def test_write_file_update_existing(self, temp_home):
        """Test updating an existing file"""
        home_path = temp_home["home_path"]

        # Read original content
        original = await read_file("workflows/sync_users.py")
        original_etag = original.etag

        # Write new content
        new_content = "import bifrost\n\ndef run(context):\n    context.info('Updated')"
        response = await write_file("workflows/sync_users.py", new_content)

        assert response.content == new_content
        assert response.etag != original_etag  # ETag should change

        # Verify file content
        file_path = home_path / "workflows" / "sync_users.py"
        assert file_path.read_text() == new_content

    async def test_write_file_creates_parent_directory(self, temp_home):
        """Test writing file creates parent directories"""
        home_path = temp_home["home_path"]

        content = "test content"
        response = await write_file("new_folder/subfolder/test.py", content)

        assert response.path == "new_folder/subfolder/test.py"

        # Verify directories and file exist
        file_path = home_path / "new_folder" / "subfolder" / "test.py"
        assert file_path.exists()
        assert file_path.read_text() == content

    async def test_write_file_atomic(self, temp_home):
        """Test atomic write behavior"""
        home_path = temp_home["home_path"]

        # Write file
        content = "test content"
        await write_file("workflows/atomic_test.py", content)

        # Verify temp file doesn't exist after write
        file_path = home_path / "workflows" / "atomic_test.py"
        temp_path = file_path.with_suffix(file_path.suffix + ".tmp")

        assert file_path.exists()
        assert not temp_path.exists()  # Temp file should be removed

    async def test_write_file_rejects_non_utf8_encoding(self, temp_home):
        """Test write_file rejects non-UTF-8 encoding"""
        with pytest.raises(ValueError, match="Only UTF-8 and base64 encodings are supported"):
            await write_file("workflows/test.py", "content", encoding="latin-1")


class TestBifrostTypesEndpoint:
    """Integration tests for bifrost types endpoint"""

    def test_bifrost_pyi_file_exists(self):
        """Test that bifrost.pyi file exists in stubs directory"""
        from pathlib import Path

        # Get the stubs path
        api_root = Path(__file__).parent.parent.parent
        stubs_path = api_root / "stubs" / "bifrost.pyi"

        assert stubs_path.exists(), f"bifrost.pyi should exist at {stubs_path}"
        assert stubs_path.is_file(), "bifrost.pyi should be a file"

    def test_bifrost_pyi_contains_expected_content(self):
        """Test that bifrost.pyi contains expected type definitions"""
        from pathlib import Path

        # Get the stubs path
        api_root = Path(__file__).parent.parent.parent
        stubs_path = api_root / "stubs" / "bifrost.pyi"

        content = stubs_path.read_text()

        # Check for key type definitions
        assert "class ExecutionContext" in content
        assert "def workflow(" in content
        assert "def param(" in content
        assert "def data_provider(" in content
        assert "class OAuthCredentials" in content
        # Check for SDK modules (now class-based)
        assert "class config:" in content
        assert "class oauth:" in content
        assert "def get(" in content  # config.get and oauth.get_token methods
        assert "@staticmethod" in content  # SDK methods use staticmethod

    def test_bifrost_pyi_is_valid_python_syntax(self):
        """Test that bifrost.pyi is valid Python syntax"""
        from pathlib import Path
        import ast

        # Get the stubs path
        api_root = Path(__file__).parent.parent.parent
        stubs_path = api_root / "stubs" / "bifrost.pyi"

        content = stubs_path.read_text()

        # Parse as Python to verify syntax
        try:
            ast.parse(content)
        except SyntaxError as e:
            pytest.fail(f"bifrost.pyi contains invalid Python syntax: {e}")
