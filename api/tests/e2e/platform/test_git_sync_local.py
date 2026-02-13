"""
Git Sync Tests — desktop-style git operations (commit, push, pull, fetch, etc.).

Uses local bare git repos (no GitHub needed). Tests validate the desktop-style
interface on GitHubSyncService: desktop_commit, desktop_push, desktop_pull,
desktop_fetch, desktop_status, desktop_diff, desktop_resolve, and preflight.

For "push from platform" tests, entity files are written to the persistent
dir (simulating what RepoSyncWriter does in production via dual-write to S3).

Fixtures:
- bare_repo: local bare git repo (tmp_path)
- working_clone: a working clone for committing test data
- sync_service: GitHubSyncService configured against local bare repo
"""

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
from src.services.manifest import read_manifest_from_dir


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


def write_entity_to_repo(persistent_dir: Path, rel_path: str, content: str) -> None:
    """Write a file to the persistent repo dir, simulating RepoSyncWriter dual-write."""
    target = persistent_dir / rel_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content)


def remove_entity_from_repo(persistent_dir: Path, rel_path: str) -> None:
    """Remove a file from the persistent repo dir, simulating RepoSyncWriter deletion."""
    target = persistent_dir / rel_path
    if target.exists():
        target.unlink()


async def write_manifest_to_repo(db_session: AsyncSession, persistent_dir: Path) -> None:
    """Generate manifest from DB and write to persistent dir, simulating RepoSyncWriter.regenerate_manifest()."""
    from src.services.manifest_generator import generate_manifest
    from src.services.manifest import write_manifest_to_dir
    manifest = await generate_manifest(db_session)
    # Filter out entities whose files don't exist in the persistent dir
    # (the test DB may contain entities from other fixtures)
    manifest.workflows = {
        k: v for k, v in manifest.workflows.items()
        if (persistent_dir / v.path).exists()
    }
    manifest.forms = {
        k: v for k, v in manifest.forms.items()
        if (persistent_dir / v.path).exists()
    }
    manifest.agents = {
        k: v for k, v in manifest.agents.items()
        if (persistent_dir / v.path).exists()
    }
    manifest.apps = {
        k: v for k, v in manifest.apps.items()
        if (persistent_dir / v.path).exists()
    }
    # Clear non-file entities that leak from other tests
    manifest.integrations = {}
    manifest.configs = {}
    manifest.tables = {}
    manifest.knowledge = {}
    manifest.events = {}
    write_manifest_to_dir(manifest, persistent_dir / ".bifrost")


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def bare_repo(tmp_path):
    """Local bare git repo with 'main' as default branch."""
    repo_path = tmp_path / "test-repo.git"
    Repo.init(str(repo_path), bare=True)
    # Set HEAD to point to main instead of master
    (repo_path / "HEAD").write_text("ref: refs/heads/main\n")
    return repo_path


@pytest.fixture
def working_clone(tmp_path, bare_repo):
    """Working clone for committing test data on 'main' branch."""
    work_path = tmp_path / "work"
    # Init a fresh repo and add origin
    repo = Repo.init(str(work_path))
    repo.create_remote("origin", str(bare_repo))
    # Create initial commit
    (work_path / ".gitkeep").touch()
    repo.index.add([".gitkeep"])
    repo.index.commit("initial")
    # Rename default branch to main and push
    repo.heads[0].rename("main")
    repo.remotes.origin.push(refspec="main:main")
    # Set upstream tracking
    repo.heads.main.set_tracking_branch(repo.remotes.origin.refs.main)
    return repo


@pytest_asyncio.fixture
async def sync_service(db_session: AsyncSession, bare_repo, tmp_path):
    """
    GitHubSyncService configured against the local bare repo.

    Uses file:// protocol to talk to the bare repo on disk.
    Replaces GitRepoManager.checkout() with a local-only version
    that persists state in a temp dir (simulating S3 persistence).
    """
    import shutil
    from contextlib import asynccontextmanager
    from src.services.github_sync import GitHubSyncService

    service = GitHubSyncService(
        db=db_session,
        repo_url=f"file://{bare_repo}",
        branch="main",
    )

    # Replace checkout() with a local-only version that simulates
    # S3 persistence by using a persistent dir on disk
    persistent_dir = tmp_path / "persistent_repo"
    persistent_dir.mkdir()

    @asynccontextmanager
    async def local_checkout():
        import tempfile
        work_dir = Path(tempfile.mkdtemp(prefix="bifrost-test-repo-"))
        try:
            # Sync down: copy persistent state to work dir
            if any(persistent_dir.iterdir()):
                shutil.copytree(persistent_dir, work_dir, dirs_exist_ok=True)
            yield work_dir
            # Sync up: copy work dir back to persistent state
            shutil.rmtree(persistent_dir)
            shutil.copytree(work_dir, persistent_dir)
        finally:
            shutil.rmtree(work_dir, ignore_errors=True)

    service.repo_manager.checkout = local_checkout
    service._persistent_dir = persistent_dir  # Expose for tests

    return service


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
    await db_session.execute(
        delete(FileIndex).where(FileIndex.path.like("forms/%"))
    )
    await db_session.execute(
        delete(FileIndex).where(FileIndex.path.like("agents/%"))
    )

    # Clean up child records before parents (foreign key dependencies)
    from src.models.orm.agents import Agent, AgentTool
    await db_session.execute(
        delete(AgentTool).where(
            AgentTool.agent_id.in_(
                select(Agent.id).where(Agent.created_by.in_(["file_sync", "git-sync"]))
            )
        )
    )
    from src.models.orm.forms import FormField
    await db_session.execute(
        delete(FormField).where(
            FormField.form_id.in_(
                select(Form.id).where(Form.created_by.in_(["test", "git-sync"]))
            )
        )
    )

    await db_session.execute(
        delete(Form).where(Form.created_by.in_(["test", "git-sync"]))
    )
    await db_session.execute(
        delete(Agent).where(Agent.created_by.in_(["file_sync", "git-sync"]))
    )

    # Clean up new entity types created by git-sync tests
    from src.models.orm.events import EventSubscription, EventSource, ScheduleSource, WebhookSource
    from src.models.orm.config import Config
    from src.models.orm.integrations import Integration, IntegrationConfigSchema, IntegrationMapping
    from src.models.orm.tables import Table

    await db_session.execute(
        delete(EventSubscription).where(EventSubscription.created_by == "git-sync")
    )
    await db_session.execute(
        delete(ScheduleSource).where(
            ScheduleSource.event_source_id.in_(
                select(EventSource.id).where(EventSource.created_by == "git-sync")
            )
        )
    )
    await db_session.execute(
        delete(WebhookSource).where(
            WebhookSource.event_source_id.in_(
                select(EventSource.id).where(EventSource.created_by == "git-sync")
            )
        )
    )
    await db_session.execute(
        delete(EventSource).where(EventSource.created_by == "git-sync")
    )
    await db_session.execute(
        delete(Config).where(Config.updated_by == "git-sync")
    )
    await db_session.execute(
        delete(IntegrationConfigSchema).where(
            IntegrationConfigSchema.integration_id.in_(
                select(Integration.id).where(Integration.name.like("Test%"))
            )
        )
    )
    await db_session.execute(
        delete(IntegrationConfigSchema).where(
            IntegrationConfigSchema.integration_id.in_(
                select(Integration.id).where(Integration.name.like("Idempotent%"))
            )
        )
    )
    await db_session.execute(
        delete(IntegrationMapping).where(
            IntegrationMapping.integration_id.in_(
                select(Integration.id).where(Integration.name.like("Test%"))
            )
        )
    )
    await db_session.execute(
        delete(Integration).where(Integration.name.like("Test%"))
    )
    await db_session.execute(
        delete(Integration).where(Integration.name.like("Idempotent%"))
    )
    await db_session.execute(
        delete(Table).where(Table.created_by == "git-sync")
    )
    await db_session.commit()


