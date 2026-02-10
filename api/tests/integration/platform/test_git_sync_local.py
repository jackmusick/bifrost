"""
Git Sync TDD Tests — define the contract for GitPython-based sync.

Uses local bare git repos (no GitHub needed). These tests define the target
interface for the redesigned GitHubSyncService with GitPython.

Fixtures:
- bare_repo: local bare git repo (tmp_path)
- working_clone: a working clone for committing test data
- sync_service: GitHubSyncService configured against local bare repo
"""

import hashlib
from pathlib import Path
from uuid import uuid4

import pytest
import pytest_asyncio
import yaml
from git import Repo
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.orm.file_index import FileIndex
from src.models.orm.forms import Form
from src.models.orm.workflows import Workflow
from src.services.file_index_service import FileIndexService
from src.services.manifest import Manifest, parse_manifest
from src.services.repo_storage import RepoStorage


# =============================================================================
# Sample Content
# =============================================================================

SAMPLE_WORKFLOW_PY = """\
from bifrost import workflow

@workflow(name="Git Sync Test Workflow")
def git_sync_test_wf(message: str):
    \"\"\"A workflow for git sync testing.\"\"\"
    return {"result": message}
"""

SAMPLE_WORKFLOW_UPDATED = """\
from bifrost import workflow

@workflow(name="Git Sync Test Workflow Updated")
def git_sync_test_wf(message: str, count: int = 5):
    \"\"\"Updated workflow.\"\"\"
    return {"result": message, "count": count}
"""

SAMPLE_FORM_YAML = """\
name: Onboarding Form
description: New hire onboarding
workflow: {workflow_id}
fields:
  - name: employee_name
    type: text
    label: Employee Name
    required: true
  - name: start_date
    type: date
    label: Start Date
"""

SAMPLE_WORKFLOW_SYNTAX_ERROR = """\
from bifrost import workflow

@workflow(name="Bad Workflow")
def bad_workflow(
    # Missing closing paren and colon
    return {"oops"}
"""

SAMPLE_WORKFLOW_RUFF_ISSUES = """\
from bifrost import workflow
import os
import sys

@workflow(name="Lint Issues Workflow")
def lint_issues_wf(x):
    y = 1
    return {"result": x}
"""

SAMPLE_WORKFLOW_CLEAN = """\
from bifrost import workflow


@workflow(name="Clean Workflow")
def clean_wf(message: str) -> dict:
    \"\"\"A clean workflow.\"\"\"
    return {"result": message}
"""


def _make_manifest(
    workflows: dict | None = None,
    forms: dict | None = None,
) -> str:
    """Build a simple .bifrost/metadata.yaml string."""
    data: dict = {
        "organizations": [],
        "roles": [],
        "workflows": workflows or {},
        "forms": forms or {},
        "agents": {},
        "apps": {},
    }
    return yaml.dump(data, default_flow_style=False, sort_keys=False)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def bare_repo(tmp_path):
    """Local bare git repo."""
    repo_path = tmp_path / "test-repo.git"
    Repo.init(str(repo_path), bare=True)
    return repo_path


@pytest.fixture
def working_clone(tmp_path, bare_repo):
    """Working clone for committing test data."""
    work_path = tmp_path / "work"
    repo = Repo.clone_from(str(bare_repo), str(work_path))
    # Create initial commit so main branch exists
    (work_path / ".gitkeep").touch()
    repo.index.add([".gitkeep"])
    repo.index.commit("initial")
    repo.remotes.origin.push()
    return repo


@pytest_asyncio.fixture
async def sync_service(db_session: AsyncSession, bare_repo):
    """
    GitHubSyncService configured against the local bare repo.

    Uses file:// protocol to talk to the bare repo on disk.
    """
    from src.services.github_sync import GitHubSyncService

    return GitHubSyncService(
        db=db_session,
        repo_url=f"file://{bare_repo}",
        branch="main",
    )


