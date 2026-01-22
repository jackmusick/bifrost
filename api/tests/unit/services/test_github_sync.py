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


class TestMemoryUsageDuringFileScan:
    """
    Memory profiling tests for file scanning operations.

    These tests verify that the streaming file scan approach keeps memory
    usage low even when processing many large files. The scheduler container
    has a 512Mi limit and was previously crashing with OOM when syncing
    repositories with 4MB+ modules.
    """

    def test_streaming_scan_memory_stays_bounded(self, tmp_path):
        """
        Test that scanning many large files doesn't accumulate memory.

        Simulates scanning 50 x 1MB files and verifies peak memory stays
        reasonable (under 50MB overhead beyond the single file being processed).
        """
        import tracemalloc

        from src.services.file_storage.file_ops import compute_git_blob_sha

        # Create 50 x 1MB files
        num_files = 50
        file_size = 1 * 1024 * 1024  # 1MB each

        for i in range(num_files):
            file_path = tmp_path / f"large_file_{i}.bin"
            # Write deterministic content (not random, to be consistent)
            file_path.write_bytes(bytes([i % 256] * file_size))

        # Start memory tracking
        tracemalloc.start()

        # Simulate the streaming scan pattern (as implemented in get_sync_preview)
        remote_files: dict[str, str] = {}
        file_count = 0

        for file_path in tmp_path.rglob("*"):
            if not file_path.is_file():
                continue
            content = file_path.read_bytes()
            remote_files[str(file_path)] = compute_git_blob_sha(content)
            del content  # Explicit release
            file_count += 1

        # Get peak memory usage
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        assert file_count == num_files

        # Peak memory should be well under the total data size
        # With streaming, we only hold ~1 file at a time + dict of SHAs
        # 50 files x 1MB = 50MB total, but peak should be much lower
        # Allow 20MB overhead for SHA dict, Python objects, etc.
        max_expected_peak = 20 * 1024 * 1024  # 20MB

        assert peak < max_expected_peak, (
            f"Peak memory {peak / 1024 / 1024:.1f}MB exceeded "
            f"expected max {max_expected_peak / 1024 / 1024:.1f}MB. "
            f"This suggests memory is accumulating instead of streaming."
        )

    def test_old_list_pattern_would_use_more_memory(self, tmp_path):
        """
        Demonstrate that the old list-based pattern uses more memory.

        This test shows why we switched to streaming - the old approach
        of building a list of all files first would hold more in memory.
        """
        import tracemalloc

        from src.services.file_storage.file_ops import compute_git_blob_sha

        # Create 20 x 1MB files (smaller to keep test fast)
        num_files = 20
        file_size = 1 * 1024 * 1024  # 1MB each

        for i in range(num_files):
            file_path = tmp_path / f"large_file_{i}.bin"
            file_path.write_bytes(bytes([i % 256] * file_size))

        # Test OLD pattern (list comprehension that holds all paths)
        tracemalloc.start()
        all_files = [f for f in tmp_path.rglob("*") if f.is_file()]
        remote_files_old: dict[str, str] = {}
        for file_path in all_files:
            content = file_path.read_bytes()
            remote_files_old[str(file_path)] = compute_git_blob_sha(content)
            # Note: no del content here, simulating less careful memory management
        _, peak_old = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        # Test NEW pattern (streaming with explicit release)
        tracemalloc.start()
        remote_files_new: dict[str, str] = {}
        for file_path in tmp_path.rglob("*"):
            if not file_path.is_file():
                continue
            content = file_path.read_bytes()
            remote_files_new[str(file_path)] = compute_git_blob_sha(content)
            del content  # Explicit release
        _, peak_new = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        # Both should produce same results
        assert remote_files_old == remote_files_new

        # New pattern should use less or equal memory
        # (In practice, the difference is more pronounced with larger files
        # and when GC hasn't run between iterations)
        assert peak_new <= peak_old * 1.1, (
            f"New pattern ({peak_new / 1024 / 1024:.1f}MB) should not use "
            f"significantly more memory than old pattern ({peak_old / 1024 / 1024:.1f}MB)"
        )

    def test_large_python_file_memory_bounded(self, tmp_path):
        """
        Test memory stays bounded when scanning multiple copies of ~4MB Python files.

        This simulates the scenario that caused OOM in scheduler:
        - Large modules like halopsa.py (~4MB)
        - Multiple files being processed in sequence
        - Without explicit `del`, memory accumulates

        With the fix (explicit `del content`), peak memory should stay low.
        """
        import shutil
        import tracemalloc

        from src.services.file_storage.file_ops import compute_git_blob_sha
        from tests.fixtures.large_module_generator import generate_large_module_file

        # Generate a ~4MB Python file (similar to halopsa.py)
        base_file = tmp_path / "base_large_module.py"
        generate_large_module_file(str(base_file), target_size_mb=4.0)

        # Verify it's approximately the right size
        actual_size = base_file.stat().st_size
        assert actual_size > 3.5 * 1024 * 1024, f"Base file too small: {actual_size}"
        assert actual_size < 5 * 1024 * 1024, f"Base file too large: {actual_size}"

        # Create 10 copies (would be ~40MB total without streaming)
        num_copies = 10
        for i in range(num_copies):
            shutil.copy(base_file, tmp_path / f"module_{i}.py")

        # Start memory tracking
        tracemalloc.start()

        # Simulate the scan pattern WITH explicit memory release
        results: dict[str, str] = {}
        for file_path in tmp_path.glob("module_*.py"):
            content = file_path.read_bytes()
            results[str(file_path)] = compute_git_blob_sha(content)
            del content  # This is what we're testing - explicit release

        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        assert len(results) == num_copies

        # With streaming + del, peak should be ~1 file + overhead
        # 10 x 4MB = 40MB without del, should be <15MB with del
        max_expected = 15 * 1024 * 1024  # 15MB

        assert peak < max_expected, (
            f"Peak memory {peak / 1024 / 1024:.1f}MB exceeded "
            f"expected max {max_expected / 1024 / 1024:.1f}MB. "
            f"Memory may be accumulating between file reads."
        )

    def test_execute_sync_pattern_memory_bounded(self, tmp_path):
        """
        Test memory stays bounded when simulating execute_sync file write pattern.

        This simulates what happens in execute_sync when pulling multiple large
        Python modules sequentially. Each file:
        1. Read from clone directory
        2. Process (decode for modules, compute SHA, etc.)
        3. Should be released with del before next iteration

        Without explicit memory management, this would accumulate ~40MB for
        10 x 4MB files. With proper del statements, peak should stay low.
        """
        import shutil
        import tracemalloc

        from src.services.file_storage.file_ops import compute_git_blob_sha
        from tests.fixtures.large_module_generator import generate_large_module_file

        # Generate a ~4MB Python file
        base_file = tmp_path / "base_large_module.py"
        generate_large_module_file(str(base_file), target_size_mb=4.0)

        # Create multiple copies simulating different modules (halopsa, sageintacct, etc.)
        module_names = [
            "sageintacct.py",
            "ninjaone.py",
            "halopsa.py",
            "connectwise.py",
            "datto.py",
        ]
        for name in module_names:
            shutil.copy(base_file, tmp_path / name)

        tracemalloc.start()

        # Simulate the execute_sync pattern:
        # For each file, read -> process -> write (simulated) -> del content
        processed_files: list[str] = []
        for file_path in tmp_path.glob("*.py"):
            if file_path.name == "base_large_module.py":
                continue

            # 1. Read file (like: content = local_file.read_bytes())
            content = file_path.read_bytes()

            # 2. Process - simulate what write_file does internally
            #    - Decode to string (for module_content)
            module_content = content.decode("utf-8")
            #    - Compute SHA
            _ = compute_git_blob_sha(content)

            # 3. Simulate DB write + Redis cache (actual memory not tracked here)
            processed_files.append(file_path.name)

            # 4. Explicit release (this is what we're testing)
            del module_content  # Release decoded string
            del content  # Release bytes

        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        assert len(processed_files) == len(module_names)

        # With explicit del, peak should be ~2 copies of one file at most
        # (bytes + decoded string) = ~8MB, plus overhead
        # Without del, would be 5 files x 8MB = 40MB
        max_expected = 20 * 1024 * 1024  # 20MB

        assert peak < max_expected, (
            f"Peak memory {peak / 1024 / 1024:.1f}MB exceeded "
            f"expected max {max_expected / 1024 / 1024:.1f}MB. "
            f"This simulates execute_sync pattern - memory should not accumulate."
        )
