"""
Unit tests for FileStorageService.reindex_workspace_files().

Tests the reindexing of file_index entries and reconciliation of orphaned
workflows and data providers.
"""

import sys

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4


def clear_libcst_modules():
    """
    Clear libcst and dependent modules from sys.modules to get fresh parser state.

    This function clears the libcst module cache before importing FileStorageService
    to ensure the libcst parser is not in a corrupted state from previous tests.
    """
    # Remove all libcst modules from cache
    libcst_modules = [k for k in list(sys.modules.keys()) if k.startswith('libcst')]
    for mod in libcst_modules:
        del sys.modules[mod]

    # Also remove decorator_property_service to force reimport with fresh libcst
    service_key = 'src.services.decorator_property_service'
    if service_key in sys.modules:
        del sys.modules[service_key]

    # Remove file_storage to force reimport with fresh decorator_property_service
    storage_key = 'src.services.file_storage'
    if storage_key in sys.modules:
        del sys.modules[storage_key]

    # Also clear sub-modules
    for key in list(sys.modules.keys()):
        if key.startswith('src.services.file_storage'):
            del sys.modules[key]


@pytest.fixture
def mock_db():
    """Mock async database session."""
    db = AsyncMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    return db


@pytest.fixture
def temp_workspace(tmp_path):
    """Create a temporary workspace with test files."""
    # Create test directory structure
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    # Create some Python files with workflow decorators
    workflow_file = workspace / "workflows" / "my_workflow.py"
    workflow_file.parent.mkdir(parents=True, exist_ok=True)
    workflow_file.write_text("""
from bifrost import workflow

@workflow(id="12345678-1234-5678-1234-567812345678", name="Test Workflow", description="A test workflow")
def my_workflow():
    pass
""")

    # Create a data provider file
    provider_file = workspace / "providers" / "my_provider.py"
    provider_file.parent.mkdir(parents=True, exist_ok=True)
    provider_file.write_text("""
from bifrost import data_provider

@data_provider(id="87654321-4321-8765-4321-876543218765", name="Test Provider")
def my_provider():
    return []
""")

    # Create a regular Python file (no decorators)
    utils_file = workspace / "utils.py"
    utils_file.write_text("""
def helper():
    return "helper"
""")

    return workspace