@pytest_asyncio.fixture(autouse=True)
async def cleanup_test_data(db_session: AsyncSession):
    """Clean up test data between tests."""
    yield

    await db_session.execute(
        delete(Workflow).where(Workflow.path.like("workflows/git_sync_test%"))
    )
    await db_session.execute(
        delete(Workflow).where(Workflow.path.like("test_git_%"))
    )
    await db_session.execute(
        delete(FileIndex).where(FileIndex.path.like("workflows/git_sync_test%"))
    )
    await db_session.execute(
        delete(FileIndex).where(FileIndex.path.like("test_git_%"))
    )
    await db_session.execute(
        delete(FileIndex).where(FileIndex.path.like(".bifrost/%"))
    )
    await db_session.commit()


# =============================================================================
# Platform → Empty Repo (Initial Export)
# =============================================================================


@pytest.mark.integration
@pytest.mark.asyncio
class TestPushToEmptyRepo:
    """Push platform state to an empty repo (initial git connect)."""

    async def test_push_to_empty_repo(
        self,
        db_session: AsyncSession,
        sync_service,
        bare_repo,
        tmp_path,
    ):
        """
        Create entities in DB, push → clone and verify workflow .py files,
        form .form.yaml, manifest.
        """
        # Create a workflow in DB
        wf_id = uuid4()
        wf = Workflow(
            id=wf_id,
            name="Git Sync Test Workflow",
            function_name="git_sync_test_wf",
            path="workflows/git_sync_test_wf.py",
            is_active=True,
        )
        db_session.add(wf)
        await db_session.commit()

        # Push to empty repo
        result = await sync_service.push()

        assert result.success is True
        assert result.pushed > 0

        # Verify by cloning the repo and checking files
        verify_path = tmp_path / "verify"
        verify_repo = Repo.clone_from(f"file://{bare_repo}", str(verify_path))

        # Workflow .py file should exist
        wf_file = verify_path / "workflows" / "git_sync_test_wf.py"
        assert wf_file.exists(), "Workflow .py file should exist in repo"

        # Manifest should exist
        manifest_file = verify_path / ".bifrost" / "metadata.yaml"
        assert manifest_file.exists(), "Manifest should exist in repo"

    async def test_push_generates_manifest(
        self,
        db_session: AsyncSession,
        sync_service,
        bare_repo,
        tmp_path,
    ):
        """Push → .bifrost/metadata.yaml exists with correct entries."""
        wf_id = uuid4()
        wf = Workflow(
            id=wf_id,
            name="Manifest Test Workflow",
            function_name="manifest_test_wf",
            path="workflows/git_sync_test_manifest.py",
            is_active=True,
        )
        db_session.add(wf)
        await db_session.commit()

        await sync_service.push()

        # Clone and verify manifest
        verify_path = tmp_path / "verify"
        Repo.clone_from(f"file://{bare_repo}", str(verify_path))

        manifest_file = verify_path / ".bifrost" / "metadata.yaml"
        manifest = parse_manifest(manifest_file.read_text())

        # Workflow should be in manifest
        assert len(manifest.workflows) >= 1
        found = False
        for name, mwf in manifest.workflows.items():
            if mwf.id == str(wf_id):
                found = True
                assert mwf.path == "workflows/git_sync_test_manifest.py"
                assert mwf.function_name == "manifest_test_wf"
                break
        assert found, f"Workflow {wf_id} should be in manifest"


# =============================================================================
# Platform → Existing Repo (Incremental Push)
# =============================================================================


