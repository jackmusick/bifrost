"""
Unit tests for Bifrost Files SDK module.

Tests both platform mode (inside workflows) and external mode (CLI).
Uses mocked dependencies for fast, isolated testing.
"""

import os
import pytest
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, mock_open, patch, PropertyMock
from uuid import uuid4

from bifrost._context import set_execution_context, clear_execution_context


@pytest.fixture
def test_org_id():
    """Return a test organization ID."""
    return str(uuid4())


@pytest.fixture
def test_context(test_org_id):
    """Create execution context for platform mode testing."""
    from src.sdk.context import ExecutionContext, Organization

    org = Organization(id=test_org_id, name="Test Org", is_active=True)
    return ExecutionContext(
        user_id="test-user",
        email="test@example.com",
        name="Test User",
        scope=test_org_id,
        organization=org,
        is_platform_admin=False,
        is_function_key=False,
        execution_id="test-exec-123",
    )


class TestFilesPlatformMode:
    """Test files SDK methods in platform mode (inside workflows)."""

    @pytest.fixture(autouse=True)
    def cleanup_context(self):
        """Ensure context is cleared after each test."""
        yield
        clear_execution_context()

    @pytest.mark.asyncio
    async def test_read_text_file_from_workspace(self, test_context):
        """Test reading a text file from workspace location."""
        from bifrost import files

        set_execution_context(test_context)

        mock_content = "Hello, workspace!"
        mock_path = MagicMock(spec=Path)
        mock_file = mock_open(read_data=mock_content)

        with patch("bifrost.files.files._resolve_path", return_value=mock_path):
            with patch("builtins.open", mock_file):
                result = await files.read("data/test.txt", location="workspace")

        assert result == mock_content
        mock_file.assert_called_once_with(mock_path, "r", encoding="utf-8")

    @pytest.mark.asyncio
    async def test_read_text_file_from_temp(self, test_context):
        """Test reading a text file from temp location."""
        from bifrost import files

        set_execution_context(test_context)

        mock_content = "Temporary data"
        mock_path = MagicMock(spec=Path)
        mock_file = mock_open(read_data=mock_content)

        with patch("bifrost.files.files._resolve_path", return_value=mock_path):
            with patch("builtins.open", mock_file):
                result = await files.read("temp_file.txt", location="temp")

        assert result == mock_content

    @pytest.mark.asyncio
    async def test_read_from_uploads_location_uses_s3(self, test_context):
        """Test reading from uploads location uses S3 in platform mode."""
        from bifrost import files

        set_execution_context(test_context)

        mock_content = b"Uploaded file content"

        with patch("bifrost.files._read_from_s3", AsyncMock(return_value=mock_content)):
            result = await files.read("uploads/form_id/uuid/file.txt", location="uploads")

        assert result == mock_content.decode("utf-8")

    @pytest.mark.asyncio
    async def test_read_from_uploads_raises_when_s3_not_configured(self, test_context):
        """Test reading from uploads raises error when S3 not configured."""
        from bifrost import files

        set_execution_context(test_context)

        with patch(
            "bifrost.files._read_from_s3",
            AsyncMock(side_effect=RuntimeError("S3 storage not configured - cannot read uploaded files"))
        ):
            with pytest.raises(
                RuntimeError, match="S3 storage not configured - cannot read uploaded files"
            ):
                await files.read("uploads/file.txt", location="uploads")

    @pytest.mark.asyncio
    async def test_read_from_s3_raises_file_not_found_on_no_such_key(self, test_context):
        """Test reading from S3 raises FileNotFoundError when key doesn't exist."""
        from bifrost import files

        set_execution_context(test_context)

        with patch(
            "bifrost.files._read_from_s3",
            AsyncMock(side_effect=FileNotFoundError("File not found in S3: uploads/missing.txt"))
        ):
            with pytest.raises(FileNotFoundError, match="File not found in S3"):
                await files.read("uploads/missing.txt", location="uploads")

    @pytest.mark.asyncio
    async def test_read_bytes_from_workspace(self, test_context):
        """Test reading binary data from workspace."""
        from bifrost import files

        set_execution_context(test_context)

        mock_content = b"\x89PNG\r\n\x1a\n"  # PNG header
        mock_path = MagicMock(spec=Path)
        mock_file = mock_open(read_data=mock_content)

        with patch("bifrost.files.files._resolve_path", return_value=mock_path):
            with patch("builtins.open", mock_file):
                result = await files.read_bytes("images/logo.png", location="workspace")

        assert result == mock_content
        mock_file.assert_called_once_with(mock_path, "rb")

    @pytest.mark.asyncio
    async def test_read_bytes_from_uploads_uses_s3(self, test_context):
        """Test reading binary data from uploads uses S3."""
        from bifrost import files

        set_execution_context(test_context)

        mock_content = b"\x89PNG\r\n\x1a\n"

        with patch("bifrost.files._read_from_s3", AsyncMock(return_value=mock_content)):
            result = await files.read_bytes("uploads/image.png", location="uploads")

        assert result == mock_content

    @pytest.mark.asyncio
    async def test_write_text_file_to_workspace(self, test_context):
        """Test writing text to workspace location."""
        from bifrost import files

        set_execution_context(test_context)

        mock_path = MagicMock(spec=Path)
        mock_path.parent = MagicMock(spec=Path)
        mock_file = mock_open()

        with patch("bifrost.files.files._resolve_path", return_value=mock_path):
            with patch("builtins.open", mock_file):
                await files.write("output/report.txt", "Report data", location="workspace")

        # Verify parent directory creation
        mock_path.parent.mkdir.assert_called_once_with(parents=True, exist_ok=True)
        # Verify file was written
        mock_file.assert_called_once_with(mock_path, "w", encoding="utf-8")
        handle = mock_file()
        handle.write.assert_called_once_with("Report data")

    @pytest.mark.asyncio
    async def test_write_text_creates_parent_directories(self, test_context):
        """Test that write creates parent directories if they don't exist."""
        from bifrost import files

        set_execution_context(test_context)

        mock_path = MagicMock(spec=Path)
        mock_path.parent = MagicMock(spec=Path)
        mock_file = mock_open()

        with patch("bifrost.files.files._resolve_path", return_value=mock_path):
            with patch("builtins.open", mock_file):
                await files.write(
                    "deeply/nested/path/file.txt", "content", location="workspace"
                )

        # Verify mkdir was called with parents=True, exist_ok=True
        mock_path.parent.mkdir.assert_called_once_with(parents=True, exist_ok=True)

    @pytest.mark.asyncio
    async def test_write_bytes_to_temp(self, test_context):
        """Test writing binary data to temp location."""
        from bifrost import files

        set_execution_context(test_context)

        binary_data = b"\x89PNG\r\n\x1a\n"
        mock_path = MagicMock(spec=Path)
        mock_path.parent = MagicMock(spec=Path)
        mock_file = mock_open()

        with patch("bifrost.files.files._resolve_path", return_value=mock_path):
            with patch("builtins.open", mock_file):
                await files.write_bytes("temp_image.png", binary_data, location="temp")

        # Verify file was opened in binary write mode
        mock_file.assert_called_once_with(mock_path, "wb")
        # Verify content was written
        handle = mock_file()
        handle.write.assert_called_once_with(binary_data)

    @pytest.mark.asyncio
    async def test_list_directory_in_workspace(self, test_context):
        """Test listing files in workspace directory."""
        from bifrost import files

        set_execution_context(test_context)

        mock_path = MagicMock(spec=Path)
        mock_path.exists.return_value = True
        mock_path.is_dir.return_value = True

        # Create proper mock items with name attribute
        mock_item1 = MagicMock(spec=Path)
        mock_item1.name = "file1.txt"
        mock_item2 = MagicMock(spec=Path)
        mock_item2.name = "file2.csv"
        mock_item3 = MagicMock(spec=Path)
        mock_item3.name = "subdir"

        mock_path.iterdir.return_value = [mock_item1, mock_item2, mock_item3]

        with patch("bifrost.files.files._resolve_path", return_value=mock_path):
            result = await files.list("data", location="workspace")

        assert result == ["file1.txt", "file2.csv", "subdir"]

    @pytest.mark.asyncio
    async def test_list_raises_error_when_directory_not_found(self, test_context):
        """Test list raises FileNotFoundError when directory doesn't exist."""
        from bifrost import files

        set_execution_context(test_context)

        mock_path = MagicMock(spec=Path)
        mock_path.exists.return_value = False

        with patch("bifrost.files.files._resolve_path", return_value=mock_path):
            with pytest.raises(FileNotFoundError, match="Directory not found"):
                await files.list("nonexistent", location="workspace")

    @pytest.mark.asyncio
    async def test_list_raises_error_when_path_is_file(self, test_context):
        """Test list raises ValueError when path is a file, not directory."""
        from bifrost import files

        set_execution_context(test_context)

        mock_path = MagicMock(spec=Path)
        mock_path.exists.return_value = True
        mock_path.is_dir.return_value = False

        with patch("bifrost.files.files._resolve_path", return_value=mock_path):
            with pytest.raises(ValueError, match="Not a directory"):
                await files.list("file.txt", location="workspace")

    @pytest.mark.asyncio
    async def test_delete_file_from_workspace(self, test_context):
        """Test deleting a file from workspace."""
        from bifrost import files

        set_execution_context(test_context)

        mock_path = MagicMock(spec=Path)
        mock_path.exists.return_value = True
        mock_path.is_dir.return_value = False

        with patch("bifrost.files.files._resolve_path", return_value=mock_path):
            await files.delete("old_file.txt", location="workspace")

        mock_path.unlink.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_directory_from_temp(self, test_context):
        """Test deleting a directory from temp location."""
        from bifrost import files

        set_execution_context(test_context)

        mock_path = MagicMock(spec=Path)
        mock_path.exists.return_value = True
        mock_path.is_dir.return_value = True

        with patch("bifrost.files.files._resolve_path", return_value=mock_path):
            with patch("bifrost.files.shutil.rmtree") as mock_rmtree:
                await files.delete("old_dir", location="temp")

        mock_rmtree.assert_called_once_with(mock_path)

    @pytest.mark.asyncio
    async def test_delete_raises_error_when_path_not_found(self, test_context):
        """Test delete raises FileNotFoundError when path doesn't exist."""
        from bifrost import files

        set_execution_context(test_context)

        mock_path = MagicMock(spec=Path)
        mock_path.exists.return_value = False

        with patch("bifrost.files.files._resolve_path", return_value=mock_path):
            with pytest.raises(FileNotFoundError, match="Path not found"):
                await files.delete("missing.txt", location="workspace")

    @pytest.mark.asyncio
    async def test_exists_returns_true_when_file_exists(self, test_context):
        """Test exists returns True when file exists."""
        from bifrost import files

        set_execution_context(test_context)

        mock_path = MagicMock(spec=Path)
        mock_path.exists.return_value = True

        with patch("bifrost.files.files._resolve_path", return_value=mock_path):
            result = await files.exists("data/file.txt", location="workspace")

        assert result is True

    @pytest.mark.asyncio
    async def test_exists_returns_false_when_file_not_found(self, test_context):
        """Test exists returns False when file doesn't exist."""
        from bifrost import files

        set_execution_context(test_context)

        mock_path = MagicMock(spec=Path)
        mock_path.exists.return_value = False

        with patch("bifrost.files.files._resolve_path", return_value=mock_path):
            result = await files.exists("missing.txt", location="workspace")

        assert result is False

    @pytest.mark.asyncio
    async def test_exists_returns_false_on_invalid_path(self, test_context):
        """Test exists returns False when path validation fails."""
        from bifrost import files

        set_execution_context(test_context)

        with patch(
            "bifrost.files.files._resolve_path",
            side_effect=ValueError("Invalid path"),
        ):
            result = await files.exists("../../etc/passwd", location="workspace")

        assert result is False

    @pytest.mark.asyncio
    async def test_resolve_path_prevents_directory_traversal(self, test_context):
        """Test that _resolve_path prevents directory traversal attacks."""
        from bifrost.files import files

        set_execution_context(test_context)

        # Test various directory traversal attempts
        malicious_paths = [
            "../../etc/passwd",
            "../../../etc/passwd",
            "data/../../etc/passwd",
        ]

        for malicious_path in malicious_paths:
            with pytest.raises(ValueError, match="Path must be within"):
                # Need to create actual temp directories for this test
                with patch("pathlib.Path.exists", return_value=True):
                    files._resolve_path(malicious_path, "workspace")

    @pytest.mark.asyncio
    async def test_workspace_location_uses_correct_base_dir(self, test_context):
        """Test that workspace location uses /tmp/bifrost/workspace."""
        from bifrost.files import files

        set_execution_context(test_context)

        # Just verify the constant is set correctly
        assert str(files.WORKSPACE_FILES_DIR) == "/tmp/bifrost/workspace"

    @pytest.mark.asyncio
    async def test_temp_location_uses_correct_base_dir(self, test_context):
        """Test that temp location uses /tmp/bifrost/tmp."""
        from bifrost.files import files

        set_execution_context(test_context)

        # Just verify the constant is set correctly
        assert str(files.TEMP_FILES_DIR) == "/tmp/bifrost/tmp"


