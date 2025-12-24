"""
Integration tests for workspace reindexing and orphaned workflow reconciliation.

Tests that orphaned workflows (those whose source files no longer exist)
are properly marked as inactive during workspace reindexing.
"""

import pytest
import pytest_asyncio
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import Workflow, DataProvider, WorkspaceFile, Execution
from src.models.enums import GitStatus
from src.services.file_storage_service import FileStorageService


# Use hardcoded test workspace path for isolation
TEST_WORKSPACE = Path("/tmp/bifrost/test_workspace_reindex")


@pytest_asyncio.fixture
async def clean_workspace():
    """Create a clean test workspace directory."""
    import shutil

    # Clean before test
    if TEST_WORKSPACE.exists():
        shutil.rmtree(TEST_WORKSPACE)
    TEST_WORKSPACE.mkdir(parents=True, exist_ok=True)

    yield TEST_WORKSPACE

    # Clean after test
    if TEST_WORKSPACE.exists():
        shutil.rmtree(TEST_WORKSPACE)


@pytest_asyncio.fixture
async def clean_tables(db_session: AsyncSession):
    """Clean up test data from tables before and after test."""
    # Clean before test - delete executions first to avoid FK constraint violations
    await db_session.execute(delete(Execution))
    await db_session.execute(delete(Workflow))
    await db_session.execute(delete(DataProvider))
    await db_session.execute(delete(WorkspaceFile))
    await db_session.commit()

    yield

    # Clean after test - delete executions first to avoid FK constraint violations
    await db_session.execute(delete(Execution))
    await db_session.execute(delete(Workflow))
    await db_session.execute(delete(DataProvider))
    await db_session.execute(delete(WorkspaceFile))
    await db_session.commit()