@pytest.mark.integration
@pytest.mark.asyncio
class TestIncrementalPush:
    """Push changes to a repo that already has content."""

    async def test_push_updates_modified_files(
        self,
        db_session: AsyncSession,
        sync_service,
        bare_repo,
        tmp_path,
    ):
        """Push, modify workflow, push again → repo has updated content."""
        wf_id = uuid4()
        wf = Workflow(
            id=wf_id,
            name="Git Sync Test Workflow",
            function_name="git_sync_test_wf",
            path="workflows/git_sync_test_incremental.py",
            is_active=True,
        )
        db_session.add(wf)
        await db_session.commit()

        # First push
        result1 = await sync_service.push()
        assert result1.success is True

        # Modify the workflow name
        wf.name = "Git Sync Test Workflow Updated"
        wf.description = "Updated description"
        await db_session.commit()

        # Second push
        result2 = await sync_service.push()
        assert result2.success is True

        # Verify updated content
        verify_path = tmp_path / "verify"
        Repo.clone_from(f"file://{bare_repo}", str(verify_path))
        manifest = parse_manifest(
            (verify_path / ".bifrost" / "metadata.yaml").read_text()
        )
        # Manifest should reflect the update
        found = False
        for name, mwf in manifest.workflows.items():
            if mwf.id == str(wf_id):
                found = True
                break
        assert found

    async def test_push_deletes_removed_files(
        self,
        db_session: AsyncSession,
        sync_service,
        bare_repo,
        tmp_path,
    ):
        """Push, delete workflow, push again → file gone from repo."""
        wf_id = uuid4()
        wf = Workflow(
            id=wf_id,
            name="Git Sync Delete Test",
            function_name="git_sync_delete_wf",
            path="workflows/git_sync_test_delete.py",
            is_active=True,
        )
        db_session.add(wf)
        await db_session.commit()

        # First push
        await sync_service.push()

        # Deactivate the workflow
        wf.is_active = False
        await db_session.commit()

        # Second push
        await sync_service.push()

        # Verify file is gone
        verify_path = tmp_path / "verify"
        Repo.clone_from(f"file://{bare_repo}", str(verify_path))
        wf_file = verify_path / "workflows" / "git_sync_test_delete.py"
        assert not wf_file.exists(), "Deleted workflow file should be gone from repo"


# =============================================================================
# Repo → Platform (Pull)
# =============================================================================