# =============================================================================
# Platform → Empty Repo (Initial Export)
# =============================================================================


@pytest.mark.e2e
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
        Create entities in DB, write file to repo dir, commit + push →
        clone and verify workflow .py files, manifest.
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

        # Write workflow file to persistent dir (simulates RepoSyncWriter)
        write_entity_to_repo(
            sync_service._persistent_dir,
            "workflows/git_sync_test_wf.py",
            SAMPLE_WORKFLOW_PY,
        )
        await write_manifest_to_repo(db_session, sync_service._persistent_dir)

        # Commit + push
        commit_result = await sync_service.desktop_commit("initial commit")
        assert commit_result.success is True
        assert commit_result.files_committed > 0

        push_result = await sync_service.desktop_push()
        assert push_result.success is True
        assert push_result.pushed_commits > 0

        # Verify by cloning the repo and checking files
        verify_path = tmp_path / "verify"
        Repo.clone_from(f"file://{bare_repo}", str(verify_path), branch="main")

        # Workflow .py file should exist
        wf_file = verify_path / "workflows" / "git_sync_test_wf.py"
        assert wf_file.exists(), "Workflow .py file should exist in repo"

        # Split manifest files should exist (not legacy metadata.yaml)
        bifrost_dir = verify_path / ".bifrost"
        assert bifrost_dir.exists(), "Manifest directory should exist in repo"
        assert (bifrost_dir / "workflows.yaml").exists(), "Split workflows.yaml should exist"
        assert not (bifrost_dir / "metadata.yaml").exists(), "Legacy metadata.yaml should not exist"

    async def test_push_generates_manifest(
        self,
        db_session: AsyncSession,
        sync_service,
        bare_repo,
        tmp_path,
    ):
        """Commit + push → .bifrost/ split files exist with correct entries."""
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

        # Write workflow file to persistent dir (simulates RepoSyncWriter)
        write_entity_to_repo(
            sync_service._persistent_dir,
            "workflows/git_sync_test_manifest.py",
            SAMPLE_WORKFLOW_PY,
        )
        await write_manifest_to_repo(db_session, sync_service._persistent_dir)

        # Commit + push
        await sync_service.desktop_commit("initial commit")
        await sync_service.desktop_push()

        # Clone and verify manifest
        verify_path = tmp_path / "verify"
        Repo.clone_from(f"file://{bare_repo}", str(verify_path), branch="main")

        manifest = read_manifest_from_dir(verify_path / ".bifrost")

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


@pytest.mark.e2e
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
        """Commit+push, modify workflow file, commit+push again → repo has updated content."""
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

        # Write workflow file and first commit+push
        write_entity_to_repo(
            sync_service._persistent_dir,
            "workflows/git_sync_test_incremental.py",
            SAMPLE_WORKFLOW_PY,
        )
        await write_manifest_to_repo(db_session, sync_service._persistent_dir)
        result1 = await sync_service.desktop_commit("initial commit")
        assert result1.success is True
        await sync_service.desktop_push()

        # Modify the workflow name in DB and update file in persistent dir
        wf.name = "Git Sync Test Workflow Updated"
        wf.description = "Updated description"
        await db_session.commit()
        write_entity_to_repo(
            sync_service._persistent_dir,
            "workflows/git_sync_test_incremental.py",
            SAMPLE_WORKFLOW_UPDATED,
        )
        await write_manifest_to_repo(db_session, sync_service._persistent_dir)

        # Second commit+push
        result2 = await sync_service.desktop_commit("update workflow")
        assert result2.success is True
        await sync_service.desktop_push()

        # Verify updated content
        verify_path = tmp_path / "verify"
        Repo.clone_from(f"file://{bare_repo}", str(verify_path), branch="main")
        manifest = read_manifest_from_dir(verify_path / ".bifrost")
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
        """Commit+push, delete workflow file, commit+push again → file gone from repo."""
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

        # Write file and first commit+push
        write_entity_to_repo(
            sync_service._persistent_dir,
            "workflows/git_sync_test_delete.py",
            SAMPLE_WORKFLOW_PY,
        )
        await write_manifest_to_repo(db_session, sync_service._persistent_dir)
        await sync_service.desktop_commit("initial commit")
        await sync_service.desktop_push()

        # Deactivate the workflow and remove file from persistent dir
        wf.is_active = False
        await db_session.commit()
        remove_entity_from_repo(
            sync_service._persistent_dir,
            "workflows/git_sync_test_delete.py",
        )
        await write_manifest_to_repo(db_session, sync_service._persistent_dir)

        # Second commit+push
        await sync_service.desktop_commit("delete workflow")
        await sync_service.desktop_push()

        # Verify file is gone
        verify_path = tmp_path / "verify"
        Repo.clone_from(f"file://{bare_repo}", str(verify_path), branch="main")
        wf_file = verify_path / "workflows" / "git_sync_test_delete.py"
        assert not wf_file.exists(), "Deleted workflow file should be gone from repo"


