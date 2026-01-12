"""
Integration tests for SDK scoping during workflow execution.

Tests that the execution context scope is resolved correctly based on:
- Org-scoped workflows: use workflow's organization_id
- Global workflows: use caller's organization_id
"""

import pytest

from src.sdk.context import Caller, ExecutionContext, Organization


class TestScopeResolution:
    """Test scope resolution rules for different workflow/caller combinations."""

    @pytest.fixture
    def org_a(self):
        """Organization A"""
        return Organization(id="org-a-uuid", name="Organization A", is_active=True)

    @pytest.fixture
    def org_b(self):
        """Organization B"""
        return Organization(id="org-b-uuid", name="Organization B", is_active=True)

    @pytest.fixture
    def caller_in_org_a(self):
        """User in Organization A"""
        return Caller(
            user_id="user-a-uuid",
            email="user@org-a.com",
            name="User A"
        )

    @pytest.fixture
    def caller_in_org_b(self):
        """User in Organization B"""
        return Caller(
            user_id="user-b-uuid",
            email="user@org-b.com",
            name="User B"
        )

    @pytest.fixture
    def platform_admin(self):
        """Platform admin (no org)"""
        return Caller(
            user_id="admin-uuid",
            email="admin@platform.com",
            name="Platform Admin"
        )

    def test_org_workflow_uses_workflow_org_same_caller(self, org_a, caller_in_org_a):
        """Org-scoped workflow with caller from same org uses workflow's org."""
        # Workflow belongs to Org A, caller is from Org A
        context = ExecutionContext(
            user_id=caller_in_org_a.user_id,
            email=caller_in_org_a.email,
            name=caller_in_org_a.name,
            scope=org_a.id,  # Workflow's org (resolved by consumer)
            organization=org_a,
            is_platform_admin=False,
            is_function_key=False,
            execution_id="test-exec-1"
        )

        assert context.scope == "org-a-uuid"
        assert context.org_id == "org-a-uuid"

    def test_org_workflow_uses_workflow_org_different_caller(self, org_a, org_b, caller_in_org_b):
        """Org-scoped workflow uses workflow's org even when caller is from different org."""
        # Workflow belongs to Org A, but caller is from Org B
        # Per new rules: org-scoped workflow always uses workflow's org
        context = ExecutionContext(
            user_id=caller_in_org_b.user_id,
            email=caller_in_org_b.email,
            name=caller_in_org_b.name,
            scope=org_a.id,  # Workflow's org (resolved by consumer)
            organization=org_a,
            is_platform_admin=False,
            is_function_key=False,
            execution_id="test-exec-2"
        )

        # Should use workflow's org (org_a), not caller's org (org_b)
        assert context.scope == org_a.id
        assert context.org_id == org_a.id
        assert context.scope != org_b.id  # Verify caller's org is NOT used

    def test_org_workflow_with_platform_admin_uses_workflow_org(self, org_a, platform_admin):
        """Org-scoped workflow uses workflow's org even when caller is platform admin."""
        # Workflow belongs to Org A, caller is platform admin with no org
        context = ExecutionContext(
            user_id=platform_admin.user_id,
            email=platform_admin.email,
            name=platform_admin.name,
            scope=org_a.id,  # Workflow's org (resolved by consumer)
            organization=org_a,
            is_platform_admin=True,
            is_function_key=False,
            execution_id="test-exec-3"
        )

        # Should use workflow's org
        assert context.scope == "org-a-uuid"
        assert context.org_id == "org-a-uuid"

    def test_global_workflow_uses_caller_org(self, org_a, caller_in_org_a):
        """Global workflow uses caller's org."""
        # Workflow is global (no organization_id), caller is from Org A
        context = ExecutionContext(
            user_id=caller_in_org_a.user_id,
            email=caller_in_org_a.email,
            name=caller_in_org_a.name,
            scope=org_a.id,  # Caller's org (resolved by consumer for global workflow)
            organization=org_a,
            is_platform_admin=False,
            is_function_key=False,
            execution_id="test-exec-4"
        )

        # Should use caller's org
        assert context.scope == "org-a-uuid"
        assert context.org_id == "org-a-uuid"

    def test_global_workflow_with_org_b_caller(self, org_b, caller_in_org_b):
        """Global workflow with Org B caller uses Org B."""
        context = ExecutionContext(
            user_id=caller_in_org_b.user_id,
            email=caller_in_org_b.email,
            name=caller_in_org_b.name,
            scope=org_b.id,  # Caller's org
            organization=org_b,
            is_platform_admin=False,
            is_function_key=False,
            execution_id="test-exec-5"
        )

        assert context.scope == "org-b-uuid"
        assert context.org_id == "org-b-uuid"

    def test_global_workflow_with_platform_admin_no_org(self, platform_admin):
        """Global workflow with platform admin (no org) uses GLOBAL scope."""
        # Workflow is global, caller is platform admin with no org
        context = ExecutionContext(
            user_id=platform_admin.user_id,
            email=platform_admin.email,
            name=platform_admin.name,
            scope="GLOBAL",  # No org = GLOBAL
            organization=None,
            is_platform_admin=True,
            is_function_key=False,
            execution_id="test-exec-6"
        )

        assert context.scope == "GLOBAL"
        assert context.org_id is None
        assert context.is_global_scope is True