@pytest.mark.integration
@pytest.mark.asyncio
class TestPull:
    """Pull changes from repo into platform."""

    async def test_pull_new_workflow(
        self,
        db_session: AsyncSession,
        sync_service,
        working_clone,
    ):
        """Commit .py with @workflow to repo, pull → workflows table + file_index populated."""
        work_dir = Path(working_clone.working_dir)

        # Create workflow file in the repo
        wf_dir = work_dir / "workflows"
        wf_dir.mkdir(exist_ok=True)
        wf_file = wf_dir / "git_sync_test_pulled.py"
        wf_file.write_text(SAMPLE_WORKFLOW_PY)

        # Create a manifest pointing to this file
        wf_id = str(uuid4())
        manifest_content = _make_manifest(
            workflows={
                "Git Sync Test Workflow": {
                    "id": wf_id,
                    "path": "workflows/git_sync_test_pulled.py",
                    "function_name": "git_sync_test_wf",
                    "type": "workflow",
                }
            }
        )
        bifrost_dir = work_dir / ".bifrost"
        bifrost_dir.mkdir(exist_ok=True)
        (bifrost_dir / "metadata.yaml").write_text(manifest_content)

        # Commit and push
        working_clone.index.add([
            "workflows/git_sync_test_pulled.py",
            ".bifrost/metadata.yaml",
        ])
        working_clone.index.commit("add test workflow")
        working_clone.remotes.origin.push()

        # Pull into platform
        result = await sync_service.pull()

        assert result.success is True
        assert result.pulled > 0

        # Verify workflow in DB
        wf_result = await db_session.execute(
            select(Workflow).where(Workflow.id == wf_id)
        )
        wf = wf_result.scalar_one_or_none()
        assert wf is not None
        assert wf.name == "Git Sync Test Workflow"
        assert wf.function_name == "git_sync_test_wf"

        # Verify file_index populated
        fi_result = await db_session.execute(
            select(FileIndex).where(
                FileIndex.path == "workflows/git_sync_test_pulled.py"
            )
        )
        fi = fi_result.scalar_one_or_none()
        assert fi is not None
        assert "@workflow" in fi.content

    async def test_pull_new_form(
        self,
        db_session: AsyncSession,
        sync_service,
        working_clone,
    ):
        """Commit .form.yaml to repo, pull → forms table populated."""
        work_dir = Path(working_clone.working_dir)

        form_id = str(uuid4())
        wf_id = str(uuid4())

        # Create form yaml
        forms_dir = work_dir / "forms"
        forms_dir.mkdir(exist_ok=True)
        form_file = forms_dir / f"{form_id}.form.yaml"
        form_file.write_text(SAMPLE_FORM_YAML.format(workflow_id=wf_id))

        # Create manifest
        manifest_content = _make_manifest(
            forms={
                "Onboarding Form": {
                    "id": form_id,
                    "path": f"forms/{form_id}.form.yaml",
                }
            }
        )
        bifrost_dir = work_dir / ".bifrost"
        bifrost_dir.mkdir(exist_ok=True)
        (bifrost_dir / "metadata.yaml").write_text(manifest_content)

        working_clone.index.add([
            f"forms/{form_id}.form.yaml",
            ".bifrost/metadata.yaml",
        ])
        working_clone.index.commit("add test form")
        working_clone.remotes.origin.push()

        # Pull
        result = await sync_service.pull()
        assert result.success is True

        # Verify form in DB
        form_result = await db_session.execute(
            select(Form).where(Form.id == form_id)
        )
        form = form_result.scalar_one_or_none()
        assert form is not None
        assert form.name == "Onboarding Form"

    async def test_pull_modified_workflow(
        self,
        db_session: AsyncSession,
        sync_service,
        working_clone,
        bare_repo,
        tmp_path,
    ):
        """Push, modify in repo, pull → file_index updated."""
        # Create workflow in platform
        wf_id = uuid4()
        wf = Workflow(
            id=wf_id,
            name="Git Sync Test Workflow",
            function_name="git_sync_test_wf",
            path="workflows/git_sync_test_modified.py",
            is_active=True,
        )
        db_session.add(wf)
        await db_session.commit()

        # Push to repo
        await sync_service.push()

        # Modify in repo
        work_dir = Path(working_clone.working_dir)
        working_clone.remotes.origin.pull()
        wf_file = work_dir / "workflows" / "git_sync_test_modified.py"
        wf_file.write_text(SAMPLE_WORKFLOW_UPDATED)
        working_clone.index.add(["workflows/git_sync_test_modified.py"])
        working_clone.index.commit("update workflow")
        working_clone.remotes.origin.push()

        # Pull into platform
        result = await sync_service.pull()
        assert result.success is True

        # Verify file_index has updated content
        fi_result = await db_session.execute(
            select(FileIndex).where(
                FileIndex.path == "workflows/git_sync_test_modified.py"
            )
        )
        fi = fi_result.scalar_one_or_none()
        assert fi is not None
        assert "Updated" in fi.content

    async def test_pull_deleted_file(
        self,
        db_session: AsyncSession,
        sync_service,
        working_clone,
    ):
        """Push, delete in repo, pull → entity deactivated, file_index cleaned."""
        # Create workflow in platform
        wf_id = uuid4()
        wf = Workflow(
            id=wf_id,
            name="Git Sync Delete Pull Test",
            function_name="git_sync_delete_pull_wf",
            path="workflows/git_sync_test_del_pull.py",
            is_active=True,
        )
        db_session.add(wf)
        await db_session.commit()

        # Push
        await sync_service.push()

        # Delete in repo
        work_dir = Path(working_clone.working_dir)
        working_clone.remotes.origin.pull()
        wf_file = work_dir / "workflows" / "git_sync_test_del_pull.py"
        if wf_file.exists():
            wf_file.unlink()
        working_clone.index.remove(["workflows/git_sync_test_del_pull.py"])
        working_clone.index.commit("delete workflow")
        working_clone.remotes.origin.push()

        # Pull
        result = await sync_service.pull()
        assert result.success is True

        # Workflow should be deactivated
        await db_session.refresh(wf)
        assert wf.is_active is False

        # file_index entry should be removed
        fi_result = await db_session.execute(
            select(FileIndex).where(
                FileIndex.path == "workflows/git_sync_test_del_pull.py"
            )
        )
        assert fi_result.scalar_one_or_none() is None


# =============================================================================
# Renames
# =============================================================================