# =============================================================================
# Repo → Platform (Pull)
# =============================================================================


@pytest.mark.e2e
@pytest.mark.asyncio
class TestPull:
    """Pull changes from repo into platform."""

    async def test_pull_new_workflow(
        self,
        db_session: AsyncSession,
        sync_service,
        working_clone,
    ):
        """Commit .py with @workflow to repo, desktop_pull → workflows table + file_index populated."""
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
        result = await sync_service.desktop_pull()

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
        """Commit .form.yaml to repo, desktop_pull → forms table populated."""
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
        result = await sync_service.desktop_pull()
        assert result.success is True

        # Verify form in DB
        form_result = await db_session.execute(
            select(Form).where(Form.id == form_id)
        )
        form = form_result.scalar_one_or_none()
        assert form is not None
        assert form.name == "Onboarding Form"

    async def test_pull_new_form_with_fields(
        self,
        db_session: AsyncSession,
        sync_service,
        working_clone,
    ):
        """Form pulled from repo should have field definitions."""
        from src.models.orm.forms import Form, FormField
        from src.models.orm.workflows import Workflow

        work_dir = Path(working_clone.working_dir)

        # Create a workflow to be referenced
        wf_id = uuid4()
        db_session.add(Workflow(
            id=wf_id,
            name="form_test_workflow",
            path="workflows/form_test.py",
            function_name="form_test_workflow",
            is_active=True,
        ))
        await db_session.flush()

        form_id = uuid4()
        form_yaml = f"""name: Test Form With Fields
description: Form with field definitions
workflow_id: {wf_id}
form_schema:
  fields:
  - name: email
    type: text
    label: Email Address
    required: true
  - name: count
    type: number
    label: Count
    required: false
    default_value: 5
"""
        form_dir = work_dir / "forms"
        form_dir.mkdir(exist_ok=True)
        (form_dir / f"{form_id}.form.yaml").write_text(form_yaml)

        manifest_dir = work_dir / ".bifrost"
        manifest_dir.mkdir(exist_ok=True)
        (manifest_dir / "metadata.yaml").write_text(f"""forms:
  Test Form With Fields:
    id: "{form_id}"
    path: forms/{form_id}.form.yaml
    organization_id: null
    roles: []
workflows: {{}}
agents: {{}}
apps: {{}}
organizations: []
roles: []
""")

        working_clone.index.add(["forms/", ".bifrost/"])
        working_clone.index.commit("Add form with fields")
        working_clone.remotes.origin.push()

        # Pull into platform
        result = await sync_service.desktop_pull()
        assert result.success is True

        # Verify form was created
        form = await db_session.get(Form, form_id)
        assert form is not None
        assert form.name == "Test Form With Fields"
        assert str(form.workflow_id) == str(wf_id)

        # Verify fields were imported
        from sqlalchemy import select
        fields = (await db_session.execute(
            select(FormField).where(FormField.form_id == form_id).order_by(FormField.position)
        )).scalars().all()
        assert len(fields) == 2
        assert fields[0].name == "email"
        assert fields[0].type == "text"
        assert fields[0].required is True
        assert fields[1].name == "count"
        assert fields[1].default_value == 5

    async def test_pull_new_agent_with_tools(
        self,
        db_session: AsyncSession,
        sync_service,
        working_clone,
    ):
        """Agent pulled from repo should have tool associations."""
        from src.models.orm.agents import Agent
        from src.models.orm.workflows import Workflow

        work_dir = Path(working_clone.working_dir)

        # Create a workflow to be referenced as a tool
        wf_id = uuid4()
        db_session.add(Workflow(
            id=wf_id,
            name="agent_tool_workflow",
            path="workflows/agent_tool.py",
            function_name="agent_tool_workflow",
            is_active=True,
        ))
        await db_session.flush()

        agent_id = uuid4()
        agent_yaml = f"""name: Test Agent With Tools
description: Agent with tool associations
system_prompt: You are a test agent.
channels:
- chat
tool_ids:
- {wf_id}
"""
        # Write agent file + workflow file + manifest
        agent_dir = work_dir / "agents"
        agent_dir.mkdir(exist_ok=True)
        (agent_dir / f"{agent_id}.agent.yaml").write_text(agent_yaml)

        wf_dir = work_dir / "workflows"
        wf_dir.mkdir(exist_ok=True)
        (wf_dir / "agent_tool.py").write_text(SAMPLE_WORKFLOW_PY)

        manifest_dir = work_dir / ".bifrost"
        manifest_dir.mkdir(exist_ok=True)
        (manifest_dir / "metadata.yaml").write_text(f"""agents:
  Test Agent With Tools:
    id: "{agent_id}"
    path: agents/{agent_id}.agent.yaml
    organization_id: null
    roles: []
workflows:
  agent_tool_workflow:
    id: "{wf_id}"
    path: workflows/agent_tool.py
    function_name: agent_tool_workflow
forms: {{}}
apps: {{}}
organizations: []
roles: []
""")

        # Commit to repo
        working_clone.index.add(["agents/", "workflows/", ".bifrost/"])
        working_clone.index.commit("Add agent with tools")
        working_clone.remotes.origin.push()

        # Pull into platform
        result = await sync_service.desktop_pull()
        assert result.success is True

        # Verify agent was created with tool association
        agent = await db_session.get(Agent, agent_id)
        assert agent is not None
        assert agent.name == "Test Agent With Tools"
        assert agent.channels == ["chat"]

        # Verify tool association
        from sqlalchemy import select
        from src.models.orm.agents import AgentTool
        tools = (await db_session.execute(
            select(AgentTool).where(AgentTool.agent_id == agent_id)
        )).scalars().all()
        assert len(tools) == 1
        assert tools[0].workflow_id == wf_id

    async def test_pull_modified_workflow(
        self,
        db_session: AsyncSession,
        sync_service,
        working_clone,
        bare_repo,
        tmp_path,
    ):
        """Commit+push, modify in repo, desktop_pull → file_index updated."""
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

        # Write file to persistent dir and commit+push
        write_entity_to_repo(
            sync_service._persistent_dir,
            "workflows/git_sync_test_modified.py",
            SAMPLE_WORKFLOW_PY,
        )
        await write_manifest_to_repo(db_session, sync_service._persistent_dir)
        await sync_service.desktop_commit("initial commit")
        await sync_service.desktop_push()

        # Modify in repo via working clone
        work_dir = Path(working_clone.working_dir)
        working_clone.remotes.origin.pull()
        wf_file = work_dir / "workflows" / "git_sync_test_modified.py"
        wf_file.write_text(SAMPLE_WORKFLOW_UPDATED)
        working_clone.index.add(["workflows/git_sync_test_modified.py"])
        working_clone.index.commit("update workflow")
        working_clone.remotes.origin.push()

        # Pull into platform
        result = await sync_service.desktop_pull()
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
        """Commit+push, delete in repo, desktop_pull → entity deactivated, file_index cleaned."""
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

        # Write file and commit+push
        write_entity_to_repo(
            sync_service._persistent_dir,
            "workflows/git_sync_test_del_pull.py",
            SAMPLE_WORKFLOW_PY,
        )
        await write_manifest_to_repo(db_session, sync_service._persistent_dir)
        await sync_service.desktop_commit("initial commit")
        await sync_service.desktop_push()

        # Delete in repo via working clone
        work_dir = Path(working_clone.working_dir)
        working_clone.remotes.origin.pull()
        wf_file = work_dir / "workflows" / "git_sync_test_del_pull.py"
        if wf_file.exists():
            wf_file.unlink()
        working_clone.index.remove(["workflows/git_sync_test_del_pull.py"])
        working_clone.index.commit("delete workflow")
        working_clone.remotes.origin.push()

        # Pull
        result = await sync_service.desktop_pull()
        assert result.success is True

        # Workflow should be hard-deleted (git history is the undo mechanism)
        wf_result = await db_session.execute(
            select(Workflow).where(Workflow.id == wf_id)
        )
        assert wf_result.scalar_one_or_none() is None

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


