"""
Git Sync Service

GitPython-based synchronization. S3 _repo/ is the persistent working tree.

Key principles:
1. DB is source of truth for "local" state
2. GitPython for clone/pull/push/commit
3. Conflict detection with user resolution
4. .bifrost/metadata.yaml declares entity identity
5. Preflight validates repo health (syntax, lint, refs, orphans)
"""

import hashlib
import logging
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Awaitable, Callable, Literal

import yaml
from git import Repo as GitRepo
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.github_sync_entity_metadata import extract_entity_metadata
from src.services.manifest import (
    Manifest,
    parse_manifest,
    serialize_manifest,
    get_all_entity_ids,
)
from src.services.manifest_generator import generate_manifest
from src.services.entity_serializers import (
    serialize_form_to_yaml,
    serialize_agent_to_yaml,
    serialize_app_to_yaml,
)

logger = logging.getLogger(__name__)

# Type alias for progress callback
ProgressCallback = Callable[[dict], Awaitable[None]]
LogCallback = Callable[[str, str], Awaitable[None]]


# =============================================================================
# Pydantic Models
# =============================================================================


class SyncActionType(str, Enum):
    """Type of sync action."""
    ADD = "add"
    MODIFY = "modify"
    DELETE = "delete"


class SyncAction(BaseModel):
    """A single sync action (pull or push)."""
    path: str = Field(..., description="File path relative to workspace root")
    action: SyncActionType = Field(..., description="Type of action")
    sha: str | None = Field(default=None, description="Content hash")

    # Entity metadata for UI display
    display_name: str | None = Field(default=None)
    entity_type: str | None = Field(default=None)
    parent_slug: str | None = Field(default=None)

    model_config = ConfigDict(from_attributes=True)


def _enrich_sync_action(
    path: str,
    action: SyncActionType,
    sha: str | None = None,
    content: bytes | None = None,
) -> SyncAction:
    """Create a SyncAction enriched with entity metadata."""
    metadata = extract_entity_metadata(path, content)
    return SyncAction(
        path=path,
        action=action,
        sha=sha,
        display_name=metadata.display_name,
        entity_type=metadata.entity_type,
        parent_slug=metadata.parent_slug,
    )


class ConflictInfo(BaseModel):
    """Information about a conflict between local and remote."""
    path: str = Field(..., description="File path with conflict")
    local_content: str | None = Field(default=None)
    remote_content: str | None = Field(default=None)
    local_sha: str = Field(...)
    remote_sha: str = Field(...)
    display_name: str | None = Field(default=None)
    entity_type: str | None = Field(default=None)
    parent_slug: str | None = Field(default=None)

    model_config = ConfigDict(from_attributes=True)


class WorkflowReference(BaseModel):
    """A reference to an entity that uses a workflow."""
    type: str = Field(...)
    id: str = Field(...)
    name: str = Field(...)

    model_config = ConfigDict(from_attributes=True)


class OrphanInfo(BaseModel):
    """Information about a workflow that will become orphaned."""
    workflow_id: str = Field(...)
    workflow_name: str = Field(...)
    function_name: str = Field(...)
    last_path: str = Field(...)
    used_by: list[WorkflowReference] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class PreflightIssue(BaseModel):
    """A single issue found during preflight validation."""
    path: str = Field(...)
    line: int | None = Field(default=None)
    message: str = Field(...)
    severity: Literal["error", "warning"] = Field(...)
    category: Literal["syntax", "lint", "ref", "orphan", "manifest"] = Field(...)

    model_config = ConfigDict(from_attributes=True)


class PreflightResult(BaseModel):
    """Result of preflight validation."""
    valid: bool = Field(...)
    issues: list[PreflightIssue] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class SyncPreview(BaseModel):
    """Preview of sync operations before execution."""
    to_pull: list[SyncAction] = Field(default_factory=list)
    to_push: list[SyncAction] = Field(default_factory=list)
    conflicts: list[ConflictInfo] = Field(default_factory=list)
    preflight: PreflightResult = Field(
        default_factory=lambda: PreflightResult(valid=True),
    )
    is_empty: bool = Field(default=False)
    commit_sha: str | None = Field(default=None)

    model_config = ConfigDict(from_attributes=True)


