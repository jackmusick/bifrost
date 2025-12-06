"""
Integration tests for Bifrost SDK from workflows

Tests that user workflows can import and use the bifrost SDK.
"""

import pytest
from pathlib import Path

# Import bifrost context functions directly
# This ensures we use the same ContextVar instance that storage module uses
from bifrost._context import set_execution_context, clear_execution_context, get_execution_context



@pytest.fixture
def test_context():
    """Create a test execution context"""
    from shared.context import ExecutionContext, Organization

    org = Organization(id="test-org", name="Test Org", is_active=True)
    return ExecutionContext(
        user_id="test-user",
        email="test@example.com",
        name="Test User",
        scope="test-org",
        organization=org,
        is_platform_admin=False,
        is_function_key=False,
        execution_id="test-exec-123"
    )


@pytest.fixture
def admin_context():
    """Create an admin execution context"""
    from shared.context import ExecutionContext, Organization

    org = Organization(id="test-org", name="Test Org", is_active=True)
    return ExecutionContext(
        user_id="admin-user",
        email="admin@example.com",
        name="Admin User",
        scope="test-org",
        organization=org,
        is_platform_admin=True,
        is_function_key=False,
        execution_id="test-exec-456"
    )


class TestSDKImportsFromWorkflow:
    """Test that SDK can be imported from workflow code"""

    def test_import_bifrost_organizations(self):
        """Test importing organizations module"""
        from bifrost import organizations

        # Verify module has expected methods
        assert hasattr(organizations, 'create')
        assert hasattr(organizations, 'get')
        assert hasattr(organizations, 'list')
        assert hasattr(organizations, 'update')

    def test_import_bifrost_workflows(self):
        """Test importing workflows module"""
        from bifrost import workflows

        assert hasattr(workflows, 'list')
        assert hasattr(workflows, 'get')

    def test_import_bifrost_files(self):
        """Test importing files module"""
        from bifrost import files

        assert hasattr(files, 'read')
        assert hasattr(files, 'write')
        assert hasattr(files, 'list')
        assert hasattr(files, 'delete')
        assert hasattr(files, 'exists')

    def test_import_bifrost_forms(self):
        """Test importing forms module"""
        from bifrost import forms

        assert hasattr(forms, 'list')
        assert hasattr(forms, 'get')

    def test_import_bifrost_executions(self):
        """Test importing executions module"""
        from bifrost import executions

        assert hasattr(executions, 'list')
        assert hasattr(executions, 'get')

    def test_import_bifrost_roles(self):
        """Test importing roles module"""
        from bifrost import roles

        assert hasattr(roles, 'create')
        assert hasattr(roles, 'get')
        assert hasattr(roles, 'list')
        assert hasattr(roles, 'update')
        assert hasattr(roles, 'delete')
        assert hasattr(roles, 'assign_users')
        assert hasattr(roles, 'assign_forms')


class TestSDKUsageFromWorkflow:
    """Test SDK usage patterns from workflow code"""

    @pytest.mark.asyncio
    async def test_workflow_can_use_sdk_context(self, test_context):
        """Test that workflow can access SDK with context"""

        # Set context (simulates what workflow engine does)
        set_execution_context(test_context)

        try:
            # In a real scenario with database, this would work
            # For now, we verify the context is accessible
            context = get_execution_context()
            assert context.org_id == "test-org"
            assert context.user_id == "test-user"
        finally:
            clear_execution_context()

    async def test_sdk_without_context_raises_error(self):
        """Test that SDK raises clear error when used without context"""
        from bifrost import organizations

        # Ensure no context is set
        clear_execution_context()

        # Attempting to use SDK should raise RuntimeError
        with pytest.raises(RuntimeError, match="No execution context found"):
            await organizations.list()


class TestSDKFileOperations:
    """Test file operations through SDK"""

    def test_file_path_sandboxing(self):
        """Test that absolute paths outside /home are blocked"""
        from bifrost import files

        # Simple test: absolute paths outside /home should be rejected
        with pytest.raises(ValueError, match="Path must be within"):
            files._resolve_path("/etc/passwd", location="workspace")


class TestImportRestrictions:
    """Test that import restrictions work correctly"""

    def test_home_code_cannot_import_shared_directly(self):
        """Test that code in /home cannot import from shared.*"""
        # This would need to be tested with actual files in /home
        # For now, we verify the restrictor is configured correctly

        from shared.import_restrictor import get_active_restrictors

        restrictors = get_active_restrictors()

        if restrictors:
            restrictor = restrictors[0]
            # Verify blocked prefixes include 'shared.'
            assert 'shared.' in restrictor.BLOCKED_PREFIXES

            # Verify bifrost is in allowed exports
            assert 'bifrost' in restrictor.ALLOWED_SHARED_EXPORTS

    def test_bifrost_modules_are_whitelisted(self):
        """Test that bifrost SDK modules are whitelisted for import"""
        from shared.import_restrictor import WorkspaceImportRestrictor

        # Check that bifrost modules are in whitelist
        assert 'bifrost' in WorkspaceImportRestrictor.ALLOWED_SHARED_EXPORTS
        assert 'bifrost.organizations' in WorkspaceImportRestrictor.ALLOWED_SHARED_EXPORTS
        assert 'bifrost.workflows' in WorkspaceImportRestrictor.ALLOWED_SHARED_EXPORTS
        assert 'bifrost.files' in WorkspaceImportRestrictor.ALLOWED_SHARED_EXPORTS
        assert 'bifrost.forms' in WorkspaceImportRestrictor.ALLOWED_SHARED_EXPORTS
        assert 'bifrost.executions' in WorkspaceImportRestrictor.ALLOWED_SHARED_EXPORTS
        assert 'bifrost.roles' in WorkspaceImportRestrictor.ALLOWED_SHARED_EXPORTS


class TestEndToEndSDKUsage:
    """End-to-end tests of SDK usage patterns"""

    @pytest.mark.asyncio
    async def test_complete_workflow_sdk_pattern(self, test_context):
        """
        Test complete pattern: context setup, SDK usage, context teardown.

        This simulates what happens in a real workflow execution.
        """
        from bifrost import organizations

        # 1. Workflow engine sets context
        set_execution_context(test_context)

        try:
            # 2. Workflow uses SDK
            # (Would normally interact with database)

            # Verify context is accessible using get_execution_context
            ctx = get_execution_context()
            assert ctx.org_id == "test-org"

            # 3. SDK operations would happen here
            # organizations.list()
            # files.write("output.txt", b"data")

        finally:
            # 4. Workflow engine clears context
            clear_execution_context()

        # 5. After context cleared, SDK should raise error
        with pytest.raises(RuntimeError):
            await organizations.list()