@pytest.mark.e2e
@pytest.mark.asyncio
class TestRenames:
    """Renames are detected correctly during sync."""

    async def test_rename_in_repo_detected_on_pull(
        self,
        db_session: AsyncSession,
        sync_service,
        working_clone,
    ):
        """Commit+push, rename file in repo, desktop_pull → platform path updated."""
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

        # Write file and commit+push
        write_entity_to_repo(
            sync_service._persistent_dir,
            "workflows/git_sync_test_rename_old.py",
            SAMPLE_WORKFLOW_PY,
        )
        await write_manifest_to_repo(db_session, sync_service._persistent_dir)
        await sync_service.desktop_commit("initial commit")
        await sync_service.desktop_push()

        # Rename in repo via working clone
        work_dir = Path(working_clone.working_dir)
        working_clone.remotes.origin.pull()
        old_file = work_dir / "workflows" / "git_sync_test_rename_old.py"
        new_file = work_dir / "workflows" / "git_sync_test_rename_new.py"
        if old_file.exists():
            new_file.write_text(old_file.read_text())
            old_file.unlink()

        # Update manifest with new path (split format: workflows.yaml)
        wf_manifest = work_dir / ".bifrost" / "workflows.yaml"
        if wf_manifest.exists():
            wf_data_yaml = yaml.safe_load(wf_manifest.read_text())
            for name, wf_data in wf_data_yaml.get("workflows", {}).items():
                if wf_data.get("id") == str(wf_id):
                    wf_data["path"] = "workflows/git_sync_test_rename_new.py"
            wf_manifest.write_text(
                yaml.dump(wf_data_yaml, default_flow_style=False, sort_keys=False)
            )

        working_clone.index.add([
            "workflows/git_sync_test_rename_new.py",
            ".bifrost/workflows.yaml",
        ])
        working_clone.index.remove(["workflows/git_sync_test_rename_old.py"])
        working_clone.index.commit("rename workflow")
        working_clone.remotes.origin.push()

        # Pull
        result = await sync_service.desktop_pull()
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
        """Commit+push, rename in platform, commit+push → repo has new path."""
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

        # Write file and commit+push
        write_entity_to_repo(
            sync_service._persistent_dir,
            "workflows/git_sync_test_plat_old.py",
            SAMPLE_WORKFLOW_PY,
        )
        await write_manifest_to_repo(db_session, sync_service._persistent_dir)
        await sync_service.desktop_commit("initial commit")
        await sync_service.desktop_push()

        # Rename in platform: remove old file, write new file, update DB path
        remove_entity_from_repo(
            sync_service._persistent_dir,
            "workflows/git_sync_test_plat_old.py",
        )
        write_entity_to_repo(
            sync_service._persistent_dir,
            "workflows/git_sync_test_plat_new.py",
            SAMPLE_WORKFLOW_PY,
        )
        wf.path = "workflows/git_sync_test_plat_new.py"
        await db_session.commit()
        await write_manifest_to_repo(db_session, sync_service._persistent_dir)

        # Commit+push again
        await sync_service.desktop_commit("rename workflow")
        await sync_service.desktop_push()

        # Verify new path in repo
        verify_path = tmp_path / "verify"
        Repo.clone_from(f"file://{bare_repo}", str(verify_path), branch="main")
        old_file = verify_path / "workflows" / "git_sync_test_plat_old.py"
        new_file = verify_path / "workflows" / "git_sync_test_plat_new.py"
        assert not old_file.exists(), "Old path should be gone"
        assert new_file.exists(), "New path should exist"


# =============================================================================
# Conflicts
# =============================================================================