class TestFilesExternalMode:
    """Test files SDK methods in external mode (CLI with local filesystem)."""

    @pytest.fixture(autouse=True)
    def clear_context(self):
        """Ensure no platform context."""
        clear_execution_context()
        yield

    @pytest.mark.asyncio
    async def test_read_text_from_workspace_uses_cwd(self):
        """Test reading text file from workspace uses CWD in external mode."""
        from bifrost import files

        mock_content = "Local file content"
        mock_path = MagicMock(spec=Path)
        mock_path.exists.return_value = True
        mock_file = mock_open(read_data=mock_content)

        with patch("bifrost.files._resolve_local_path", return_value=mock_path):
            with patch("builtins.open", mock_file):
                result = await files.read("data/file.txt", location="workspace")

        assert result == mock_content

    @pytest.mark.asyncio
    async def test_read_text_from_temp_uses_temp_dir(self):
        """Test reading text file from temp uses /tmp/bifrost-tmp."""
        from bifrost import files

        mock_content = "Temp file"
        mock_path = MagicMock(spec=Path)
        mock_path.exists.return_value = True
        mock_file = mock_open(read_data=mock_content)

        with patch("bifrost.files._resolve_local_path", return_value=mock_path):
            with patch("builtins.open", mock_file):
                result = await files.read("temp.txt", location="temp")

        assert result == mock_content

    @pytest.mark.asyncio
    async def test_read_from_uploads_uses_local_temp(self):
        """Test reading from uploads uses /tmp/bifrost-uploads in external mode."""
        from bifrost import files

        mock_content = "Uploaded locally"
        mock_path = MagicMock(spec=Path)
        mock_path.exists.return_value = True
        mock_file = mock_open(read_data=mock_content)

        with patch("bifrost.files._resolve_local_path", return_value=mock_path):
            with patch("builtins.open", mock_file):
                result = await files.read("file.txt", location="uploads")

        assert result == mock_content

    @pytest.mark.asyncio
    async def test_read_raises_file_not_found_in_external_mode(self):
        """Test read raises FileNotFoundError when file doesn't exist."""
        from bifrost import files

        mock_path = MagicMock(spec=Path)
        mock_path.exists.return_value = False

        with patch("bifrost.files._resolve_local_path", return_value=mock_path):
            with pytest.raises(FileNotFoundError, match="File not found"):
                await files.read("missing.txt", location="workspace")

    @pytest.mark.asyncio
    async def test_read_bytes_from_workspace_in_external_mode(self):
        """Test reading binary file from workspace in external mode."""
        from bifrost import files

        mock_content = b"\x89PNG\r\n\x1a\n"
        mock_path = MagicMock(spec=Path)
        mock_path.exists.return_value = True
        mock_file = mock_open(read_data=mock_content)

        with patch("bifrost.files._resolve_local_path", return_value=mock_path):
            with patch("builtins.open", mock_file):
                result = await files.read_bytes("image.png", location="workspace")

        assert result == mock_content

    @pytest.mark.asyncio
    async def test_write_text_to_workspace_in_external_mode(self):
        """Test writing text to workspace in external mode."""
        from bifrost import files

        mock_path = MagicMock(spec=Path)
        mock_path.parent = MagicMock(spec=Path)
        mock_file = mock_open()

        with patch("bifrost.files._resolve_local_path", return_value=mock_path):
            with patch("builtins.open", mock_file):
                await files.write("output.txt", "data", location="workspace")

        handle = mock_file()
        handle.write.assert_called_once_with("data")

    @pytest.mark.asyncio
    async def test_write_creates_parent_dirs_in_external_mode(self):
        """Test write creates parent directories in external mode."""
        from bifrost import files

        mock_path = MagicMock(spec=Path)
        mock_path.parent = MagicMock(spec=Path)
        mock_file = mock_open()

        with patch("bifrost.files._resolve_local_path", return_value=mock_path):
            with patch("builtins.open", mock_file):
                await files.write("nested/path/file.txt", "content", location="workspace")

        mock_path.parent.mkdir.assert_called_once_with(parents=True, exist_ok=True)

    @pytest.mark.asyncio
    async def test_write_bytes_to_temp_in_external_mode(self):
        """Test writing binary data to temp in external mode."""
        from bifrost import files

        binary_data = b"\x00\x01\x02"
        mock_path = MagicMock(spec=Path)
        mock_path.parent = MagicMock(spec=Path)
        mock_file = mock_open()

        with patch("bifrost.files._resolve_local_path", return_value=mock_path):
            with patch("builtins.open", mock_file):
                await files.write_bytes("binary.dat", binary_data, location="temp")

        handle = mock_file()
        handle.write.assert_called_once_with(binary_data)

    @pytest.mark.asyncio
    async def test_list_directory_in_external_mode(self):
        """Test listing directory in external mode."""
        from bifrost import files

        mock_path = MagicMock(spec=Path)
        mock_path.exists.return_value = True
        mock_path.is_dir.return_value = True

        # Create proper mock items with name attribute
        mock_item1 = MagicMock(spec=Path)
        mock_item1.name = "file1.txt"
        mock_item2 = MagicMock(spec=Path)
        mock_item2.name = "file2.txt"

        mock_path.iterdir.return_value = [mock_item1, mock_item2]

        with patch("bifrost.files._resolve_local_path", return_value=mock_path):
            result = await files.list("data", location="workspace")

        assert result == ["file1.txt", "file2.txt"]

    @pytest.mark.asyncio
    async def test_delete_file_in_external_mode(self):
        """Test deleting file in external mode."""
        from bifrost import files

        mock_path = MagicMock(spec=Path)
        mock_path.exists.return_value = True
        mock_path.is_dir.return_value = False

        with patch("bifrost.files._resolve_local_path", return_value=mock_path):
            await files.delete("file.txt", location="workspace")

        mock_path.unlink.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_directory_in_external_mode(self):
        """Test deleting directory in external mode."""
        from bifrost import files

        mock_path = MagicMock(spec=Path)
        mock_path.exists.return_value = True
        mock_path.is_dir.return_value = True

        with patch("bifrost.files._resolve_local_path", return_value=mock_path):
            with patch("bifrost.files.shutil.rmtree") as mock_rmtree:
                await files.delete("old_dir", location="temp")

        mock_rmtree.assert_called_once_with(mock_path)

    @pytest.mark.asyncio
    async def test_exists_returns_true_in_external_mode(self):
        """Test exists returns True in external mode."""
        from bifrost import files

        mock_path = MagicMock(spec=Path)
        mock_path.exists.return_value = True

        with patch("bifrost.files._resolve_local_path", return_value=mock_path):
            result = await files.exists("file.txt", location="workspace")

        assert result is True

    @pytest.mark.asyncio
    async def test_exists_returns_false_in_external_mode(self):
        """Test exists returns False in external mode."""
        from bifrost import files

        mock_path = MagicMock(spec=Path)
        mock_path.exists.return_value = False

        with patch("bifrost.files._resolve_local_path", return_value=mock_path):
            result = await files.exists("missing.txt", location="workspace")

        assert result is False

    @pytest.mark.asyncio
    async def test_external_mode_prevents_directory_traversal(self):
        """Test that external mode prevents directory traversal attacks."""
        from bifrost.files import _resolve_local_path

        malicious_paths = [
            "../../etc/passwd",
            "../../../etc/passwd",
        ]

        for malicious_path in malicious_paths:
            with pytest.raises(ValueError, match="Path must be within"):
                _resolve_local_path(malicious_path, "workspace")

    @pytest.mark.asyncio
    async def test_external_mode_rejects_absolute_paths(self):
        """Test that external mode rejects absolute paths."""
        from bifrost.files import _resolve_local_path

        with pytest.raises(ValueError, match="Absolute paths not allowed"):
            _resolve_local_path("/etc/passwd", "workspace")

    @pytest.mark.asyncio
    async def test_get_local_base_dir_workspace_returns_cwd(self):
        """Test that workspace location returns CWD in external mode."""
        from bifrost.files import _get_local_base_dir

        mock_cwd = "/home/user/project"

        with patch("os.getcwd", return_value=mock_cwd):
            base_dir = _get_local_base_dir("workspace")

        assert str(base_dir) == mock_cwd

    @pytest.mark.asyncio
    async def test_get_local_base_dir_temp_returns_temp_path(self):
        """Test that temp location returns /tmp/bifrost-tmp."""
        from bifrost.files import _get_local_base_dir

        with patch("tempfile.gettempdir", return_value="/tmp"):
            base_dir = _get_local_base_dir("temp")

        assert str(base_dir) == "/tmp/bifrost-tmp"

    @pytest.mark.asyncio
    async def test_get_local_base_dir_uploads_returns_uploads_path(self):
        """Test that uploads location returns /tmp/bifrost-uploads."""
        from bifrost.files import _get_local_base_dir

        with patch("tempfile.gettempdir", return_value="/tmp"):
            base_dir = _get_local_base_dir("uploads")

        assert str(base_dir) == "/tmp/bifrost-uploads"


