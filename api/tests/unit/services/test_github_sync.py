"""
Unit tests for GitHub Sync Service.

Tests the GitHubSyncService data models and exceptions.
"""

from src.services.github_sync import (
    SyncAction,
    SyncActionType,
    ConflictInfo,
    OrphanInfo,
    UnresolvedRefInfo,
    WorkflowReference,
    SyncPreview,
    SyncResult,
    SyncExecuteRequest,
    SyncError,
    ConflictError,
    OrphanError,
    UnresolvedRefsError,
    TreeEntry,
    GitHubAPIError,
)


class TestSyncActionType:
    """Tests for SyncActionType enum."""

    def test_action_types(self):
        """Test all action types are defined."""
        assert SyncActionType.ADD.value == "add"
        assert SyncActionType.MODIFY.value == "modify"
        assert SyncActionType.DELETE.value == "delete"


class TestSyncAction:
    """Tests for SyncAction model."""

    def test_creates_sync_action(self):
        """Test SyncAction creation."""
        action = SyncAction(
            path="test.py",
            action=SyncActionType.ADD,
            sha="abc123",
        )

        assert action.path == "test.py"
        assert action.action == SyncActionType.ADD
        assert action.sha == "abc123"

    def test_sync_action_without_sha(self):
        """Test SyncAction with no sha."""
        action = SyncAction(
            path="test.py",
            action=SyncActionType.DELETE,
        )

        assert action.sha is None


class TestConflictInfo:
    """Tests for ConflictInfo model."""

    def test_creates_conflict_info(self):
        """Test ConflictInfo creation."""
        conflict = ConflictInfo(
            path="conflict.py",
            local_content="local code",
            remote_content="remote code",
            local_sha="local-sha",
            remote_sha="remote-sha",
        )

        assert conflict.path == "conflict.py"
        assert conflict.local_content == "local code"
        assert conflict.remote_content == "remote code"
        assert conflict.local_sha == "local-sha"
        assert conflict.remote_sha == "remote-sha"

    def test_conflict_info_without_content(self):
        """Test ConflictInfo without content (content may be lazy loaded)."""
        conflict = ConflictInfo(
            path="conflict.py",
            local_sha="local-sha",
            remote_sha="remote-sha",
        )

        assert conflict.local_content is None
        assert conflict.remote_content is None


class TestWorkflowReference:
    """Tests for WorkflowReference model."""

    def test_creates_workflow_reference(self):
        """Test WorkflowReference creation."""
        ref = WorkflowReference(
            type="form",
            id="form-123",
            name="Test Form",
        )

        assert ref.type == "form"
        assert ref.id == "form-123"
        assert ref.name == "Test Form"


class TestOrphanInfo:
    """Tests for OrphanInfo model."""

    def test_creates_orphan_info(self):
        """Test OrphanInfo creation."""
        orphan = OrphanInfo(
            workflow_id="wf-123",
            workflow_name="My Workflow",
            function_name="my_workflow",
            last_path="workflows/my_workflow.py",
        )

        assert orphan.workflow_id == "wf-123"
        assert orphan.workflow_name == "My Workflow"
        assert orphan.function_name == "my_workflow"
        assert orphan.last_path == "workflows/my_workflow.py"
        assert len(orphan.used_by) == 0

    def test_orphan_info_with_references(self):
        """Test OrphanInfo with usage references."""
        orphan = OrphanInfo(
            workflow_id="wf-123",
            workflow_name="My Workflow",
            function_name="my_workflow",
            last_path="workflows/my_workflow.py",
            used_by=[
                WorkflowReference(type="form", id="form-1", name="Test Form"),
                WorkflowReference(type="app", id="app-1", name="Test App"),
            ],
        )

        assert len(orphan.used_by) == 2
        assert orphan.used_by[0].type == "form"
        assert orphan.used_by[1].type == "app"


class TestUnresolvedRefInfo:
    """Tests for UnresolvedRefInfo model."""

    def test_creates_unresolved_ref_info(self):
        """Test UnresolvedRefInfo creation."""
        ref = UnresolvedRefInfo(
            entity_type="app",
            entity_path="apps/abc123.app.json",
            field_path="pages.0.launch_workflow_id",
            portable_ref="workflows/my_workflow.py::my_function",
        )

        assert ref.entity_type == "app"
        assert ref.entity_path == "apps/abc123.app.json"
        assert ref.field_path == "pages.0.launch_workflow_id"
        assert ref.portable_ref == "workflows/my_workflow.py::my_function"


class TestSyncPreview:
    """Tests for SyncPreview model."""

    def test_creates_empty_preview(self):
        """Test empty SyncPreview creation."""
        preview = SyncPreview(is_empty=True)

        assert preview.is_empty is True
        assert len(preview.to_pull) == 0
        assert len(preview.to_push) == 0
        assert len(preview.conflicts) == 0
        assert len(preview.will_orphan) == 0
        assert len(preview.unresolved_refs) == 0

    def test_creates_preview_with_changes(self):
        """Test SyncPreview with changes."""
        preview = SyncPreview(
            to_pull=[SyncAction(path="new.py", action=SyncActionType.ADD)],
            to_push=[SyncAction(path="changed.py", action=SyncActionType.MODIFY)],
            is_empty=False,
        )

        assert preview.is_empty is False
        assert len(preview.to_pull) == 1
        assert len(preview.to_push) == 1

    def test_preview_with_conflicts(self):
        """Test SyncPreview with conflicts."""
        preview = SyncPreview(
            conflicts=[
                ConflictInfo(
                    path="conflict.py",
                    local_sha="local",
                    remote_sha="remote",
                )
            ],
            is_empty=False,
        )

        assert len(preview.conflicts) == 1

    def test_preview_with_unresolved_refs(self):
        """Test SyncPreview with unresolved refs."""
        preview = SyncPreview(
            unresolved_refs=[
                UnresolvedRefInfo(
                    entity_type="app",
                    entity_path="apps/test.app.json",
                    field_path="pages.0.launch_workflow_id",
                    portable_ref="workflows/missing.py::missing_func",
                )
            ],
            is_empty=False,
        )

        assert len(preview.unresolved_refs) == 1
        assert preview.unresolved_refs[0].portable_ref == "workflows/missing.py::missing_func"