@pytest.mark.e2e
@pytest.mark.asyncio
class TestConflicts:
    """Conflict detection when both sides modify."""

    async def test_both_modified_is_conflict(
        self,
        db_session: AsyncSession,
        sync_service,
        working_clone,
    ):
        """Commit+push, modify both sides, desktop_pull → conflict detected."""
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

        # Write file and commit+push
        write_entity_to_repo(
            sync_service._persistent_dir,
            "workflows/git_sync_test_conflict.py",
            SAMPLE_WORKFLOW_PY,
        )
        await write_manifest_to_repo(db_session, sync_service._persistent_dir)
        await sync_service.desktop_commit("initial commit")
        await sync_service.desktop_push()

        # Modify in repo via working clone
        work_dir = Path(working_clone.working_dir)
        working_clone.remotes.origin.pull()
        wf_file = work_dir / "workflows" / "git_sync_test_conflict.py"
        wf_file.write_text(SAMPLE_WORKFLOW_UPDATED)
        working_clone.index.add(["workflows/git_sync_test_conflict.py"])
        working_clone.index.commit("modify workflow in repo")
        working_clone.remotes.origin.push()

        # Modify in platform (different change) — write different content to persistent dir
        wf.name = "Conflict Test Workflow Platform Modified"
        await db_session.commit()
        write_entity_to_repo(
            sync_service._persistent_dir,
            "workflows/git_sync_test_conflict.py",
            SAMPLE_WORKFLOW_CLEAN,  # Different content from repo change
        )
        await write_manifest_to_repo(db_session, sync_service._persistent_dir)

        # Commit locally (creates divergent history)
        await sync_service.desktop_commit("modify workflow in platform")

        # Pull should detect conflict since both sides diverged
        pull_result = await sync_service.desktop_pull()
        assert pull_result.success is False
        assert len(pull_result.conflicts) > 0

        conflict_paths = [c.path for c in pull_result.conflicts]
        # The conflict could be on the workflow file or any manifest split file
        assert any(
            "git_sync_test_conflict" in p or ".bifrost/" in p
            for p in conflict_paths
        ), f"Expected conflict on test file, got: {conflict_paths}"

    async def test_platform_modified_repo_deleted_is_conflict(
        self,
        db_session: AsyncSession,
        sync_service,
        working_clone,
    ):
        """Commit+push, modify platform + delete in repo → conflict on pull."""
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

        # Write file and commit+push
        write_entity_to_repo(
            sync_service._persistent_dir,
            "workflows/git_sync_test_del_conflict.py",
            SAMPLE_WORKFLOW_PY,
        )
        await write_manifest_to_repo(db_session, sync_service._persistent_dir)
        await sync_service.desktop_commit("initial commit")
        await sync_service.desktop_push()

        # Delete in repo via working clone
        work_dir = Path(working_clone.working_dir)
        working_clone.remotes.origin.pull()
        wf_file = work_dir / "workflows" / "git_sync_test_del_conflict.py"
        if wf_file.exists():
            wf_file.unlink()
        working_clone.index.remove(["workflows/git_sync_test_del_conflict.py"])
        working_clone.index.commit("delete workflow in repo")
        working_clone.remotes.origin.push()

        # Modify in platform (creates divergent local commit)
        wf.name = "Delete Conflict Test Modified"
        wf.description = "Modified after repo deletion"
        await db_session.commit()
        write_entity_to_repo(
            sync_service._persistent_dir,
            "workflows/git_sync_test_del_conflict.py",
            SAMPLE_WORKFLOW_UPDATED,
        )
        await write_manifest_to_repo(db_session, sync_service._persistent_dir)
        await sync_service.desktop_commit("modify workflow in platform")

        # Pull should detect conflict (delete vs modify)
        pull_result = await sync_service.desktop_pull()
        # Either an explicit conflict or a failed merge
        has_conflict = len(pull_result.conflicts) > 0
        has_error = pull_result.success is False
        assert has_conflict or has_error, (
            f"Expected conflict or error. conflicts={pull_result.conflicts}, "
            f"success={pull_result.success}, error={pull_result.error}"
        )


# =============================================================================
# Round-Trip
# =============================================================================