class SyncResult(BaseModel):
    """Result of sync execution."""
    success: bool = Field(...)
    pulled: int = Field(default=0)
    pushed: int = Field(default=0)
    orphaned_workflows: list[str] = Field(default_factory=list)
    commit_sha: str | None = Field(default=None)
    error: str | None = Field(default=None)

    model_config = ConfigDict(from_attributes=True)


class SyncExecuteRequest(BaseModel):
    """Request to execute sync with conflict resolutions."""
    conflict_resolutions: dict[str, Literal["keep_local", "keep_remote"]] = Field(
        default_factory=dict,
    )
    confirm_orphans: bool = Field(default=False)

    model_config = ConfigDict(from_attributes=True)


# =============================================================================
# Errors
# =============================================================================


class SyncError(Exception):
    """Error during sync operation."""
    pass


class ConflictError(SyncError):
    """Unresolved conflicts exist."""
    def __init__(self, conflicts: list[str]):
        self.conflicts = conflicts
        super().__init__(f"Unresolved conflicts: {', '.join(conflicts)}")


class OrphanError(SyncError):
    """User must confirm orphan workflows."""
    def __init__(self, orphans: list[str]):
        self.orphans = orphans
        super().__init__(f"Must confirm orphan workflows: {', '.join(orphans)}")


# =============================================================================
# Helpers
# =============================================================================


def _content_hash(content: bytes) -> str:
    """SHA-256 of bytes."""
    return hashlib.sha256(content).hexdigest()


def _walk_tree(root: Path) -> dict[str, bytes]:
    """Walk a directory tree and return {relative_path: content} for all files."""
    files: dict[str, bytes] = {}
    for p in root.rglob("*"):
        if p.is_dir():
            continue
        rel = str(p.relative_to(root))
        # Skip .git internals
        if rel.startswith(".git/") or rel == ".git":
            continue
        files[rel] = p.read_bytes()
    return files


# =============================================================================
# Git Sync Service
# =============================================================================


