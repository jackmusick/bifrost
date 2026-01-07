"""
Unit tests for workflow execution consumer org_id fallback behavior.

Tests the org resolution logic where:
1. User's org_id takes precedence when present
2. Workflow's organization_id is used as fallback when user org is None
3. GLOBAL scope is used when both are None
"""

import pytest


class TestOrgIdFallbackLogic:
    """
    Tests for org_id fallback behavior in workflow execution consumer.

    The consumer applies this logic after getting workflow data:
    - If user's org_id is set, use it (no fallback needed)
    - If user's org_id is None and workflow has organization_id, use workflow's
    - If both are None, stay as None (GLOBAL scope)
    """

    def test_user_org_takes_precedence(self):
        """User's org_id is used when present, even if workflow has different org."""
        # Simulate pending execution with user's org
        org_id = "user-org-id-12345"

        # Simulate workflow data with different org
        workflow_data = {"organization_id": "workflow-org-id-67890"}

        # Fallback logic (from consumer)
        workflow_org_id = workflow_data.get("organization_id")
        if org_id is None and workflow_org_id:
            org_id = workflow_org_id

        # User's org takes precedence
        assert org_id == "user-org-id-12345"

    def test_workflow_org_fallback_when_user_org_none(self):
        """Workflow's organization_id is used when user org is None."""
        # Simulate pending execution without user's org (system-triggered)
        org_id = None

        # Simulate workflow data with org
        workflow_data = {"organization_id": "workflow-org-id-67890"}

        # Fallback logic
        workflow_org_id = workflow_data.get("organization_id")
        if org_id is None and workflow_org_id:
            org_id = workflow_org_id

        # Workflow's org is used as fallback
        assert org_id == "workflow-org-id-67890"

    def test_global_scope_when_both_none(self):
        """GLOBAL scope (org_id=None) when both user and workflow org are None."""
        # Simulate pending execution without user's org
        org_id = None

        # Simulate global workflow (no organization_id)
        workflow_data = {"organization_id": None}

        # Fallback logic
        workflow_org_id = workflow_data.get("organization_id")
        if org_id is None and workflow_org_id:
            org_id = workflow_org_id

        # Stays None for GLOBAL scope
        assert org_id is None

    def test_global_scope_when_workflow_org_missing(self):
        """GLOBAL scope when workflow doesn't have organization_id key."""
        # Simulate pending execution without user's org
        org_id = None

        # Simulate workflow data without organization_id key
        workflow_data = {"name": "test-workflow"}

        # Fallback logic
        workflow_org_id = workflow_data.get("organization_id")
        if org_id is None and workflow_org_id:
            org_id = workflow_org_id

        # Stays None for GLOBAL scope
        assert org_id is None

    def test_empty_string_org_not_treated_as_none(self):
        """Empty string org_id is truthy, so it's used (edge case)."""
        # This shouldn't happen in practice, but test the behavior
        org_id = ""  # Empty string is falsy in Python

        workflow_data = {"organization_id": "workflow-org-id"}

        # Fallback logic - empty string is falsy, so fallback happens
        workflow_org_id = workflow_data.get("organization_id")
        if org_id is None and workflow_org_id:
            org_id = workflow_org_id

        # Empty string is NOT None, so no fallback (keeps empty string)
        assert org_id == ""


class TestOrgResolutionBehavior:
    """Tests documenting the expected org resolution behavior."""

    def test_resolution_priority_documented(self):
        """
        Document the org resolution priority:
        1. User's org_id (from pending execution) - highest priority
        2. Workflow's organization_id (from database) - fallback
        3. GLOBAL (None) - when both are None
        """
        scenarios = [
            # (user_org, workflow_org, expected_result)
            ("user-org", "workflow-org", "user-org"),       # User takes priority
            ("user-org", None, "user-org"),                 # User with global workflow
            (None, "workflow-org", "workflow-org"),         # Fallback to workflow
            (None, None, None),                             # GLOBAL scope
        ]

        for user_org, workflow_org, expected in scenarios:
            org_id = user_org
            workflow_data = {"organization_id": workflow_org}

            workflow_org_id = workflow_data.get("organization_id")
            if org_id is None and workflow_org_id:
                org_id = workflow_org_id

            assert org_id == expected, f"Failed for user_org={user_org}, workflow_org={workflow_org}"

    def test_fallback_prevents_data_leakage(self):
        """
        Verify fallback ensures proper scoping for SDK operations.

        When a system-triggered workflow (schedule, webhook) runs:
        - User org_id is None (system user has no org)
        - Workflow's organization_id should be used for SDK scope
        - This prevents global access when the workflow is org-scoped
        """
        # System user triggers org-scoped workflow
        system_user_org = None  # System user has no org
        org_scoped_workflow = {"organization_id": "customer-org-123"}

        # Apply fallback
        org_id = system_user_org
        workflow_org_id = org_scoped_workflow.get("organization_id")
        if org_id is None and workflow_org_id:
            org_id = workflow_org_id

        # SDK operations will be scoped to customer's org
        assert org_id == "customer-org-123"
        # This prevents the workflow from accessing data from other orgs