@pytest.mark.e2e
@pytest.mark.asyncio
class TestRoundTrip:
    """Entity identity preserved through push/pull cycles."""

    async def test_workflow_survives_round_trip(
        self,
        db_session: AsyncSession,
        sync_service,
        working_clone,
    ):
        """Create → commit+push → modify in repo → desktop_pull → ID preserved, content matches."""
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

        # Write file and commit+push
        write_entity_to_repo(
            sync_service._persistent_dir,
            "workflows/git_sync_test_roundtrip.py",
            SAMPLE_WORKFLOW_PY,
        )
        await write_manifest_to_repo(db_session, sync_service._persistent_dir)
        await sync_service.desktop_commit("initial commit")
        await sync_service.desktop_push()

        # Modify in repo via working clone
        work_dir = Path(working_clone.working_dir)
        working_clone.remotes.origin.pull()
        wf_file = work_dir / "workflows" / "git_sync_test_roundtrip.py"
        wf_file.write_text(SAMPLE_WORKFLOW_UPDATED)
        working_clone.index.add(["workflows/git_sync_test_roundtrip.py"])
        working_clone.index.commit("update workflow content")
        working_clone.remotes.origin.push()

        # Pull
        result = await sync_service.desktop_pull()
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
        """Create workflow + form → commit+push → verify form yaml has UUID ref → pull → UUID preserved."""
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
            created_by="test",
        )
        db_session.add(form)
        await db_session.commit()

        # Write both entity files to persistent dir (simulates RepoSyncWriter)
        write_entity_to_repo(
            sync_service._persistent_dir,
            "workflows/git_sync_test_formref.py",
            SAMPLE_WORKFLOW_PY,
        )
        write_entity_to_repo(
            sync_service._persistent_dir,
            f"forms/{form_id}.form.yaml",
            SAMPLE_FORM_YAML.format(workflow_id=wf_id),
        )
        await write_manifest_to_repo(db_session, sync_service._persistent_dir)

        # Commit + push
        await sync_service.desktop_commit("initial commit")
        await sync_service.desktop_push()

        # Verify form yaml in repo contains UUID reference
        verify_path = tmp_path / "verify"
        Repo.clone_from(f"file://{bare_repo}", str(verify_path), branch="main")

        # Find our specific form yaml by ID
        form_file = verify_path / "forms" / f"{form_id}.form.yaml"
        assert form_file.exists(), f"Form yaml should exist in repo at forms/{form_id}.form.yaml"

        form_yaml = form_file.read_text()
        assert str(wf_id) in form_yaml, "Form yaml should contain workflow UUID reference"

        # Pull back
        result = await sync_service.desktop_pull()
        assert result.success is True

        # UUID should be preserved
        await db_session.refresh(form)
        assert str(form.workflow_id) == str(wf_id)

    async def test_agent_with_tools_survives_round_trip(
        self,
        db_session: AsyncSession,
        sync_service,
        working_clone,
        bare_repo,
        tmp_path,
    ):
        """Create agent with tools -> commit+push -> pull back -> tools preserved."""
        from src.models.orm.agents import Agent, AgentTool
        from src.models.orm.workflows import Workflow as WfModel

        # Create workflow (tool) and agent in DB
        wf_id = uuid4()
        db_session.add(WfModel(
            id=wf_id,
            name="RT Agent Tool WF",
            path="workflows/git_sync_test_rt_agent_tool.py",
            function_name="rt_agent_tool_wf",
            is_active=True,
        ))

        agent_id = uuid4()
        agent = Agent(
            id=agent_id,
            name="Round Trip Agent",
            system_prompt="Test agent for round trip",
            channels=["chat"],
            is_active=True,
            created_by="file_sync",
        )
        db_session.add(agent)
        await db_session.flush()

        # Add tool association
        db_session.add(AgentTool(agent_id=agent_id, workflow_id=wf_id))
        await db_session.commit()

        # Write agent YAML and workflow file to persistent dir
        agent_yaml = f"""id: {agent_id}
name: Round Trip Agent
system_prompt: Test agent for round trip
channels:
- chat
tool_ids:
- {wf_id}
"""
        write_entity_to_repo(
            sync_service._persistent_dir,
            f"agents/{agent_id}.agent.yaml",
            agent_yaml,
        )
        write_entity_to_repo(
            sync_service._persistent_dir,
            "workflows/git_sync_test_rt_agent_tool.py",
            SAMPLE_WORKFLOW_PY,
        )
        await write_manifest_to_repo(db_session, sync_service._persistent_dir)

        # Commit + push
        commit_result = await sync_service.desktop_commit("initial commit with agent")
        assert commit_result.success is True
        await sync_service.desktop_push()

        # Verify agent YAML exists in repo with tool_ids
        verify_path = tmp_path / "verify"
        Repo.clone_from(f"file://{bare_repo}", str(verify_path), branch="main")
        agent_file = verify_path / "agents" / f"{agent_id}.agent.yaml"
        assert agent_file.exists(), "Agent YAML should be in repo"
        agent_content = agent_file.read_text()
        assert str(wf_id) in agent_content, "Agent YAML should contain tool UUID"

        # Pull back
        result = await sync_service.desktop_pull()
        assert result.success is True

        # Verify agent still exists with tools
        await db_session.refresh(agent)
        assert agent.name == "Round Trip Agent"
        assert agent.channels == ["chat"]

        tools = (await db_session.execute(
            select(AgentTool).where(AgentTool.agent_id == agent_id)
        )).scalars().all()
        assert len(tools) >= 1, f"Agent should still have tool associations, got {len(tools)}"
        assert any(t.workflow_id == wf_id for t in tools)

    async def test_form_with_fields_survives_round_trip(
        self,
        db_session: AsyncSession,
        sync_service,
        working_clone,
        bare_repo,
        tmp_path,
    ):
        """Create form with fields -> commit+push -> pull back -> fields preserved."""
        from src.models.orm.forms import FormField
        from src.models.orm.workflows import Workflow as WfModel

        # Create workflow and form in DB
        wf_id = uuid4()
        db_session.add(WfModel(
            id=wf_id,
            name="RT Form WF",
            path="workflows/git_sync_test_rt_form.py",
            function_name="rt_form_wf",
            is_active=True,
        ))

        form_id = uuid4()
        form = Form(
            id=form_id,
            name="Round Trip Form",
            description="Test form for round trip",
            workflow_id=str(wf_id),
            is_active=True,
            created_by="test",
        )
        db_session.add(form)
        await db_session.flush()

        # Add form fields
        db_session.add(FormField(
            form_id=form_id,
            name="email",
            type="text",
            label="Email Address",
            required=True,
            position=0,
        ))
        db_session.add(FormField(
            form_id=form_id,
            name="count",
            type="number",
            label="Count",
            required=False,
            default_value=5,
            position=1,
        ))
        await db_session.commit()

        # Write form YAML and workflow file to persistent dir
        form_yaml = f"""id: {form_id}
name: Round Trip Form
description: Test form for round trip
workflow_id: {wf_id}
form_schema:
  fields:
  - name: email
    type: text
    label: Email Address
    required: true
  - name: count
    type: number
    label: Count
    required: false
    default_value: 5
"""
        write_entity_to_repo(
            sync_service._persistent_dir,
            f"forms/{form_id}.form.yaml",
            form_yaml,
        )
        write_entity_to_repo(
            sync_service._persistent_dir,
            "workflows/git_sync_test_rt_form.py",
            SAMPLE_WORKFLOW_PY,
        )
        await write_manifest_to_repo(db_session, sync_service._persistent_dir)

        # Commit + push
        commit_result = await sync_service.desktop_commit("initial commit with form")
        assert commit_result.success is True
        await sync_service.desktop_push()

        # Verify form YAML exists in repo
        verify_path = tmp_path / "verify"
        Repo.clone_from(f"file://{bare_repo}", str(verify_path), branch="main")
        form_file = verify_path / "forms" / f"{form_id}.form.yaml"
        assert form_file.exists(), "Form YAML should be in repo"

        # Pull back
        result = await sync_service.desktop_pull()
        assert result.success is True

        # Verify form still exists with fields
        await db_session.refresh(form)
        assert form.name == "Round Trip Form"
        assert str(form.workflow_id) == str(wf_id)

        fields = (await db_session.execute(
            select(FormField).where(FormField.form_id == form_id).order_by(FormField.position)
        )).scalars().all()
        assert len(fields) == 2, f"Form should have 2 fields, got {len(fields)}"
        assert fields[0].name == "email"
        assert fields[0].required is True
        assert fields[1].name == "count"
        assert fields[1].default_value == 5


# =============================================================================
# Orphan Detection
# =============================================================================


@pytest.mark.e2e
@pytest.mark.asyncio
class TestOrphanDetection:
    """Orphan warnings when referenced workflows are deleted."""

    async def test_orphan_warning_on_workflow_delete(
        self,
        db_session: AsyncSession,
        sync_service,
        working_clone,
    ):
        """Commit+push workflow + form, delete workflow in repo, pull → preflight warns about orphan on next commit attempt."""
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
            created_by="test",
        )
        db_session.add(form)
        await db_session.commit()

        # Write both entity files and commit+push
        write_entity_to_repo(
            sync_service._persistent_dir,
            "workflows/git_sync_test_orphan.py",
            SAMPLE_WORKFLOW_PY,
        )
        write_entity_to_repo(
            sync_service._persistent_dir,
            f"forms/{form_id}.form.yaml",
            SAMPLE_FORM_YAML.format(workflow_id=wf_id),
        )
        await write_manifest_to_repo(db_session, sync_service._persistent_dir)
        await sync_service.desktop_commit("initial commit")
        await sync_service.desktop_push()

        # Delete workflow from repo via working clone (keep form)
        work_dir = Path(working_clone.working_dir)
        working_clone.remotes.origin.pull()
        wf_file = work_dir / "workflows" / "git_sync_test_orphan.py"
        if wf_file.exists():
            wf_file.unlink()
        # Update manifest to remove the workflow entry (split format)
        wf_manifest = work_dir / ".bifrost" / "workflows.yaml"
        if wf_manifest.exists():
            wf_manifest.unlink()
        working_clone.git.add(A=True)
        working_clone.index.commit("delete workflow, leave form")
        working_clone.remotes.origin.push()

        # Pull the changes from repo
        await sync_service.desktop_pull()

        # Now run preflight — orphan detection happens here
        # The form still references a workflow UUID that is no longer in the manifest
        preflight = await sync_service.preflight()

        # Check preflight for orphan warnings
        has_orphan_warning = any(
            i.category == "orphan" for i in preflight.issues
        )

        assert has_orphan_warning, (
            f"Preflight should warn about orphaned form referencing deleted workflow. "
            f"Issues: {preflight.issues}"
        )