class GitHubSyncService:
    """
    Git sync service using GitPython.

    All git operations go through GitPython against repo_url.
    The working tree is serialized to/from S3 _repo/ between operations.
    """

    def __init__(
        self,
        db: AsyncSession,
        repo_url: str,
        branch: str = "main",
    ):
        self.db = db
        self.repo_url = repo_url
        self.branch = branch

    # -----------------------------------------------------------------
    # Push: platform → remote repo
    # -----------------------------------------------------------------

    async def push(
        self,
        progress_callback: ProgressCallback | None = None,
        log_callback: LogCallback | None = None,
        conflict_resolutions: dict[str, str] | None = None,
    ) -> SyncResult:
        """
        Serialize current DB state to a git working tree, commit, and push.

        For initial connect (empty repo): creates initial commit.
        For incremental: commits changes and pushes.

        Args:
            conflict_resolutions: Dict mapping file paths to resolution strategy
                ("keep_local" or "keep_remote"). Files resolved as "keep_remote"
                are excluded from the push (remote version preserved).
        """
        resolutions = conflict_resolutions or {}
        tmp_dir = Path(tempfile.mkdtemp(prefix="bifrost-sync-push-"))
        try:
            # Clone or init
            repo = self._clone_or_init(tmp_dir)

            # For incremental push: remove all tracked content files first
            # so that deleted entities disappear from the repo.
            # Keep .git/ and .gitkeep intact.
            if repo.head.is_valid():
                for item in tmp_dir.iterdir():
                    if item.name == ".git":
                        continue
                    if item.is_dir():
                        shutil.rmtree(item)
                    else:
                        item.unlink()

            # Serialize platform state to working tree
            await self._serialize_platform_state(tmp_dir)

            # Apply conflict resolutions: for "keep_remote" files, restore
            # the remote version so the push doesn't overwrite it.
            for conflict_path, resolution in resolutions.items():
                if resolution == "keep_remote":
                    try:
                        repo.git.checkout("--", conflict_path)
                    except Exception:
                        pass  # File may not exist in remote yet

            # Stage everything: git add -A (handles adds, modifications, deletions)
            repo.git.add(A=True)

            # Check if there are changes to commit
            if repo.head.is_valid() and not repo.index.diff("HEAD"):
                return SyncResult(success=True, pushed=0)

            # Count files being pushed
            if repo.head.is_valid():
                pushed_count = len(repo.index.diff("HEAD"))
            else:
                pushed_count = len(repo.untracked_files) + len(list(repo.index.diff(None)))

            # Commit
            commit = repo.index.commit("Sync from Bifrost")

            # Push
            origin = repo.remotes.origin
            origin.push(refspec=f"HEAD:refs/heads/{self.branch}")

            logger.info(f"Pushed {pushed_count} files, commit={commit.hexsha[:8]}")
            return SyncResult(
                success=True,
                pushed=max(pushed_count, 1),  # At least 1 if we committed
                commit_sha=commit.hexsha,
            )

        except Exception as e:
            logger.error(f"Push failed: {e}", exc_info=True)
            return SyncResult(success=False, error=str(e))
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    # -----------------------------------------------------------------
    # Pull: remote repo → platform
    # -----------------------------------------------------------------

    async def pull(
        self,
        progress_callback: ProgressCallback | None = None,
        log_callback: LogCallback | None = None,
        confirm_orphans: bool = False,
    ) -> SyncResult:
        """
        Pull remote changes into the platform DB and file_index.

        Args:
            confirm_orphans: If True, deactivate workflows that exist in DB
                but were removed from the manifest. If False, skip orphan cleanup.
        """
        tmp_dir = Path(tempfile.mkdtemp(prefix="bifrost-sync-pull-"))
        try:
            repo = self._clone_or_init(tmp_dir)

            # Pull latest
            if repo.remotes:
                repo.remotes.origin.pull(self.branch)

            # Read manifest
            manifest_path = tmp_dir / ".bifrost" / "metadata.yaml"
            if not manifest_path.exists():
                return SyncResult(success=True, pulled=0)

            manifest = parse_manifest(manifest_path.read_text())

            # Import workflows
            pulled = 0
            # Track which workflow IDs are still in the manifest
            manifest_wf_ids = set()
            for wf_name, mwf in manifest.workflows.items():
                manifest_wf_ids.add(mwf.id)
                wf_path = tmp_dir / mwf.path
                if wf_path.exists():
                    content = wf_path.read_bytes()
                    await self._import_workflow(wf_name, mwf, content)
                    pulled += 1
                else:
                    # File deleted from repo → deactivate
                    await self._deactivate_workflow(mwf.id)

            # Deactivate workflows that exist in DB but were removed from manifest
            # Only if user confirmed orphan cleanup
            if confirm_orphans:
                await self._deactivate_missing_workflows(manifest_wf_ids)

            # Import forms
            for _form_name, mform in manifest.forms.items():
                form_path = tmp_dir / mform.path
                if form_path.exists():
                    content = form_path.read_bytes()
                    await self._import_form(mform, content)
                    pulled += 1

            # Import agents
            for _agent_name, magent in manifest.agents.items():
                agent_path = tmp_dir / magent.path
                if agent_path.exists():
                    content = agent_path.read_bytes()
                    await self._import_agent(magent, content)
                    pulled += 1

            # Import apps
            for _app_name, mapp in manifest.apps.items():
                app_path = tmp_dir / mapp.path
                if app_path.exists():
                    content = app_path.read_bytes()
                    await self._import_app(mapp, content)
                    pulled += 1

            # Update file_index: sync all files from repo, remove stale entries
            await self._update_file_index(tmp_dir)

            await self.db.commit()

            commit_sha = repo.head.commit.hexsha if repo.head.is_valid() else None
            logger.info(f"Pulled {pulled} entities, commit={commit_sha[:8] if commit_sha else 'none'}")
            return SyncResult(
                success=True,
                pulled=pulled,
                commit_sha=commit_sha,
            )

        except Exception as e:
            logger.error(f"Pull failed: {e}", exc_info=True)
            return SyncResult(success=False, error=str(e))
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    # -----------------------------------------------------------------
    # Preview: what will change?
    # -----------------------------------------------------------------

    async def preview(
        self,
        progress_callback: ProgressCallback | None = None,
        log_callback: LogCallback | None = None,
    ) -> SyncPreview:
        """
        Compare platform state with remote repo and return a preview of changes.
        """
        tmp_dir = Path(tempfile.mkdtemp(prefix="bifrost-sync-preview-"))
        try:
            repo = self._clone_or_init(tmp_dir)

            # Get remote state (what's in the repo)
            remote_files = _walk_tree(tmp_dir)
            remote_hashes = {p: _content_hash(c) for p, c in remote_files.items()}

            # Get local state (serialize platform to temp)
            local_dir = Path(tempfile.mkdtemp(prefix="bifrost-sync-local-"))
            try:
                await self._serialize_platform_state(local_dir)
                local_files = _walk_tree(local_dir)
                local_hashes = {p: _content_hash(c) for p, c in local_files.items()}
            finally:
                shutil.rmtree(local_dir, ignore_errors=True)

            to_push: list[SyncAction] = []
            to_pull: list[SyncAction] = []
            conflicts: list[ConflictInfo] = []

            all_paths = set(local_hashes.keys()) | set(remote_hashes.keys())

            for path in sorted(all_paths):
                local_hash = local_hashes.get(path)
                remote_hash = remote_hashes.get(path)

                if local_hash and not remote_hash:
                    # Only in local → push ADD
                    to_push.append(_enrich_sync_action(
                        path, SyncActionType.ADD, sha=local_hash,
                        content=local_files.get(path),
                    ))

                elif remote_hash and not local_hash:
                    # Only in remote → pull ADD
                    to_pull.append(_enrich_sync_action(
                        path, SyncActionType.ADD, sha=remote_hash,
                        content=remote_files.get(path),
                    ))

                elif local_hash != remote_hash:
                    # Both exist but different → conflict
                    local_content = local_files.get(path, b"")
                    remote_content = remote_files.get(path, b"")
                    metadata = extract_entity_metadata(path, remote_content)
                    conflicts.append(ConflictInfo(
                        path=path,
                        local_content=local_content.decode("utf-8", errors="replace"),
                        remote_content=remote_content.decode("utf-8", errors="replace"),
                        local_sha=local_hash or "",
                        remote_sha=remote_hash or "",
                        display_name=metadata.display_name,
                        entity_type=metadata.entity_type,
                        parent_slug=metadata.parent_slug,
                    ))

            # Run preflight on remote repo
            pf = await self._run_preflight(tmp_dir)

            commit_sha = repo.head.commit.hexsha if repo.head.is_valid() else None
            is_empty = not to_push and not to_pull and not conflicts

            return SyncPreview(
                to_pull=to_pull,
                to_push=to_push,
                conflicts=conflicts,
                preflight=pf,
                is_empty=is_empty,
                commit_sha=commit_sha,
            )

        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    # -----------------------------------------------------------------
    # Preflight: validate repo health
    # -----------------------------------------------------------------

    async def preflight(
        self,
    ) -> PreflightResult:
        """
        Validate the remote repo's health without syncing.

        Checks: Python syntax, ruff lint, UUID ref resolution, manifest validity.
        """
        tmp_dir = Path(tempfile.mkdtemp(prefix="bifrost-sync-preflight-"))
        try:
            self._clone_or_init(tmp_dir)
            return await self._run_preflight(tmp_dir)
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    # -----------------------------------------------------------------
    # Internal: git operations
    # -----------------------------------------------------------------

    def _clone_or_init(self, target: Path) -> GitRepo:
        """Clone from repo_url, or init if repo is empty."""
        try:
            repo = GitRepo.clone_from(
                self.repo_url,
                str(target),
                branch=self.branch,
            )
            return repo
        except Exception as e:
            err_str = str(e)
            # Empty repo or branch doesn't exist yet
            if "not found" in err_str.lower() or "empty" in err_str.lower() or "could not find remote branch" in err_str.lower():
                repo = GitRepo.init(str(target))
                repo.create_remote("origin", self.repo_url)
                return repo
            raise SyncError(f"Failed to clone {self.repo_url}: {e}") from e

    # -----------------------------------------------------------------
    # Internal: serialize platform state to working tree
    # -----------------------------------------------------------------

    async def _serialize_platform_state(self, work_dir: Path) -> None:
        """Write all platform entities to the working tree directory."""
        from uuid import UUID

        from sqlalchemy.orm import selectinload

        from src.models.orm.agents import Agent
        from src.models.orm.applications import Application
        from src.models.orm.forms import Form
        from src.services.file_index_service import FileIndexService
        from src.services.repo_storage import RepoStorage

        # Generate manifest from DB
        manifest = await generate_manifest(self.db)

        # Write workflow .py files from file_index (S3 _repo/)
        file_index = FileIndexService(self.db, RepoStorage())
        for manifest_wf_name, mwf in manifest.workflows.items():
            content = await file_index.read(mwf.path)
            if not content:
                # file_index has no content — generate a stub from DB metadata
                content = (
                    f"from bifrost import workflow\n\n\n"
                    f"@workflow(name=\"{manifest_wf_name}\")\n"
                    f"def {mwf.function_name}():\n"
                    f"    pass\n"
                )
            file_path = work_dir / mwf.path
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(content)

        # Serialize forms to YAML (eagerly load fields for serialization)
        for _form_name, mform in manifest.forms.items():
            form_result = await self.db.execute(
                select(Form)
                .options(selectinload(Form.fields))
                .where(Form.id == UUID(mform.id))
            )
            form = form_result.scalar_one_or_none()
            if form:
                form_content = serialize_form_to_yaml(form)
                file_path = work_dir / mform.path
                file_path.parent.mkdir(parents=True, exist_ok=True)
                file_path.write_text(form_content)

        # Serialize agents to YAML (eagerly load tools for serialization)
        for _agent_name, magent in manifest.agents.items():
            agent_result = await self.db.execute(
                select(Agent)
                .options(selectinload(Agent.tools))
                .where(Agent.id == UUID(magent.id))
            )
            agent = agent_result.scalar_one_or_none()
            if agent:
                agent_content = serialize_agent_to_yaml(agent)
                file_path = work_dir / magent.path
                file_path.parent.mkdir(parents=True, exist_ok=True)
                file_path.write_text(agent_content)

        # Serialize apps to YAML
        for _app_name, mapp in manifest.apps.items():
            app_result = await self.db.execute(
                select(Application)
                .where(Application.id == UUID(mapp.id))
            )
            app = app_result.scalar_one_or_none()
            if app:
                app_content = serialize_app_to_yaml(app)
                file_path = work_dir / mapp.path
                file_path.parent.mkdir(parents=True, exist_ok=True)
                file_path.write_text(app_content)

        # Write manifest
        manifest_path = work_dir / ".bifrost" / "metadata.yaml"
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(serialize_manifest(manifest))

    # -----------------------------------------------------------------
    # Internal: import entities from repo
    # -----------------------------------------------------------------

    async def _import_workflow(self, manifest_name: str, mwf, _content: bytes) -> None:
        """Import a workflow from repo into the DB."""
        from uuid import UUID

        from sqlalchemy.dialects.postgresql import insert

        from src.models.orm.workflows import Workflow

        stmt = insert(Workflow).values(
            id=UUID(mwf.id),
            name=manifest_name,
            function_name=mwf.function_name,
            path=mwf.path,
            type=getattr(mwf, "type", "workflow"),
            is_active=True,
            organization_id=UUID(mwf.organization_id) if mwf.organization_id else None,
        ).on_conflict_do_update(
            index_elements=["id"],
            set_={
                "name": manifest_name,
                "function_name": mwf.function_name,
                "path": mwf.path,
                "type": getattr(mwf, "type", "workflow"),
                "is_active": True,
                "updated_at": datetime.now(timezone.utc),
            },
        )
        await self.db.execute(stmt)

    async def _import_form(self, mform, content: bytes) -> None:
        """Import a form from repo YAML into the DB."""
        from uuid import UUID

        from sqlalchemy.dialects.postgresql import insert

        from src.models.orm.forms import Form

        data = yaml.safe_load(content.decode("utf-8"))
        if not data:
            return

        stmt = insert(Form).values(
            id=UUID(mform.id),
            name=data.get("name", ""),
            description=data.get("description"),
            workflow_id=data.get("workflow"),
            is_active=True,
            created_by="git-sync",
            organization_id=UUID(mform.organization_id) if mform.organization_id else None,
        ).on_conflict_do_update(
            index_elements=["id"],
            set_={
                "name": data.get("name", ""),
                "description": data.get("description"),
                "workflow_id": data.get("workflow"),
                "is_active": True,
                "updated_at": datetime.now(timezone.utc),
            },
        )
        await self.db.execute(stmt)

    async def _import_agent(self, magent, content: bytes) -> None:
        """Import an agent from repo YAML into the DB."""
        from uuid import UUID

        from sqlalchemy.dialects.postgresql import insert

        from src.models.orm.agents import Agent

        data = yaml.safe_load(content.decode("utf-8"))
        if not data:
            return

        stmt = insert(Agent).values(
            id=UUID(magent.id),
            name=data.get("name", ""),
            system_prompt=data.get("system_prompt", ""),
            description=data.get("description"),
            is_active=True,
            created_by="git-sync",
            organization_id=UUID(magent.organization_id) if magent.organization_id else None,
        ).on_conflict_do_update(
            index_elements=["id"],
            set_={
                "name": data.get("name", ""),
                "system_prompt": data.get("system_prompt", ""),
                "description": data.get("description"),
                "is_active": True,
                "updated_at": datetime.now(timezone.utc),
            },
        )
        await self.db.execute(stmt)

    async def _import_app(self, mapp, content: bytes) -> None:
        """Import an app from repo into the DB (metadata only)."""
        from uuid import UUID

        from sqlalchemy.dialects.postgresql import insert

        from src.models.orm.applications import Application

        data = yaml.safe_load(content.decode("utf-8"))
        if not data:
            return

        stmt = insert(Application).values(
            id=UUID(mapp.id),
            name=data.get("name", ""),
            description=data.get("description"),
            slug=data.get("slug", str(UUID(mapp.id))),
            organization_id=UUID(mapp.organization_id) if mapp.organization_id else None,
        ).on_conflict_do_update(
            index_elements=["id"],
            set_={
                "name": data.get("name", ""),
                "description": data.get("description"),
                "updated_at": datetime.now(timezone.utc),
            },
        )
        await self.db.execute(stmt)

    async def _deactivate_workflow(self, workflow_id: str) -> None:
        """Deactivate a workflow by ID."""
        from uuid import UUID

        from sqlalchemy import update

        from src.models.orm.workflows import Workflow

        stmt = update(Workflow).where(
            Workflow.id == UUID(workflow_id)
        ).values(
            is_active=False,
            updated_at=datetime.now(timezone.utc),
        )
        await self.db.execute(stmt)

    async def _deactivate_missing_workflows(self, manifest_wf_ids: set[str]) -> None:
        """Deactivate workflows that were synced before but are no longer in the manifest."""
        from src.models.orm.workflows import Workflow

        if not manifest_wf_ids:
            return

        # Find active workflows whose paths start with "workflows/" (synced from git)
        # that are NOT in the current manifest
        result = await self.db.execute(
            select(Workflow.id).where(
                Workflow.is_active == True,  # noqa: E712
                Workflow.path.like("workflows/%"),
            )
        )
        all_active_ids = {str(row[0]) for row in result.all()}
        to_deactivate = all_active_ids - manifest_wf_ids

        for wf_id in to_deactivate:
            await self._deactivate_workflow(wf_id)

    async def _update_file_index(self, work_dir: Path) -> None:
        """Update file_index from all files in the working tree, remove stale entries."""
        from sqlalchemy import delete, text
        from sqlalchemy.dialects.postgresql import insert

        from src.models.orm.file_index import FileIndex
        from src.services.file_index_service import _is_text_file

        files = _walk_tree(work_dir)
        repo_paths = set()
        for rel_path, content in files.items():
            repo_paths.add(rel_path)
            if _is_text_file(rel_path):
                try:
                    content_str = content.decode("utf-8")
                except UnicodeDecodeError:
                    continue
                content_hash = _content_hash(content)
                stmt = insert(FileIndex).values(
                    path=rel_path,
                    content=content_str,
                    content_hash=content_hash,
                ).on_conflict_do_update(
                    index_elements=[FileIndex.path],
                    set_={
                        "content": content_str,
                        "content_hash": content_hash,
                        "updated_at": text("NOW()"),
                    },
                )
                await self.db.execute(stmt)

        # Remove file_index entries that no longer exist in the repo
        existing_result = await self.db.execute(select(FileIndex.path))
        existing_paths = {row[0] for row in existing_result.all()}
        stale_paths = existing_paths - repo_paths
        if stale_paths:
            await self.db.execute(
                delete(FileIndex).where(FileIndex.path.in_(stale_paths))
            )

    # -----------------------------------------------------------------
    # Internal: preflight validation
    # -----------------------------------------------------------------

    async def _run_preflight(self, repo_dir: Path) -> PreflightResult:
        """Run all preflight checks against a repo directory."""
        issues: list[PreflightIssue] = []

        # 1. Check manifest validity
        manifest_path = repo_dir / ".bifrost" / "metadata.yaml"
        manifest: Manifest | None = None
        if manifest_path.exists():
            try:
                manifest = parse_manifest(manifest_path.read_text())
                # Verify all paths exist
                from src.services.manifest import get_all_paths
                for path in get_all_paths(manifest):
                    if not (repo_dir / path).exists():
                        issues.append(PreflightIssue(
                            path=".bifrost/metadata.yaml",
                            message=f"Manifest references missing file: {path}",
                            severity="error",
                            category="manifest",
                        ))
            except Exception as e:
                issues.append(PreflightIssue(
                    path=".bifrost/metadata.yaml",
                    message=f"Invalid manifest: {e}",
                    severity="error",
                    category="manifest",
                ))

        # 2. Syntax check all .py files
        for py_file in repo_dir.rglob("*.py"):
            rel = str(py_file.relative_to(repo_dir))
            if rel.startswith(".git/"):
                continue
            try:
                source = py_file.read_text()
                compile(source, rel, "exec")
            except SyntaxError as e:
                issues.append(PreflightIssue(
                    path=rel,
                    line=e.lineno,
                    message=f"Syntax error: {e.msg}",
                    severity="error",
                    category="syntax",
                ))

        # 3. Ruff lint check
        py_files = [
            str(f) for f in repo_dir.rglob("*.py")
            if not str(f.relative_to(repo_dir)).startswith(".git/")
        ]
        if py_files:
            try:
                result = subprocess.run(
                    ["ruff", "check", "--output-format=json", "--no-fix", *py_files],
                    capture_output=True,
                    text=True,
                    timeout=60,
                    cwd=str(repo_dir),
                )
                if result.stdout.strip():
                    import json
                    for violation in json.loads(result.stdout):
                        rel_path = str(Path(violation["filename"]).relative_to(repo_dir))
                        issues.append(PreflightIssue(
                            path=rel_path,
                            line=violation.get("location", {}).get("row"),
                            message=f"{violation.get('code', '?')}: {violation.get('message', '')}",
                            severity="warning",
                            category="lint",
                        ))
            except (subprocess.TimeoutExpired, FileNotFoundError):
                pass  # ruff not available or timed out — skip lint

        # 4. Ref resolution (UUID references in entity files)
        if manifest:
            entity_ids = get_all_entity_ids(manifest)
            # Check forms for workflow UUID references
            for form_name, mform in manifest.forms.items():
                form_path = repo_dir / mform.path
                if form_path.exists():
                    try:
                        data = yaml.safe_load(form_path.read_text())
                        if data:
                            wf_ref = data.get("workflow")
                            if wf_ref and wf_ref not in entity_ids:
                                issues.append(PreflightIssue(
                                    path=mform.path,
                                    message=f"Form references unknown workflow UUID: {wf_ref}",
                                    severity="error",
                                    category="ref",
                                ))
                            launch_ref = data.get("launch_workflow")
                            if launch_ref and launch_ref not in entity_ids:
                                issues.append(PreflightIssue(
                                    path=mform.path,
                                    message=f"Form references unknown launch workflow UUID: {launch_ref}",
                                    severity="error",
                                    category="ref",
                                ))
                    except Exception:
                        pass

            # 5. Orphan detection — workflows referenced by forms but missing from manifest
            wf_ids = {mwf.id for mwf in manifest.workflows.values()}
            for form_name, mform in manifest.forms.items():
                form_path = repo_dir / mform.path
                if form_path.exists():
                    try:
                        data = yaml.safe_load(form_path.read_text())
                        if data:
                            wf_ref = data.get("workflow")
                            if wf_ref and wf_ref not in wf_ids:
                                issues.append(PreflightIssue(
                                    path=mform.path,
                                    message=f"Form '{form_name}' references workflow {wf_ref} which is not in the manifest (will be orphaned)",
                                    severity="warning",
                                    category="orphan",
                                ))
                    except Exception:
                        pass

        has_errors = any(i.severity == "error" for i in issues)
        return PreflightResult(valid=not has_errors, issues=issues)
