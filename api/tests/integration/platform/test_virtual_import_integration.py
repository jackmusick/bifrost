"""
Integration tests for virtual import system and init container.

Tests the complete flow of:
1. Module cache warming from database
2. Worker loading modules from Redis cache
3. Virtual import hook integration
"""

import sys

import pytest
import pytest_asyncio
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
class TestModuleCacheWarming:
    """Tests for init container cache warming functionality."""

    @pytest_asyncio.fixture
    async def module_in_db(self, db_session: AsyncSession):
        """Create a test module in the database."""
        content = 'TEST_VALUE = "from_database"\ndef get_value(): return TEST_VALUE'
        module = WorkspaceFile(
            path="test_integration_module.py",
            content=content,
            content_hash="abc123",
            size_bytes=len(content.encode("utf-8")),
            entity_type="module",
            entity_id=None,
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
    async def test_warm_cache_from_db_loads_modules(
        self, db_session: AsyncSession, module_in_db: WorkspaceFile
    ):
        """Test that warm_cache_from_db loads modules into Redis cache."""
        from src.core.module_cache import (
            clear_module_cache,
            get_module,
            warm_cache_from_db,
        )

        # Clear cache first
        await clear_module_cache()

        # Verify module is not in cache
        cached = await get_module("test_integration_module.py")
        assert cached is None, "Module should not be in cache before warming"

        # Warm cache - pass session to avoid event loop conflicts
        count = await warm_cache_from_db(session=db_session)
        assert count >= 1, "Should have cached at least one module"

        # Verify module is now in cache
        cached = await get_module("test_integration_module.py")
        assert cached is not None, "Module should be in cache after warming"
        assert cached["content"] == module_in_db.content
        assert cached["path"] == module_in_db.path

    @pytest_asyncio.fixture
    async def deleted_module_in_db(self, db_session: AsyncSession):
        """Create a deleted test module in the database."""
        content = "# deleted"
        module = WorkspaceFile(
            path="deleted_module.py",
            content=content,
            content_hash="deleted",
            size_bytes=len(content.encode("utf-8")),
            entity_type="module",
            entity_id=None,
            is_deleted=True,  # Marked as deleted
        )
        db_session.add(module)
        await db_session.commit()
        await db_session.refresh(module)

        yield module

        # Cleanup
        await db_session.delete(module)
        await db_session.commit()

    @pytest.mark.asyncio
    async def test_warm_cache_excludes_deleted_modules(
        self, db_session: AsyncSession, deleted_module_in_db: WorkspaceFile
    ):
        """Test that deleted modules are not cached."""
        from src.core.module_cache import (
            clear_module_cache,
            get_module,
            warm_cache_from_db,
        )

        await clear_module_cache()
        # Pass session to avoid event loop conflicts
        await warm_cache_from_db(session=db_session)

        # Verify deleted module is not in cache
        cached = await get_module("deleted_module.py")
        assert cached is None, "Deleted modules should not be cached"


@pytest.mark.integration
class TestVirtualImportIntegration:
    """Integration tests for virtual import from Redis cache."""

    @pytest.fixture(autouse=True)
    def cleanup(self):
        """Clean up after each test."""
        yield
        # Remove virtual import hooks
        sys.meta_path = [
            finder
            for finder in sys.meta_path
            if not finder.__class__.__name__ == "VirtualModuleFinder"
        ]
        # Remove test modules from sys.modules
        to_remove = [k for k in sys.modules if k.startswith("integration_test_")]
        for k in to_remove:
            del sys.modules[k]
        # Reset global finder
        import src.services.execution.virtual_import as module

        module._finder = None

    @pytest.mark.asyncio
    async def test_virtual_import_loads_from_redis(self, db_session: AsyncSession):
        """Test importing a module via virtual import hook from Redis cache."""
        from src.core.module_cache import clear_module_cache, set_module
        from src.services.execution.virtual_import import (
            install_virtual_import_hook,
            remove_virtual_import_hook,
        )

        # Set up module in Redis cache
        await clear_module_cache()
        await set_module(
            path="integration_test_virtual.py",
            content='VIRTUAL_IMPORT_VALUE = "loaded_from_redis"\ndef test_func(): return 42',
            content_hash="test123",
        )

        # Install virtual import hook
        install_virtual_import_hook()

        try:
            # Import the module - should be loaded from Redis
            import integration_test_virtual  # type: ignore[import-not-found]

            assert integration_test_virtual.VIRTUAL_IMPORT_VALUE == "loaded_from_redis"
            assert integration_test_virtual.test_func() == 42
            # Virtual modules use relative paths, not absolute filesystem paths
            assert integration_test_virtual.__file__ == "integration_test_virtual.py"

        finally:
            remove_virtual_import_hook()
            await clear_module_cache()

    @pytest.mark.asyncio
    async def test_virtual_import_package_with_submodule(self, db_session: AsyncSession):
        """Test importing a package with submodules from Redis cache."""
        from src.core.module_cache import clear_module_cache, set_module
        from src.services.execution.virtual_import import (
            install_virtual_import_hook,
            invalidate_module_index,
            remove_virtual_import_hook,
        )

        # Set up package in Redis cache
        await clear_module_cache()
        await set_module(
            path="integration_test_pkg/__init__.py",
            content='PKG_NAME = "test_package"',
            content_hash="pkg123",
        )
        await set_module(
            path="integration_test_pkg/helpers.py",
            content='HELPER_VALUE = "from_helpers"',
            content_hash="helper123",
        )

        # Install virtual import hook
        install_virtual_import_hook()
        invalidate_module_index()  # Force refresh of index

        try:
            # Import package and submodule
            import integration_test_pkg  # type: ignore[import-not-found]
            from integration_test_pkg import helpers  # type: ignore[import-not-found]

            assert integration_test_pkg.PKG_NAME == "test_package"
            assert helpers.HELPER_VALUE == "from_helpers"

        finally:
            remove_virtual_import_hook()
            await clear_module_cache()


@pytest.mark.integration
class TestWorkerVirtualImportHook:
    """Tests for worker.py virtual import hook installation."""

    @pytest.fixture(autouse=True)
    def cleanup(self):
        """Clean up after each test."""
        yield
        # Remove virtual import hooks
        sys.meta_path = [
            finder
            for finder in sys.meta_path
            if not finder.__class__.__name__ == "VirtualModuleFinder"
        ]
        # Reset global finder
        import src.services.execution.virtual_import as module

        module._finder = None

    def test_install_virtual_import_hook(self):
        """Test that install_virtual_import_hook creates and registers a finder."""
        from src.services.execution.virtual_import import (
            get_virtual_finder,
            install_virtual_import_hook,
        )

        # Install the hook
        finder = install_virtual_import_hook()

        # Verify the hook was created
        assert finder is not None, "install_virtual_import_hook should return a finder"

        # Verify it can be retrieved
        retrieved = get_virtual_finder()
        assert retrieved is finder, "get_virtual_finder should return the installed finder"

    def test_virtual_finder_in_meta_path_after_install(self):
        """Test that VirtualModuleFinder is in sys.meta_path after installation."""
        from src.services.execution.virtual_import import install_virtual_import_hook

        # Install the hook
        install_virtual_import_hook()

        # Check it's in meta_path
        has_virtual_finder = any(
            finder.__class__.__name__ == "VirtualModuleFinder" for finder in sys.meta_path
        )
        assert has_virtual_finder, "VirtualModuleFinder should be in sys.meta_path"


@pytest.mark.integration
class TestEndToEndModuleLoading:
    """End-to-end tests for module loading from DB through Redis to import."""

    @pytest.fixture(autouse=True)
    def cleanup(self):
        """Clean up after each test."""
        yield
        # Remove virtual import hooks
        sys.meta_path = [
            finder
            for finder in sys.meta_path
            if not finder.__class__.__name__ == "VirtualModuleFinder"
        ]
        # Remove test modules
        to_remove = [k for k in sys.modules if k.startswith("e2e_test_")]
        for k in to_remove:
            del sys.modules[k]
        # Reset global finder
        import src.services.execution.virtual_import as module

        module._finder = None

    @pytest.mark.asyncio
    async def test_full_flow_db_to_import(self, db_session: AsyncSession):
        """Test complete flow: DB -> cache warming -> Redis -> virtual import."""
        from src.core.module_cache import clear_module_cache, warm_cache_from_db
        from src.services.execution.virtual_import import (
            install_virtual_import_hook,
            invalidate_module_index,
            remove_virtual_import_hook,
        )

        # Step 1: Create module in database
        content = """
WORKFLOW_NAME = "e2e_test"

def run_workflow(params):
    return {"status": "success", "name": WORKFLOW_NAME, "params": params}
"""
        module = WorkspaceFile(
            path="e2e_test_workflow.py",
            content=content,
            content_hash="e2e123",
            size_bytes=len(content.encode("utf-8")),
            entity_type="module",
            entity_id=None,
            is_deleted=False,
        )
        db_session.add(module)
        await db_session.commit()

        try:
            # Step 2: Clear and warm cache - pass session to avoid event loop conflicts
            await clear_module_cache()
            count = await warm_cache_from_db(session=db_session)
            assert count >= 1

            # Step 3: Install virtual import hook
            install_virtual_import_hook()
            invalidate_module_index()

            # Step 4: Import and use the module
            import e2e_test_workflow  # type: ignore[import-not-found]

            assert e2e_test_workflow.WORKFLOW_NAME == "e2e_test"

            result = e2e_test_workflow.run_workflow({"key": "value"})
            assert result["status"] == "success"
            assert result["name"] == "e2e_test"
            assert result["params"] == {"key": "value"}

        finally:
            remove_virtual_import_hook()
            await clear_module_cache()
            await db_session.delete(module)
            await db_session.commit()