class TestFilesContextDetection:
    """Test that files SDK correctly detects platform vs external mode."""

    def test_is_platform_context_true_when_context_set(self):
        """Test _is_platform_context() returns True when context is set."""
        from bifrost.files import _is_platform_context
        from src.sdk.context import ExecutionContext, Organization

        org = Organization(id="test-org", name="Test", is_active=True)
        context = ExecutionContext(
            user_id="user",
            email="user@test.com",
            name="User",
            scope="test-org",
            organization=org,
            is_platform_admin=False,
            is_function_key=False,
            execution_id="exec-123",
        )

        try:
            set_execution_context(context)
            assert _is_platform_context() is True
        finally:
            clear_execution_context()

    def test_is_platform_context_false_when_no_context(self):
        """Test _is_platform_context() returns False when no context."""
        from bifrost.files import _is_platform_context

        clear_execution_context()
        assert _is_platform_context() is False


class TestFilesPathSandboxing:
    """Test path sandboxing and security features."""

    @pytest.mark.asyncio
    async def test_workspace_cannot_access_temp_files(self):
        """Test that workspace location cannot access temp files via path traversal."""
        from bifrost.files import files
        from src.sdk.context import ExecutionContext, Organization

        org = Organization(id="test-org", name="Test", is_active=True)
        context = ExecutionContext(
            user_id="user",
            email="user@test.com",
            name="User",
            scope="test-org",
            organization=org,
            is_platform_admin=False,
            is_function_key=False,
            execution_id="exec-123",
        )

        try:
            set_execution_context(context)

            # Try to access temp directory from workspace location - should fail
            with pytest.raises(ValueError, match="Path must be within workspace"):
                with patch("pathlib.Path.exists", return_value=True):
                    files._resolve_path("../../tmp/secret.txt", "workspace")
        finally:
            clear_execution_context()

    @pytest.mark.asyncio
    async def test_temp_cannot_access_workspace_files(self):
        """Test that temp location cannot access workspace files via path traversal."""
        from bifrost.files import files
        from src.sdk.context import ExecutionContext, Organization

        org = Organization(id="test-org", name="Test", is_active=True)
        context = ExecutionContext(
            user_id="user",
            email="user@test.com",
            name="User",
            scope="test-org",
            organization=org,
            is_platform_admin=False,
            is_function_key=False,
            execution_id="exec-123",
        )

        try:
            set_execution_context(context)

            # Try to access workspace directory from temp location - should fail
            with pytest.raises(ValueError, match="Path must be within temp"):
                with patch("pathlib.Path.exists", return_value=True):
                    files._resolve_path("../../workspace/data.txt", "temp")
        finally:
            clear_execution_context()
