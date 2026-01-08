"""
Integration tests for Git operations with Python modules.

Tests the git integration flow for modules:
1. Git push: Serialize modules from workspace_files.content to files
2. Git pull: Parse modules from files and upsert to workspace_files.content
3. Entity type transitions: module -> workflow and workflow -> module
4. Deleted file handling
"""

from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.orm.workspace import WorkspaceFile


@pytest.fixture(autouse=True)
def reset_redis_client():
    """Reset the Redis client singleton between tests to avoid event loop issues."""
    import src.core.redis_client as redis_module

    # Reset before test
    redis_module._redis_client = None
    yield
    # Reset after test
    redis_module._redis_client = None


@pytest.mark.integration
class TestGitModuleSerialization:
    """Tests for serializing modules from DB to workspace files during git push."""

    @pytest_asyncio.fixture
    async def module_in_db(self, db_session: AsyncSession):
        """Create a test module in the database."""
        module = WorkspaceFile(
            path="shared/helpers.py",
            content='HELPER_VALUE = "from_database"\ndef helper_func(): return 42',
            content_hash="abc123",
            size_bytes=60,
            content_type="text/x-python",
            entity_type="module",
            is_deleted=False,
        )
        db_session.add(module)
        await db_session.commit()
        await db_session.refresh(module)

        yield module

        # Cleanup
        await db_session.delete(module)
        await db_session.commit()

    @pytest.mark.asyncio
    async def test_serialize_modules_includes_module_files(
        self, db_session: AsyncSession, module_in_db: WorkspaceFile, tmp_path: Path
    ):
        """Test that _serialize_platform_entities_to_workspace includes modules."""
        from src.services.git_integration import GitIntegrationService

        # Create service with workspace pointing to tmp_path
        service = GitIntegrationService()
        service.workspace_path = tmp_path

        # Run serialization - pass session to avoid event loop issues in tests
        serialized_paths = await service._serialize_platform_entities_to_workspace(
            session=db_session
        )

        # Verify module was serialized
        assert "shared/helpers.py" in serialized_paths

        # Verify file content
        file_path = tmp_path / "shared" / "helpers.py"
        assert file_path.exists()
        content = file_path.read_text()
        assert 'HELPER_VALUE = "from_database"' in content

    @pytest.mark.asyncio
    async def test_serialize_modules_excludes_deleted(
        self, db_session: AsyncSession, tmp_path: Path
    ):
        """Test that deleted modules are not serialized."""
        # Create a deleted module
        deleted_module = WorkspaceFile(
            path="deleted_module.py",
            content="# deleted content",
            content_hash="deleted",
            size_bytes=20,
            content_type="text/x-python",
            entity_type="module",
            is_deleted=True,
        )
        db_session.add(deleted_module)
        await db_session.commit()

        try:
            from src.services.git_integration import GitIntegrationService

            service = GitIntegrationService()
            service.workspace_path = tmp_path

            # Pass session to avoid event loop issues in tests
            serialized_paths = await service._serialize_platform_entities_to_workspace(
                session=db_session
            )

            # Verify deleted module was not serialized
            assert "deleted_module.py" not in serialized_paths
            assert not (tmp_path / "deleted_module.py").exists()

        finally:
            await db_session.delete(deleted_module)
            await db_session.commit()


@pytest.mark.integration
class TestGitModuleParsing:
    """Tests for parsing modules from files to DB during git pull."""

    @pytest.mark.asyncio
    async def test_parse_python_file_creates_module(
        self, db_session: AsyncSession, tmp_path: Path
    ):
        """Test that _parse_python_file creates a module entry for non-workflow Python files."""
        from src.services.git_integration import GitIntegrationService
        from src.services.decorator_property_service import DecoratorPropertyService

        # Create a module file (no @workflow decorator)
        module_path = tmp_path / "utils" / "helpers.py"
        module_path.parent.mkdir(parents=True)
        module_content = '''
def calculate_total(items):
    """Calculate total of items."""
    return sum(items)

CONSTANT_VALUE = 100
'''
        module_path.write_text(module_content)

        service = GitIntegrationService()
        service.workspace_path = tmp_path
        decorator_service = DecoratorPropertyService()

        # Parse the file
        await service._parse_python_file(
            db_session, "utils/helpers.py", module_path, decorator_service
        )
        await db_session.commit()

        # Verify module was created in workspace_files
        stmt = select(WorkspaceFile).where(WorkspaceFile.path == "utils/helpers.py")
        result = await db_session.execute(stmt)
        ws_file = result.scalar_one_or_none()

        assert ws_file is not None
        assert ws_file.entity_type == "module"
        assert ws_file.content == module_content
        assert ws_file.is_deleted is False

    @pytest.mark.asyncio
    async def test_parse_python_file_detects_workflow(
        self, db_session: AsyncSession, tmp_path: Path
    ):
        """Test that _parse_python_file detects workflow files correctly."""
        from src.services.git_integration import GitIntegrationService
        from src.services.decorator_property_service import DecoratorPropertyService

        # Create a workflow file (has @workflow decorator)
        workflow_path = tmp_path / "workflows" / "my_workflow.py"
        workflow_path.parent.mkdir(parents=True)
        workflow_content = '''from bifrost import workflow

@workflow(name="Test Workflow")
async def my_workflow(params: dict):
    """Test workflow."""
    return {"status": "success"}
'''
        workflow_path.write_text(workflow_content)

        service = GitIntegrationService()
        service.workspace_path = tmp_path
        decorator_service = DecoratorPropertyService()

        # Parse the file
        await service._parse_python_file(
            db_session, "workflows/my_workflow.py", workflow_path, decorator_service
        )
        await db_session.commit()

        # Verify workspace_files entry has entity_type="workflow"
        stmt = select(WorkspaceFile).where(WorkspaceFile.path == "workflows/my_workflow.py")
        result = await db_session.execute(stmt)
        ws_file = result.scalar_one_or_none()

        assert ws_file is not None
        assert ws_file.entity_type == "workflow"
        # Workflows don't store content in workspace_files.content
        assert ws_file.content is None


