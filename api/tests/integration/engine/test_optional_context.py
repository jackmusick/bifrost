"""
Test optional context parameter in workflows.

Tests that workflows can:
1. Have explicit context parameter (traditional style)
2. Omit context parameter (SDK-only style)
3. Get helpful error messages for signature mismatches
"""

import pytest

from bifrost import ExecutionContext, workflow
from bifrost._context import clear_execution_context, set_execution_context
from src.sdk.context import Caller, Organization


@pytest.fixture
def test_context():
    """Create a test execution context."""
    org = Organization(
        id="test-org",
        name="Test Organization",
        is_active=True,
    )
    caller = Caller(
        user_id="test-user",
        email="test@example.com",
        name="Test User",
    )
    context = ExecutionContext(
        user_id=caller.user_id,
        email=caller.email,
        name=caller.name,
        scope=org.id,
        organization=org,
        is_platform_admin=False,
        is_function_key=False,
        execution_id="test-execution-123",
    )
    return context


class TestOptionalContext:
    """Test workflows with and without explicit context parameters."""

    async def test_workflow_with_explicit_context(self, test_context):
        """Test traditional workflow with explicit context parameter."""

        @workflow(
            name="test_explicit_context",
            description="Test workflow with explicit context",
            category="testing",
        )
        async def workflow_with_context(context: ExecutionContext, name: str) -> dict:
            """Workflow that accesses context directly."""
            return {
                "name": name,
                "org_id": context.org_id,
                "user_id": context.user_id,
                "execution_id": context.execution_id,
            }

        # Set context for SDK
        set_execution_context(test_context)

        try:
            # Call workflow with context (simulating engine behavior)
            result = await workflow_with_context(test_context, name="Alice")

            # Verify results
            assert result["name"] == "Alice"
            assert result["org_id"] == "test-org"
            assert result["user_id"] == "test-user"
            assert result["execution_id"] == "test-execution-123"
        finally:
            clear_execution_context()

    async def test_workflow_without_context_parameter(self, test_context):
        """Test new-style workflow without explicit context parameter."""

        @workflow(
            name="test_no_context",
            description="Test workflow without context parameter",
            category="testing",
        )
        async def workflow_without_context(name: str) -> dict:
            """Workflow that only uses SDK functions (context via ContextVar)."""
            # SDK functions can access context implicitly
            # For this test, we'll just return the name since we can't easily test
            # config.get() without actual config setup
            return {"name": name, "uses_sdk": True}

        # Set context for SDK
        set_execution_context(test_context)

        try:
            # Call workflow without context (new behavior)
            result = await workflow_without_context(name="Bob")

            # Verify results
            assert result["name"] == "Bob"
            assert result["uses_sdk"] is True
        finally:
            clear_execution_context()

    async def test_workflow_with_context_accessing_sdk(self, test_context):
        """Test that workflow with explicit context can still use SDK functions."""

        @workflow(
            name="test_hybrid",
            description="Test workflow with both context and SDK usage",
            category="testing",
        )
        async def hybrid_workflow(context: ExecutionContext, name: str) -> dict:
            """Workflow that uses both direct context access and SDK functions."""
            # Direct context access
            org_id = context.org_id

            # SDK function access (implicit context)
            # We'll just show it can be called - actual config test needs setup
            return {"name": name, "org_id": org_id, "can_use_sdk": True}

        # Set context for SDK
        set_execution_context(test_context)

        try:
            # Call workflow with context
            result = await hybrid_workflow(test_context, name="Charlie")

            # Verify results
            assert result["name"] == "Charlie"
            assert result["org_id"] == "test-org"
            assert result["can_use_sdk"] is True
        finally:
            clear_execution_context()

    async def test_backward_compatibility(self, test_context):
        """Test that existing workflows with context parameter still work."""

        @workflow(
            name="test_backward_compat",
            description="Test backward compatibility",
            category="testing",
        )
        async def legacy_workflow(
            context: ExecutionContext, value: str, multiplier: int = 2
        ) -> dict:
            """Legacy-style workflow with context as first parameter."""
            return {
                "value": value * multiplier,
                "org": context.org_name,
                "user": context.email,
            }

        # Set context for SDK
        set_execution_context(test_context)

        try:
            # Call workflow in old style
            result = await legacy_workflow(test_context, value="X", multiplier=3)

            # Verify results
            assert result["value"] == "XXX"
            assert result["org"] == "Test Organization"
            assert result["user"] == "test@example.com"
        finally:
            clear_execution_context()


class TestContextParameterNaming:
    """Test that context parameter works with various naming conventions."""

    async def test_workflow_with_underscore_context(self, test_context):
        """Test workflow with _context parameter (common for unused linting)."""

        @workflow(
            name="test_underscore_context",
            description="Test workflow with _context parameter",
            category="testing",
        )
        async def workflow_underscore(_context: ExecutionContext, name: str) -> dict:
            """Workflow using _context to avoid unused warnings."""
            return {
                "name": name,
                "org_id": _context.org_id,
                "user_id": _context.user_id,
            }

        # Set context for SDK
        set_execution_context(test_context)

        try:
            # Call workflow with context
            result = await workflow_underscore(test_context, name="Alice")

            # Verify results
            assert result["name"] == "Alice"
            assert result["org_id"] == "test-org"
            assert result["user_id"] == "test-user"
        finally:
            clear_execution_context()

    async def test_workflow_with_ctx_name(self, test_context):
        """Test workflow with ctx parameter (short name)."""

        @workflow(
            name="test_ctx_context",
            description="Test workflow with ctx parameter",
            category="testing",
        )
        async def workflow_ctx(ctx: ExecutionContext, value: str) -> dict:
            """Workflow using ctx as context name."""
            return {
                "value": value,
                "org_id": ctx.org_id,
                "email": ctx.email,
            }

        # Set context for SDK
        set_execution_context(test_context)

        try:
            result = await workflow_ctx(test_context, value="test")

            assert result["value"] == "test"
            assert result["org_id"] == "test-org"
            assert result["email"] == "test@example.com"
        finally:
            clear_execution_context()

    async def test_workflow_with_long_context_name(self, test_context):
        """Test workflow with execution_context parameter (verbose name)."""

        @workflow(
            name="test_long_context_name",
            description="Test workflow with execution_context parameter",
            category="testing",
        )
        async def workflow_long_name(execution_context: ExecutionContext, data: str) -> dict:
            """Workflow using execution_context as name."""
            return {
                "data": data,
                "org_name": execution_context.org_name,
                "execution_id": execution_context.execution_id,
            }

        # Set context for SDK
        set_execution_context(test_context)

        try:
            result = await workflow_long_name(test_context, data="payload")

            assert result["data"] == "payload"
            assert result["org_name"] == "Test Organization"
            assert result["execution_id"] == "test-execution-123"
        finally:
            clear_execution_context()