@pytest.mark.integration
@pytest.mark.asyncio
class TestRenames:
    """Renames are detected correctly during sync."""

    async def test_rename_in_repo_detected_on_pull(
        self,
        db_session: AsyncSession,
        sync_service,
        working_clone,
    ):
        """Push, rename file in repo, pull → platform path updated."""
        wf_id = uuid4()
        wf = Workflow(
            id=wf_id,
            name="Rename Test Workflow",
            function_name="rename_test_wf",
            path="workflows/git_sync_test_rename_old.py",
            is_active=True,
        )
        db_session.add(wf)
        await db_session.commit()

        # Push
        await sync_service.push()

        # Rename in repo
        work_dir = Path(working_clone.working_dir)
        working_clone.remotes.origin.pull()
        old_file = work_dir / "workflows" / "git_sync_test_rename_old.py"
        new_file = work_dir / "workflows" / "git_sync_test_rename_new.py"
        if old_file.exists():
            new_file.write_text(old_file.read_text())
            old_file.unlink()

        # Update manifest with new path
        manifest_file = work_dir / ".bifrost" / "metadata.yaml"
        if manifest_file.exists():
            manifest_data = yaml.safe_load(manifest_file.read_text())
            for name, wf_data in manifest_data.get("workflows", {}).items():
                if wf_data.get("id") == str(wf_id):
                    wf_data["path"] = "workflows/git_sync_test_rename_new.py"
            manifest_file.write_text(
                yaml.dump(manifest_data, default_flow_style=False, sort_keys=False)
            )

        working_clone.index.add([
            "workflows/git_sync_test_rename_new.py",
            ".bifrost/metadata.yaml",
        ])
        working_clone.index.remove(["workflows/git_sync_test_rename_old.py"])
        working_clone.index.commit("rename workflow")
        working_clone.remotes.origin.push()

        # Pull
        result = await sync_service.pull()
        assert result.success is True

        # Workflow path should be updated
        await db_session.refresh(wf)
        assert wf.path == "workflows/git_sync_test_rename_new.py"

    async def test_rename_in_platform_pushed(
        self,
        db_session: AsyncSession,
        sync_service,
        working_clone,
        bare_repo,
        tmp_path,
    ):
        """Push, rename in platform, push → repo has new path."""
        wf_id = uuid4()
        wf = Workflow(
            id=wf_id,
            name="Platform Rename Test",
            function_name="platform_rename_wf",
            path="workflows/git_sync_test_plat_old.py",
            is_active=True,
        )
        db_session.add(wf)
        await db_session.commit()

        # Push
        await sync_service.push()

        # Rename in platform (update path)
        wf.path = "workflows/git_sync_test_plat_new.py"
        await db_session.commit()

        # Push again
        await sync_service.push()

        # Verify new path in repo
        verify_path = tmp_path / "verify"
        Repo.clone_from(f"file://{bare_repo}", str(verify_path))
        old_file = verify_path / "workflows" / "git_sync_test_plat_old.py"
        new_file = verify_path / "workflows" / "git_sync_test_plat_new.py"
        assert not old_file.exists(), "Old path should be gone"
        assert new_file.exists(), "New path should exist"


# =============================================================================
# Conflicts
# =============================================================================