@pytest.mark.integration
class TestEntityTypeTransitions:
    """Tests for module <-> workflow transitions during git operations."""

    @pytest.mark.asyncio
    async def test_module_to_workflow_transition(
        self, db_session: AsyncSession, tmp_path: Path
    ):
        """Test that adding @workflow decorator changes entity_type from module to workflow."""
        from src.services.git_integration import GitIntegrationService
        from src.services.decorator_property_service import DecoratorPropertyService

        # Create initial module file
        file_path_str = "transitions/helper.py"
        file_path = tmp_path / file_path_str
        file_path.parent.mkdir(parents=True)

        # Start as a module
        module_content = '''
def helper_function():
    return "helper"
'''
        file_path.write_text(module_content)

        service = GitIntegrationService()
        service.workspace_path = tmp_path
        decorator_service = DecoratorPropertyService()

        # Parse as module
        await service._parse_python_file(
            db_session, file_path_str, file_path, decorator_service
        )
        await db_session.commit()

        # Verify it's a module
        stmt = select(WorkspaceFile).where(WorkspaceFile.path == file_path_str)
        result = await db_session.execute(stmt)
        ws_file = result.scalar_one()
        assert ws_file.entity_type == "module"
        assert ws_file.content is not None

        # Now add @workflow decorator
        workflow_content = '''from bifrost import workflow

@workflow(name="Converted Workflow")
async def helper_function():
    return "helper"
'''
        file_path.write_text(workflow_content)

        # Re-parse
        await service._parse_python_file(
            db_session, file_path_str, file_path, decorator_service
        )
        await db_session.commit()

        # Refresh and verify transition
        await db_session.refresh(ws_file)
        assert ws_file.entity_type == "workflow"
        assert ws_file.content is None  # Cleared during workflow transition

    @pytest.mark.asyncio
    async def test_workflow_to_module_transition(
        self, db_session: AsyncSession, tmp_path: Path
    ):
        """Test that removing @workflow decorator changes entity_type from workflow to module."""
        from src.services.git_integration import GitIntegrationService
        from src.services.decorator_property_service import DecoratorPropertyService

        file_path_str = "transitions/workflow.py"
        file_path = tmp_path / file_path_str
        file_path.parent.mkdir(parents=True)

        # Start as a workflow
        workflow_content = '''from bifrost import workflow

@workflow(name="My Workflow")
async def my_workflow():
    return "result"
'''
        file_path.write_text(workflow_content)

        service = GitIntegrationService()
        service.workspace_path = tmp_path
        decorator_service = DecoratorPropertyService()

        # Parse as workflow
        await service._parse_python_file(
            db_session, file_path_str, file_path, decorator_service
        )
        await db_session.commit()

        # Verify it's a workflow
        stmt = select(WorkspaceFile).where(WorkspaceFile.path == file_path_str)
        result = await db_session.execute(stmt)
        ws_file = result.scalar_one()
        assert ws_file.entity_type == "workflow"

        # Remove @workflow decorator
        module_content = '''
async def my_workflow():
    return "result"
'''
        file_path.write_text(module_content)

        # Re-parse
        await service._parse_python_file(
            db_session, file_path_str, file_path, decorator_service
        )
        await db_session.commit()

        # Refresh and verify transition
        await db_session.refresh(ws_file)
        assert ws_file.entity_type == "module"
        assert ws_file.content == module_content


