"""
Unit tests for Workflow Orphan Service.

Tests the WorkflowOrphanService data models and basic service initialization.
"""

from unittest.mock import MagicMock


from src.services.workflow_orphan import (
    WorkflowOrphanService,
    OrphanedWorkflow,
    WorkflowReference,
    Replacement,
    FunctionSignature,
)


class TestWorkflowOrphanServiceInit:
    """Tests for WorkflowOrphanService initialization."""

    def test_creates_service_with_db(self):
        """Test service initialization with database session."""
        mock_db = MagicMock()
        service = WorkflowOrphanService(db=mock_db)

        assert service.db == mock_db


class TestOrphanedWorkflowModel:
    """Tests for OrphanedWorkflow data model."""

    def test_creates_orphaned_workflow(self):
        """Test OrphanedWorkflow model creation."""
        orphan = OrphanedWorkflow(
            id="wf-123",
            name="Test Workflow",
            function_name="test_func",
            last_path="workflows/test.py",
            code="def test_func(): pass",
            used_by=[],
            orphaned_at=None,
        )

        assert orphan.id == "wf-123"
        assert orphan.name == "Test Workflow"
        assert orphan.function_name == "test_func"
        assert orphan.code is not None

    def test_orphaned_workflow_with_usage(self):
        """Test OrphanedWorkflow with usage references."""
        orphan = OrphanedWorkflow(
            id="wf-123",
            name="Test Workflow",
            function_name="test_func",
            last_path="workflows/test.py",
            code="def test_func(): pass",
            used_by=[
                WorkflowReference(type="form", id="form-1", name="Test Form"),
                WorkflowReference(type="app", id="app-1", name="Test App"),
            ],
            orphaned_at=None,
        )

        assert len(orphan.used_by) == 2
        assert orphan.used_by[0].type == "form"
        assert orphan.used_by[1].type == "app"

    def test_orphaned_workflow_without_code(self):
        """Test OrphanedWorkflow can have None code."""
        orphan = OrphanedWorkflow(
            id="wf-123",
            name="Test Workflow",
            function_name="test_func",
            last_path="workflows/test.py",
            code=None,
            used_by=[],
            orphaned_at=None,
        )

        assert orphan.code is None


class TestWorkflowReferenceModel:
    """Tests for WorkflowReference data model."""

    def test_creates_form_reference(self):
        """Test WorkflowReference for form."""
        ref = WorkflowReference(
            type="form",
            id="form-123",
            name="Test Form",
        )

        assert ref.type == "form"
        assert ref.id == "form-123"
        assert ref.name == "Test Form"

    def test_creates_app_reference(self):
        """Test WorkflowReference for app."""
        ref = WorkflowReference(
            type="app",
            id="app-123",
            name="Test App",
        )

        assert ref.type == "app"

    def test_creates_agent_reference(self):
        """Test WorkflowReference for agent."""
        ref = WorkflowReference(
            type="agent",
            id="agent-123",
            name="Test Agent",
        )

        assert ref.type == "agent"


class TestReplacementModel:
    """Tests for Replacement data model."""

    def test_creates_exact_replacement(self):
        """Test Replacement with exact compatibility."""
        replacement = Replacement(
            path="workflows/replacement.py",
            function_name="replacement_func",
            signature="(arg1: str) -> None",
            compatibility="exact",
        )

        assert replacement.path == "workflows/replacement.py"
        assert replacement.function_name == "replacement_func"
        assert replacement.compatibility == "exact"

    def test_creates_compatible_replacement(self):
        """Test Replacement with compatible compatibility."""
        replacement = Replacement(
            path="workflows/other.py",
            function_name="other_func",
            signature="(arg1: str, arg2: int = 0) -> None",
            compatibility="compatible",
        )

        assert replacement.compatibility == "compatible"

    def test_creates_incompatible_replacement(self):
        """Test Replacement with incompatible compatibility."""
        replacement = Replacement(
            path="workflows/incompatible.py",
            function_name="incompatible_func",
            signature="(different_arg: bytes) -> int",
            compatibility="incompatible",
        )

        assert replacement.compatibility == "incompatible"


class TestFunctionSignature:
    """Tests for FunctionSignature dataclass."""

    def test_creates_function_signature(self):
        """Test FunctionSignature creation."""
        sig = FunctionSignature(
            name="test_func",
            parameters=[
                ("arg1", "str", False),
                ("arg2", "int", True),
            ],
            return_type="None",
        )

        assert sig.name == "test_func"
        assert len(sig.parameters) == 2
        assert sig.parameters[0] == ("arg1", "str", False)
        assert sig.parameters[1] == ("arg2", "int", True)
        assert sig.return_type == "None"

    def test_function_signature_without_return_type(self):
        """Test FunctionSignature without return type annotation."""
        sig = FunctionSignature(
            name="no_return_type",
            parameters=[],
            return_type=None,
        )

        assert sig.return_type is None

    def test_function_signature_with_no_type_annotations(self):
        """Test FunctionSignature with untyped parameters."""
        sig = FunctionSignature(
            name="untyped_func",
            parameters=[
                ("arg1", None, False),
                ("arg2", None, False),
            ],
            return_type=None,
        )

        assert sig.parameters[0][1] is None
        assert sig.parameters[1][1] is None