@pytest.mark.integration
@pytest.mark.asyncio
class TestConflicts:
    """Conflict detection when both sides modify."""

    async def test_both_modified_is_conflict(
        self,
        db_session: AsyncSession,
        sync_service,
        working_clone,
    ):
        """Push, modify both sides, preview → conflict detected."""
        wf_id = uuid4()
        wf = Workflow(
            id=wf_id,
            name="Conflict Test Workflow",
            function_name="conflict_test_wf",
            path="workflows/git_sync_test_conflict.py",
            is_active=True,
        )
        db_session.add(wf)
        await db_session.commit()

        # Push
        await sync_service.push()

        # Modify in repo
        work_dir = Path(working_clone.working_dir)
        working_clone.remotes.origin.pull()
        wf_file = work_dir / "workflows" / "git_sync_test_conflict.py"
        wf_file.write_text(SAMPLE_WORKFLOW_UPDATED)
        working_clone.index.add(["workflows/git_sync_test_conflict.py"])
        working_clone.index.commit("modify workflow in repo")
        working_clone.remotes.origin.push()

        # Modify in platform (different change)
        wf.name = "Conflict Test Workflow Platform Modified"
        await db_session.commit()

        # Preview should show conflict
        preview = await sync_service.preview()
        assert len(preview.conflicts) > 0

        conflict_paths = [c.path for c in preview.conflicts]
        # The conflict could be on the manifest or the workflow file
        assert any(
            "git_sync_test_conflict" in p or "metadata.yaml" in p
            for p in conflict_paths
        ), f"Expected conflict on test file, got: {conflict_paths}"

    async def test_platform_modified_repo_deleted_is_conflict(
        self,
        db_session: AsyncSession,
        sync_service,
        working_clone,
    ):
        """Push, modify platform + delete repo → conflict detected."""
        wf_id = uuid4()
        wf = Workflow(
            id=wf_id,
            name="Delete Conflict Test",
            function_name="delete_conflict_wf",
            path="workflows/git_sync_test_del_conflict.py",
            is_active=True,
        )
        db_session.add(wf)
        await db_session.commit()

        # Push
        await sync_service.push()

        # Delete in repo
        work_dir = Path(working_clone.working_dir)
        working_clone.remotes.origin.pull()
        wf_file = work_dir / "workflows" / "git_sync_test_del_conflict.py"
        if wf_file.exists():
            wf_file.unlink()
        working_clone.index.remove(["workflows/git_sync_test_del_conflict.py"])
        working_clone.index.commit("delete workflow in repo")
        working_clone.remotes.origin.push()

        # Modify in platform
        wf.name = "Delete Conflict Test Modified"
        wf.description = "Modified after repo deletion"
        await db_session.commit()

        # Preview should detect conflict
        preview = await sync_service.preview()
        # Either an explicit conflict or a to_pull delete + to_push modify
        has_conflict = len(preview.conflicts) > 0
        has_divergence = (
            any("del_conflict" in a.path for a in preview.to_pull) and
            any("del_conflict" in a.path or "metadata" in a.path for a in preview.to_push)
        )
        assert has_conflict or has_divergence, (
            f"Expected conflict or divergence. conflicts={preview.conflicts}, "
            f"to_pull={preview.to_pull}, to_push={preview.to_push}"
        )


# =============================================================================
# Round-Trip
# =============================================================================


@pytest.mark.integration
@pytest.mark.asyncio
class TestRoundTrip:
    """Entity identity preserved through push/pull cycles."""

    async def test_workflow_survives_round_trip(
        self,
        db_session: AsyncSession,
        sync_service,
        working_clone,
    ):
        """Create → push → modify in repo → pull → ID preserved, content matches."""
        wf_id = uuid4()
        wf = Workflow(
            id=wf_id,
            name="Round Trip Test",
            function_name="round_trip_wf",
            path="workflows/git_sync_test_roundtrip.py",
            is_active=True,
        )
        db_session.add(wf)
        await db_session.commit()

        # Push
        await sync_service.push()

        # Modify in repo
        work_dir = Path(working_clone.working_dir)
        working_clone.remotes.origin.pull()
        wf_file = work_dir / "workflows" / "git_sync_test_roundtrip.py"
        wf_file.write_text(SAMPLE_WORKFLOW_UPDATED)
        working_clone.index.add(["workflows/git_sync_test_roundtrip.py"])
        working_clone.index.commit("update workflow content")
        working_clone.remotes.origin.push()

        # Pull
        result = await sync_service.pull()
        assert result.success is True

        # ID should be preserved
        await db_session.refresh(wf)
        assert wf.id == wf_id
        assert wf.is_active is True

        # file_index should have updated content
        fi_result = await db_session.execute(
            select(FileIndex).where(
                FileIndex.path == "workflows/git_sync_test_roundtrip.py"
            )
        )
        fi = fi_result.scalar_one_or_none()
        assert fi is not None
        assert "Updated" in fi.content

    async def test_form_uuid_refs_round_trip(
        self,
        db_session: AsyncSession,
        sync_service,
        working_clone,
        bare_repo,
        tmp_path,
    ):
        """Create workflow + form → push → verify form yaml has UUID ref → pull → UUID preserved."""
        wf_id = uuid4()
        wf = Workflow(
            id=wf_id,
            name="Form Ref Workflow",
            function_name="form_ref_wf",
            path="workflows/git_sync_test_formref.py",
            is_active=True,
        )
        db_session.add(wf)

        form_id = uuid4()
        form = Form(
            id=form_id,
            name="Form Ref Test",
            workflow_id=str(wf_id),
            is_active=True,
        )
        db_session.add(form)
        await db_session.commit()

        # Push
        await sync_service.push()

        # Verify form yaml in repo contains UUID reference
        verify_path = tmp_path / "verify"
        Repo.clone_from(f"file://{bare_repo}", str(verify_path))

        # Find the form yaml
        form_files = list((verify_path / "forms").glob("*.form.yaml")) if (verify_path / "forms").exists() else []
        assert len(form_files) >= 1, "Form yaml should exist in repo"

        form_yaml = form_files[0].read_text()
        assert str(wf_id) in form_yaml, "Form yaml should contain workflow UUID reference"

        # Pull back
        result = await sync_service.pull()
        assert result.success is True

        # UUID should be preserved
        await db_session.refresh(form)
        assert str(form.workflow_id) == str(wf_id)


