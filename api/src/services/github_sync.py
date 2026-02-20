"""
Git Sync Service

GitPython-based synchronization. S3 _repo/ is the persistent working tree.

Key principles:
1. Git working tree is source of truth during sync operations
2. GitPython for clone/pull/push/commit
3. Conflict detection with user resolution
4. .bifrost/ split manifest files declare entity identity
5. Preflight validates repo health (syntax, lint, refs, orphans)
"""

import hashlib
import logging
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import UUID

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
        DiscardResult,
        DiffResult,
        FetchResult,
        PullResult,
        PushResult,
        ResolveResult,
        WorkingTreeStatus,
    )
    from src.services.sync_ops import SyncOp

from src.services.manifest import (
    Manifest,
    get_all_entity_ids,
    read_manifest_from_dir,
)

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

                # Regenerate manifest from DB so working tree reflects current platform state
                await self._regenerate_manifest_to_dir(self.db, work_dir)

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
        """Get working tree status (uncommitted changes)."""
        from src.models.contracts.github import ChangedFile, MergeConflict, WorkingTreeStatus

        try:
            async with self.repo_manager.checkout() as work_dir:
                repo = self._open_or_init(work_dir)

                # Regenerate manifest from DB so working tree reflects current platform state
                await self._regenerate_manifest_to_dir(self.db, work_dir)

                # Check for unresolved conflicts BEFORE git add (which would resolve them)
                conflict_list: list[MergeConflict] = []
                try:
                    unmerged = repo.index.unmerged_blobs()
                    for cpath in sorted(unmerged.keys()):
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
                        metadata = extract_entity_metadata(str(cpath))
                        conflict_list.append(MergeConflict(
                            path=str(cpath),
                            ours_content=ours_content,
                            theirs_content=theirs_content,
                            display_name=metadata.display_name,
                            entity_type=metadata.entity_type,
                        ))
                except Exception:
                    pass  # No unmerged entries

                # If there are conflicts, don't stage/unstage — just return conflicts
                if conflict_list:
                    return WorkingTreeStatus(
                        changed_files=[],
                        total_changes=0,
                        conflicts=conflict_list,
                    )

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
                            # Porcelain rename format: "old_path -> new_path"
                            if " -> " in path:
                                path = path.split(" -> ", 1)[1]
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

    @staticmethod
    async def _regenerate_manifest_to_dir(db, work_dir) -> None:
        """Generate manifest from DB and write split files to work_dir/.bifrost/."""
        from src.services.manifest import serialize_manifest_dir, MANIFEST_FILES
        from src.services.manifest_generator import generate_manifest

        manifest = await generate_manifest(db)

        # Filter out entities whose files don't exist in work_dir.
        # The DB may contain entities from other workspaces or deleted files;
        # the manifest should only reference files actually present in the repo.
        manifest.workflows = {
            k: v for k, v in manifest.workflows.items()
            if (work_dir / v.path).exists()
        }
        manifest.forms = {
            k: v for k, v in manifest.forms.items()
            if (work_dir / v.path).exists()
        }
        manifest.agents = {
            k: v for k, v in manifest.agents.items()
            if (work_dir / v.path).exists()
        }
        manifest.apps = {
            k: v for k, v in manifest.apps.items()
            if (work_dir / v.path).exists()
        }

        # Filter configs to only include those whose integration_id is present
        # in the manifest (or has no integration_id). This prevents stale configs
        # from referencing integrations that aren't part of this repo.
        integration_ids = {v.id for v in manifest.integrations.values()}
        manifest.configs = {
            k: v for k, v in manifest.configs.items()
            if v.integration_id is None or v.integration_id in integration_ids
        }

        files = serialize_manifest_dir(manifest)

        bifrost_dir = work_dir / ".bifrost"
        bifrost_dir.mkdir(parents=True, exist_ok=True)

        for filename, content in files.items():
            (bifrost_dir / filename).write_text(content)

        # Remove files for now-empty entity types
        for filename in MANIFEST_FILES.values():
            path = bifrost_dir / filename
            if filename not in files and path.exists():
                path.unlink()

    async def _reindex_registered_workflows(self, work_dir) -> int:
        """Re-run WorkflowIndexer on all registered workflow .py files."""
        from src.services.file_storage.indexers.workflow import WorkflowIndexer
        from src.models.orm.workflows import Workflow as WfORM
        from sqlalchemy import select

        indexer = WorkflowIndexer(self.db)
        result = await self.db.execute(
            select(WfORM.path).where(WfORM.is_active.is_(True)).distinct()
        )
        paths = [row[0] for row in result.all()]
        count = 0

        for py_path in paths:
            full_path = work_dir / py_path
            if full_path.exists():
                content = full_path.read_bytes()
                await indexer.index_python_file(py_path, content)
                count += 1

        logger.info(f"Re-indexed {count} registered workflow files")
        return count

    async def desktop_commit(self, message: str) -> "CommitResult":
        """
        Commit working tree changes (local only, no push).
        Runs preflight, commits if valid.
        """
        from src.models.contracts.github import CommitResult

        try:
            async with self.repo_manager.checkout() as work_dir:
                repo = self._open_or_init(work_dir)

                # Regenerate manifest from DB before staging
                await self._regenerate_manifest_to_dir(self.db, work_dir)

                # Stage everything (now includes fresh manifest)
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

    async def desktop_pull(self, job_id: str | None = None) -> "PullResult":
        """
        Pull remote changes. On success, import entities.
        On conflict, return PullResult with conflicts list.
        """
        from src.models.contracts.github import MergeConflict, PullResult

        async def _progress(phase: str) -> None:
            if job_id:
                from src.core.pubsub import publish_git_progress
                await publish_git_progress(job_id, phase)

        try:
            async with self.repo_manager.checkout() as work_dir:
                repo = self._open_or_init(work_dir)

                # NOTE: We intentionally do NOT regenerate the manifest here.
                # The sync_execute flow commits first (which regenerates the manifest),
                # then calls desktop_pull. Regenerating here would overwrite the
                # manifest with DB state and stash it, causing conflicts with remote.

                # Fetch first
                await _progress("Fetching remote...")
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

                # Stash local changes before merge (like GitHub Desktop)
                stashed = False
                try:
                    # --include-untracked captures new files too
                    result = repo.git.stash("push", "--include-untracked", "-m", "bifrost-pull-stash")
                    stashed = "No local changes" not in result
                except Exception as e:
                    logger.debug(f"Stash before pull: {e}")

                # Attempt merge
                await _progress("Merging changes...")
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
                        # Note: stash stays intact, will be popped after resolve
                        return PullResult(
                            success=False,
                            conflicts=conflicts,
                            error="Merge conflicts detected",
                        )
                    else:
                        # Non-conflict merge failure — restore stash and re-raise
                        if stashed:
                            try:
                                repo.git.stash("pop")
                            except Exception:
                                logger.warning("Failed to pop stash after merge failure")
                        raise

                # Import entities from the clean merged state BEFORE popping stash.
                # Stash pop can overwrite merged YAML with pre-merge content, so
                # we must import while the working tree reflects the merged remote.
                await _progress("Importing entities...")
                async with self.db.begin_nested():
                    pulled = await self._import_all_entities(work_dir)
                    await self._delete_removed_entities(work_dir)
                    await self._update_file_index(work_dir)
                await self.db.commit()

                # Pop stash to restore local changes (after import reads clean state)
                await _progress("Cleaning up...")
                if stashed:
                    try:
                        repo.git.stash("pop")
                    except Exception as e:
                        logger.warning(f"Stash pop had conflicts: {e}")

                        # Parse stash pop conflicts the same way as merge conflicts
                        stash_conflicts: list[MergeConflict] = []
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
                            stash_conflicts.append(MergeConflict(
                                path=cpath,
                                ours_content=ours_content,
                                theirs_content=theirs_content,
                                display_name=metadata.display_name,
                                entity_type=metadata.entity_type,
                            ))

                        return PullResult(
                            success=False,
                            conflicts=stash_conflicts,
                            error="Local changes conflict with pulled changes",
                        )

                # Sync app preview files from repo to _apps/{id}/preview/
                await self._sync_app_previews(work_dir)

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

                # Check for merge state or unmerged entries (stash pop conflicts)
                merge_head = work_dir / ".git" / "MERGE_HEAD"
                is_merge = merge_head.exists()
                has_unmerged = bool(repo.index.unmerged_blobs())

                if not is_merge and not has_unmerged:
                    return ResolveResult(success=False, error="No conflicts to resolve")

                # Apply resolutions
                for cpath, resolution in resolutions.items():
                    if resolution == "ours":
                        repo.git.checkout("--ours", cpath)
                    elif resolution == "theirs":
                        repo.git.checkout("--theirs", cpath)
                    repo.git.add(cpath)

                # Complete the operation
                if is_merge:
                    repo.index.commit("Merge with conflict resolution")
                else:
                    # Stash pop conflict — merge already succeeded, just commit resolved files
                    repo.index.commit("Apply stashed changes with conflict resolution")

                # Import entities atomically with savepoint
                async with self.db.begin_nested():
                    pulled = await self._import_all_entities(work_dir)
                    await self._delete_removed_entities(work_dir)
                    await self._update_file_index(work_dir)
                await self.db.commit()

                # Sync app preview files from repo to _apps/{id}/preview/
                await self._sync_app_previews(work_dir)

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

    async def desktop_discard(self, paths: list[str]) -> "DiscardResult":
        """Discard working tree changes for specific files (git checkout -- <path>)."""
        from src.models.contracts.github import DiscardResult

        try:
            async with self.repo_manager.checkout() as work_dir:
                repo = self._open_or_init(work_dir)
                discarded = []

                for path in paths:
                    file_path = work_dir / path
                    try:
                        if repo.head.is_valid():
                            try:
                                # File exists in HEAD — restore it
                                repo.git.checkout("HEAD", "--", path)
                                discarded.append(path)
                                continue
                            except Exception:
                                pass
                        # Untracked or not in HEAD — just delete
                        if file_path.exists():
                            file_path.unlink()
                            discarded.append(path)
                    except Exception as e:
                        logger.warning(f"Failed to discard {path}: {e}")

                logger.info(f"Discarded {len(discarded)} file(s)")
                return DiscardResult(success=True, discarded=discarded)
        except Exception as e:
            logger.error(f"Discard failed: {e}", exc_info=True)
            return DiscardResult(success=False, error=str(e))

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

    async def _execute_ops(self, ops: "list[SyncOp]") -> int:
        """Execute a list of SyncOps against the DB in order.

        Returns the number of ops executed.
        """
        from src.services.sync_ops import SyncOp  # noqa: F401
        for op in ops:
            await op.execute(self.db)
        return len(ops)

    @staticmethod
    def _ops_to_issues(ops: "list[SyncOp]") -> list[str]:
        """Convert a list of SyncOps to human-readable validation issues.

        Currently returns an empty list — resolution methods detect missing
        refs by logging warnings and skipping. Future work can add issue
        markers to ops for richer dry-run output.
        """
        return []

    async def _plan_import(self, manifest: "Manifest", work_dir: Path) -> "list[SyncOp]":
        """Build and execute SyncOps for importing a manifest (entities only).

        Resolves and immediately executes ops in dependency order.
        Deletions are handled separately by _delete_removed_entities / _resolve_deletions.
        Indexer side-effects (WorkflowIndexer, FormIndexer, AgentIndexer) remain
        in _import_all_entities.

        Import order:
        0a. Organizations (no deps)
        0b. Roles (no deps)
        1.  Workflows (refs org_id)
        2.  Integrations (refs workflow UUIDs for data_provider)
        3.  Configs (refs integration + org UUIDs)
        4.  Apps (refs org UUIDs)
        5.  Tables (refs org + app UUIDs)
        6.  Event Sources + Subscriptions (refs integration + workflow UUIDs)
        7.  Forms (refs workflow + org UUIDs) — metadata only
        8.  Agents (refs workflow + org UUIDs) — metadata only

        Returns the collected workflow + form + agent ops for callers that want
        to inspect them (e.g. for logging or dry-run analysis).
        """
        from src.services.sync_ops import SyncOp  # noqa: F401

        all_ops: list[SyncOp] = []

        # 0a. Resolve organizations (no deps) — execute immediately
        org_ops: list[SyncOp] = []
        for morg in manifest.organizations:
            org_ops.extend(await self._resolve_organization(morg))
        for op in org_ops:
            await op.execute(self.db)
        all_ops.extend(org_ops)

        # 0b. Resolve roles (no deps) — execute immediately
        role_ops: list[SyncOp] = []
        for mrole in manifest.roles:
            role_ops.extend(await self._resolve_role(mrole))
        for op in role_ops:
            await op.execute(self.db)
        all_ops.extend(role_ops)

        # 1. Resolve workflows — execute immediately
        for wf_name, mwf in manifest.workflows.items():
            wf_path = work_dir / mwf.path
            if wf_path.exists():
                wf_ops = await self._resolve_workflow(wf_name, mwf)
                for op in wf_ops:
                    await op.execute(self.db)
                all_ops.extend(wf_ops)

        # 2. Resolve integrations (with config_schema, oauth_provider, mappings)
        for integ_name, minteg in manifest.integrations.items():
            integ_ops = await self._resolve_integration(integ_name, minteg)
            for op in integ_ops:
                await op.execute(self.db)
            all_ops.extend(integ_ops)

        # 3. Resolve configs
        for _config_key, mcfg in manifest.configs.items():
            cfg_ops = await self._resolve_config(mcfg)
            for op in cfg_ops:
                await op.execute(self.db)
            all_ops.extend(cfg_ops)

        # 4. Resolve apps (before tables — tables ref application_id)
        for _app_name, mapp in manifest.apps.items():
            app_path = work_dir / mapp.path
            if app_path.exists():
                content = app_path.read_bytes()
                app_ops = await self._resolve_app(mapp, content)
                for op in app_ops:
                    await op.execute(self.db)
                all_ops.extend(app_ops)

        # 5. Resolve tables (refs org + app UUIDs)
        for table_name, mtable in manifest.tables.items():
            table_ops = await self._resolve_table(table_name, mtable)
            for op in table_ops:
                await op.execute(self.db)
            all_ops.extend(table_ops)

        # 6. Resolve event sources + subscriptions
        for es_name, mes in manifest.events.items():
            es_ops = await self._resolve_event_source(es_name, mes)
            for op in es_ops:
                await op.execute(self.db)
            all_ops.extend(es_ops)

        # 7. Resolve forms (metadata ops only — indexer called in _import_all_entities)
        for _form_name, mform in manifest.forms.items():
            form_path = work_dir / mform.path
            if form_path.exists():
                content = form_path.read_bytes()
                form_ops = await self._resolve_form(mform, content)
                for op in form_ops:
                    await op.execute(self.db)
                all_ops.extend(form_ops)

        # 8. Resolve agents (metadata ops only — indexer called in _import_all_entities)
        for _agent_name, magent in manifest.agents.items():
            agent_path = work_dir / magent.path
            if agent_path.exists():
                content = agent_path.read_bytes()
                agent_ops = await self._resolve_agent(magent, content)
                for op in agent_ops:
                    await op.execute(self.db)
                all_ops.extend(agent_ops)

        return all_ops

    async def _import_all_entities(self, work_dir: Path) -> int:
        """Import all entities from the working tree into the DB.

        Delegates to _plan_import which resolves and immediately executes ops,
        then runs indexer side-effects for workflows, forms, and agents.

        Import order follows dependency chain:
        0a. Organizations (no deps)
        0b. Roles (no deps)
        1.  Workflows (refs org_id)
        2.  Integrations (refs workflow UUIDs for data_provider)
        3.  Configs (refs integration + org UUIDs)
        4.  Apps (refs org UUIDs)
        5.  Tables (refs org + app UUIDs)
        6.  Event Sources + Subscriptions (refs integration + workflow UUIDs)
        7.  Forms (refs workflow + org UUIDs)
        8.  Agents (refs workflow + org UUIDs)

        Returns count of entities imported.
        """
        from uuid import UUID

        bifrost_dir = work_dir / ".bifrost"
        manifest = read_manifest_from_dir(bifrost_dir)

        has_entities = (
            manifest.organizations or manifest.roles
            or manifest.workflows or manifest.forms or manifest.agents or manifest.apps
            or manifest.integrations or manifest.configs or manifest.tables
            or manifest.events
        )
        if not has_entities:
            return 0

        count = 0

        # Run all resolve ops (including immediate execution inside _plan_import)
        await self._plan_import(manifest, work_dir)

        # Count imported entities
        count += len(manifest.organizations)
        count += len(manifest.roles)
        count += sum(1 for mwf in manifest.workflows.values() if (work_dir / mwf.path).exists())
        count += len(manifest.integrations)
        count += len(manifest.configs)
        count += sum(1 for mapp in manifest.apps.values() if (work_dir / mapp.path).exists())
        count += len(manifest.tables)
        count += len(manifest.events)

        # Indexer side-effects: FormIndexer for each form
        from src.services.file_storage.indexers.form import FormIndexer
        form_indexer = FormIndexer(self.db)
        for _form_name, mform in manifest.forms.items():
            form_path = work_dir / mform.path
            if form_path.exists():
                content = form_path.read_bytes()
                data = yaml.safe_load(content.decode("utf-8"))
                if data:
                    data["id"] = mform.id
                    # Resolve portable refs (path::function_name) to UUIDs
                    await self._resolve_ref_field(data, "workflow_id")
                    await self._resolve_ref_field(data, "launch_workflow_id")
                    updated_content = yaml.dump(data, default_flow_style=False, sort_keys=False).encode("utf-8")
                    await form_indexer.index_form(f"forms/{mform.id}.form.yaml", updated_content)

                    # Post-indexer: update org_id and access_level (indexer skips these)
                    from sqlalchemy import update as sa_update
                    from src.models.orm.forms import Form
                    org_id_uuid = UUID(mform.organization_id) if mform.organization_id else None
                    form_id_uuid = UUID(mform.id)
                    post_values: dict = {}
                    if org_id_uuid:
                        post_values["organization_id"] = org_id_uuid
                    if hasattr(mform, "access_level") and mform.access_level:
                        post_values["access_level"] = mform.access_level
                    if post_values:
                        post_values["updated_at"] = datetime.now(timezone.utc)
                        await self.db.execute(
                            sa_update(Form).where(Form.id == form_id_uuid).values(**post_values)
                        )
                count += 1

        # Indexer side-effects: AgentIndexer for each agent
        from src.services.file_storage.indexers.agent import AgentIndexer
        agent_indexer = AgentIndexer(self.db)
        for _agent_name, magent in manifest.agents.items():
            agent_path = work_dir / magent.path
            if agent_path.exists():
                content = agent_path.read_bytes()
                data = yaml.safe_load(content.decode("utf-8"))
                if data:
                    data["id"] = magent.id
                    # Resolve portable refs (path::function_name) to UUIDs in tool_ids
                    await self._resolve_ref_field(data, "tool_ids")
                    if "tools" in data and "tool_ids" not in data:
                        await self._resolve_ref_field(data, "tools")
                    updated_content = yaml.dump(data, default_flow_style=False, sort_keys=False).encode("utf-8")
                    await agent_indexer.index_agent(f"agents/{magent.id}.agent.yaml", updated_content)

                    # Post-indexer: update org_id and access_level (indexer skips these)
                    from sqlalchemy import update as sa_update
                    from src.models.orm.agents import Agent
                    org_id_uuid = UUID(magent.organization_id) if magent.organization_id else None
                    agent_id_uuid = UUID(magent.id)
                    post_values_a: dict = {}
                    if org_id_uuid:
                        post_values_a["organization_id"] = org_id_uuid
                    if hasattr(magent, "access_level") and magent.access_level:
                        post_values_a["access_level"] = magent.access_level
                    if post_values_a:
                        post_values_a["updated_at"] = datetime.now(timezone.utc)
                        await self.db.execute(
                            sa_update(Agent).where(Agent.id == agent_id_uuid).values(**post_values_a)
                        )
                count += 1

        return count

    async def _delete_removed_entities(self, work_dir: Path) -> None:
        """Delete entities that disappeared from the manifest after a pull.

        Delegates to _resolve_deletions which returns ops, then executes them.
        Kept as a separate method for backward compatibility with callers.
        """
        deletion_ops = await self._resolve_deletions(work_dir)
        for op in deletion_ops:
            await op.execute(self.db)

    # -----------------------------------------------------------------
    # App preview sync
    # -----------------------------------------------------------------

    async def _sync_app_previews(self, work_dir: Path) -> None:
        """Sync app preview files from repo working tree to _apps/{id}/preview/ in S3.

        Reads the manifest to find app entries, derives the source directory
        from each app's path, and copies files to the preview store.
        """
        from src.services.app_storage import AppStorageService

        bifrost_dir = work_dir / ".bifrost"
        manifest = read_manifest_from_dir(bifrost_dir)

        if not manifest.apps:
            return

        app_storage = AppStorageService(self.repo_manager._settings)

        for _app_name, mapp in manifest.apps.items():
            # Derive source directory from app path (e.g. "apps/tickbox-grc/app.yaml" -> "apps/tickbox-grc")
            app_source_dir = str(Path(mapp.path).parent)

            try:
                synced, compile_errors = await app_storage.sync_preview_compiled(
                    mapp.id, app_source_dir
                )
                logger.info(f"Synced {synced} compiled preview files for app {mapp.id}")
                if compile_errors:
                    logger.warning(
                        f"Compile errors for app {mapp.id}: {compile_errors}"
                    )
            except Exception as e:
                logger.warning(f"Failed to sync preview for app {mapp.id}: {e}")

    # -----------------------------------------------------------------
    # Reimport from repo (no git operations)
    # -----------------------------------------------------------------

    async def reimport_from_repo(self) -> int:
        """Re-import all entities from S3 _repo/ without git operations.

        Downloads the working tree from S3, imports entities into DB,
        updates file_index, and syncs app previews.

        Returns count of entities imported.
        """
        async with self.repo_manager.checkout() as work_dir:
            # Regenerate manifest from current DB state
            await self._regenerate_manifest_to_dir(self.db, work_dir)

            # Import entities atomically with savepoint
            async with self.db.begin_nested():
                count = await self._import_all_entities(work_dir)
                await self._delete_removed_entities(work_dir)
                await self._update_file_index(work_dir)
            await self.db.commit()

            # Re-run indexers on all registered workflow files
            await self._reindex_registered_workflows(work_dir)

            # Sync app preview files
            await self._sync_app_previews(work_dir)

            logger.info(f"Reimport complete: {count} entities")
            return count

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

    async def _resolve_organization(self, morg) -> "list[SyncOp]":
        """Resolve an organization from manifest into SyncOps.

        ID-first, name-fallback upsert strategy. Returns ops list without
        executing — caller is responsible for execution order.
        """
        from uuid import UUID

        from src.models.orm.organizations import Organization
        from src.services.sync_ops import SyncOp, Upsert  # noqa: F401

        org_id = UUID(morg.id)

        # 1. Try by ID first (handles renames)
        by_id = await self.db.execute(
            select(Organization.id).where(Organization.id == org_id)
        )
        existing_by_id = by_id.scalar_one_or_none()

        if existing_by_id is not None:
            return [Upsert(
                model=Organization,
                id=org_id,
                values={"name": morg.name, "is_active": True},
                match_on="id",
            )]

        # 2. Try by name (cross-env ID sync)
        by_name = await self.db.execute(
            select(Organization.id).where(Organization.name == morg.name)
        )
        existing_by_name = by_name.scalar_one_or_none()

        if existing_by_name is not None:
            return [Upsert(
                model=Organization,
                id=org_id,
                values={"id": org_id, "name": morg.name, "is_active": True},
                match_on="name",
            )]

        # 3. Insert new
        return [Upsert(
            model=Organization,
            id=org_id,
            values={"name": morg.name, "is_active": True, "created_by": "git-sync"},
            match_on="id",
        )]

    async def _resolve_role(self, mrole) -> "list[SyncOp]":
        """Resolve a role from manifest into SyncOps.

        ID-first, name-fallback upsert strategy. Returns ops list without
        executing — caller is responsible for execution order.
        """
        from uuid import UUID

        from src.models.orm.users import Role
        from src.services.sync_ops import SyncOp, Upsert  # noqa: F401

        role_id = UUID(mrole.id)

        # 1. Try by ID first (handles renames)
        by_id = await self.db.execute(
            select(Role.id).where(Role.id == role_id)
        )
        existing_by_id = by_id.scalar_one_or_none()

        if existing_by_id is not None:
            return [Upsert(
                model=Role,
                id=role_id,
                values={"name": mrole.name, "is_active": True},
                match_on="id",
            )]

        # 2. Try by name (cross-env ID sync)
        by_name = await self.db.execute(
            select(Role.id).where(Role.name == mrole.name)
        )
        existing_by_name = by_name.scalar_one_or_none()

        if existing_by_name is not None:
            return [Upsert(
                model=Role,
                id=role_id,
                values={"id": role_id, "name": mrole.name, "is_active": True},
                match_on="name",
            )]

        # 3. Insert new
        return [Upsert(
            model=Role,
            id=role_id,
            values={"name": mrole.name, "is_active": True, "created_by": "git-sync"},
            match_on="id",
        )]

    async def _sync_role_assignments(self, entity_id, manifest_roles: list[str], junction_model, entity_fk_name: str) -> None:
        """Sync role assignments for an entity: add first, then remove (no permission gap).

        Args:
            entity_id: The entity's UUID
            manifest_roles: List of role UUID strings from manifest
            junction_model: The ORM model for the junction table (e.g. WorkflowRole)
            entity_fk_name: The FK column name on the junction table (e.g. 'workflow_id')
        """
        from uuid import UUID

        from sqlalchemy import delete as sa_delete
        from sqlalchemy.dialects.postgresql import insert

        desired_role_ids = {UUID(r) for r in manifest_roles}

        # Get current assignments
        entity_fk_col = getattr(junction_model, entity_fk_name)
        role_id_col = getattr(junction_model, "role_id")
        result = await self.db.execute(
            select(role_id_col).where(entity_fk_col == entity_id)
        )
        current_role_ids = {row[0] for row in result.all()}

        # ADD new assignments first (no permission gap)
        for role_id in desired_role_ids - current_role_ids:
            stmt = insert(junction_model).values(**{
                entity_fk_name: entity_id,
                "role_id": role_id,
                "assigned_by": "git-sync",
            }).on_conflict_do_nothing()
            await self.db.execute(stmt)

        # THEN remove stale assignments
        for role_id in current_role_ids - desired_role_ids:
            await self.db.execute(
                sa_delete(junction_model).where(
                    entity_fk_col == entity_id,
                    role_id_col == role_id,
                )
            )

    async def _resolve_workflow(self, manifest_name: str, mwf) -> "list[SyncOp]":
        """Resolve a workflow from manifest into SyncOps.

        Uses natural-key (path+function_name) or ID lookup to determine the
        correct upsert strategy. Returns ops list without executing.
        """
        from uuid import UUID

        from src.models.orm.workflow_roles import WorkflowRole
        from src.models.orm.workflows import Workflow
        from src.services.sync_ops import SyncOp, SyncRoles, Upsert  # noqa: F401

        wf_id = UUID(mwf.id)
        org_id = UUID(mwf.organization_id) if mwf.organization_id else None

        # Check for existing workflow by natural key (path, function_name) OR by ID
        by_natural = await self.db.execute(
            select(Workflow.id).where(
                Workflow.path == mwf.path,
                Workflow.function_name == mwf.function_name,
            )
        )
        existing_by_natural = by_natural.scalar_one_or_none()

        by_id = await self.db.execute(
            select(Workflow.id).where(Workflow.id == wf_id)
        )
        existing_by_id = by_id.scalar_one_or_none()

        wf_values = {
            "name": manifest_name,
            "function_name": mwf.function_name,
            "path": mwf.path,
            "type": getattr(mwf, "type", "workflow"),
            "is_active": True,
            "organization_id": org_id,
            "access_level": getattr(mwf, "access_level", "role_based"),
            "endpoint_enabled": getattr(mwf, "endpoint_enabled", False),
            "timeout_seconds": getattr(mwf, "timeout_seconds", 1800),
            "public_endpoint": getattr(mwf, "public_endpoint", False),
            "category": getattr(mwf, "category", "General"),
            "tags": getattr(mwf, "tags", []),
        }

        ops: list[SyncOp] = []

        if existing_by_natural is not None:
            # Match on natural key — update (including ID if it changed)
            ops.append(Upsert(
                model=Workflow,
                id=existing_by_natural,
                values={"id": wf_id, **wf_values},
                match_on="id",
            ))
        elif existing_by_id is not None:
            # Same ID but path/function changed (rename) — update
            ops.append(Upsert(
                model=Workflow,
                id=wf_id,
                values=wf_values,
                match_on="id",
            ))
        else:
            # New workflow — insert
            ops.append(Upsert(
                model=Workflow,
                id=wf_id,
                values=wf_values,
                match_on="id",
            ))

        # Role sync op
        if hasattr(mwf, "roles") and mwf.roles:
            role_ids = {UUID(r) for r in mwf.roles}
            ops.append(SyncRoles(
                junction_model=WorkflowRole,
                entity_fk="workflow_id",
                entity_id=wf_id,
                role_ids=role_ids,
            ))

        return ops

    async def _resolve_workflow_ref(self, ref: str) -> "UUID | None":
        """Resolve a workflow reference: try UUID, then path::function_name, then name.

        Used by event subscription sync to support flexible workflow_id formats
        in the manifest (UUID, path::func, or workflow name).

        Returns UUID if found, None otherwise.
        """
        from uuid import UUID

        from src.models.orm.workflows import Workflow

        # 1. Try as UUID — direct ID match
        try:
            wf_id = UUID(ref)
            result = await self.db.execute(select(Workflow.id).where(Workflow.id == wf_id))
            if result.scalar_one_or_none():
                return wf_id
        except ValueError:
            pass

        # 2. Try as path::function_name
        if "::" in ref:
            path, func = ref.rsplit("::", 1)
            result = await self.db.execute(
                select(Workflow.id).where(Workflow.path == path, Workflow.function_name == func)
            )
            wf_id = result.scalar_one_or_none()
            if wf_id:
                return wf_id

        # 3. Try as workflow name
        result = await self.db.execute(select(Workflow.id).where(Workflow.name == ref))
        wf_id = result.scalar_one_or_none()
        if wf_id:
            return wf_id

        return None

    async def _resolve_portable_ref(self, ref: str) -> str | None:
        """Resolve a path::function_name portable ref to a workflow UUID string.

        Args:
            ref: A string like "workflows/foo.py::bar"

        Returns:
            UUID string if found, None otherwise
        """
        from src.models.orm.workflows import Workflow

        if "::" not in ref:
            return None

        path, _, function_name = ref.rpartition("::")
        if not path or not function_name:
            return None

        result = await self.db.execute(
            select(Workflow.id).where(
                Workflow.path == path,
                Workflow.function_name == function_name,
                Workflow.is_active.is_(True),
            )
        )
        wf_id = result.scalar_one_or_none()
        return str(wf_id) if wf_id else None

    async def _resolve_ref_field(self, data: dict, field_name: str) -> None:
        """Resolve a portable ref in a dict field to a UUID in-place.

        If the field value contains '::', attempts to resolve it.
        If resolution fails, the value is left unchanged (will be stored as-is).
        """
        value = data.get(field_name)
        if isinstance(value, str) and "::" in value:
            resolved = await self._resolve_portable_ref(value)
            if resolved:
                data[field_name] = resolved
                logger.info(f"Resolved portable ref '{value}' -> '{resolved}'")
            else:
                logger.warning(f"Could not resolve portable ref '{value}' for field '{field_name}'")
        elif isinstance(value, list):
            # Handle list fields like tool_ids
            resolved_list = []
            for item in value:
                if isinstance(item, str) and "::" in item:
                    resolved = await self._resolve_portable_ref(item)
                    resolved_list.append(resolved if resolved else item)
                else:
                    resolved_list.append(item)
            data[field_name] = resolved_list

    async def _resolve_deletions(self, work_dir: Path) -> "list[SyncOp]":
        """Compute delete/deactivate ops for entities removed from the manifest.

        Git history provides the undo mechanism — no need for a DB recycle bin.
        Compares manifest entity IDs against active DB entities to find deletions.

        Deletion strategy per entity type:
        - Workflows, Forms, Agents, Apps: hard-delete (existing behavior)
        - Integrations, Configs, Events: hard-delete (manifest is source of truth)
        - Tables: soft-delete (keep data, set inactive — never created here currently)
        - Knowledge: not managed by git-sync (ephemeral, derived from documents)
        - Organizations, Roles: soft-delete (only git-sync created ones)
        """
        from uuid import UUID

        from src.models.orm.agents import Agent
        from src.models.orm.applications import Application
        from src.models.orm.config import Config
        from src.models.orm.events import EventSource, EventSubscription
        from src.models.orm.forms import Form
        from src.models.orm.integrations import Integration
        from src.models.orm.organizations import Organization
        from src.models.orm.tables import Table
        from src.models.orm.users import Role
        from src.models.orm.workflows import Workflow
        from src.services.sync_ops import Deactivate, Delete, SyncOp  # noqa: F401

        manifest = read_manifest_from_dir(work_dir / ".bifrost")

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

        # IDs present in manifest (no file check needed for non-file entities)
        present_integ_ids = {minteg.id for minteg in manifest.integrations.values()}
        present_config_ids = {mcfg.id for mcfg in manifest.configs.values()}
        present_table_ids = {mtable.id for mtable in manifest.tables.values()}
        present_event_ids = {mes.id for mes in manifest.events.values()}
        present_sub_ids: set[str] = set()
        for mes in manifest.events.values():
            for msub in mes.subscriptions:
                present_sub_ids.add(msub.id)
        present_org_ids = {morg.id for morg in manifest.organizations}
        present_role_ids = {mrole.id for mrole in manifest.roles}

        ops: list[SyncOp] = []

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
                ops.append(Delete(model=Workflow, id=UUID(wf_id)))

        # Delete integrations not in manifest
        integ_result = await self.db.execute(
            select(Integration.id).where(Integration.is_deleted == False)  # noqa: E712
        )
        for row in integ_result.all():
            integ_id = str(row[0])
            if integ_id not in present_integ_ids:
                logger.info(f"Deleting integration {integ_id} — removed from repo")
                ops.append(Delete(model=Integration, id=UUID(integ_id)))

        # Delete configs not in manifest (skip integration-schema-linked configs —
        # those are user-set values managed by IntegrationConfigSchema cascade)
        config_result = await self.db.execute(
            select(Config.id, Config.config_schema_id)
        )
        for row in config_result.all():
            config_id = str(row[0])
            if config_id not in present_config_ids and row[1] is None:
                logger.info(f"Deleting config {config_id} — removed from repo")
                ops.append(Delete(model=Config, id=UUID(config_id)))

        # Soft-delete tables not in manifest (keep data)
        table_result = await self.db.execute(select(Table.id))
        for row in table_result.all():
            table_id = str(row[0])
            if table_id not in present_table_ids:
                logger.info(f"Table {table_id} not in manifest (data preserved)")

        # Delete event subscriptions not in manifest
        sub_result = await self.db.execute(select(EventSubscription.id))
        for row in sub_result.all():
            sub_id = str(row[0])
            if sub_id not in present_sub_ids:
                logger.info(f"Deleting event subscription {sub_id} — removed from repo")
                ops.append(Delete(model=EventSubscription, id=UUID(sub_id)))

        # Delete event sources not in manifest
        es_result = await self.db.execute(select(EventSource.id))
        for row in es_result.all():
            es_id = str(row[0])
            if es_id not in present_event_ids:
                logger.info(f"Deleting event source {es_id} — removed from repo")
                ops.append(Delete(model=EventSource, id=UUID(es_id)))

        # Delete forms synced from git that are no longer present
        form_result = await self.db.execute(
            select(Form.id).where(Form.created_by == "git-sync")
        )
        for row in form_result.all():
            form_id = str(row[0])
            if form_id not in present_form_ids:
                logger.info(f"Deleting form {form_id} — removed from repo")
                ops.append(Delete(model=Form, id=UUID(form_id)))

        # Delete agents synced from git that are no longer present
        agent_result = await self.db.execute(
            select(Agent.id).where(Agent.created_by == "git-sync")
        )
        for row in agent_result.all():
            agent_id = str(row[0])
            if agent_id not in present_agent_ids:
                logger.info(f"Deleting agent {agent_id} — removed from repo")
                ops.append(Delete(model=Agent, id=UUID(agent_id)))

        # Delete apps — check all apps in manifest scope
        app_result = await self.db.execute(select(Application.id))
        all_app_ids = {str(row[0]) for row in app_result.all()}
        manifest_app_ids = {mapp.id for mapp in manifest.apps.values()}
        for app_id in all_app_ids:
            if app_id in manifest_app_ids and app_id not in present_app_ids:
                logger.info(f"Deleting app {app_id} — removed from repo")
                ops.append(Delete(model=Application, id=UUID(app_id)))

        # Soft-delete organizations not in manifest (only git-sync created ones)
        if present_org_ids:
            org_result = await self.db.execute(
                select(Organization.id).where(
                    Organization.is_active == True,  # noqa: E712
                    Organization.created_by == "git-sync",
                )
            )
            for row in org_result.all():
                org_id = str(row[0])
                if org_id not in present_org_ids:
                    logger.info(f"Deactivating organization {org_id} — removed from manifest")
                    ops.append(Deactivate(model=Organization, id=UUID(org_id)))

        # Soft-delete roles not in manifest (only git-sync created ones)
        if present_role_ids:
            role_result = await self.db.execute(
                select(Role.id).where(
                    Role.is_active == True,  # noqa: E712
                    Role.created_by == "git-sync",
                )
            )
            for row in role_result.all():
                role_id = str(row[0])
                if role_id not in present_role_ids:
                    logger.info(f"Deactivating role {role_id} — removed from manifest")
                    ops.append(Deactivate(model=Role, id=UUID(role_id)))


        return ops

    async def _resolve_integration(self, integ_name: str, minteg) -> "list[SyncOp]":
        """Resolve an integration from manifest into SyncOps.

        Upserts the integration and directly executes config schema, oauth
        provider, and mapping sub-operations (these are complex sub-object
        syncs without their own resolution pattern).
        """
        from uuid import UUID

        from sqlalchemy.dialects.postgresql import insert

        from src.models.orm.integrations import Integration, IntegrationConfigSchema, IntegrationMapping
        from src.models.orm.oauth import OAuthProvider
        from src.services.sync_ops import SyncOp, Upsert  # noqa: F401

        integ_id = UUID(minteg.id)

        # Two-step upsert: check by natural key (name) or by ID
        by_name = await self.db.execute(
            select(Integration.id).where(Integration.name == integ_name)
        )
        existing_by_name = by_name.scalar_one_or_none()

        integ_values: dict = {
            "name": integ_name,
            "entity_id": minteg.entity_id,
            "entity_id_name": minteg.entity_id_name,
            "default_entity_id": minteg.default_entity_id,
            "list_entities_data_provider_id": (
                UUID(minteg.list_entities_data_provider_id)
                if minteg.list_entities_data_provider_id else None
            ),
            "is_deleted": False,
        }

        # Upsert integration row FIRST (must exist before config schema / mapping FKs)
        if existing_by_name is not None:
            upsert_op = Upsert(
                model=Integration,
                id=existing_by_name,
                values={"id": integ_id, **integ_values},
                match_on="id",
            )
        else:
            upsert_op = Upsert(
                model=Integration,
                id=integ_id,
                values=integ_values,
                match_on="id",
            )
        await upsert_op.execute(self.db)

        # Sync config schema items: upsert by (integration_id, key) to preserve IDs
        # (Config rows reference schema IDs via FK — deleting schema cascades to configs)
        from sqlalchemy import delete as sa_delete
        existing_cs_result = await self.db.execute(
            select(IntegrationConfigSchema).where(
                IntegrationConfigSchema.integration_id == integ_id
            )
        )
        existing_cs_by_key = {cs.key: cs for cs in existing_cs_result.scalars().all()}
        manifest_cs_keys = {cs.key for cs in minteg.config_schema}

        for cs in minteg.config_schema:
            if cs.key in existing_cs_by_key:
                existing_cs = existing_cs_by_key[cs.key]
                existing_cs.type = cs.type
                existing_cs.required = cs.required
                existing_cs.description = cs.description
                existing_cs.options = cs.options
                existing_cs.position = cs.position
            else:
                cs_stmt = insert(IntegrationConfigSchema).values(
                    integration_id=integ_id,
                    key=cs.key,
                    type=cs.type,
                    required=cs.required,
                    description=cs.description,
                    options=cs.options,
                    position=cs.position,
                )
                await self.db.execute(cs_stmt)

        removed_keys = set(existing_cs_by_key.keys()) - manifest_cs_keys
        if removed_keys:
            await self.db.execute(
                sa_delete(IntegrationConfigSchema).where(
                    IntegrationConfigSchema.integration_id == integ_id,
                    IntegrationConfigSchema.key.in_(removed_keys),
                )
            )

        # Sync OAuth provider (structure only — client_secret never imported)
        if minteg.oauth_provider:
            op_data = minteg.oauth_provider
            op_stmt = insert(OAuthProvider).values(
                provider_name=op_data.provider_name,
                display_name=op_data.display_name,
                oauth_flow_type=op_data.oauth_flow_type,
                client_id=op_data.client_id,
                encrypted_client_secret=b"",  # placeholder — needs manual setup
                authorization_url=op_data.authorization_url,
                token_url=op_data.token_url,
                token_url_defaults=op_data.token_url_defaults or {},
                scopes=op_data.scopes or [],
                redirect_uri=op_data.redirect_uri,
                integration_id=integ_id,
            ).on_conflict_do_update(
                constraint="uq_oauth_providers_integration_id",
                set_={
                    "display_name": op_data.display_name,
                    "oauth_flow_type": op_data.oauth_flow_type,
                    **(
                        {"client_id": op_data.client_id}
                        if op_data.client_id and op_data.client_id != "__NEEDS_SETUP__"
                        else {}
                    ),
                    "authorization_url": op_data.authorization_url,
                    "token_url": op_data.token_url,
                    "token_url_defaults": op_data.token_url_defaults or {},
                    "scopes": op_data.scopes or [],
                    "redirect_uri": op_data.redirect_uri,
                    "updated_at": datetime.now(timezone.utc),
                },
            )
            await self.db.execute(op_stmt)

        # Sync mappings: upsert by (integration_id, organization_id) to preserve oauth_token_id
        existing_m_result = await self.db.execute(
            select(IntegrationMapping).where(
                IntegrationMapping.integration_id == integ_id
            )
        )
        existing_m_by_org: dict[str | None, IntegrationMapping] = {
            str(m.organization_id) if m.organization_id else None: m
            for m in existing_m_result.scalars().all()
        }
        manifest_org_ids = {mapping.organization_id for mapping in minteg.mappings}

        for mapping in minteg.mappings:
            org_key = mapping.organization_id  # str or None
            if org_key in existing_m_by_org:
                existing_m = existing_m_by_org[org_key]
                existing_m.entity_id = mapping.entity_id
                existing_m.entity_name = mapping.entity_name
                if mapping.oauth_token_id is not None:
                    existing_m.oauth_token_id = UUID(mapping.oauth_token_id)
            else:
                m_stmt = insert(IntegrationMapping).values(
                    integration_id=integ_id,
                    organization_id=UUID(mapping.organization_id) if mapping.organization_id else None,
                    entity_id=mapping.entity_id,
                    entity_name=mapping.entity_name,
                    oauth_token_id=UUID(mapping.oauth_token_id) if mapping.oauth_token_id else None,
                )
                await self.db.execute(m_stmt)

        for org_key, existing_m in existing_m_by_org.items():
            if org_key not in manifest_org_ids:
                await self.db.execute(
                    sa_delete(IntegrationMapping).where(
                        IntegrationMapping.id == existing_m.id
                    )
                )

        # Return empty list — all operations executed directly above
        return []

    async def _resolve_config(self, mcfg) -> "list[SyncOp]":
        """Resolve a config entry from manifest into SyncOps.

        Skips writing value if type=SECRET and existing value is non-null
        (don't overwrite manually-entered secrets). Returns ops list.
        """
        from uuid import UUID

        from sqlalchemy.dialects.postgresql import insert

        from src.models.orm.config import Config
        from src.services.sync_ops import SyncOp, Upsert  # noqa: F401

        cfg_id = UUID(mcfg.id)
        integ_id = UUID(mcfg.integration_id) if mcfg.integration_id else None
        org_id = UUID(mcfg.organization_id) if mcfg.organization_id else None

        # Check for existing config by natural key (integration_id, org_id, key)
        existing_query = select(Config.id, Config.value).where(Config.key == mcfg.key)
        if integ_id:
            existing_query = existing_query.where(Config.integration_id == integ_id)
        else:
            existing_query = existing_query.where(Config.integration_id.is_(None))
        if org_id:
            existing_query = existing_query.where(Config.organization_id == org_id)
        else:
            existing_query = existing_query.where(Config.organization_id.is_(None))

        result = await self.db.execute(existing_query)
        existing = result.first()

        if existing is not None:
            existing_id, existing_value = existing

            # Secret with existing value — don't overwrite
            if mcfg.config_type == "secret" and existing_value is not None:
                return []

            # Update existing row (including ID if it changed)
            update_values: dict = {
                "id": cfg_id,
                "key": mcfg.key,
                "config_type": mcfg.config_type,
                "description": mcfg.description,
                "integration_id": integ_id,
                "organization_id": org_id,
                "updated_by": "git-sync",
            }
            if mcfg.config_type != "secret":
                update_values["value"] = mcfg.value if mcfg.value is not None else {}

            return [Upsert(
                model=Config,
                id=existing_id,
                values=update_values,
                match_on="id",
            )]
        else:
            # Insert new row — use direct insert (Config has complex natural key)
            stmt = insert(Config).values(
                id=cfg_id,
                key=mcfg.key,
                config_type=mcfg.config_type,
                description=mcfg.description,
                integration_id=integ_id,
                organization_id=org_id,
                value=mcfg.value if mcfg.value is not None else {},
                updated_by="git-sync",
            ).on_conflict_do_update(
                index_elements=["id"],
                set_={
                    "key": mcfg.key,
                    "config_type": mcfg.config_type,
                    "description": mcfg.description,
                    "integration_id": integ_id,
                    "organization_id": org_id,
                    "updated_by": "git-sync",
                    "updated_at": datetime.now(timezone.utc),
                    **({"value": mcfg.value if mcfg.value is not None else {}} if mcfg.config_type != "secret" else {}),
                },
            )
            await self.db.execute(stmt)
            return []

    async def _resolve_app(self, mapp, content: bytes) -> "list[SyncOp]":
        """Resolve an app from repo into SyncOps (metadata only).

        The indexer call (app.yaml parsing) is a side-effect performed in
        _import_all_entities, not here.
        """
        from pathlib import PurePosixPath
        from uuid import UUID

        from src.models.orm.app_roles import AppRole
        from src.models.orm.applications import Application
        from src.services.sync_ops import SyncOp, SyncRoles, Upsert  # noqa: F401

        data = yaml.safe_load(content.decode("utf-8"))
        if not data:
            return []

        # Derive repo_path from the manifest's canonical path
        repo_path = str(PurePosixPath(mapp.path).parent) if mapp.path else None

        # Slug from manifest entry, or derive from repo_path leaf
        slug = mapp.slug or (PurePosixPath(repo_path).name if repo_path else None)
        if not slug:
            logger.warning(f"App {mapp.id} has no slug or path, skipping")
            return []

        # Ensure repo_path is set even if only slug was available
        if not repo_path:
            repo_path = f"apps/{slug}"

        app_id = UUID(mapp.id)
        org_id = UUID(mapp.organization_id) if mapp.organization_id else None
        access_level = getattr(mapp, "access_level", "role_based")

        # Two-step: check for existing app by natural key (org_id, slug)
        existing_query = select(Application.id).where(Application.slug == slug)
        if org_id:
            existing_query = existing_query.where(Application.organization_id == org_id)
        else:
            existing_query = existing_query.where(Application.organization_id.is_(None))

        existing = await self.db.execute(existing_query)
        existing_id = existing.scalar_one_or_none()

        app_values = {
            "name": data.get("name", ""),
            "description": data.get("description"),
            "slug": slug,
            "repo_path": repo_path,
            "organization_id": org_id,
            "access_level": access_level,
        }

        ops: list[SyncOp] = []

        if existing_id is not None:
            ops.append(Upsert(
                model=Application,
                id=existing_id,
                values={"id": app_id, **app_values},
                match_on="id",
            ))
        else:
            ops.append(Upsert(
                model=Application,
                id=app_id,
                values=app_values,
                match_on="id",
            ))

        # Role sync op
        if hasattr(mapp, "roles") and mapp.roles:
            role_ids = {UUID(r) for r in mapp.roles}
            ops.append(SyncRoles(
                junction_model=AppRole,
                entity_fk="app_id",
                entity_id=app_id,
                role_ids=role_ids,
            ))

        return ops

    async def _resolve_table(self, table_name: str, mtable) -> "list[SyncOp]":
        """Resolve a table definition from manifest into SyncOps (schema only, no data).

        Two-pass natural-key lookup (mirrors _resolve_workflow):
        1. Match by (name, organization_id) — if found, update including ID realignment
        2. Match by ID — if found, update name/schema
        3. Otherwise insert new

        ID realignment ensures the DB row ID matches the manifest UUID so that
        _resolve_deletions can correctly identify which tables are present.
        Documents are preserved in all cases (cascade is on the table row, and
        we never delete the row here).
        """
        from uuid import UUID

        from sqlalchemy import update
        from sqlalchemy.dialects.postgresql import insert

        from src.models.orm.tables import Table
        from src.services.sync_ops import SyncOp  # noqa: F401

        table_id = UUID(mtable.id)
        org_id = UUID(mtable.organization_id) if mtable.organization_id else None
        app_id = UUID(mtable.application_id) if mtable.application_id else None
        now = datetime.now(timezone.utc)

        # 1. Look up by natural key (name + org)
        natural_q = select(Table.id).where(
            Table.name == table_name,
            Table.organization_id == org_id,
        )
        existing_by_natural = (await self.db.execute(natural_q)).scalar_one_or_none()

        if existing_by_natural is not None:
            if existing_by_natural != table_id:
                # ID mismatch (cross-env) — realign the DB row's ID to the manifest ID.
                # Documents have ON UPDATE CASCADE on table_id so they follow along.
                logger.info(
                    f"Realigning table {table_name!r}: DB id={existing_by_natural} → manifest id={table_id}"
                )
            await self.db.execute(
                update(Table)
                .where(Table.id == existing_by_natural)
                .values(
                    id=table_id,
                    description=mtable.description,
                    application_id=app_id,
                    schema=mtable.table_schema,
                    updated_at=now,
                )
            )
            return []

        # 2. Look up by ID (name changed, same ID)
        existing_by_id = (
            await self.db.execute(select(Table.id).where(Table.id == table_id))
        ).scalar_one_or_none()

        if existing_by_id is not None:
            await self.db.execute(
                update(Table)
                .where(Table.id == table_id)
                .values(
                    name=table_name,
                    description=mtable.description,
                    application_id=app_id,
                    schema=mtable.table_schema,
                    updated_at=now,
                )
            )
            return []

        # 3. New table — insert
        stmt = insert(Table).values(
            id=table_id,
            name=table_name,
            description=mtable.description,
            organization_id=org_id,
            application_id=app_id,
            schema=mtable.table_schema,
            created_by="git-sync",
        ).on_conflict_do_nothing()
        await self.db.execute(stmt)

        return []

    async def _resolve_event_source(self, es_name: str, mes) -> "list[SyncOp]":
        """Resolve an event source + subscriptions from manifest into SyncOps.

        Event sources use PostgreSQL ON CONFLICT upserts (PostgreSQL-specific
        constructs); executed directly here, returning empty ops list.
        """
        from uuid import UUID

        from sqlalchemy.dialects.postgresql import insert

        from src.models.orm.events import EventSource, EventSubscription, ScheduleSource, WebhookSource
        from src.services.sync_ops import SyncOp  # noqa: F401

        es_id = UUID(mes.id)

        # Upsert event source
        stmt = insert(EventSource).values(
            id=es_id,
            name=es_name,
            source_type=mes.source_type,
            organization_id=UUID(mes.organization_id) if mes.organization_id else None,
            is_active=mes.is_active,
            created_by="git-sync",
        ).on_conflict_do_update(
            index_elements=["id"],
            set_={
                "name": es_name,
                "source_type": mes.source_type,
                "is_active": mes.is_active,
                "updated_at": datetime.now(timezone.utc),
            },
        )
        await self.db.execute(stmt)

        # Upsert schedule source if applicable
        if mes.source_type == "schedule" and mes.cron_expression:
            sched_stmt = insert(ScheduleSource).values(
                event_source_id=es_id,
                cron_expression=mes.cron_expression,
                timezone=mes.timezone or "UTC",
                enabled=mes.schedule_enabled if mes.schedule_enabled is not None else True,
            ).on_conflict_do_update(
                index_elements=["event_source_id"],
                set_={
                    "cron_expression": mes.cron_expression,
                    "timezone": mes.timezone or "UTC",
                    "enabled": mes.schedule_enabled if mes.schedule_enabled is not None else True,
                    "updated_at": datetime.now(timezone.utc),
                },
            )
            await self.db.execute(sched_stmt)

        # Upsert webhook source if applicable (external state left empty)
        if mes.source_type == "webhook":
            wh_stmt = insert(WebhookSource).values(
                event_source_id=es_id,
                adapter_name=mes.adapter_name,
                integration_id=UUID(mes.webhook_integration_id) if mes.webhook_integration_id else None,
                config=mes.webhook_config or {},
            ).on_conflict_do_update(
                index_elements=["event_source_id"],
                set_={
                    "adapter_name": mes.adapter_name,
                    "integration_id": UUID(mes.webhook_integration_id) if mes.webhook_integration_id else None,
                    "config": mes.webhook_config or {},
                    "updated_at": datetime.now(timezone.utc),
                },
            )
            await self.db.execute(wh_stmt)

        # Sync subscriptions: upsert each
        # workflow_id may be a UUID string, a path::function_name portable ref, or a name
        for msub in mes.subscriptions:
            wf_id: UUID | None = None
            try:
                wf_id = UUID(msub.workflow_id)
            except (ValueError, AttributeError):
                pass

            if wf_id is None:
                # Try path::function_name or name resolution
                resolved = await self._resolve_workflow_ref(msub.workflow_id)
                if resolved is None:
                    logger.warning(
                        f"Event subscription {msub.id}: could not resolve workflow ref "
                        f"'{msub.workflow_id}', skipping"
                    )
                    continue
                wf_id = resolved

            sub_stmt = insert(EventSubscription).values(
                id=UUID(msub.id),
                event_source_id=es_id,
                workflow_id=wf_id,
                event_type=msub.event_type,
                filter_expression=msub.filter_expression,
                input_mapping=msub.input_mapping,
                is_active=msub.is_active,
                created_by="git-sync",
            ).on_conflict_do_update(
                index_elements=["event_source_id", "workflow_id"],
                set_={
                    "id": UUID(msub.id),
                    "workflow_id": wf_id,
                    "event_type": msub.event_type,
                    "filter_expression": msub.filter_expression,
                    "input_mapping": msub.input_mapping,
                    "is_active": msub.is_active,
                    "updated_at": datetime.now(timezone.utc),
                },
            )
            await self.db.execute(sub_stmt)

        return []

    async def _resolve_form(self, mform, content: bytes) -> "list[SyncOp]":
        """Resolve form metadata from manifest into SyncOps.

        The FormIndexer call (content parsing) is a side-effect performed in
        _import_all_entities, not here. This method only handles metadata ops.
        """
        from uuid import UUID

        from src.models.orm.forms import Form, FormRole
        from src.services.sync_ops import SyncOp, SyncRoles, Upsert  # noqa: F401

        data = yaml.safe_load(content.decode("utf-8"))
        if not data:
            return []

        org_id = UUID(mform.organization_id) if mform.organization_id else None
        form_id = UUID(mform.id)
        ops: list[SyncOp] = []

        if org_id:
            form_values: dict = {
                "name": data.get("name", ""),
                "is_active": True,
                "created_by": "git-sync",
                "organization_id": org_id,
            }
            if hasattr(mform, "access_level") and mform.access_level:
                form_values["access_level"] = mform.access_level
            ops.append(Upsert(
                model=Form,
                id=form_id,
                values=form_values,
                match_on="id",
            ))

        # Role sync op (FormRole.assigned_by is NOT NULL — pass via extra_fields)
        if hasattr(mform, "roles") and mform.roles:
            role_ids = {UUID(r) for r in mform.roles}
            ops.append(SyncRoles(
                junction_model=FormRole,
                entity_fk="form_id",
                entity_id=form_id,
                role_ids=role_ids,
                extra_fields={"assigned_by": "git-sync"},
            ))

        return ops

    async def _resolve_agent(self, magent, content: bytes) -> "list[SyncOp]":
        """Resolve agent metadata from manifest into SyncOps.

        The AgentIndexer call (content parsing) is a side-effect performed in
        _import_all_entities, not here. This method only handles metadata ops.
        """
        from uuid import UUID

        from src.models.orm.agents import Agent, AgentRole
        from src.services.sync_ops import SyncOp, SyncRoles, Upsert  # noqa: F401

        data = yaml.safe_load(content.decode("utf-8"))
        if not data:
            return []

        org_id = UUID(magent.organization_id) if magent.organization_id else None
        agent_id = UUID(magent.id)
        ops: list[SyncOp] = []

        if org_id:
            agent_values: dict = {
                "name": data.get("name", ""),
                "system_prompt": data.get("system_prompt", ""),
                "is_active": True,
                "created_by": "git-sync",
                "organization_id": org_id,
            }
            if hasattr(magent, "access_level") and magent.access_level:
                agent_values["access_level"] = magent.access_level
            ops.append(Upsert(
                model=Agent,
                id=agent_id,
                values=agent_values,
                match_on="id",
            ))

        # Role sync op (AgentRole.assigned_by is NOT NULL — pass via extra_fields)
        if hasattr(magent, "roles") and magent.roles:
            role_ids = {UUID(r) for r in magent.roles}
            ops.append(SyncRoles(
                junction_model=AgentRole,
                entity_fk="agent_id",
                entity_id=agent_id,
                role_ids=role_ids,
                extra_fields={"assigned_by": "git-sync"},
            ))

        return ops

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
        bifrost_dir = repo_dir / ".bifrost"
        manifest: Manifest | None = None
        if bifrost_dir.exists():
            try:
                manifest = read_manifest_from_dir(bifrost_dir)
                # Verify all paths exist
                from src.services.manifest import get_all_paths
                for path in get_all_paths(manifest):
                    if not (repo_dir / path).exists():
                        issues.append(PreflightIssue(
                            path=".bifrost/",
                            message=f"Manifest references missing file: {path}",
                            severity="error",
                            category="manifest",
                            fix_hint="This file was deleted but the entity is still registered. Use 'Clean up & Retry' to remove orphaned references.",
                            auto_fixable=True,
                        ))
            except Exception as e:
                issues.append(PreflightIssue(
                    path=".bifrost/",
                    message=f"Invalid manifest: {e}",
                    severity="error",
                    category="manifest",
                    fix_hint="The manifest is malformed. Run 'Reimport' from Settings > Maintenance.",
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
                    fix_hint=f"Fix the syntax error in {rel} at line {e.lineno}.",
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
                            fix_hint="This is a style warning and won't block your commit.",
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
                                    fix_hint="Edit this form and assign a valid workflow.",
                                ))
                            launch_ref = data.get("launch_workflow")
                            if launch_ref and launch_ref not in entity_ids:
                                issues.append(PreflightIssue(
                                    path=mform.path,
                                    message=f"Form references unknown launch workflow UUID: {launch_ref}",
                                    severity="error",
                                    category="ref",
                                    fix_hint="Edit this form and assign a valid launch workflow.",
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
                                    fix_hint="Register the referenced workflow, or update the form to reference an active one.",
                                ))
                    except Exception:
                        pass

            # 6. Cross-reference validation for new entity types
            from src.services.manifest import validate_manifest
            ref_errors = validate_manifest(manifest)
            for err in ref_errors:
                issues.append(PreflightIssue(
                    path=".bifrost/",
                    message=err,
                    severity="error",
                    category="ref",
                    fix_hint="Check that all referenced entity IDs exist and are active.",
                ))

            # 7. Health warnings (non-blocking)
            # Secret configs with null values
            for cfg_key, mcfg in manifest.configs.items():
                if mcfg.config_type == "secret" and mcfg.value is None:
                    issues.append(PreflightIssue(
                        path=".bifrost/configs.yaml",
                        message=f"Config '{cfg_key}' (type=secret) needs a value after import",
                        severity="warning",
                        category="health",
                        fix_hint="Set a value for this config in Settings > Integrations.",
                    ))

            # OAuth providers needing setup
            for integ_name, minteg in manifest.integrations.items():
                if minteg.oauth_provider and minteg.oauth_provider.client_id == "__NEEDS_SETUP__":
                    issues.append(PreflightIssue(
                        path=".bifrost/integrations.yaml",
                        message=f"Integration '{integ_name}' OAuth provider needs client_id and client_secret setup",
                        severity="warning",
                        category="health",
                        fix_hint="Configure OAuth client_id and client_secret in Settings > Integrations.",
                    ))

            # Webhook sources needing external registration
            for es_name, mes in manifest.events.items():
                if mes.source_type == "webhook":
                    issues.append(PreflightIssue(
                        path=".bifrost/events.yaml",
                        message=f"Webhook source '{es_name}' will need external registration after import",
                        severity="warning",
                        category="health",
                        fix_hint="Register this webhook URL with the external service after import.",
                    ))

        has_errors = any(i.severity == "error" for i in issues)
        return PreflightResult(valid=not has_errors, issues=issues)