class TestReindexWorkspaceFiles:
    """Tests for reindex_workspace_files method."""

    @pytest.mark.asyncio
    async def test_indexes_existing_files(self, mock_db, temp_workspace):
        """Files in the local workspace are indexed in file_index."""
        # Setup mock responses
        mock_db.execute.return_value = MagicMock(rowcount=0, scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[]))))

        # Clear modules first, THEN import
        clear_libcst_modules()
        from src.services.file_storage import FileStorageService
        storage = FileStorageService(mock_db)
        # Mock _extract_metadata on the reindex service (it holds the function reference)
        storage._reindex_service._extract_metadata = AsyncMock()
        counts = await storage.reindex_workspace_files(temp_workspace)

        # Should have indexed the files
        assert counts["files_indexed"] == 3  # workflow, provider, utils

    @pytest.mark.asyncio
    async def test_marks_missing_files_as_deleted(self, mock_db, temp_workspace):
        """Files in file_index but not on filesystem are removed."""
        # Mock that the update statement affects 2 rows
        mock_result = MagicMock()
        mock_result.rowcount = 2
        mock_result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))
        mock_db.execute.return_value = mock_result

        # Clear modules first, THEN import
        clear_libcst_modules()
        from src.services.file_storage import FileStorageService
        storage = FileStorageService(mock_db)
        # Mock _extract_metadata to avoid complex indexer logic in unit test
        storage._reindex_service._extract_metadata = AsyncMock()
        counts = await storage.reindex_workspace_files(temp_workspace)

        # files_removed should reflect the rowcount from the update
        assert counts["files_removed"] == 2

    @pytest.mark.asyncio
    async def test_marks_orphaned_workflows_inactive(self, mock_db, temp_workspace):
        """Workflows whose files no longer exist are marked inactive.

        NOTE: Data providers are now stored in the workflows table with type='data_provider'.
        The workflows_deactivated count includes data providers.
        data_providers_deactivated is kept for backward compatibility but is always 0.
        """
        # First execute returns rowcount for files_removed
        # Subsequent calls return workflow deactivation count
        mock_results = [
            MagicMock(rowcount=0, scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))),  # mark missing files
        ]
        # Add results for file upserts
        for _ in range(3):
            mock_results.append(MagicMock())

        # Add results for orphaned endpoint workflows query
        mock_results.append(MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))))

        # Add results for workflow deactivation (includes data providers now)
        mock_results.append(MagicMock(rowcount=7))  # 5 workflows + 2 data providers

        mock_db.execute.side_effect = mock_results

        # Clear modules first, THEN import
        clear_libcst_modules()
        from src.services.file_storage import FileStorageService
        storage = FileStorageService(mock_db)
        # Mock _extract_metadata to avoid complex AST parsing in unit test
        storage._reindex_service._extract_metadata = AsyncMock()

        counts = await storage.reindex_workspace_files(temp_workspace)

        # Workflows deactivation includes data providers (consolidated into workflows table)
        assert counts["workflows_deactivated"] == 7  # All executables in workflows table
        assert counts["data_providers_deactivated"] == 0  # Always 0 now (kept for compat)

    @pytest.mark.asyncio
    async def test_extracts_metadata_from_python_files(self, mock_db, temp_workspace):
        """Python files are parsed for workflow/data_provider decorators."""
        mock_db.execute.return_value = MagicMock(
            rowcount=0,
            scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))
        )

        # Clear modules first, THEN import
        clear_libcst_modules()
        from src.services.file_storage import FileStorageService
        storage = FileStorageService(mock_db)
        mock_extract = AsyncMock()
        storage._reindex_service._extract_metadata = mock_extract

        await storage.reindex_workspace_files(temp_workspace)

        # Should have called _extract_metadata for each Python file
        assert mock_extract.call_count == 3

    @pytest.mark.asyncio
    async def test_skips_excluded_paths(self, mock_db, temp_workspace):
        """Excluded paths (like __pycache__) are not indexed."""
        # Create an excluded directory
        pycache = temp_workspace / "__pycache__"
        pycache.mkdir()
        (pycache / "cached.pyc").write_bytes(b"fake bytecode")

        mock_db.execute.return_value = MagicMock(
            rowcount=0,
            scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))
        )

        # Clear modules first, THEN import
        clear_libcst_modules()
        from src.services.file_storage import FileStorageService
        storage = FileStorageService(mock_db)
        storage._reindex_service._extract_metadata = AsyncMock()

        counts = await storage.reindex_workspace_files(temp_workspace)

        # Should only index the 3 real files, not the pycache file
        assert counts["files_indexed"] == 3

    @pytest.mark.asyncio
    async def test_handles_empty_workspace(self, mock_db, tmp_path):
        """Empty workspace results in all workflows being deactivated.

        NOTE: Data providers are now stored in the workflows table with type='data_provider'.
        The workflows_deactivated count includes data providers.
        data_providers_deactivated is kept for backward compatibility but is always 0.
        """
        empty_workspace = tmp_path / "empty_workspace"
        empty_workspace.mkdir()

        # Mock: 0 files removed, 0 indexed, but 4 workflows deactivated (includes 1 data provider)
        mock_results = [
            MagicMock(rowcount=0),  # mark missing files
            MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))),  # orphaned endpoints
            MagicMock(rowcount=4),  # workflows deactivated (includes data providers)
        ]
        mock_db.execute.side_effect = mock_results

        # Clear modules first, THEN import
        clear_libcst_modules()
        from src.services.file_storage import FileStorageService
        storage = FileStorageService(mock_db)
        # Mock _extract_metadata to avoid complex indexer logic in unit test
        storage._reindex_service._extract_metadata = AsyncMock()
        counts = await storage.reindex_workspace_files(empty_workspace)

        assert counts["files_indexed"] == 0
        assert counts["workflows_deactivated"] == 4  # Includes data providers now
        assert counts["data_providers_deactivated"] == 0  # Always 0 now (kept for compat)

    @pytest.mark.asyncio
    async def test_cleans_up_orphaned_endpoints(self, mock_db, temp_workspace):
        """Endpoint-enabled workflows have their endpoints removed before deactivation."""
        # Create a mock orphaned workflow with endpoint_enabled
        mock_workflow = MagicMock()
        mock_workflow.name = "orphaned_endpoint_workflow"
        mock_workflow.id = uuid4()

        mock_results = [
            MagicMock(rowcount=0),  # mark missing files
        ]
        # Add results for file upserts
        for _ in range(3):
            mock_results.append(MagicMock())

        # Add result for orphaned endpoint workflows query - return our mock
        mock_results.append(MagicMock(
            scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[mock_workflow])))
        ))

        # Add results for workflow/data provider deactivation
        mock_results.append(MagicMock(rowcount=1))  # workflows
        mock_results.append(MagicMock(rowcount=0))  # data providers

        mock_db.execute.side_effect = mock_results

        # Clear modules first, THEN import
        clear_libcst_modules()
        with patch("src.services.openapi_endpoints.remove_workflow_endpoint") as mock_remove:
            with patch("src.main.app"):  # Mock the FastAPI app
                from src.services.file_storage import FileStorageService
                storage = FileStorageService(mock_db)
                storage._reindex_service._extract_metadata = AsyncMock()

                await storage.reindex_workspace_files(temp_workspace)

                # Should have called remove_workflow_endpoint
                mock_remove.assert_called_once_with(
                    pytest.importorskip("src.main").app,
                    "orphaned_endpoint_workflow"
                )

    @pytest.mark.asyncio
    async def test_handles_file_read_errors(self, mock_db, temp_workspace):
        """Files that can't be read are skipped without failing."""
        # Create a file we can't read by making it a directory with the same name
        # Actually, let's just patch read_bytes to fail for one file
        original_read_bytes = Path.read_bytes

        def mock_read_bytes(self):
            if "my_workflow.py" in str(self):
                raise OSError("Permission denied")
            return original_read_bytes(self)

        mock_db.execute.return_value = MagicMock(
            rowcount=0,
            scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))
        )

        # Clear modules first, THEN import
        clear_libcst_modules()
        with patch.object(Path, "read_bytes", mock_read_bytes):
            from src.services.file_storage import FileStorageService
            storage = FileStorageService(mock_db)
            storage._reindex_service._extract_metadata = AsyncMock()

            counts = await storage.reindex_workspace_files(temp_workspace)

        # Should have only indexed 2 files (skipped the one with error)
        assert counts["files_indexed"] == 2