# =============================================================================
# Orphan Detection
# =============================================================================


@pytest.mark.integration
@pytest.mark.asyncio
class TestOrphanDetection:
    """Orphan warnings when referenced workflows are deleted."""

    async def test_orphan_warning_on_workflow_delete(
        self,
        db_session: AsyncSession,
        sync_service,
        working_clone,
    ):
        """Push workflow + form referencing it, delete workflow in repo → preview warns."""
        wf_id = uuid4()
        wf = Workflow(
            id=wf_id,
            name="Orphan Source Workflow",
            function_name="orphan_source_wf",
            path="workflows/git_sync_test_orphan.py",
            is_active=True,
        )
        db_session.add(wf)

        form_id = uuid4()
        form = Form(
            id=form_id,
            name="Orphan Form Test",
            workflow_id=str(wf_id),
            is_active=True,
        )
        db_session.add(form)
        await db_session.commit()

        # Push both
        await sync_service.push()

        # Delete workflow from repo (keep form)
        work_dir = Path(working_clone.working_dir)
        working_clone.remotes.origin.pull()
        wf_file = work_dir / "workflows" / "git_sync_test_orphan.py"
        if wf_file.exists():
            wf_file.unlink()
        working_clone.index.remove(["workflows/git_sync_test_orphan.py"])
        working_clone.index.commit("delete workflow, leave form")
        working_clone.remotes.origin.push()

        # Preview should warn about orphan
        preview = await sync_service.preview()

        # Check preflight for orphan warnings
        has_orphan_warning = any(
            i.category == "orphan" for i in preview.preflight.issues
        )

        assert has_orphan_warning, (
            "Preview should warn about orphaned form referencing deleted workflow"
        )


# =============================================================================
# Preflight Validation
# =============================================================================