@pytest.mark.integration
class TestDeletedFileHandling:
    """Tests for handling deleted files during git pull."""

    @pytest.mark.asyncio
    async def test_handle_deleted_module_soft_deletes(
        self, db_session: AsyncSession, tmp_path: Path
    ):
        """Test that _handle_deleted_file soft-deletes module records."""
        # Create a module in the database
        module = WorkspaceFile(
            path="to_delete/helper.py",
            content="# content to delete",
            content_hash="todelete123",
            size_bytes=20,
            content_type="text/x-python",
            entity_type="module",
            is_deleted=False,
        )
        db_session.add(module)
        await db_session.commit()
        await db_session.refresh(module)

        try:
            from src.services.git_integration import GitIntegrationService

            service = GitIntegrationService()
            service.workspace_path = tmp_path

            # Handle deletion
            await service._handle_deleted_file(db_session, "to_delete/helper.py")
            await db_session.commit()

            # Refresh and verify soft delete
            await db_session.refresh(module)
            assert module.is_deleted is True
            assert module.content is None  # Content cleared

        finally:
            # Hard delete for cleanup
            await db_session.delete(module)
            await db_session.commit()

    @pytest.mark.asyncio
    async def test_handle_deleted_module_invalidates_cache(
        self, db_session: AsyncSession, tmp_path: Path
    ):
        """Test that deleting a module invalidates the Redis cache."""
        from src.core.module_cache import get_module, set_module, clear_module_cache

        # Set up module in cache
        await clear_module_cache()
        await set_module("cached_module.py", "# cached content", "cached123")

        # Create corresponding DB record
        module = WorkspaceFile(
            path="cached_module.py",
            content="# cached content",
            content_hash="cached123",
            size_bytes=20,
            content_type="text/x-python",
            entity_type="module",
            is_deleted=False,
        )
        db_session.add(module)
        await db_session.commit()

        try:
            # Verify module is in cache
            cached = await get_module("cached_module.py")
            assert cached is not None

            from src.services.git_integration import GitIntegrationService

            service = GitIntegrationService()
            service.workspace_path = tmp_path

            # Handle deletion
            await service._handle_deleted_file(db_session, "cached_module.py")
            await db_session.commit()

            # Verify cache was invalidated
            cached = await get_module("cached_module.py")
            assert cached is None

        finally:
            await db_session.delete(module)
            await db_session.commit()
            await clear_module_cache()


@pytest.mark.integration
class TestParseAndUpsertPlatformEntities:
    """Tests for the main _parse_and_upsert_platform_entities method."""

    @pytest.mark.asyncio
    async def test_parse_handles_mixed_file_types(
        self, db_session: AsyncSession, tmp_path: Path
    ):
        """Test that _parse_and_upsert_platform_entities handles modules and workflows."""
        from src.services.git_integration import GitIntegrationService

        # Create test files
        (tmp_path / "utils").mkdir()
        (tmp_path / "workflows").mkdir()

        # Module file
        (tmp_path / "utils" / "helpers.py").write_text('''
def utility_function():
    return "utility"
''')

        # Workflow file
        (tmp_path / "workflows" / "main.py").write_text('''from bifrost import workflow

@workflow(name="Main Workflow")
async def main_workflow():
    return "success"
''')

        service = GitIntegrationService()
        service.workspace_path = tmp_path

        # Parse files
        await service._parse_and_upsert_platform_entities([
            "utils/helpers.py",
            "workflows/main.py",
        ])

        # Verify module
        stmt = select(WorkspaceFile).where(WorkspaceFile.path == "utils/helpers.py")
        result = await db_session.execute(stmt)
        module = result.scalar_one_or_none()
        assert module is not None
        assert module.entity_type == "module"

        # Verify workflow workspace entry
        stmt = select(WorkspaceFile).where(WorkspaceFile.path == "workflows/main.py")
        result = await db_session.execute(stmt)
        workflow_ws = result.scalar_one_or_none()
        assert workflow_ws is not None
        assert workflow_ws.entity_type == "workflow"

    @pytest.mark.asyncio
    async def test_parse_handles_deleted_files(
        self, db_session: AsyncSession, tmp_path: Path
    ):
        """Test that _parse_and_upsert_platform_entities handles deleted files."""
        from src.services.git_integration import GitIntegrationService

        # Create module in DB that will be "deleted"
        module = WorkspaceFile(
            path="deleted/module.py",
            content="# to be deleted",
            content_hash="delete123",
            size_bytes=20,
            content_type="text/x-python",
            entity_type="module",
            is_deleted=False,
        )
        db_session.add(module)
        await db_session.commit()

        try:
            service = GitIntegrationService()
            service.workspace_path = tmp_path

            # Parse with non-existent file (simulates deletion)
            # Pass session to avoid event loop issues in tests
            await service._parse_and_upsert_platform_entities(
                ["deleted/module.py"],  # File doesn't exist on disk
                session=db_session,
            )
            await db_session.commit()

            # Verify soft delete
            await db_session.refresh(module)
            assert module.is_deleted is True

        finally:
            await db_session.delete(module)
            await db_session.commit()