@pytest.mark.integration
@pytest.mark.asyncio
class TestReindexWorkspaceFiles:
    """Integration tests for reindex_workspace_files."""

    async def test_orphaned_workflow_marked_inactive(
        self,
        db_session: AsyncSession,
        clean_workspace: Path,
        clean_tables,
    ):
        """
        Workflows whose source files no longer exist are marked inactive.
        """
        workspace = clean_workspace

        # 1. Create a workflow file
        workflow_file = workspace / "my_workflow.py"
        workflow_file.write_text("""
from bifrost import workflow

@workflow(name="Test Workflow")
def test_workflow():
    pass
""")

        # 2. Create a workflow record in DB that references a non-existent file
        orphaned_workflow = Workflow(
            id=uuid4(),
            name="Orphaned Workflow",
            function_name="orphaned_func",
            file_path="orphaned_workflow.py",  # This file doesn't exist
            is_active=True,
        )
        db_session.add(orphaned_workflow)
        await db_session.commit()
        orphaned_id = orphaned_workflow.id

        # 3. Call reindex_workspace_files
        storage = FileStorageService(db_session)
        counts = await storage.reindex_workspace_files(workspace)
        await db_session.commit()

        # 4. Verify the orphaned workflow is now inactive
        result = await db_session.execute(
            select(Workflow).where(Workflow.id == orphaned_id)
        )
        workflow = result.scalar_one()
        assert workflow.is_active is False

        # 5. Verify the existing workflow was indexed and is active
        result = await db_session.execute(
            select(Workflow).where(Workflow.file_path == "my_workflow.py")
        )
        indexed_workflow = result.scalar_one_or_none()
        assert indexed_workflow is not None
        assert indexed_workflow.is_active is True

        # 6. Verify counts
        assert counts["files_indexed"] == 1
        assert counts["workflows_deactivated"] == 1

    async def test_orphaned_data_provider_marked_inactive(
        self,
        db_session: AsyncSession,
        clean_workspace: Path,
        clean_tables,
    ):
        """
        Data providers whose source files no longer exist are marked inactive.
        """
        workspace = clean_workspace

        # 1. Create a data provider file
        provider_file = workspace / "my_provider.py"
        provider_file.write_text("""
from bifrost import data_provider

@data_provider(name="Test Provider")
def test_provider():
    return []
""")

        # 2. Create a data provider record in DB that references a non-existent file
        orphaned_provider = DataProvider(
            id=uuid4(),
            name="Orphaned Provider",
            function_name="orphaned_func",
            file_path="orphaned_provider.py",  # This file doesn't exist
            is_active=True,
        )
        db_session.add(orphaned_provider)
        await db_session.commit()
        orphaned_id = orphaned_provider.id

        # 3. Call reindex_workspace_files
        storage = FileStorageService(db_session)
        counts = await storage.reindex_workspace_files(workspace)
        await db_session.commit()

        # 4. Verify the orphaned data provider is now inactive
        result = await db_session.execute(
            select(DataProvider).where(DataProvider.id == orphaned_id)
        )
        provider = result.scalar_one()
        assert provider.is_active is False

        # 5. Verify counts
        assert counts["data_providers_deactivated"] == 1

    async def test_workspace_files_table_updated(
        self,
        db_session: AsyncSession,
        clean_workspace: Path,
        clean_tables,
    ):
        """
        workspace_files table is updated to match actual files.
        """
        workspace = clean_workspace

        # 1. Create a workspace file record for a non-existent file
        orphaned_file = WorkspaceFile(
            path="orphaned_file.py",
            content_hash="abc123",
            size_bytes=100,
            content_type="text/x-python",
            git_status=GitStatus.SYNCED,
            is_deleted=False,
        )
        db_session.add(orphaned_file)
        await db_session.commit()

        # 2. Create an actual file
        real_file = workspace / "real_file.py"
        real_file.write_text("# Real file content")

        # 3. Call reindex_workspace_files
        storage = FileStorageService(db_session)
        counts = await storage.reindex_workspace_files(workspace)
        await db_session.commit()

        # 4. Verify the orphaned file record is marked as deleted
        result = await db_session.execute(
            select(WorkspaceFile).where(WorkspaceFile.path == "orphaned_file.py")
        )
        orphaned = result.scalar_one()
        assert orphaned.is_deleted is True
        assert orphaned.git_status == GitStatus.DELETED

        # 5. Verify the real file is indexed
        result = await db_session.execute(
            select(WorkspaceFile).where(WorkspaceFile.path == "real_file.py")
        )
        real = result.scalar_one()
        assert real.is_deleted is False
        assert real.git_status == GitStatus.SYNCED

        # 6. Verify counts
        assert counts["files_indexed"] == 1
        assert counts["files_removed"] == 1

    async def test_empty_workspace_deactivates_all(
        self,
        db_session: AsyncSession,
        clean_workspace: Path,
        clean_tables,
    ):
        """
        Empty workspace results in all workflows being deactivated.
        """
        workspace = clean_workspace  # Empty directory

        # 1. Create some active workflows
        for i in range(3):
            workflow = Workflow(
                id=uuid4(),
                name=f"Workflow {i}",
                function_name=f"workflow_{i}",
                file_path=f"workflow_{i}.py",
                is_active=True,
            )
            db_session.add(workflow)
        await db_session.commit()

        # 2. Call reindex_workspace_files
        storage = FileStorageService(db_session)
        counts = await storage.reindex_workspace_files(workspace)
        await db_session.commit()

        # 3. Verify all workflows are now inactive
        result = await db_session.execute(
            select(Workflow).where(Workflow.is_active == True)  # noqa: E712
        )
        active_workflows = result.scalars().all()
        assert len(active_workflows) == 0

        # 4. Verify counts
        assert counts["files_indexed"] == 0
        assert counts["workflows_deactivated"] == 3

    async def test_metadata_extraction_updates_workflow(
        self,
        db_session: AsyncSession,
        clean_workspace: Path,
        clean_tables,
    ):
        """
        Workflow metadata is extracted from Python files during reindex.
        """
        workspace = clean_workspace

        # 1. Create a workflow file with specific metadata
        workflow_file = workspace / "documented_workflow.py"
        workflow_file.write_text("""
from bifrost import workflow

@workflow(
    name="Documented Workflow",
    description="A well-documented workflow",
    category="Testing",
    tags=["test", "example"],
)
def documented_workflow(message: str, count: int = 5):
    '''Process messages with count iterations.'''
    pass
""")

        # 2. Call reindex_workspace_files
        storage = FileStorageService(db_session)
        await storage.reindex_workspace_files(workspace)
        await db_session.commit()

        # 3. Verify workflow was created with correct metadata
        result = await db_session.execute(
            select(Workflow).where(Workflow.file_path == "documented_workflow.py")
        )
        workflow = result.scalar_one()

        assert workflow.name == "Documented Workflow"
        assert workflow.description == "A well-documented workflow"
        assert workflow.category == "Testing"
        assert workflow.is_active is True
        assert workflow.function_name == "documented_workflow"
        # Parameters should be extracted
        assert len(workflow.parameters_schema) == 2