@pytest.mark.integration
@pytest.mark.asyncio
class TestPreflightValidation:
    """Preflight checks validate repo health before sync."""

    async def test_preflight_catches_syntax_error(
        self,
        sync_service,
        working_clone,
    ):
        """Commit .py with syntax error → preflight returns error."""
        work_dir = Path(working_clone.working_dir)

        wf_dir = work_dir / "workflows"
        wf_dir.mkdir(exist_ok=True)
        (wf_dir / "test_git_bad_syntax.py").write_text(SAMPLE_WORKFLOW_SYNTAX_ERROR)

        bifrost_dir = work_dir / ".bifrost"
        bifrost_dir.mkdir(exist_ok=True)
        (bifrost_dir / "metadata.yaml").write_text(_make_manifest(
            workflows={
                "Bad Workflow": {
                    "id": str(uuid4()),
                    "path": "workflows/test_git_bad_syntax.py",
                    "function_name": "bad_workflow",
                    "type": "workflow",
                }
            }
        ))

        working_clone.index.add([
            "workflows/test_git_bad_syntax.py",
            ".bifrost/metadata.yaml",
        ])
        working_clone.index.commit("add bad workflow")
        working_clone.remotes.origin.push()

        preflight = await sync_service.preflight()

        assert preflight.valid is False
        syntax_issues = [i for i in preflight.issues if i.category == "syntax"]
        assert len(syntax_issues) > 0, "Should have syntax error issues"

    async def test_preflight_catches_unresolved_ref(
        self,
        sync_service,
        working_clone,
    ):
        """Commit form yaml referencing nonexistent UUID → preflight returns error."""
        work_dir = Path(working_clone.working_dir)

        fake_wf_id = str(uuid4())
        form_id = str(uuid4())

        forms_dir = work_dir / "forms"
        forms_dir.mkdir(exist_ok=True)
        (forms_dir / f"{form_id}.form.yaml").write_text(
            SAMPLE_FORM_YAML.format(workflow_id=fake_wf_id)
        )

        bifrost_dir = work_dir / ".bifrost"
        bifrost_dir.mkdir(exist_ok=True)
        (bifrost_dir / "metadata.yaml").write_text(_make_manifest(
            forms={
                "Onboarding Form": {
                    "id": form_id,
                    "path": f"forms/{form_id}.form.yaml",
                }
            }
            # No workflow in manifest — ref is unresolved
        ))

        working_clone.index.add([
            f"forms/{form_id}.form.yaml",
            ".bifrost/metadata.yaml",
        ])
        working_clone.index.commit("add form with bad ref")
        working_clone.remotes.origin.push()

        preflight = await sync_service.preflight()

        assert preflight.valid is False
        ref_issues = [i for i in preflight.issues if i.category == "ref"]
        assert len(ref_issues) > 0, "Should have unresolved ref issues"

    async def test_preflight_catches_ruff_violations(
        self,
        sync_service,
        working_clone,
    ):
        """Commit .py with linting issues → preflight returns warnings."""
        work_dir = Path(working_clone.working_dir)

        wf_dir = work_dir / "workflows"
        wf_dir.mkdir(exist_ok=True)
        (wf_dir / "test_git_lint.py").write_text(SAMPLE_WORKFLOW_RUFF_ISSUES)

        bifrost_dir = work_dir / ".bifrost"
        bifrost_dir.mkdir(exist_ok=True)
        (bifrost_dir / "metadata.yaml").write_text(_make_manifest(
            workflows={
                "Lint Issues Workflow": {
                    "id": str(uuid4()),
                    "path": "workflows/test_git_lint.py",
                    "function_name": "lint_issues_wf",
                    "type": "workflow",
                }
            }
        ))

        working_clone.index.add([
            "workflows/test_git_lint.py",
            ".bifrost/metadata.yaml",
        ])
        working_clone.index.commit("add lint-issues workflow")
        working_clone.remotes.origin.push()

        preflight = await sync_service.preflight()

        lint_issues = [i for i in preflight.issues if i.category == "lint"]
        assert len(lint_issues) > 0, "Should have lint warning issues"
        # Lint issues should be warnings, not errors
        assert all(i.severity == "warning" for i in lint_issues)

    async def test_preflight_passes_clean_repo(
        self,
        sync_service,
        working_clone,
    ):
        """Valid repo → preflight returns clean."""
        work_dir = Path(working_clone.working_dir)

        wf_dir = work_dir / "workflows"
        wf_dir.mkdir(exist_ok=True)
        (wf_dir / "test_git_clean.py").write_text(SAMPLE_WORKFLOW_CLEAN)

        bifrost_dir = work_dir / ".bifrost"
        bifrost_dir.mkdir(exist_ok=True)
        (bifrost_dir / "metadata.yaml").write_text(_make_manifest(
            workflows={
                "Clean Workflow": {
                    "id": str(uuid4()),
                    "path": "workflows/test_git_clean.py",
                    "function_name": "clean_wf",
                    "type": "workflow",
                }
            }
        ))

        working_clone.index.add([
            "workflows/test_git_clean.py",
            ".bifrost/metadata.yaml",
        ])
        working_clone.index.commit("add clean workflow")
        working_clone.remotes.origin.push()

        preflight = await sync_service.preflight()

        assert preflight.valid is True
        errors = [i for i in preflight.issues if i.severity == "error"]
        assert len(errors) == 0, f"Should have no errors, got: {errors}"