class TestSyncResult:
    """Tests for SyncResult model."""

    def test_creates_success_result(self):
        """Test successful SyncResult."""
        result = SyncResult(
            success=True,
            pulled=5,
            pushed=3,
            commit_sha="abc123",
        )

        assert result.success is True
        assert result.pulled == 5
        assert result.pushed == 3
        assert result.commit_sha == "abc123"
        assert result.error is None

    def test_creates_error_result(self):
        """Test failed SyncResult."""
        result = SyncResult(
            success=False,
            error="Something went wrong",
        )

        assert result.success is False
        assert result.error == "Something went wrong"

    def test_result_with_orphans(self):
        """Test SyncResult with orphaned workflows."""
        result = SyncResult(
            success=True,
            orphaned_workflows=["wf-1", "wf-2"],
        )

        assert len(result.orphaned_workflows) == 2


class TestSyncExecuteRequest:
    """Tests for SyncExecuteRequest model."""

    def test_creates_request_with_resolutions(self):
        """Test SyncExecuteRequest with conflict resolutions."""
        request = SyncExecuteRequest(
            conflict_resolutions={
                "file1.py": "keep_local",
                "file2.py": "keep_remote",
            },
            confirm_orphans=True,
        )

        assert request.conflict_resolutions["file1.py"] == "keep_local"
        assert request.conflict_resolutions["file2.py"] == "keep_remote"
        assert request.confirm_orphans is True

    def test_creates_empty_request(self):
        """Test SyncExecuteRequest with defaults."""
        request = SyncExecuteRequest()

        assert len(request.conflict_resolutions) == 0
        assert request.confirm_orphans is False
        assert request.confirm_unresolved_refs is False

    def test_creates_request_with_unresolved_refs_confirmation(self):
        """Test SyncExecuteRequest with unresolved refs confirmation."""
        request = SyncExecuteRequest(
            confirm_unresolved_refs=True,
        )

        assert request.confirm_unresolved_refs is True


class TestTreeEntry:
    """Tests for TreeEntry dataclass."""

    def test_creates_tree_entry(self):
        """Test TreeEntry creation."""
        entry = TreeEntry(
            sha="abc123",
            size=100,
            type="blob",
            mode="100644",
        )

        assert entry.sha == "abc123"
        assert entry.size == 100
        assert entry.type == "blob"
        assert entry.mode == "100644"


class TestSyncExceptions:
    """Tests for sync exception classes."""

    def test_sync_error(self):
        """Test SyncError exception."""
        error = SyncError("Sync failed")
        assert str(error) == "Sync failed"

    def test_conflict_error(self):
        """Test ConflictError exception."""
        conflicts = ["file1.py", "file2.py"]
        error = ConflictError(conflicts)

        assert "file1.py" in str(error)
        assert "file2.py" in str(error)
        assert error.conflicts == conflicts

    def test_orphan_error(self):
        """Test OrphanError exception."""
        orphans = ["wf-1", "wf-2"]
        error = OrphanError(orphans)

        assert "wf-1" in str(error)
        assert "wf-2" in str(error)
        assert error.orphans == orphans

    def test_unresolved_refs_error(self):
        """Test UnresolvedRefsError exception."""
        refs = [
            UnresolvedRefInfo(
                entity_type="app",
                entity_path="apps/test.app.json",
                field_path="pages.0.launch_workflow_id",
                portable_ref="workflows/missing.py::func1",
            ),
            UnresolvedRefInfo(
                entity_type="form",
                entity_path="forms/test.form.json",
                field_path="workflow_id",
                portable_ref="workflows/missing.py::func2",
            ),
        ]
        error = UnresolvedRefsError(refs)

        assert "workflows/missing.py::func1" in str(error)
        assert "workflows/missing.py::func2" in str(error)
        assert error.unresolved_refs == refs

    def test_unresolved_refs_error_truncates_many_refs(self):
        """Test UnresolvedRefsError truncates message for many refs."""
        refs = [
            UnresolvedRefInfo(
                entity_type="app",
                entity_path=f"apps/test{i}.app.json",
                field_path="pages.0.launch_workflow_id",
                portable_ref=f"workflows/missing.py::func{i}",
            )
            for i in range(10)
        ]
        error = UnresolvedRefsError(refs)

        # Only first 5 should be shown, plus count of remaining
        assert "func0" in str(error)
        assert "func4" in str(error)
        assert "and 5 more" in str(error)
        assert "func5" not in str(error)  # Not shown in message


class TestGitHubAPIError:
    """Tests for GitHubAPIError exception."""

    def test_creates_error_without_status(self):
        """Test GitHubAPIError without status code."""
        error = GitHubAPIError("Something went wrong")

        assert str(error) == "Something went wrong"
        assert error.status_code is None

    def test_creates_error_with_status(self):
        """Test GitHubAPIError with status code."""
        error = GitHubAPIError("Not found", status_code=404)

        assert str(error) == "Not found"
        assert error.status_code == 404