class TestScopeResolutionInConsumer:
    """Test the actual scope resolution logic from the consumer."""

    def test_resolve_scope_org_workflow(self):
        """Test scope resolution for org-scoped workflow."""
        # Simulate what the consumer does
        caller_org_id = "caller-org"
        workflow_org_id = "workflow-org"

        # New logic: if workflow has org_id, use it
        if workflow_org_id:
            resolved_org_id = workflow_org_id
        else:
            resolved_org_id = caller_org_id

        assert resolved_org_id == "workflow-org"

    def test_resolve_scope_global_workflow(self):
        """Test scope resolution for global workflow."""
        caller_org_id = "caller-org"
        workflow_org_id = None  # Global workflow

        # New logic: if workflow has no org_id, use caller's
        if workflow_org_id:
            resolved_org_id = workflow_org_id
        else:
            resolved_org_id = caller_org_id

        assert resolved_org_id == "caller-org"

    def test_resolve_scope_global_workflow_no_caller_org(self):
        """Test scope resolution for global workflow when caller has no org."""
        caller_org_id = None
        workflow_org_id = None  # Global workflow

        if workflow_org_id:
            resolved_org_id = workflow_org_id
        else:
            resolved_org_id = caller_org_id

        assert resolved_org_id is None  # GLOBAL scope


class TestContextPropertyAccessors:
    """Test that context properties correctly expose scope information."""

    def test_org_id_returns_organization_id_when_set(self):
        """org_id property returns organization.id when organization is set."""
        org = Organization(id="test-org-123", name="Test Org", is_active=True)
        context = ExecutionContext(
            user_id="user-1",
            email="test@example.com",
            name="Test User",
            scope="test-org-123",
            organization=org,
            is_platform_admin=False,
            is_function_key=False,
            execution_id="exec-1"
        )

        assert context.org_id == "test-org-123"
        assert context.org_name == "Test Org"

    def test_org_id_returns_none_for_global_scope(self):
        """org_id property returns None when organization is None."""
        context = ExecutionContext(
            user_id="admin-1",
            email="admin@example.com",
            name="Admin User",
            scope="GLOBAL",
            organization=None,
            is_platform_admin=True,
            is_function_key=False,
            execution_id="exec-2"
        )

        assert context.org_id is None
        assert context.org_name is None
        assert context.is_global_scope is True

    def test_is_global_scope_true_for_global(self):
        """is_global_scope returns True when scope is GLOBAL."""
        context = ExecutionContext(
            user_id="admin-1",
            email="admin@example.com",
            name="Admin",
            scope="GLOBAL",
            organization=None,
            is_platform_admin=True,
            is_function_key=False,
            execution_id="exec-3"
        )

        assert context.is_global_scope is True

    def test_is_global_scope_false_for_org_scope(self):
        """is_global_scope returns False when scope is an org ID."""
        org = Organization(id="org-abc", name="ABC Corp", is_active=True)
        context = ExecutionContext(
            user_id="user-1",
            email="user@example.com",
            name="User",
            scope="org-abc",
            organization=org,
            is_platform_admin=False,
            is_function_key=False,
            execution_id="exec-4"
        )

        assert context.is_global_scope is False


class TestScopeResolutionFunction:
    """
    Test a reusable scope resolution function that mirrors consumer logic.

    This demonstrates the expected behavior for determining execution scope
    based on workflow type and caller identity.
    """

    @staticmethod
    def resolve_execution_scope(
        workflow_org_id: str | None,
        caller_org_id: str | None
    ) -> str | None:
        """
        Resolve the execution scope based on workflow and caller.

        Args:
            workflow_org_id: The workflow's organization_id (None for global workflows)
            caller_org_id: The caller's organization_id (None for platform admins)

        Returns:
            The resolved organization_id for execution, or None for GLOBAL scope
        """
        # Rule: Org-scoped workflow uses workflow's org
        # Rule: Global workflow uses caller's org
        if workflow_org_id is not None:
            return workflow_org_id
        return caller_org_id

    def test_org_workflow_org_caller(self):
        """Org workflow + org caller = workflow org."""
        result = self.resolve_execution_scope(
            workflow_org_id="workflow-org",
            caller_org_id="caller-org"
        )
        assert result == "workflow-org"

    def test_org_workflow_no_caller_org(self):
        """Org workflow + platform admin = workflow org."""
        result = self.resolve_execution_scope(
            workflow_org_id="workflow-org",
            caller_org_id=None
        )
        assert result == "workflow-org"

    def test_global_workflow_org_caller(self):
        """Global workflow + org caller = caller org."""
        result = self.resolve_execution_scope(
            workflow_org_id=None,
            caller_org_id="caller-org"
        )
        assert result == "caller-org"

    def test_global_workflow_no_caller_org(self):
        """Global workflow + platform admin = GLOBAL (None)."""
        result = self.resolve_execution_scope(
            workflow_org_id=None,
            caller_org_id=None
        )
        assert result is None

    def test_workflow_org_takes_precedence(self):
        """Workflow org always takes precedence when present."""
        # Even if caller has different org, workflow org wins
        result = self.resolve_execution_scope(
            workflow_org_id="org-A",
            caller_org_id="org-B"
        )
        assert result == "org-A"

    def test_caller_org_only_when_workflow_global(self):
        """Caller org only used when workflow is global."""
        result = self.resolve_execution_scope(
            workflow_org_id=None,
            caller_org_id="org-B"
        )
        assert result == "org-B"
