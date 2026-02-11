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
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

import yaml
from git import Repo as GitRepo
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import Settings, get_settings
from src.models.contracts.github import (
    PreflightIssue,
    PreflightResult,
)
from src.services.git_repo_manager import GitRepoManager
from src.services.github_sync_entity_metadata import extract_entity_metadata

if TYPE_CHECKING:
    from src.models.contracts.github import (
        CommitResult,
        DiffResult,
        FetchResult,
        PullResult,
        PushResult,
        ResolveResult,
        WorkingTreeStatus,
    )
from src.services.manifest import (
    Manifest,
    parse_manifest,
    serialize_manifest,
    get_all_entity_ids,
)
from src.services.manifest_generator import generate_manifest

logger = logging.getLogger(__name__)


# =============================================================================
# Errors
# =============================================================================


class SyncError(Exception):
    """Error during sync operation."""
    pass


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
        settings: Settings | None = None,
    ):
        self.db = db
        self.repo_url = repo_url
        self.branch = branch
        self.repo_manager = GitRepoManager(settings or get_settings())

    # -----------------------------------------------------------------
    # Preflight: validate repo health
    # -----------------------------------------------------------------

    async def preflight(
        self,
    ) -> PreflightResult:
        """
        Validate the remote repo's health without syncing.

        Uses GitRepoManager to restore persistent .git/ from S3.
        Checks: Python syntax, ruff lint, UUID ref resolution, manifest validity.
        """
        async with self.repo_manager.checkout() as work_dir:
            if not (work_dir / ".git").exists():
                self._clone_or_init(work_dir)
            return await self._run_preflight(work_dir)

    # -----------------------------------------------------------------
    # Desktop-style operations: fetch, status, commit, pull, push, resolve, diff
    # -----------------------------------------------------------------

    async def desktop_fetch(self) -> "FetchResult":
        """Git fetch origin. Compute ahead/behind counts."""
        from src.models.contracts.github import FetchResult

        try:
            async with self.repo_manager.checkout() as work_dir:
                repo = self._open_or_init(work_dir)

                # Fetch remote
                remote_exists = True
                try:
                    repo.remotes.origin.fetch(self.branch)
                except Exception as e:
                    err_str = str(e).lower()
                    if "not found" in err_str or "empty" in err_str or "couldn't find remote ref" in err_str:
                        remote_exists = False
                    else:
                        raise

                # Compute ahead/behind
                ahead = 0
                behind = 0
                if remote_exists and repo.head.is_valid():
                    try:
                        ahead = int(repo.git.rev_list("--count", f"origin/{self.branch}..HEAD"))
                    except Exception:
                        ahead = 0
                    try:
                        behind = int(repo.git.rev_list("--count", f"HEAD..origin/{self.branch}"))
                    except Exception:
                        behind = 0

                return FetchResult(
                    success=True,
                    commits_ahead=ahead,
                    commits_behind=behind,
                    remote_branch_exists=remote_exists,
                )
        except Exception as e:
            logger.error(f"Fetch failed: {e}", exc_info=True)
            return FetchResult(success=False, error=str(e))

    async def desktop_status(self) -> "WorkingTreeStatus":
        """Get working tree status (uncommitted changes). Regenerates manifest first."""
        from src.models.contracts.github import ChangedFile, WorkingTreeStatus

        try:
            async with self.repo_manager.checkout() as work_dir:
                repo = self._open_or_init(work_dir)

                # Regenerate manifest before checking status
                await self._regenerate_manifest_only(work_dir)

                # Stage everything to get accurate diff
                repo.git.add(A=True)

                changed: list[ChangedFile] = []

                if repo.head.is_valid():
                    # Diff staged vs HEAD
                    porcelain = repo.git.status("--porcelain")
                    for line in porcelain.strip().split("\n"):
                        if not line.strip():
                            continue
                        status_code = line[:2].strip()
                        path = line[3:].strip()
                        # Strip quotes from paths with special chars
                        if path.startswith('"') and path.endswith('"'):
                            path = path[1:-1]

                        if status_code in ("A", "??"):
                            change_type = "added"
                        elif status_code == "D":
                            change_type = "deleted"
                        elif status_code == "R":
                            change_type = "renamed"
                        else:
                            change_type = "modified"

                        metadata = extract_entity_metadata(path)
                        changed.append(ChangedFile(
                            path=path,
                            change_type=change_type,
                            display_name=metadata.display_name,
                            entity_type=metadata.entity_type,
                        ))
                else:
                    # No HEAD yet - all files are new
                    for path in repo.untracked_files:
                        metadata = extract_entity_metadata(path)
                        changed.append(ChangedFile(
                            path=path,
                            change_type="added",
                            display_name=metadata.display_name,
                            entity_type=metadata.entity_type,
                        ))

                # Unstage (reset) so we don't pollute the working tree
                if repo.head.is_valid():
                    repo.git.reset("HEAD")

                return WorkingTreeStatus(
                    changed_files=changed,
                    total_changes=len(changed),
                )
        except Exception as e:
            logger.error(f"Status failed: {e}", exc_info=True)
            return WorkingTreeStatus()

    async def desktop_commit(self, message: str) -> "CommitResult":
        """
        Commit working tree changes (local only, no push).
        Regenerates manifest, runs preflight, commits if valid.
        """
        from src.models.contracts.github import CommitResult

        try:
            async with self.repo_manager.checkout() as work_dir:
                repo = self._open_or_init(work_dir)

                # Regenerate manifest
                await self._regenerate_manifest_only(work_dir)

                # Stage everything
                repo.git.add(A=True)

                # Check if there are changes to commit
                if repo.head.is_valid() and not repo.index.diff("HEAD") and not repo.untracked_files:
                    return CommitResult(success=True, files_committed=0)

                # Run preflight
                pf = await self._run_preflight(work_dir)
                if not pf.valid:
                    return CommitResult(success=False, error="Preflight validation failed", preflight=pf)

                # Count files
                if repo.head.is_valid():
                    file_count = len(repo.index.diff("HEAD")) + len(repo.untracked_files)
                else:
                    file_count = len(repo.untracked_files) + len(list(repo.index.diff(None)))

                # Commit
                commit = repo.index.commit(message)

                logger.info(f"Committed {file_count} files: {commit.hexsha[:8]}")
                return CommitResult(
                    success=True,
                    commit_sha=commit.hexsha,
                    files_committed=max(file_count, 1),
                    preflight=pf,
                )
        except Exception as e:
            logger.error(f"Commit failed: {e}", exc_info=True)
            return CommitResult(success=False, error=str(e))

    async def desktop_pull(self) -> "PullResult":
        """
        Pull remote changes. On success, import entities.
        On conflict, return PullResult with conflicts list.
        """
        from src.models.contracts.github import MergeConflict, PullResult

        try:
            async with self.repo_manager.checkout() as work_dir:
                repo = self._open_or_init(work_dir)

                # Fetch first
                remote_exists = True
                try:
                    repo.remotes.origin.fetch(self.branch)
                except Exception as e:
                    err_str = str(e).lower()
                    if "not found" in err_str or "empty" in err_str or "couldn't find remote ref" in err_str:
                        remote_exists = False
                    else:
                        raise

                if not remote_exists:
                    return PullResult(success=True, pulled=0)

                # Attempt merge
                try:
                    repo.git.merge(f"origin/{self.branch}")
                except Exception:
                    # Check for actual merge conflict (MERGE_HEAD exists after failed merge)
                    is_merge_conflict = (work_dir / ".git" / "MERGE_HEAD").exists()

                    if is_merge_conflict:
                        # Parse conflicts using GitPython's unmerged_blobs API
                        conflicts: list[MergeConflict] = []
                        try:
                            unmerged = repo.index.unmerged_blobs()
                            conflicted_files = sorted(unmerged.keys())
                        except Exception:
                            conflicted_files = []

                        for cpath in conflicted_files:
                            ours_content = None
                            theirs_content = None
                            try:
                                ours_content = repo.git.show(f":2:{cpath}")
                            except Exception:
                                pass
                            try:
                                theirs_content = repo.git.show(f":3:{cpath}")
                            except Exception:
                                pass

                            metadata = extract_entity_metadata(cpath)
                            conflicts.append(MergeConflict(
                                path=cpath,
                                ours_content=ours_content,
                                theirs_content=theirs_content,
                                display_name=metadata.display_name,
                                entity_type=metadata.entity_type,
                            ))

                        # DON'T abort merge - leave it in merge state for resolve
                        return PullResult(
                            success=False,
                            conflicts=conflicts,
                            error="Merge conflicts detected",
                        )
                    else:
                        raise

                # Success - import entities atomically with savepoint
                async with self.db.begin_nested():
                    pulled = await self._import_all_entities(work_dir)
                    await self._delete_removed_entities(work_dir)
                    await self._update_file_index(work_dir)
                await self.db.commit()

                commit_sha = repo.head.commit.hexsha if repo.head.is_valid() else None
                logger.info(f"Pull complete: {pulled} entities, commit={commit_sha[:8] if commit_sha else 'none'}")
                return PullResult(
                    success=True,
                    pulled=pulled,
                    commit_sha=commit_sha,
                )
        except Exception as e:
            logger.error(f"Pull failed: {e}", exc_info=True)
            return PullResult(success=False, error=str(e))

    async def desktop_push(self) -> "PushResult":
        """Push existing local commits to remote. Does NOT commit first."""
        from src.models.contracts.github import PushResult

        try:
            async with self.repo_manager.checkout() as work_dir:
                repo = self._open_or_init(work_dir)

                if not repo.head.is_valid():
                    return PushResult(success=True, pushed_commits=0)

                # Count ahead before push
                ahead = 0
                try:
                    repo.remotes.origin.fetch(self.branch)
                    ahead = int(repo.git.rev_list("--count", f"origin/{self.branch}..HEAD"))
                except Exception:
                    # If remote branch doesn't exist, everything is ahead
                    ahead = int(repo.git.rev_list("--count", "HEAD"))

                if ahead == 0:
                    return PushResult(success=True, pushed_commits=0)

                # Push
                push_infos = repo.remotes.origin.push(refspec=f"HEAD:refs/heads/{self.branch}")

                # Check for push errors (GitPython doesn't raise on push failures)
                from git.remote import PushInfo
                for pi in push_infos:
                    if pi.flags & PushInfo.ERROR:
                        error_msg = pi.summary.strip() if pi.summary else "Push rejected"
                        logger.error(f"Push error: {error_msg}")
                        return PushResult(success=False, error=error_msg)
                    if pi.flags & PushInfo.REJECTED:
                        error_msg = f"Push rejected (non-fast-forward): {pi.summary.strip() if pi.summary else ''}"
                        logger.error(error_msg)
                        return PushResult(success=False, error=error_msg)
                    if pi.flags & PushInfo.REMOTE_REJECTED:
                        error_msg = f"Push remote-rejected: {pi.summary.strip() if pi.summary else ''}"
                        logger.error(error_msg)
                        return PushResult(success=False, error=error_msg)

                commit_sha = repo.head.commit.hexsha
                logger.info(f"Pushed {ahead} commits, head={commit_sha[:8]}")
                return PushResult(
                    success=True,
                    commit_sha=commit_sha,
                    pushed_commits=ahead,
                )
        except Exception as e:
            logger.error(f"Push failed: {e}", exc_info=True)
            return PushResult(success=False, error=str(e))

    async def desktop_resolve(self, resolutions: dict[str, str]) -> "ResolveResult":
        """
        Resolve merge conflicts after a failed pull.
        Applies ours/theirs per file, completes the merge, imports entities.
        """
        from src.models.contracts.github import ResolveResult

        try:
            async with self.repo_manager.checkout() as work_dir:
                repo = self._open_or_init(work_dir)

                # Verify we're in a merge state
                merge_head = work_dir / ".git" / "MERGE_HEAD"
                if not merge_head.exists():
                    return ResolveResult(success=False, error="Not in a merge state")

                # Apply resolutions
                for cpath, resolution in resolutions.items():
                    if resolution == "ours":
                        repo.git.checkout("--ours", cpath)
                    elif resolution == "theirs":
                        repo.git.checkout("--theirs", cpath)
                    repo.git.add(cpath)

                # Complete the merge
                repo.index.commit("Merge with conflict resolution")

                # Import entities atomically with savepoint
                async with self.db.begin_nested():
                    pulled = await self._import_all_entities(work_dir)
                    await self._delete_removed_entities(work_dir)
                    await self._update_file_index(work_dir)
                await self.db.commit()

                logger.info(f"Resolved conflicts, imported {pulled} entities")
                return ResolveResult(success=True, pulled=pulled)
        except Exception as e:
            logger.error(f"Resolve failed: {e}", exc_info=True)
            return ResolveResult(success=False, error=str(e))

    async def desktop_diff(self, path: str) -> "DiffResult":
        """Get file diff: HEAD content vs working tree content."""
        from src.models.contracts.github import DiffResult

        try:
            async with self.repo_manager.checkout() as work_dir:
                repo = self._open_or_init(work_dir)

                # Regenerate manifest for accurate diff
                await self._regenerate_manifest_only(work_dir)

                # Get HEAD content
                head_content = None
                if repo.head.is_valid():
                    try:
                        head_content = repo.git.show(f"HEAD:{path}")
                    except Exception:
                        pass  # File doesn't exist in HEAD (new file)

                # Get working tree content
                working_content = None
                working_path = work_dir / path
                if working_path.exists():
                    working_content = working_path.read_text(errors="replace")

                return DiffResult(
                    path=path,
                    head_content=head_content,
                    working_content=working_content,
                )
        except Exception as e:
            logger.error(f"Diff failed: {e}", exc_info=True)
            return DiffResult(path=path)

    # -----------------------------------------------------------------
    # Helpers for desktop-style operations
    # -----------------------------------------------------------------

    def _open_or_init(self, work_dir: Path) -> GitRepo:
        """Open existing .git/ or clone fresh. Ensure remote URL and user identity are set."""
        if (work_dir / ".git").exists():
            repo = GitRepo(str(work_dir))
            if "origin" in [r.name for r in repo.remotes]:
                repo.remotes.origin.set_url(self.repo_url)
            else:
                repo.create_remote("origin", self.repo_url)
        else:
            repo = self._clone_or_init(work_dir)

        # Ensure git user identity is configured (needed for merge/commit)
        with repo.config_writer() as cw:
            try:
                cw.get_value("user", "name")
            except Exception:
                cw.set_value("user", "name", "Bifrost")
            try:
                cw.get_value("user", "email")
            except Exception:
                cw.set_value("user", "email", "bifrost@localhost")

        return repo

    async def _regenerate_manifest_only(self, work_dir: Path) -> None:
        """Write .bifrost/metadata.yaml from DB state. Lightweight - no entity re-serialization."""
        manifest = await generate_manifest(self.db)
        manifest_path = work_dir / ".bifrost" / "metadata.yaml"
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(serialize_manifest(manifest))

    async def _import_all_entities(self, work_dir: Path) -> int:
        """Import all entities from the working tree into the DB. Returns count."""
        manifest_path = work_dir / ".bifrost" / "metadata.yaml"
        if not manifest_path.exists():
            return 0

        manifest = parse_manifest(manifest_path.read_text())
        count = 0

        # Import workflows
        for wf_name, mwf in manifest.workflows.items():
            wf_path = work_dir / mwf.path
            if wf_path.exists():
                content = wf_path.read_bytes()
                await self._import_workflow(wf_name, mwf, content)
                count += 1

        # Import forms
        for _form_name, mform in manifest.forms.items():
            form_path = work_dir / mform.path
            if form_path.exists():
                content = form_path.read_bytes()
                await self._import_form(mform, content)
                count += 1

        # Import agents
        for _agent_name, magent in manifest.agents.items():
            agent_path = work_dir / magent.path
            if agent_path.exists():
                content = agent_path.read_bytes()
                await self._import_agent(magent, content)
                count += 1

        # Import apps
        for _app_name, mapp in manifest.apps.items():
            app_path = work_dir / mapp.path
            if app_path.exists():
                content = app_path.read_bytes()
                await self._import_app(mapp, content)
                count += 1

        return count

    async def _delete_removed_entities(self, work_dir: Path) -> None:
        """Hard-delete entities whose files no longer exist in the working tree after a pull.

        Git history provides the undo mechanism — no need for a DB recycle bin.
        Compares manifest entity IDs against active DB entities to find deletions.
        """
        from uuid import UUID

        from sqlalchemy import delete as sa_delete

        from src.models.orm.agents import Agent
        from src.models.orm.applications import Application
        from src.models.orm.forms import Form
        from src.models.orm.workflows import Workflow

        manifest_path = work_dir / ".bifrost" / "metadata.yaml"
        if not manifest_path.exists():
            return

        manifest = parse_manifest(manifest_path.read_text())

        # Collect IDs of entities present in the manifest AND whose files exist
        present_wf_ids: set[str] = set()
        for mwf in manifest.workflows.values():
            if (work_dir / mwf.path).exists():
                present_wf_ids.add(mwf.id)

        present_form_ids: set[str] = set()
        for mform in manifest.forms.values():
            if (work_dir / mform.path).exists():
                present_form_ids.add(mform.id)

        present_agent_ids: set[str] = set()
        for magent in manifest.agents.values():
            if (work_dir / magent.path).exists():
                present_agent_ids.add(magent.id)

        present_app_ids: set[str] = set()
        for mapp in manifest.apps.values():
            if (work_dir / mapp.path).exists():
                present_app_ids.add(mapp.id)

        # Delete workflows synced from git that are no longer present
        wf_result = await self.db.execute(
            select(Workflow.id).where(
                Workflow.is_active == True,  # noqa: E712
                Workflow.path.like("workflows/%"),
            )
        )
        for row in wf_result.all():
            wf_id = str(row[0])
            if wf_id not in present_wf_ids:
                logger.info(f"Deleting workflow {wf_id} — removed from repo")
                await self.db.execute(
                    sa_delete(Workflow).where(Workflow.id == UUID(wf_id))
                )

        # Delete forms synced from git that are no longer present
        form_result = await self.db.execute(
            select(Form.id).where(
                Form.created_by == "git-sync",
            )
        )
        for row in form_result.all():
            form_id = str(row[0])
            if form_id not in present_form_ids:
                logger.info(f"Deleting form {form_id} — removed from repo")
                await self.db.execute(
                    sa_delete(Form).where(Form.id == UUID(form_id))
                )

        # Delete agents synced from git that are no longer present
        agent_result = await self.db.execute(
            select(Agent.id).where(
                Agent.created_by == "git-sync",
            )
        )
        for row in agent_result.all():
            agent_id = str(row[0])
            if agent_id not in present_agent_ids:
                logger.info(f"Deleting agent {agent_id} — removed from repo")
                await self.db.execute(
                    sa_delete(Agent).where(Agent.id == UUID(agent_id))
                )

        # Delete apps — check all apps in manifest scope
        app_result = await self.db.execute(select(Application.id))
        all_app_ids = {str(row[0]) for row in app_result.all()}
        # Only delete apps that were in a previous manifest (have matching paths)
        # For safety, only delete apps whose IDs appear in neither the manifest nor the present set
        manifest_app_ids = {mapp.id for mapp in manifest.apps.values()}
        for app_id in all_app_ids:
            if app_id in manifest_app_ids and app_id not in present_app_ids:
                logger.info(f"Deleting app {app_id} — removed from repo")
                await self.db.execute(
                    sa_delete(Application).where(Application.id == UUID(app_id))
                )

    # -----------------------------------------------------------------
    # Internal: git operations
    # -----------------------------------------------------------------

    def _clone_or_init(self, target: Path) -> GitRepo:
        """Clone from repo_url, or init if repo is empty.

        Handles the case where target already has files (e.g. entity files
        written by RepoSyncWriter before the first clone). Clones into a
        temp dir and merges .git/ + remote files into target.
        """
        import shutil
        import tempfile

        try:
            # Clone into a temp dir first (git clone requires clean dir)
            clone_dir = Path(tempfile.mkdtemp(prefix="bifrost-clone-"))
            try:
                repo = GitRepo.clone_from(
                    self.repo_url,
                    str(clone_dir),
                    branch=self.branch,
                )
                # Move .git/ to the target
                shutil.move(str(clone_dir / ".git"), str(target / ".git"))
                # Copy any tracked files from clone that aren't in target
                for item in clone_dir.iterdir():
                    if item.name == ".git":
                        continue
                    dest = target / item.name
                    if not dest.exists():
                        if item.is_dir():
                            shutil.copytree(str(item), str(dest))
                        else:
                            shutil.copy2(str(item), str(dest))
                    else:
                        logger.info(f"Skipping remote file {item.name} — already exists in working tree")
                # Open the repo at target
                return GitRepo(str(target))
            finally:
                shutil.rmtree(clone_dir, ignore_errors=True)
        except Exception as e:
            err_str = str(e)
            # Empty repo or branch doesn't exist yet
            if "not found" in err_str.lower() or "empty" in err_str.lower() or "could not find remote branch" in err_str.lower():
                repo = GitRepo.init(str(target))
                repo.create_remote("origin", self.repo_url)
                return repo
            raise SyncError(f"Failed to clone {self.repo_url}: {e}") from e

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
        """Import a form from repo YAML into the DB using FormIndexer."""
        from uuid import UUID

        from src.services.file_storage.indexers.form import FormIndexer

        data = yaml.safe_load(content.decode("utf-8"))
        if not data:
            return

        data["id"] = mform.id
        if mform.organization_id:
            from sqlalchemy.dialects.postgresql import insert as pg_insert

            from src.models.orm.forms import Form

            stmt = pg_insert(Form).values(
                id=UUID(mform.id),
                name=data.get("name", ""),
                is_active=True,
                created_by="git-sync",
                organization_id=UUID(mform.organization_id),
            ).on_conflict_do_nothing(index_elements=["id"])
            await self.db.execute(stmt)

        updated_content = yaml.dump(data, default_flow_style=False, sort_keys=False).encode("utf-8")
        indexer = FormIndexer(self.db)
        await indexer.index_form(f"forms/{mform.id}.form.yaml", updated_content)

    async def _import_agent(self, magent, content: bytes) -> None:
        """Import an agent from repo YAML into the DB using AgentIndexer."""
        from uuid import UUID

        from src.services.file_storage.indexers.agent import AgentIndexer

        data = yaml.safe_load(content.decode("utf-8"))
        if not data:
            return

        data["id"] = magent.id
        if magent.organization_id:
            from sqlalchemy.dialects.postgresql import insert as pg_insert

            from src.models.orm.agents import Agent

            stmt = pg_insert(Agent).values(
                id=UUID(magent.id),
                name=data.get("name", ""),
                system_prompt=data.get("system_prompt", ""),
                is_active=True,
                created_by="git-sync",
                organization_id=UUID(magent.organization_id),
            ).on_conflict_do_nothing(index_elements=["id"])
            await self.db.execute(stmt)

        updated_content = yaml.dump(data, default_flow_style=False, sort_keys=False).encode("utf-8")
        indexer = AgentIndexer(self.db)
        await indexer.index_agent(f"agents/{magent.id}.agent.yaml", updated_content)

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