# =============================================================================
# Preflight Validation
# =============================================================================


@pytest.mark.e2e
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


# =============================================================================
# Split Manifest Format
# =============================================================================


@pytest.mark.e2e
@pytest.mark.asyncio
class TestSplitManifestFormat:
    """Verify split manifest files work through commit/pull cycle."""

    async def test_push_creates_split_files(
        self,
        db_session: AsyncSession,
        sync_service,
        bare_repo,
        tmp_path,
    ):
        """Commit+push → .bifrost/ contains per-entity-type YAML files, not metadata.yaml."""
        wf_id = uuid4()
        wf = Workflow(
            id=wf_id,
            name="Split Manifest Test WF",
            function_name="split_manifest_wf",
            path="workflows/git_sync_test_split.py",
            is_active=True,
        )
        db_session.add(wf)
        await db_session.commit()

        write_entity_to_repo(
            sync_service._persistent_dir,
            "workflows/git_sync_test_split.py",
            SAMPLE_WORKFLOW_PY,
        )
        await write_manifest_to_repo(db_session, sync_service._persistent_dir)

        await sync_service.desktop_commit("initial commit")
        await sync_service.desktop_push()

        # Clone and verify split files
        verify_path = tmp_path / "verify"
        Repo.clone_from(f"file://{bare_repo}", str(verify_path), branch="main")

        bifrost_dir = verify_path / ".bifrost"
        assert (bifrost_dir / "workflows.yaml").exists(), "workflows.yaml should exist"
        assert not (bifrost_dir / "metadata.yaml").exists(), "legacy metadata.yaml should not exist"

        # Verify content
        wf_data = yaml.safe_load((bifrost_dir / "workflows.yaml").read_text())
        assert "workflows" in wf_data
        found = any(
            wf_entry.get("id") == str(wf_id)
            for wf_entry in wf_data["workflows"].values()
        )
        assert found, f"Workflow {wf_id} should be in workflows.yaml"

    async def test_pull_integration_from_manifest(
        self,
        db_session: AsyncSession,
        sync_service,
        working_clone,
    ):
        """Pull manifest with integration → creates Integration, config_schema, mappings in DB."""
        from src.models.orm.integrations import Integration, IntegrationConfigSchema

        work_dir = Path(working_clone.working_dir)
        integ_id = str(uuid4())

        # Write split manifest with integration
        bifrost_dir = work_dir / ".bifrost"
        bifrost_dir.mkdir(exist_ok=True)
        (bifrost_dir / "integrations.yaml").write_text(yaml.dump({
            "integrations": {
                "TestInteg": {
                    "id": integ_id,
                    "entity_id": "tenant_id",
                    "entity_id_name": "Tenant",
                    "config_schema": [
                        {"key": "api_url", "type": "string", "required": True, "position": 0},
                        {"key": "api_key", "type": "secret", "required": True, "position": 1},
                    ],
                    "mappings": [],
                },
            },
        }, default_flow_style=False))

        working_clone.index.add([".bifrost/integrations.yaml"])
        working_clone.index.commit("add integration")
        working_clone.remotes.origin.push()

        result = await sync_service.desktop_pull()
        assert result.success is True

        # Verify integration in DB
        from uuid import UUID as UUIDType
        integ = await db_session.get(Integration, UUIDType(integ_id))
        assert integ is not None
        assert integ.name == "TestInteg"
        assert integ.entity_id == "tenant_id"

        # Verify config schema
        cs_result = await db_session.execute(
            select(IntegrationConfigSchema).where(
                IntegrationConfigSchema.integration_id == UUIDType(integ_id)
            ).order_by(IntegrationConfigSchema.position)
        )
        schemas = cs_result.scalars().all()
        assert len(schemas) == 2
        assert schemas[0].key == "api_url"
        assert schemas[0].type == "string"
        assert schemas[1].key == "api_key"
        assert schemas[1].type == "secret"

    async def test_pull_config_from_manifest(
        self,
        db_session: AsyncSession,
        sync_service,
        working_clone,
    ):
        """Pull manifest with configs → creates Config entries in DB."""
        from src.models.orm.config import Config

        work_dir = Path(working_clone.working_dir)
        config_id = str(uuid4())

        bifrost_dir = work_dir / ".bifrost"
        bifrost_dir.mkdir(exist_ok=True)
        (bifrost_dir / "configs.yaml").write_text(yaml.dump({
            "configs": {
                "app/api_url": {
                    "id": config_id,
                    "key": "app/api_url",
                    "config_type": "string",
                    "description": "API Base URL",
                    "value": "https://api.example.com",
                },
            },
        }, default_flow_style=False))

        working_clone.index.add([".bifrost/configs.yaml"])
        working_clone.index.commit("add config")
        working_clone.remotes.origin.push()

        result = await sync_service.desktop_pull()
        assert result.success is True

        # Verify config in DB
        from uuid import UUID as UUIDType
        cfg = await db_session.get(Config, UUIDType(config_id))
        assert cfg is not None
        assert cfg.key == "app/api_url"
        assert cfg.config_type == "string"
        assert cfg.value == "https://api.example.com"

    async def test_pull_table_from_manifest(
        self,
        db_session: AsyncSession,
        sync_service,
        working_clone,
    ):
        """Pull manifest with table → creates Table in DB with schema."""
        from src.models.orm.tables import Table

        work_dir = Path(working_clone.working_dir)
        table_id = str(uuid4())

        bifrost_dir = work_dir / ".bifrost"
        bifrost_dir.mkdir(exist_ok=True)
        (bifrost_dir / "tables.yaml").write_text(yaml.dump({
            "tables": {
                "ticket_cache": {
                    "id": table_id,
                    "description": "Cached tickets",
                    "schema": {
                        "columns": [
                            {"name": "ticket_id", "type": "string"},
                            {"name": "subject", "type": "string"},
                        ]
                    },
                },
            },
        }, default_flow_style=False))

        working_clone.index.add([".bifrost/tables.yaml"])
        working_clone.index.commit("add table")
        working_clone.remotes.origin.push()

        result = await sync_service.desktop_pull()
        assert result.success is True

        # Verify table in DB
        from uuid import UUID as UUIDType
        table = await db_session.get(Table, UUIDType(table_id))
        assert table is not None
        assert table.name == "ticket_cache"
        assert table.description == "Cached tickets"
        assert table.schema is not None
        assert len(table.schema["columns"]) == 2

    async def test_pull_event_source_from_manifest(
        self,
        db_session: AsyncSession,
        sync_service,
        working_clone,
    ):
        """Pull manifest with schedule event source → creates EventSource + ScheduleSource + Subscription."""
        from src.models.orm.events import EventSource, EventSubscription, ScheduleSource

        work_dir = Path(working_clone.working_dir)
        es_id = str(uuid4())
        sub_id = str(uuid4())
        wf_id = str(uuid4())

        bifrost_dir = work_dir / ".bifrost"
        bifrost_dir.mkdir(exist_ok=True)

        # Need a workflow for the subscription to reference
        wf_dir = work_dir / "workflows"
        wf_dir.mkdir(exist_ok=True)
        (wf_dir / "sync_job.py").write_text(SAMPLE_WORKFLOW_CLEAN)

        (bifrost_dir / "workflows.yaml").write_text(yaml.dump({
            "workflows": {
                "sync_job": {
                    "id": wf_id,
                    "path": "workflows/sync_job.py",
                    "function_name": "clean_wf",
                },
            },
        }, default_flow_style=False))

        (bifrost_dir / "events.yaml").write_text(yaml.dump({
            "events": {
                "Daily Sync": {
                    "id": es_id,
                    "source_type": "schedule",
                    "cron_expression": "0 6 * * *",
                    "timezone": "America/New_York",
                    "schedule_enabled": True,
                    "subscriptions": [
                        {
                            "id": sub_id,
                            "workflow_id": wf_id,
                            "event_type": "scheduled",
                        },
                    ],
                },
            },
        }, default_flow_style=False))

        working_clone.index.add(["workflows/sync_job.py", ".bifrost/workflows.yaml", ".bifrost/events.yaml"])
        working_clone.index.commit("add event source")
        working_clone.remotes.origin.push()

        result = await sync_service.desktop_pull()
        assert result.success is True

        # Verify event source in DB
        from uuid import UUID as UUIDType
        es = await db_session.get(EventSource, UUIDType(es_id))
        assert es is not None
        # source_type may be an enum or string depending on how it was inserted
        source_type = es.source_type.value if hasattr(es.source_type, "value") else es.source_type
        assert source_type == "schedule"

        # Verify schedule source
        sched_result = await db_session.execute(
            select(ScheduleSource).where(ScheduleSource.event_source_id == UUIDType(es_id))
        )
        sched = sched_result.scalar_one_or_none()
        assert sched is not None
        assert sched.cron_expression == "0 6 * * *"
        assert sched.timezone == "America/New_York"

        # Verify subscription
        sub_result = await db_session.execute(
            select(EventSubscription).where(EventSubscription.event_source_id == UUIDType(es_id))
        )
        sub = sub_result.scalar_one_or_none()
        assert sub is not None
        assert str(sub.workflow_id) == wf_id
        assert sub.event_type == "scheduled"

    async def test_pull_idempotent(
        self,
        db_session: AsyncSession,
        sync_service,
        working_clone,
    ):
        """Pulling the same manifest twice doesn't create duplicates."""
        from src.models.orm.integrations import Integration

        work_dir = Path(working_clone.working_dir)
        integ_id = str(uuid4())

        bifrost_dir = work_dir / ".bifrost"
        bifrost_dir.mkdir(exist_ok=True)
        (bifrost_dir / "integrations.yaml").write_text(yaml.dump({
            "integrations": {
                "IdempotentInteg": {
                    "id": integ_id,
                    "entity_id": "tenant_id",
                },
            },
        }, default_flow_style=False))

        working_clone.index.add([".bifrost/integrations.yaml"])
        working_clone.index.commit("add integration")
        working_clone.remotes.origin.push()

        # Pull twice
        result1 = await sync_service.desktop_pull()
        assert result1.success is True
        result2 = await sync_service.desktop_pull()
        assert result2.success is True

        # Should still be exactly one integration with that ID
        from uuid import UUID as UUIDType
        integ_result = await db_session.execute(
            select(Integration).where(Integration.id == UUIDType(integ_id))
        )
        integs = integ_result.scalars().all()
        assert len(integs) == 1

    async def test_pull_reads_legacy_format(
        self,
        db_session: AsyncSession,
        sync_service,
        working_clone,
    ):
        """Pull from repo with legacy metadata.yaml still works."""
        work_dir = Path(working_clone.working_dir)

        wf_id = str(uuid4())
        wf_dir = work_dir / "workflows"
        wf_dir.mkdir(exist_ok=True)
        (wf_dir / "git_sync_test_legacy.py").write_text(SAMPLE_WORKFLOW_PY)

        # Write legacy single-file manifest
        bifrost_dir = work_dir / ".bifrost"
        bifrost_dir.mkdir(exist_ok=True)
        (bifrost_dir / "metadata.yaml").write_text(_make_manifest(
            workflows={
                "Legacy Test Workflow": {
                    "id": wf_id,
                    "path": "workflows/git_sync_test_legacy.py",
                    "function_name": "git_sync_test_wf",
                    "type": "workflow",
                }
            }
        ))

        working_clone.index.add([
            "workflows/git_sync_test_legacy.py",
            ".bifrost/metadata.yaml",
        ])
        working_clone.index.commit("add legacy format workflow")
        working_clone.remotes.origin.push()

        result = await sync_service.desktop_pull()
        assert result.success is True
        assert result.pulled > 0

        # Verify workflow imported
        wf_result = await db_session.execute(
            select(Workflow).where(Workflow.id == wf_id)
        )
        wf = wf_result.scalar_one_or_none()
        assert wf is not None
        assert wf.name == "Legacy Test Workflow"
