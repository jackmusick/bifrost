"""
GitHub Sync Service

API-based GitHub synchronization - no local git folder required.
Compares local DB state with remote GitHub state and syncs changes.

Key principles:
1. DB is source of truth for "local" state
2. All GitHub operations via API (no Dulwich/local clone)
3. Conflict detection with user resolution
4. Orphan detection for production protection
"""

import base64
import hashlib
import json
import logging
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Awaitable, Callable, Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.enums import GitStatus
from src.services.file_storage.file_ops import compute_git_blob_sha
from src.services.github_sync_entity_metadata import extract_entity_metadata
from src.services.github_sync_virtual_files import (
    SerializationError,
    VirtualFileProvider,
)

if TYPE_CHECKING:
    from src.models import Workflow

logger = logging.getLogger(__name__)

# Type alias for progress callback
# Callback receives: {"phase": str, "current": int, "total": int, "path": str | None}
ProgressCallback = Callable[[dict], Awaitable[None]]

# Type alias for log callback
# Callback receives: (level: str, message: str)
LogCallback = Callable[[str, str], Awaitable[None]]


# =============================================================================
# Pydantic Models for Sync Operations
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
    sha: str | None = Field(default=None, description="Git blob SHA (for pull actions)")

    # Entity metadata for UI display
    display_name: str | None = Field(default=None, description="Human-readable entity name")
    entity_type: str | None = Field(default=None, description="Entity type: form, agent, app, app_file, workflow")
    parent_slug: str | None = Field(default=None, description="For app_file: parent app slug")

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
    local_content: str | None = Field(default=None, description="Local content")
    remote_content: str | None = Field(default=None, description="Remote content")
    local_sha: str = Field(..., description="SHA of local content")
    remote_sha: str = Field(..., description="SHA of remote content")
    # Entity metadata for UI display
    display_name: str | None = Field(default=None, description="Human-readable entity name")
    entity_type: str | None = Field(default=None, description="Entity type: form, agent, app, app_file, workflow")
    parent_slug: str | None = Field(default=None, description="For app_file: parent app slug")

    model_config = ConfigDict(from_attributes=True)


class WorkflowReference(BaseModel):
    """A reference to an entity that uses a workflow."""
    type: str = Field(..., description="Entity type (form, app, agent)")
    id: str = Field(..., description="Entity ID")
    name: str = Field(..., description="Entity name")

    model_config = ConfigDict(from_attributes=True)


class OrphanInfo(BaseModel):
    """Information about a workflow that will become orphaned."""
    workflow_id: str = Field(..., description="Workflow UUID")
    workflow_name: str = Field(..., description="Workflow display name")
    function_name: str = Field(..., description="Python function name")
    last_path: str = Field(..., description="Last known file path")
    used_by: list[WorkflowReference] = Field(
        default_factory=list,
        description="Entities using this workflow"
    )

    model_config = ConfigDict(from_attributes=True)


class UnresolvedRefInfo(BaseModel):
    """Information about an unresolved portable workflow ref."""
    entity_type: str = Field(..., description="Type: app, form, or agent")
    entity_path: str = Field(..., description="File path being imported")
    field_path: str = Field(..., description="Field containing the ref, e.g., pages.0.launch_workflow_id")
    portable_ref: str = Field(..., description="The portable ref that couldn't be resolved")

    model_config = ConfigDict(from_attributes=True)


class SyncPreview(BaseModel):
    """Preview of sync operations before execution."""
    to_pull: list[SyncAction] = Field(
        default_factory=list,
        description="Files to pull from GitHub"
    )
    to_push: list[SyncAction] = Field(
        default_factory=list,
        description="Files to push to GitHub"
    )
    conflicts: list[ConflictInfo] = Field(
        default_factory=list,
        description="Files with conflicts"
    )
    will_orphan: list[OrphanInfo] = Field(
        default_factory=list,
        description="Workflows that will become orphaned"
    )
    unresolved_refs: list[UnresolvedRefInfo] = Field(
        default_factory=list,
        description="Workflow refs that couldn't be resolved"
    )
    serialization_errors: list[SerializationError] = Field(
        default_factory=list,
        description="Entities that failed to serialize for sync"
    )
    is_empty: bool = Field(
        default=False,
        description="True if no changes to sync"
    )

    model_config = ConfigDict(from_attributes=True)


class SyncResult(BaseModel):
    """Result of sync execution."""
    success: bool = Field(..., description="Whether sync completed successfully")
    pulled: int = Field(default=0, description="Number of files pulled")
    pushed: int = Field(default=0, description="Number of files pushed")
    orphaned_workflows: list[str] = Field(
        default_factory=list,
        description="IDs of workflows marked as orphaned"
    )
    commit_sha: str | None = Field(
        default=None,
        description="SHA of created commit (if any)"
    )
    error: str | None = Field(default=None, description="Error message if failed")

    model_config = ConfigDict(from_attributes=True)


class SyncExecuteRequest(BaseModel):
    """Request to execute sync with conflict resolutions."""
    conflict_resolutions: dict[str, Literal["keep_local", "keep_remote"]] = Field(
        default_factory=dict,
        description="Resolution for each conflicted file"
    )
    confirm_orphans: bool = Field(
        default=False,
        description="User acknowledges orphan workflows"
    )
    confirm_unresolved_refs: bool = Field(
        default=False,
        description="User acknowledges unresolved workflow refs"
    )

    model_config = ConfigDict(from_attributes=True)


# =============================================================================
# Internal Data Classes
# =============================================================================


@dataclass
class TreeEntry:
    """A single entry in a Git tree."""
    sha: str
    size: int | None
    type: str  # "blob" or "tree"
    mode: str


# =============================================================================
# GitHub API Client
# =============================================================================


class GitHubAPIError(Exception):
    """Error from GitHub API."""
    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class GitHubAPIClient:
    """
    Thin wrapper around GitHub REST API for git operations.

    Uses Git Data API for low-level operations:
    - Trees: list files in repo
    - Blobs: read/write file contents
    - Commits: create commits
    - Refs: update branch pointers
    """

    BASE_URL = "https://api.github.com"

    def __init__(self, token: str):
        self.token = token
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    async def get_tree(
        self,
        repo: str,
        sha: str,
        recursive: bool = False,
    ) -> dict[str, TreeEntry]:
        """
        Get tree (file listing) for a commit or tree SHA.

        Args:
            repo: Repository in "owner/repo" format
            sha: Commit or tree SHA
            recursive: If True, get all files recursively

        Returns:
            Dict mapping path to TreeEntry
        """
        url = f"{self.BASE_URL}/repos/{repo}/git/trees/{sha}"
        if recursive:
            url += "?recursive=1"

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, headers=self.headers)
            if response.status_code != 200:
                raise GitHubAPIError(
                    f"Failed to get tree: {response.text}",
                    response.status_code,
                )
            data = response.json()

        # Filter to blobs only (files, not directories)
        return {
            entry["path"]: TreeEntry(
                sha=entry["sha"],
                size=entry.get("size"),
                type=entry["type"],
                mode=entry["mode"],
            )
            for entry in data.get("tree", [])
            if entry["type"] == "blob"
        }

    async def get_blob_content(self, repo: str, sha: str) -> bytes:
        """
        Get content of a blob by SHA.

        Args:
            repo: Repository in "owner/repo" format
            sha: Blob SHA

        Returns:
            File content as bytes
        """
        url = f"{self.BASE_URL}/repos/{repo}/git/blobs/{sha}"

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, headers=self.headers)
            if response.status_code != 200:
                raise GitHubAPIError(
                    f"Failed to get blob: {response.text}",
                    response.status_code,
                )
            data = response.json()

        if data.get("encoding") == "base64":
            return base64.b64decode(data["content"])
        return data["content"].encode()

    async def create_blob(self, repo: str, content: bytes) -> str:
        """
        Create a blob with the given content.

        Args:
            repo: Repository in "owner/repo" format
            content: File content

        Returns:
            SHA of created blob
        """
        url = f"{self.BASE_URL}/repos/{repo}/git/blobs"

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                url,
                headers=self.headers,
                json={
                    "content": base64.b64encode(content).decode(),
                    "encoding": "base64",
                },
            )
            if response.status_code not in (200, 201):
                raise GitHubAPIError(
                    f"Failed to create blob: {response.text}",
                    response.status_code,
                )
            return response.json()["sha"]

    async def create_tree(
        self,
        repo: str,
        tree_items: list[dict],
        base_tree: str,
    ) -> str:
        """
        Create a new tree.

        Args:
            repo: Repository in "owner/repo" format
            tree_items: List of tree entries with path, mode, type, sha
            base_tree: Base tree SHA to build on

        Returns:
            SHA of created tree
        """
        url = f"{self.BASE_URL}/repos/{repo}/git/trees"

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                url,
                headers=self.headers,
                json={
                    "base_tree": base_tree,
                    "tree": tree_items,
                },
            )
            if response.status_code not in (200, 201):
                raise GitHubAPIError(
                    f"Failed to create tree: {response.text}",
                    response.status_code,
                )
            return response.json()["sha"]

    async def create_commit(
        self,
        repo: str,
        message: str,
        tree: str,
        parents: list[str],
    ) -> str:
        """
        Create a new commit.

        Args:
            repo: Repository in "owner/repo" format
            message: Commit message
            tree: Tree SHA
            parents: List of parent commit SHAs

        Returns:
            SHA of created commit
        """
        url = f"{self.BASE_URL}/repos/{repo}/git/commits"

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                url,
                headers=self.headers,
                json={
                    "message": message,
                    "tree": tree,
                    "parents": parents,
                },
            )
            if response.status_code not in (200, 201):
                raise GitHubAPIError(
                    f"Failed to create commit: {response.text}",
                    response.status_code,
                )
            return response.json()["sha"]

    async def get_ref(self, repo: str, ref: str) -> str:
        """
        Get the SHA that a ref points to.

        Args:
            repo: Repository in "owner/repo" format
            ref: Reference like "heads/main"

        Returns:
            SHA of the ref target
        """
        url = f"{self.BASE_URL}/repos/{repo}/git/ref/{ref}"

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, headers=self.headers)
            if response.status_code != 200:
                raise GitHubAPIError(
                    f"Failed to get ref: {response.text}",
                    response.status_code,
                )
            return response.json()["object"]["sha"]

    async def update_ref(self, repo: str, ref: str, sha: str) -> None:
        """
        Update a ref to point to a new SHA.

        Args:
            repo: Repository in "owner/repo" format
            ref: Reference like "heads/main"
            sha: New SHA to point to
        """
        url = f"{self.BASE_URL}/repos/{repo}/git/refs/{ref}"

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.patch(
                url,
                headers=self.headers,
                json={"sha": sha},
            )
            if response.status_code != 200:
                raise GitHubAPIError(
                    f"Failed to update ref: {response.text}",
                    response.status_code,
                )

    async def get_commit(self, repo: str, sha: str) -> dict:
        """
        Get commit details.

        Args:
            repo: Repository in "owner/repo" format
            sha: Commit SHA

        Returns:
            Commit data including tree SHA
        """
        url = f"{self.BASE_URL}/repos/{repo}/git/commits/{sha}"

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, headers=self.headers)
            if response.status_code != 200:
                raise GitHubAPIError(
                    f"Failed to get commit: {response.text}",
                    response.status_code,
                )
            return response.json()


# =============================================================================
# Sync Errors
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


class UnresolvedRefsError(SyncError):
    """User must confirm unresolved workflow refs."""
    def __init__(self, unresolved_refs: list[UnresolvedRefInfo]):
        self.unresolved_refs = unresolved_refs
        refs_summary = ", ".join(r.portable_ref for r in unresolved_refs[:5])
        if len(unresolved_refs) > 5:
            refs_summary += f" (and {len(unresolved_refs) - 5} more)"
        super().__init__(f"Unresolved workflow refs: {refs_summary}")


# =============================================================================
# GitHub Sync Service
# =============================================================================


class GitHubSyncService:
    """
    GitHub sync using API only - no local git folder.

    Compares local DB state with remote GitHub state, detects conflicts
    and orphans, and executes sync with user's resolutions.
    """

    def __init__(
        self,
        db: AsyncSession,
        github_token: str,
        repo: str,
        branch: str = "main",
    ):
        """
        Initialize GitHub sync service.

        Args:
            db: Database session
            github_token: GitHub personal access token
            repo: Repository in "owner/repo" format
            branch: Branch to sync with
        """
        self.db = db
        self.github = GitHubAPIClient(github_token)
        self.repo = repo
        self.branch = branch

    @staticmethod
    def _compute_content_hash(content: bytes) -> str:
        """Compute SHA-256 hash of content."""
        return hashlib.sha256(content).hexdigest()

    async def get_local_content(self, path: str) -> str | None:
        """
        Get serialized content for a file from the database.

        For regular workspace files, reads from storage.
        For virtual files (forms, agents, apps), serializes the entity.

        Args:
            path: File path to fetch content for

        Returns:
            File content as string, or None if not found
        """
        from src.services.file_storage import FileStorageService

        try:
            # Check if this is a virtual file (form, agent, app)
            if VirtualFileProvider.is_virtual_file_path(path):
                entity_type = VirtualFileProvider.get_entity_type_from_path(path)
                filename = path.split("/")[-1]
                entity_id = VirtualFileProvider.extract_id_from_filename(filename)

                if entity_type and entity_id:
                    provider = VirtualFileProvider(self.db)
                    vf = await provider.get_virtual_file_by_id(entity_type, entity_id)
                    if vf and vf.content:
                        return vf.content.decode("utf-8", errors="replace")
                return None

            # Regular workspace file
            file_storage = FileStorageService(self.db)
            content, _ = await file_storage.read_file(path)
            return content.decode("utf-8", errors="replace")
        except Exception as e:
            logger.debug(f"Failed to get local content for {path}: {e}")
            return None

    async def get_remote_content(self, path: str) -> str | None:
        """
        Get file content from GitHub.

        Clones the repo to a temp directory and reads the file.
        Uses shallow clone for efficiency.

        Args:
            path: File path to fetch content for

        Returns:
            File content as string, or None if not found
        """
        clone_dir: str | None = None
        try:
            clone_dir = self._clone_to_temp()
            clone_path = Path(clone_dir)
            file_path = clone_path / path

            if not file_path.exists():
                return None

            content = file_path.read_bytes()
            return content.decode("utf-8", errors="replace")
        except Exception as e:
            logger.debug(f"Failed to get remote content for {path}: {e}")
            return None
        finally:
            if clone_dir:
                try:
                    shutil.rmtree(clone_dir, ignore_errors=True)
                except Exception:
                    pass

    async def _get_local_file_shas(
        self,
    ) -> dict[str, tuple[str | None, GitStatus, bool]]:
        """
        Get path -> (github_sha, git_status, is_deleted) mapping from DB.

        This is much faster than _get_local_files() which reads every file
        from S3 to compute git blob SHA.

        Now includes soft-deleted files so we can detect local deletes that
        need to be pushed to GitHub.

        Returns:
            Dict mapping path to tuple of (github_sha, git_status, is_deleted)
        """
        from src.models import WorkspaceFile

        # Include deleted files so we can push deletes to remote
        stmt = select(
            WorkspaceFile.path,
            WorkspaceFile.github_sha,
            WorkspaceFile.git_status,
            WorkspaceFile.is_deleted,
        )
        result = await self.db.execute(stmt)
        return {
            row.path: (row.github_sha, row.git_status, row.is_deleted)
            for row in result
            if not row.path.endswith("/")  # Skip folders
        }

    async def _get_virtual_file_shas(
        self,
    ) -> tuple[dict[str, str], list[SerializationError]]:
        """
        Get path -> computed_sha mapping for virtual platform files.

        Virtual files are platform entities (apps, forms, agents) serialized
        to JSON with portable workflow refs.

        Returns:
            Tuple of:
            - Dict mapping path to computed git blob SHA
            - List of serialization errors encountered
        """
        provider = VirtualFileProvider(self.db)
        result = await provider.get_all_virtual_files()

        shas = {
            vf.path: vf.computed_sha
            for vf in result.files
            if vf.computed_sha is not None
        }

        return shas, result.errors

    def _clone_to_temp(self) -> str:
        """
        Clone repository to a temporary directory using git CLI.

        Uses shallow clone (--depth 1) for speed. The clone is ephemeral
        and should be cleaned up after use with shutil.rmtree().

        Returns:
            Path to the temporary directory containing the clone

        Raises:
            SyncError: If git clone fails
        """
        temp_dir = tempfile.mkdtemp(prefix="bifrost-git-")

        # Clone with token in URL for auth (x-access-token is GitHub's convention)
        clone_url = f"https://x-access-token:{self.github.token}@github.com/{self.repo}.git"

        try:
            result = subprocess.run(
                [
                    "git", "clone",
                    "--depth", "1",
                    "--branch", self.branch,
                    "--single-branch",
                    clone_url,
                    temp_dir,
                ],
                capture_output=True,
                text=True,
                timeout=300,  # 5 minute timeout for large repos
            )

            if result.returncode != 0:
                # Sanitize error message to avoid leaking token
                stderr = result.stderr.replace(self.github.token, "***")
                raise SyncError(f"Git clone failed: {stderr}")

            logger.info(f"Cloned {self.repo}:{self.branch} to {temp_dir}")
            return temp_dir

        except subprocess.TimeoutExpired:
            shutil.rmtree(temp_dir, ignore_errors=True)
            raise SyncError("Git clone timed out after 5 minutes")
        except Exception as e:
            shutil.rmtree(temp_dir, ignore_errors=True)
            if isinstance(e, SyncError):
                raise
            raise SyncError(f"Git clone failed: {e}")

    async def get_sync_preview(
        self,
        progress_callback: ProgressCallback | None = None,
        log_callback: LogCallback | None = None,
    ) -> SyncPreview:
        """
        Compare local DB state with remote GitHub state.

        Uses a fast approach:
        1. Clone repo to temp dir (shallow clone for speed)
        2. Walk clone to get remote file paths and compute their git SHAs
        3. Query DB for local file SHAs (no S3 read!)
        4. Compare SHAs to categorize changes
        5. Only fetch content for conflicts (lazy read)

        Returns preview of changes without executing:
        - Files to pull from GitHub
        - Files to push to GitHub
        - Files with conflicts
        - Workflows that will become orphaned

        Args:
            progress_callback: Optional async callback for progress updates.
                Called with {"phase": str, "current": int, "total": int, "path": str | None}
            log_callback: Optional async callback for log messages.
                Called with (level: str, message: str)

        Returns:
            SyncPreview with all changes categorized
        """
        from src.services.editor.file_filter import is_excluded_path
        from src.services.file_storage import FileStorageService

        # Helper to report progress
        async def report(phase: str, current: int, total: int, path: str | None = None) -> None:
            if progress_callback:
                await progress_callback({"phase": phase, "current": current, "total": total, "path": path})

        # Helper to log
        async def log(level: str, message: str) -> None:
            if log_callback:
                await log_callback(level, message)

        clone_dir: str | None = None
        try:
            # 1. Clone repo to temp directory
            await report("cloning", 0, 1)
            await log("info", f"Cloning {self.repo}:{self.branch}...")
            logger.info(f"Cloning {self.repo}:{self.branch} for sync preview...")
            clone_dir = self._clone_to_temp()
            clone_path = Path(clone_dir)
            await report("cloning", 1, 1)

            # 2. Walk clone to get remote files and compute their git SHAs
            await report("scanning", 0, 0)
            await log("info", "Scanning remote files...")
            remote_files: dict[str, str] = {}  # path -> git_sha

            # First pass: count files for progress reporting
            all_files = [f for f in clone_path.rglob("*") if f.is_file()]
            total_files = len(all_files)

            for i, file_path in enumerate(all_files):
                rel_path = str(file_path.relative_to(clone_path))
                # Skip .git directory and excluded paths
                if rel_path.startswith(".git/") or is_excluded_path(rel_path):
                    continue
                content = file_path.read_bytes()
                remote_files[rel_path] = compute_git_blob_sha(content)
                # Report progress every 50 files or at the end
                if i % 50 == 0 or i == total_files - 1:
                    await report("scanning", i + 1, total_files, rel_path)

            logger.info(f"Found {len(remote_files)} files in remote")
            await log("info", f"Found {len(remote_files)} files in remote")

            # 2b. Identify virtual files in remote and extract entity IDs
            # Virtual files are platform entities (apps, forms, agents) that can be synced
            remote_virtual_files: dict[str, tuple[str, str, str]] = {}  # entity_id -> (path, sha, entity_type)

            for path, sha in list(remote_files.items()):
                if VirtualFileProvider.is_virtual_file_path(path):
                    entity_type = VirtualFileProvider.get_entity_type_from_path(path)

                    # App files use path as stable identifier
                    if entity_type == "app_file":
                        remote_virtual_files[path] = (path, sha, entity_type)
                        del remote_files[path]
                        continue

                    # Apps: extract UUID from app.json for stable matching
                    if entity_type == "app":
                        app_slug = VirtualFileProvider.extract_app_slug_from_path(path)
                        if app_slug:
                            app_dir = f"apps/{app_slug}"
                            # Read app.json to extract UUID
                            try:
                                app_json_path = clone_path / path
                                app_json_content = app_json_path.read_bytes()
                                app_data = json.loads(app_json_content.decode("utf-8"))
                                app_uuid = app_data.get("id")
                                if app_uuid:
                                    # Use app::{uuid} as stable entity ID
                                    entity_id = f"app::{app_uuid}"
                                    remote_virtual_files[entity_id] = (path, sha, entity_type)
                                else:
                                    # Fallback to app_dir if no UUID
                                    remote_virtual_files[app_dir] = (path, sha, entity_type)
                            except Exception as e:
                                # Fallback to app_dir on error
                                logger.debug(f"Failed to read app.json for {path}: {e}")
                                remote_virtual_files[app_dir] = (path, sha, entity_type)
                            del remote_files[path]
                        continue

                    # Forms and agents use UUID-based filenames
                    filename = path.split("/")[-1]
                    entity_id = VirtualFileProvider.extract_id_from_filename(filename)

                    if entity_type and entity_id:
                        remote_virtual_files[entity_id] = (path, sha, entity_type)
                        # Remove from regular remote_files to handle separately
                        del remote_files[path]
                    else:
                        # Non-standard filename - try reading content
                        try:
                            file_path_obj = clone_path / path
                            content = file_path_obj.read_bytes()
                            entity_id = VirtualFileProvider.extract_id_from_content(content)
                            if entity_id and entity_type:
                                remote_virtual_files[entity_id] = (path, sha, entity_type)
                                del remote_files[path]
                        except Exception:
                            pass  # Leave as regular file

            logger.info(f"Found {len(remote_virtual_files)} virtual files in remote")

            # 3. Get local file SHAs from DB (no S3 read!)
            await report("loading_local", 0, 0)
            await log("info", "Loading local file state...")
            local_shas = await self._get_local_file_shas()
            logger.info(f"Found {len(local_shas)} files in local DB")
            await log("info", f"Found {len(local_shas)} files in local DB")

            # 3b. Get virtual platform file SHAs (and collect serialization errors)
            await report("serializing", 0, 0)
            await log("info", "Serializing virtual files...")
            virtual_shas, serialization_errors = await self._get_virtual_file_shas()
            logger.info(f"Found {len(virtual_shas)} virtual platform files")
            await log("info", f"Found {len(virtual_shas)} virtual platform files")
            if serialization_errors:
                logger.warning(
                    f"Found {len(serialization_errors)} serialization errors"
                )
                await log("warning", f"Found {len(serialization_errors)} serialization errors")

            # Note: We do NOT merge virtual_shas into local_shas because virtual files
            # are compared by entity ID, not by path. They are handled separately below.

            # 4. Categorize changes by comparing SHAs (regular workspace files only)
            # Now using git_status for intelligent conflict detection:
            # - SYNCED: File unchanged since last sync, remote changes are safe to pull
            # - MODIFIED: File changed locally, remote changes are conflicts
            # - DELETED: File deleted locally, may need to push delete
            # - UNTRACKED: New local file, should push
            await report("comparing", 0, len(remote_files) + len(local_shas))
            await log("info", "Comparing file SHAs...")
            to_pull: list[SyncAction] = []
            to_push: list[SyncAction] = []
            conflicts: list[ConflictInfo] = []
            conflict_paths: set[str] = set()

            total_to_compare = len(remote_files) + len(local_shas)
            compared_count = 0

            # Check files in remote
            for path, remote_sha in remote_files.items():
                compared_count += 1
                if compared_count % 100 == 0:
                    await report("comparing", compared_count, total_to_compare, path)
                local_info = local_shas.get(path)

                if local_info is None:
                    # New file in remote - pull it
                    # Read content from clone for entity metadata extraction
                    remote_content: bytes | None = None
                    try:
                        remote_content = (clone_path / path).read_bytes()
                    except Exception:
                        pass
                    to_pull.append(_enrich_sync_action(
                        path=path,
                        action=SyncActionType.ADD,
                        sha=remote_sha,
                        content=remote_content,
                    ))
                    continue

                local_sha, local_status, is_deleted = local_info

                if is_deleted:
                    # File was deleted locally
                    if local_sha == remote_sha:
                        # Remote unchanged since we synced - push the delete
                        to_push.append(_enrich_sync_action(
                            path=path,
                            action=SyncActionType.DELETE,
                        ))
                    else:
                        # Remote changed after we synced, then we deleted locally - conflict
                        # User needs to decide: keep remote version or confirm delete
                        conflict_paths.add(path)

                        # Read remote content for conflict info
                        remote_content_str = None
                        remote_content: bytes | None = None
                        try:
                            remote_file = clone_path / path
                            remote_content = remote_file.read_bytes()
                            remote_content_str = remote_content.decode("utf-8", errors="replace")
                        except Exception:
                            pass

                        conflict_metadata = extract_entity_metadata(path, remote_content)
                        conflicts.append(ConflictInfo(
                            path=path,
                            local_content=None,  # Deleted locally
                            remote_content=remote_content_str,
                            local_sha="",  # Deleted
                            remote_sha=remote_sha,
                            display_name=conflict_metadata.display_name,
                            entity_type=conflict_metadata.entity_type,
                            parent_slug=conflict_metadata.parent_slug,
                        ))
                    continue

                if local_sha is None:
                    # Never synced before but exists locally (UNTRACKED) - shouldn't happen
                    # if remote has it too, treat as conflict to be safe
                    logger.warning(f"File {path} exists in remote but local has no SHA")
                    conflict_paths.add(path)

                    remote_content_str = None
                    local_content_str = None
                    remote_content: bytes | None = None
                    local_content: bytes | None = None

                    try:
                        remote_file = clone_path / path
                        remote_content = remote_file.read_bytes()
                        remote_content_str = remote_content.decode("utf-8", errors="replace")
                    except Exception:
                        pass

                    try:
                        file_storage = FileStorageService(self.db)
                        local_content, _ = await file_storage.read_file(path)
                        local_content_str = local_content.decode("utf-8", errors="replace")
                    except Exception:
                        pass

                    conflict_metadata = extract_entity_metadata(
                        path, local_content if local_content else remote_content
                    )
                    conflicts.append(ConflictInfo(
                        path=path,
                        local_content=local_content_str,
                        remote_content=remote_content_str,
                        local_sha=compute_git_blob_sha(local_content) if local_content else "",
                        remote_sha=remote_sha,
                        display_name=conflict_metadata.display_name,
                        entity_type=conflict_metadata.entity_type,
                        parent_slug=conflict_metadata.parent_slug,
                    ))
                    continue

                if local_sha != remote_sha:
                    # SHA differs - use git_status to determine if conflict or just pull
                    if local_status == GitStatus.SYNCED:
                        # File not modified locally, remote changed - safe to pull
                        remote_content: bytes | None = None
                        try:
                            remote_content = (clone_path / path).read_bytes()
                        except Exception:
                            pass
                        to_pull.append(_enrich_sync_action(
                            path=path,
                            action=SyncActionType.MODIFY,
                            sha=remote_sha,
                            content=remote_content,
                        ))
                    else:
                        # File modified locally (MODIFIED status) AND remote changed - conflict
                        conflict_paths.add(path)

                        # Read content from clone and from S3 for conflict info (lazy read)
                        remote_content_str = None
                        local_content_str = None
                        local_computed_sha = ""
                        remote_content: bytes | None = None
                        local_content: bytes | None = None

                        try:
                            remote_file = clone_path / path
                            remote_content = remote_file.read_bytes()
                            remote_content_str = remote_content.decode("utf-8", errors="replace")
                        except Exception:
                            pass

                        try:
                            file_storage = FileStorageService(self.db)
                            local_content, _ = await file_storage.read_file(path)
                            local_content_str = local_content.decode("utf-8", errors="replace")
                            local_computed_sha = compute_git_blob_sha(local_content)
                        except Exception:
                            pass

                        # Extract entity metadata for UI display
                        conflict_metadata = extract_entity_metadata(
                            path, local_content if local_content else remote_content
                        )
                        conflicts.append(ConflictInfo(
                            path=path,
                            local_content=local_content_str,
                            remote_content=remote_content_str,
                            local_sha=local_computed_sha,
                            remote_sha=remote_sha,
                            display_name=conflict_metadata.display_name,
                            entity_type=conflict_metadata.entity_type,
                            parent_slug=conflict_metadata.parent_slug,
                        ))

            # Check files only in local (not in remote)
            for path, local_info in local_shas.items():
                if path in remote_files:
                    # Already handled above
                    continue

                local_sha, local_status, is_deleted = local_info

                if is_deleted:
                    # Deleted locally, doesn't exist remotely - already in sync, no action needed
                    continue

                if local_sha is not None:
                    # File was synced before but now deleted in remote
                    if local_status == GitStatus.SYNCED:
                        # File not modified locally - safe to pull the delete
                        to_pull.append(_enrich_sync_action(
                            path=path,
                            action=SyncActionType.DELETE,
                        ))
                    else:
                        # File modified locally, deleted remotely - conflict
                        # Read local content for conflict info
                        local_content_str = None
                        local_computed_sha = ""
                        local_content_bytes: bytes | None = None
                        try:
                            file_storage = FileStorageService(self.db)
                            local_content_bytes, _ = await file_storage.read_file(path)
                            local_content_str = local_content_bytes.decode("utf-8", errors="replace")
                            local_computed_sha = compute_git_blob_sha(local_content_bytes)
                        except Exception:
                            pass

                        # Extract entity metadata for UI display
                        conflict_metadata = extract_entity_metadata(path, local_content_bytes)
                        conflict_paths.add(path)
                        conflicts.append(ConflictInfo(
                            path=path,
                            local_content=local_content_str,
                            remote_content=None,  # Deleted remotely
                            local_sha=local_computed_sha,
                            remote_sha="",  # Deleted
                            display_name=conflict_metadata.display_name,
                            entity_type=conflict_metadata.entity_type,
                            parent_slug=conflict_metadata.parent_slug,
                        ))
                else:
                    # New local file (never synced, UNTRACKED) - push
                    # Read local content for entity metadata extraction
                    local_file_content: bytes | None = None
                    try:
                        file_storage = FileStorageService(self.db)
                        local_file_content, _ = await file_storage.read_file(path)
                    except Exception:
                        pass
                    to_push.append(_enrich_sync_action(
                        path=path,
                        action=SyncActionType.ADD,
                        content=local_file_content,
                    ))

            # 5. Compare virtual files by entity ID
            # Virtual files use entity ID as stable identifier, not path
            provider = VirtualFileProvider(self.db)
            local_virtual_result = await provider.get_all_virtual_files()

            # Build local map by entity ID for comparison
            local_virtual_by_id = {
                vf.entity_id: vf
                for vf in local_virtual_result.files
            }
            # Note: errors already captured via _get_virtual_file_shas() above

            # Virtual files in local but not in remote -> push
            for entity_id, vf in local_virtual_by_id.items():
                if entity_id not in remote_virtual_files:
                    to_push.append(_enrich_sync_action(
                        path=vf.path,
                        action=SyncActionType.ADD,
                        content=vf.content,
                    ))

            # Virtual files in remote but not in local -> pull
            for entity_id, (remote_path, remote_sha, _) in remote_virtual_files.items():
                if entity_id not in local_virtual_by_id:
                    # Read content from clone for entity metadata extraction
                    vf_remote_content: bytes | None = None
                    try:
                        vf_remote_content = (clone_path / remote_path).read_bytes()
                    except Exception:
                        pass
                    to_pull.append(_enrich_sync_action(
                        path=remote_path,
                        action=SyncActionType.ADD,
                        sha=remote_sha,
                        content=vf_remote_content,
                    ))

            # Both exist -> compare SHAs
            for entity_id, vf in local_virtual_by_id.items():
                if entity_id in remote_virtual_files:
                    remote_path, remote_sha, _ = remote_virtual_files[entity_id]
                    if vf.computed_sha != remote_sha:
                        # Conflict - different content
                        conflict_paths.add(vf.path)

                        # Get content for conflict display
                        local_content_str = vf.content.decode("utf-8", errors="replace") if vf.content else None
                        remote_content_str = None
                        try:
                            remote_file = clone_path / remote_path
                            remote_content = remote_file.read_bytes()
                            remote_content_str = remote_content.decode("utf-8", errors="replace")
                        except Exception:
                            pass

                        metadata = extract_entity_metadata(vf.path, vf.content)
                        conflicts.append(ConflictInfo(
                            path=vf.path,  # Use local path (consistent UUID-based naming)
                            local_content=local_content_str,
                            remote_content=remote_content_str,
                            local_sha=vf.computed_sha or "",
                            remote_sha=remote_sha,
                            display_name=metadata.display_name,
                            entity_type=metadata.entity_type,
                            parent_slug=metadata.parent_slug,
                        ))

            # 5b. Detect path collisions between to_pull and to_push
            # This handles the case where app child files are categorized incorrectly
            # due to different identification methods for local vs remote
            to_pull_paths = {a.path for a in to_pull}
            to_push_paths = {a.path for a in to_push}
            collision_paths = to_pull_paths & to_push_paths

            if collision_paths:
                logger.info(f"Found {len(collision_paths)} path collisions between pull/push")

                for collision_path in collision_paths:
                    # Find the actions from both lists
                    pull_action = next((a for a in to_pull if a.path == collision_path), None)
                    push_action = next((a for a in to_push if a.path == collision_path), None)

                    if pull_action and push_action:
                        # Get content and SHA for conflict display
                        remote_content_str = None
                        local_content_str = None
                        local_computed_sha = ""

                        try:
                            remote_file = clone_path / collision_path
                            if remote_file.exists():
                                remote_content = remote_file.read_bytes()
                                remote_content_str = remote_content.decode("utf-8", errors="replace")
                        except Exception:
                            pass

                        try:
                            # Try virtual file first
                            if VirtualFileProvider.is_virtual_file_path(collision_path):
                                # Find matching virtual file by path
                                matching_vf = next((vf for vf in local_virtual_result.files if vf.path == collision_path), None)
                                if matching_vf:
                                    if matching_vf.content:
                                        local_content_str = matching_vf.content.decode("utf-8", errors="replace")
                                    if matching_vf.computed_sha:
                                        local_computed_sha = matching_vf.computed_sha
                            else:
                                collision_file_storage = FileStorageService(self.db)
                                local_file_content, _ = await collision_file_storage.read_file(collision_path)
                                local_content_str = local_file_content.decode("utf-8", errors="replace")
                                local_computed_sha = compute_git_blob_sha(local_file_content)
                        except Exception:
                            pass

                        # If SHAs match, this is not a real conflict - skip it
                        if local_computed_sha and local_computed_sha == pull_action.sha:
                            logger.debug(f"Skipping false collision (SHAs match): {collision_path}")
                            # Remove from both lists since content is identical
                            to_pull = [a for a in to_pull if a.path != collision_path]
                            to_push = [a for a in to_push if a.path != collision_path]
                            continue

                        # Get entity metadata for display
                        content_for_metadata = local_content_str.encode("utf-8") if local_content_str else None
                        metadata = extract_entity_metadata(collision_path, content_for_metadata)

                        # Move to conflicts
                        conflicts.append(ConflictInfo(
                            path=collision_path,
                            local_content=local_content_str,
                            remote_content=remote_content_str,
                            local_sha=local_computed_sha,
                            remote_sha=pull_action.sha or "",
                            display_name=metadata.display_name,
                            entity_type=metadata.entity_type,
                            parent_slug=metadata.parent_slug,
                        ))
                        conflict_paths.add(collision_path)

                # Remove collision paths from to_pull and to_push (only conflicting ones remain)
                to_pull = [a for a in to_pull if a.path not in collision_paths]
                to_push = [a for a in to_push if a.path not in collision_paths]

            # 6. Detect orphaned workflows
            await report("analyzing_orphans", 0, len(to_pull))
            await log("info", "Detecting orphaned workflows...")
            will_orphan = await self._detect_orphans(to_pull, to_push, conflicts, clone_dir)

            # 7. Detect unresolved workflow refs in virtual files to pull
            await report("analyzing_refs", 0, len(to_pull))
            await log("info", "Checking workflow references...")
            unresolved_refs = await self._detect_unresolved_refs(to_pull, clone_path)

            await log("info", f"Analysis complete: {len(to_pull)} to pull, {len(to_push)} to push, {len(conflicts)} conflicts")
            is_empty = (
                len(to_pull) == 0
                and len(to_push) == 0
                and len(conflicts) == 0
            )

            return SyncPreview(
                to_pull=to_pull,
                to_push=to_push,
                conflicts=conflicts,
                will_orphan=will_orphan,
                unresolved_refs=unresolved_refs,
                serialization_errors=serialization_errors,
                is_empty=is_empty,
            )

        finally:
            # Clean up clone directory
            if clone_dir:
                try:
                    shutil.rmtree(clone_dir, ignore_errors=True)
                    logger.debug(f"Cleaned up preview clone directory: {clone_dir}")
                except Exception as e:
                    logger.warning(f"Failed to clean up clone directory {clone_dir}: {e}")

    async def _detect_orphans(
        self,
        to_pull: list[SyncAction],
        to_push: list[SyncAction],
        conflicts: list[ConflictInfo],
        clone_dir: str | None = None,
    ) -> list[OrphanInfo]:
        """
        Detect which workflows will become orphaned after sync.

        A workflow becomes orphaned when:
        1. Its file is deleted (in to_pull with action=delete)
        2. Its file is modified and the workflow function is removed

        Args:
            to_pull: Files to pull from remote
            to_push: Files to push to remote (unused but kept for API consistency)
            conflicts: Conflicted files (unused but kept for API consistency)
            clone_dir: Path to cloned repo for reading new content

        Returns:
            List of orphan info for workflows that will be orphaned
        """
        # Silence unused variable warnings
        _ = to_push
        _ = conflicts

        orphans: list[OrphanInfo] = []

        # Get paths being deleted or modified (could affect workflows)
        deleted_paths: set[str] = set()
        modified_paths: set[str] = set()

        for action in to_pull:
            if action.action == SyncActionType.DELETE:
                deleted_paths.add(action.path)
            elif action.action == SyncActionType.MODIFY:
                modified_paths.add(action.path)

        # For deleted files, all workflows in them become orphaned
        for path in deleted_paths:
            if not path.endswith(".py"):
                continue

            workflows = await self._get_workflows_in_file(path)
            for wf in workflows:
                used_by = await self._get_workflow_references(str(wf.id))
                orphans.append(OrphanInfo(
                    workflow_id=str(wf.id),
                    workflow_name=wf.name,
                    function_name=wf.function_name,
                    last_path=path,
                    used_by=used_by,
                ))

        # For modified files being pulled, check if workflows are removed
        if clone_dir:
            clone_path = Path(clone_dir)
            for path in modified_paths:
                if not path.endswith(".py"):
                    continue

                # Read content from local clone instead of API
                file_path = clone_path / path
                if not file_path.exists():
                    continue

                try:
                    new_content = file_path.read_bytes()
                except Exception:
                    continue

                # Get current workflows in this file
                workflows = await self._get_workflows_in_file(path)

                for wf in workflows:
                    # Check if function still exists in new content
                    if not self._file_contains_function(new_content, wf.function_name):
                        used_by = await self._get_workflow_references(str(wf.id))
                        orphans.append(OrphanInfo(
                            workflow_id=str(wf.id),
                            workflow_name=wf.name,
                            function_name=wf.function_name,
                            last_path=path,
                            used_by=used_by,
                        ))

        return orphans

    async def _detect_unresolved_refs(
        self,
        to_pull: list[SyncAction],
        clone_path: Path,
    ) -> list[UnresolvedRefInfo]:
        """
        Detect workflow refs in virtual files that cannot be resolved.

        When importing forms, apps, or agents from GitHub, they may reference
        workflows using portable refs (path::function_name). If those workflows
        don't exist in the target environment, the import would fail or leave
        broken references.

        Args:
            to_pull: Files to pull from remote
            clone_path: Path to cloned repo for reading file content

        Returns:
            List of UnresolvedRefInfo for refs that couldn't be resolved
        """
        from src.models.contracts.agents import AgentPublic
        from src.models.contracts.forms import FormPublic
        from src.models.contracts.refs import get_workflow_ref_paths
        from src.services.file_storage.ref_translation import (
            build_ref_to_uuid_map,
            get_nested_value,
        )

        unresolved_refs: list[UnresolvedRefInfo] = []

        # Build the ref-to-UUID map for checking
        ref_to_uuid = await build_ref_to_uuid_map(self.db)

        # Check each virtual file being pulled
        for action in to_pull:
            if not VirtualFileProvider.is_virtual_file_path(action.path):
                continue

            entity_type = VirtualFileProvider.get_entity_type_from_path(action.path)

            # Get the model class for this entity type to find workflow ref fields
            # App files don't have workflow refs in their content (they're in source code)
            if entity_type == "form":
                model_class = FormPublic
            elif entity_type == "agent":
                model_class = AgentPublic
            else:
                # Apps and app_files don't have JSON-embedded workflow refs
                continue

            # Read the content from clone
            file_path = clone_path / action.path
            if not file_path.exists():
                continue

            try:
                content = file_path.read_bytes()
                data = json.loads(content.decode("utf-8"))

                # Get workflow ref fields from model annotations (not from _export)
                workflow_ref_fields = get_workflow_ref_paths(model_class)

                for field_path in workflow_ref_fields:
                    # Get the value at this field path
                    ref_value = get_nested_value(data, field_path)

                    # Check if it looks like a portable ref (contains "::")
                    if ref_value and isinstance(ref_value, str) and "::" in ref_value:
                        if ref_value not in ref_to_uuid:
                            # This ref can't be resolved
                            unresolved_refs.append(UnresolvedRefInfo(
                                entity_type=entity_type or "unknown",
                                entity_path=action.path,
                                field_path=field_path,
                                portable_ref=ref_value,
                            ))
            except json.JSONDecodeError:
                # Not valid JSON, will fail during import anyway
                pass
            except Exception as e:
                logger.debug(f"Error checking unresolved refs in {action.path}: {e}")

        return unresolved_refs

    async def _get_workflows_in_file(self, path: str) -> list["Workflow"]:
        """Get all workflows associated with a file path."""
        from src.models import Workflow

        stmt = select(Workflow).where(
            Workflow.path == path,
            Workflow.is_active.is_(True),
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def _get_workflow_references(self, workflow_id: str) -> list[WorkflowReference]:
        """
        Find all entities (forms, apps, agents) that reference a workflow.
        """
        from src.models import Form, Agent

        refs: list[WorkflowReference] = []

        # Check forms
        stmt = select(Form).where(
            or_(
                Form.workflow_id == workflow_id,
                Form.launch_workflow_id == workflow_id,
            )
        )
        result = await self.db.execute(stmt)
        for form in result.scalars():
            refs.append(WorkflowReference(
                type="form",
                id=str(form.id),
                name=form.name,
            ))

        # Note: The component engine has been removed. Apps no longer reference
        # workflows through pages/components. Code engine apps reference workflows
        # through their code files, which is not tracked in the database.

        # Check agents (tools relationship)
        try:
            stmt = select(Agent)
            result = await self.db.execute(stmt)
            for agent in result.scalars():
                # Check if this workflow is a tool for this agent
                if hasattr(agent, "tools"):
                    for tool in agent.tools:
                        if str(tool.id) == workflow_id:
                            refs.append(WorkflowReference(
                                type="agent",
                                id=str(agent.id),
                                name=agent.name,
                            ))
                            break
        except Exception:
            pass  # Agent tools might not be loaded

        return refs

    def _file_contains_function(self, content: bytes, function_name: str) -> bool:
        """
        Check if a Python file contains a function definition.

        Uses AST parsing for accuracy.
        """
        import ast

        try:
            tree = ast.parse(content.decode("utf-8", errors="replace"))
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if node.name == function_name:
                        return True
            return False
        except SyntaxError:
            # If we can't parse, do a simple text search as fallback
            content_str = content.decode("utf-8", errors="replace")
            return f"def {function_name}(" in content_str or f"async def {function_name}(" in content_str

    async def execute_sync(
        self,
        conflict_resolutions: dict[str, Literal["keep_local", "keep_remote"]],
        confirm_orphans: bool = False,
        confirm_unresolved_refs: bool = False,
        progress_callback: ProgressCallback | None = None,
        log_callback: LogCallback | None = None,
    ) -> SyncResult:
        """
        Execute the sync with user's conflict resolutions.

        Args:
            conflict_resolutions: Dict mapping path to resolution choice
            confirm_orphans: Whether user confirmed orphan workflows
            confirm_unresolved_refs: Whether user confirmed unresolved workflow refs
            progress_callback: Optional async callback for progress updates.
                Called with {"phase": str, "current": int, "total": int, "path": str | None}

        Returns:
            SyncResult with counts and status

        Raises:
            ConflictError: If conflicts exist without resolution
            OrphanError: If orphans exist without confirmation
            UnresolvedRefsError: If unresolved refs exist without confirmation
        """
        from src.services.file_storage import FileStorageService

        # Helper to report progress
        async def report(phase: str, current: int, total: int, path: str | None = None) -> None:
            if progress_callback:
                await progress_callback({
                    "phase": phase,
                    "current": current,
                    "total": total,
                    "path": path,
                })

        # Helper for milestone logging (every 5%)
        logged_milestones: set[int] = set()

        async def log_milestone(phase: str, current: int, total: int) -> None:
            if not log_callback or total == 0:
                return
            percent = (current * 100) // total
            milestone = (percent // 5) * 5  # Round to nearest 5%
            if milestone > 0 and milestone not in logged_milestones:
                logged_milestones.add(milestone)
                await log_callback("info", f"{phase}: {current}/{total} ({milestone}%)")

        # Get fresh preview
        preview = await self.get_sync_preview()

        # Validate orphan confirmation
        if preview.will_orphan and not confirm_orphans:
            raise OrphanError([o.workflow_id for o in preview.will_orphan])

        # Validate unresolved refs confirmation
        if preview.unresolved_refs and not confirm_unresolved_refs:
            raise UnresolvedRefsError(preview.unresolved_refs)

        # Validate conflict resolutions
        if preview.conflicts:
            for conflict in preview.conflicts:
                if conflict.path not in conflict_resolutions:
                    raise ConflictError([c.path for c in preview.conflicts if c.path not in conflict_resolutions])

        file_storage = FileStorageService(self.db)
        pulled = 0
        pushed = 0
        clone_dir: str | None = None

        # Calculate totals for progress reporting
        total_pull = len(preview.to_pull)
        total_conflicts = len([r for r in conflict_resolutions.values() if r == "keep_remote"])

        # Clone repo for pulling (much faster than per-file API calls)
        need_clone = total_pull > 0 or total_conflicts > 0
        if need_clone:
            if log_callback:
                await log_callback("info", "Cloning repository...")
            await report("cloning", 0, 1, None)
            try:
                clone_dir = self._clone_to_temp()
                if log_callback:
                    await log_callback("info", "Repository cloned successfully")
            except SyncError as e:
                logger.error(f"Failed to clone repository: {e}")
                if log_callback:
                    await log_callback("error", f"Failed to clone: {e}")
                return SyncResult(
                    success=False,
                    pulled=0,
                    pushed=0,
                    error=str(e),
                )

        try:
            # 1. Pull remote changes (read from local clone)
            for i, action in enumerate(preview.to_pull):
                # Report progress before processing each file
                await report("pulling", i + 1, total_pull, action.path)
                await log_milestone("Pulling", i + 1, total_pull)

                try:
                    if action.action == SyncActionType.DELETE:
                        # Check if this is a virtual file (app, form, agent)
                        if VirtualFileProvider.is_virtual_file_path(action.path):
                            await self._delete_virtual_file(action.path)
                        else:
                            await file_storage.delete_file(action.path)
                        logger.debug(f"Deleted local file: {action.path}")
                    else:
                        if not action.sha or not clone_dir:
                            continue
                        # Read from local clone instead of API
                        local_file = Path(clone_dir) / action.path
                        if not local_file.exists():
                            logger.warning(f"File not in clone: {action.path}")
                            continue
                        content = local_file.read_bytes()

                        # Check if this is a virtual file (app, form, agent)
                        if VirtualFileProvider.is_virtual_file_path(action.path):
                            # Use indexer to import virtual file
                            await self._import_virtual_file(action.path, content)
                            # Virtual files don't need github_sha update (no workspace_file entry)
                        else:
                            # Regular file - use file storage
                            await file_storage.write_file(
                                path=action.path,
                                content=content,
                                updated_by="github_sync",
                                force_deactivation=True,  # Allow deactivation during sync
                            )
                            # Update github_sha for this file
                            await self._update_github_sha(action.path, action.sha)
                        logger.debug(f"Pulled file: {action.path}")
                    pulled += 1
                except Exception as e:
                    logger.error(f"Failed to pull {action.path}: {e}")
                    if log_callback:
                        await log_callback("error", f"Failed to pull {action.path}: {e}")
                    return SyncResult(
                        success=False,
                        pulled=pulled,
                        pushed=pushed,
                        error=f"Failed to pull {action.path}: {e}",
                    )

            # 2. Apply conflict resolutions (read from local clone)
            conflict_index = 0
            for path, resolution in conflict_resolutions.items():
                if resolution == "keep_remote":
                    conflict_index += 1
                    # Report progress for resolving conflicts
                    await report("resolving", conflict_index, total_conflicts, path)

                    # Find the conflict to get remote SHA
                    conflict = next((c for c in preview.conflicts if c.path == path), None)
                    if conflict and conflict.remote_sha and clone_dir:
                        try:
                            # Read from local clone instead of API
                            local_file = Path(clone_dir) / path
                            if local_file.exists():
                                content = local_file.read_bytes()

                                # Check if this is a virtual file (app, form, agent)
                                if VirtualFileProvider.is_virtual_file_path(path):
                                    # Use indexer to import virtual file
                                    await self._import_virtual_file(path, content)
                                else:
                                    # Regular file - use file storage
                                    await file_storage.write_file(
                                        path=path,
                                        content=content,
                                        updated_by="github_sync",
                                        force_deactivation=True,
                                    )
                                    await self._update_github_sha(path, conflict.remote_sha)
                                logger.debug(f"Resolved conflict (keep remote): {path}")
                                pulled += 1
                        except Exception as e:
                            logger.error(f"Failed to resolve conflict for {path}: {e}")
                            if log_callback:
                                await log_callback("error", f"Failed to resolve conflict for {path}: {e}")
                    elif conflict and conflict.remote_content is None:
                        # Remote deleted the file
                        try:
                            # Check if this is a virtual file (app, form, agent)
                            if VirtualFileProvider.is_virtual_file_path(path):
                                await self._delete_virtual_file(path)
                            else:
                                await file_storage.delete_file(path)
                            logger.debug(f"Resolved conflict (remote deleted): {path}")
                            pulled += 1
                        except Exception as e:
                            logger.error(f"Failed to delete file for conflict {path}: {e}")
                            if log_callback:
                                await log_callback("error", f"Failed to delete file for conflict {path}: {e}")
                    # keep_local: will be pushed below

            # 3. Mark orphaned workflows
            for orphan_info in preview.will_orphan:
                await self._mark_workflow_orphaned(orphan_info.workflow_id)

            # 4. Push local changes
            files_to_push = list(preview.to_push)

            # Add "keep_local" conflict resolutions to push list
            for path, resolution in conflict_resolutions.items():
                if resolution == "keep_local":
                    # Check if not already in push list
                    if not any(a.path == path for a in files_to_push):
                        files_to_push.append(_enrich_sync_action(
                            path=path,
                            action=SyncActionType.MODIFY,
                        ))

            commit_sha: str | None = None
            if files_to_push:
                try:
                    commit_sha = await self._push_changes(files_to_push, progress_callback, log_callback)
                    pushed = len(files_to_push)
                    logger.info(f"Pushed {pushed} files, commit: {commit_sha}")
                except Exception as e:
                    logger.error(f"Failed to push changes: {e}")
                    if log_callback:
                        await log_callback("error", f"Failed to push changes: {e}")
                    return SyncResult(
                        success=False,
                        pulled=pulled,
                        pushed=0,
                        error=f"Failed to push changes: {e}",
                    )

            await self.db.commit()

            return SyncResult(
                success=True,
                pulled=pulled,
                pushed=pushed,
                orphaned_workflows=[o.workflow_id for o in preview.will_orphan],
                commit_sha=commit_sha,
            )

        finally:
            # Clean up the temporary clone directory
            if clone_dir:
                try:
                    shutil.rmtree(clone_dir, ignore_errors=True)
                    logger.debug(f"Cleaned up clone directory: {clone_dir}")
                except Exception as e:
                    logger.warning(f"Failed to clean up clone directory {clone_dir}: {e}")

    async def _push_changes(
        self,
        to_push: list[SyncAction],
        progress_callback: ProgressCallback | None = None,
        log_callback: LogCallback | None = None,
    ) -> str:
        """
        Push local changes to GitHub using Git Data API.

        Args:
            to_push: List of files to push
            progress_callback: Optional async callback for progress updates
            log_callback: Optional async callback for log messages

        Returns:
            SHA of created commit
        """
        from src.services.file_storage import FileStorageService

        file_storage = FileStorageService(self.db)
        total_push = len(to_push)

        # Helper for milestone logging (every 5%)
        logged_milestones: set[int] = set()

        async def log_milestone(current: int) -> None:
            if not log_callback or total_push == 0:
                return
            percent = (current * 100) // total_push
            milestone = (percent // 5) * 5
            if milestone > 0 and milestone not in logged_milestones:
                logged_milestones.add(milestone)
                await log_callback("info", f"Pushing: {current}/{total_push} ({milestone}%)")

        # Helper to report progress
        async def report(current: int, path: str | None = None) -> None:
            if progress_callback:
                await progress_callback({
                    "phase": "pushing",
                    "current": current,
                    "total": total_push,
                    "path": path,
                })

        # 1. Get current commit SHA
        current_sha = await self.github.get_ref(self.repo, f"heads/{self.branch}")
        current_commit = await self.github.get_commit(self.repo, current_sha)
        base_tree_sha = current_commit["tree"]["sha"]

        # 2. Pre-fetch all virtual files for efficient lookup
        # Virtual files include apps, app_files, forms, and agents
        vf_provider = VirtualFileProvider(self.db)
        all_vf_result = await vf_provider.get_all_virtual_files()
        virtual_files_by_path = {vf.path: vf for vf in all_vf_result.files}

        # 3. Create blobs for each file
        tree_items: list[dict] = []
        blob_shas: dict[str, str] = {}

        for i, action in enumerate(to_push):
            # Report progress before processing each file
            await report(i + 1, action.path)
            await log_milestone(i + 1)

            if action.action == SyncActionType.DELETE:
                # Delete by setting sha to None
                tree_items.append({
                    "path": action.path,
                    "mode": "100644",
                    "type": "blob",
                    "sha": None,
                })
            else:
                # Read local content - check for virtual files first
                content: bytes | None = None
                try:
                    if action.path in virtual_files_by_path:
                        # Get content from pre-fetched virtual files
                        vf = virtual_files_by_path[action.path]
                        if vf.content:
                            content = vf.content
                        else:
                            logger.warning(f"Virtual file has no content: {action.path}")
                            continue
                    elif VirtualFileProvider.is_virtual_file_path(action.path):
                        # Virtual file path but not in our list - shouldn't happen
                        logger.warning(f"Virtual file not found in provider: {action.path}")
                        continue
                    else:
                        # Regular file - read from file storage
                        content, _ = await file_storage.read_file(action.path)
                except FileNotFoundError:
                    logger.warning(f"File to push not found: {action.path}")
                    continue

                # Create blob
                blob_sha = await self.github.create_blob(self.repo, content)
                blob_shas[action.path] = blob_sha

                tree_items.append({
                    "path": action.path,
                    "mode": "100644",
                    "type": "blob",
                    "sha": blob_sha,
                })

        if not tree_items:
            raise SyncError("No files to push")

        # 4. Create new tree
        new_tree_sha = await self.github.create_tree(
            self.repo,
            tree_items,
            base_tree_sha,
        )

        # 5. Create commit
        commit_sha = await self.github.create_commit(
            self.repo,
            message="Sync from Bifrost",
            tree=new_tree_sha,
            parents=[current_sha],
        )

        # 6. Update branch ref
        await self.github.update_ref(
            self.repo,
            f"heads/{self.branch}",
            commit_sha,
        )

        # 7. Update github_sha for pushed files (skip virtual files)
        for path, blob_sha in blob_shas.items():
            if not VirtualFileProvider.is_virtual_file_path(path):
                await self._update_github_sha(path, blob_sha)
            # Virtual files don't have workspace_file entries, so no SHA to update

        return commit_sha

    async def _update_github_sha(self, path: str, sha: str) -> None:
        """
        Update the github_sha column for a file and set git_status to SYNCED.

        This should be called after successfully syncing a file with GitHub
        (either pull or push). Setting git_status=SYNCED indicates the file
        content matches GitHub, enabling smart conflict detection on future syncs.

        Args:
            path: File path
            sha: New GitHub blob SHA
        """
        from src.models import WorkspaceFile
        from sqlalchemy import update

        stmt = (
            update(WorkspaceFile)
            .where(WorkspaceFile.path == path)
            .values(github_sha=sha, git_status=GitStatus.SYNCED)
        )
        await self.db.execute(stmt)

    async def _mark_workflow_orphaned(self, workflow_id: str) -> None:
        """
        Mark a workflow as orphaned.

        Args:
            workflow_id: Workflow UUID string
        """
        from src.models import Workflow
        from sqlalchemy import update
        from uuid import UUID

        stmt = (
            update(Workflow)
            .where(Workflow.id == UUID(workflow_id))
            .values(
                is_orphaned=True,
                updated_at=datetime.utcnow(),
            )
        )
        await self.db.execute(stmt)
        logger.info(f"Marked workflow as orphaned: {workflow_id}")

    async def _import_virtual_file(self, path: str, content: bytes) -> None:
        """
        Import a virtual file (app, form, agent) using the appropriate indexer.

        Virtual files are platform entities stored in their own database tables,
        not in workspace_files. This method routes the content to the correct
        indexer based on the file path pattern.

        Args:
            path: File path (e.g., "apps/my-app/app.json", "forms/{id}.form.json")
            content: File content bytes
        """
        from src.services.file_storage.indexers.agent import AgentIndexer
        from src.services.file_storage.indexers.app import AppIndexer
        from src.services.file_storage.indexers.form import FormIndexer

        entity_type = VirtualFileProvider.get_entity_type_from_path(path)

        if entity_type == "form":
            indexer = FormIndexer(self.db)
            await indexer.index_form(path, content)
            logger.debug(f"Imported form from {path}")
        elif entity_type == "agent":
            indexer = AgentIndexer(self.db)
            await indexer.index_agent(path, content)
            logger.debug(f"Imported agent from {path}")
        elif entity_type == "app":
            indexer = AppIndexer(self.db)
            await indexer.index_app_json(path, content)
            logger.debug(f"Imported app from {path}")
        elif entity_type == "app_file":
            indexer = AppIndexer(self.db)
            await indexer.index_app_file(path, content)
            logger.debug(f"Imported app file from {path}")
        else:
            raise ValueError(f"Unknown virtual file type for path: {path}")

    async def _delete_virtual_file(self, path: str) -> None:
        """
        Delete a virtual file (app, form, agent) from its database table.

        Virtual files don't exist in workspace_files - they're stored in their
        own tables (applications, forms, agents). This method deletes the entity
        from the appropriate table based on the file path pattern.

        Args:
            path: File path (e.g., "forms/{id}.form.json", "apps/my-app/app.json")
        """
        from uuid import UUID
        from sqlalchemy import delete
        from src.models import Form
        from src.models.orm import Agent
        from src.services.file_storage.indexers.app import AppIndexer

        entity_type = VirtualFileProvider.get_entity_type_from_path(path)

        # Handle apps separately - they use slug, not UUID
        if entity_type == "app":
            slug = VirtualFileProvider.extract_app_slug_from_path(path)
            if slug:
                indexer = AppIndexer(self.db)
                await indexer.delete_app(slug)
                logger.debug(f"Deleted app {slug}")
            return
        elif entity_type == "app_file":
            indexer = AppIndexer(self.db)
            await indexer.delete_app_file(path)
            logger.debug(f"Deleted app file {path}")
            return

        # Forms and agents use UUID in filename
        filename = path.split("/")[-1]
        entity_id_str = VirtualFileProvider.extract_id_from_filename(filename)

        if not entity_id_str:
            logger.warning(f"Could not extract entity ID from virtual file path: {path}")
            return

        try:
            entity_id = UUID(entity_id_str)
        except ValueError:
            logger.warning(f"Invalid entity ID in virtual file path: {path}")
            return

        if entity_type == "form":
            stmt = delete(Form).where(Form.id == entity_id)
            await self.db.execute(stmt)
            logger.debug(f"Deleted form {entity_id}")
        elif entity_type == "agent":
            stmt = delete(Agent).where(Agent.id == entity_id)
            await self.db.execute(stmt)
            logger.debug(f"Deleted agent {entity_id}")


# =============================================================================
# Factory function
# =============================================================================


def get_github_sync_service(
    db: AsyncSession,
    github_token: str,
    repo: str,
    branch: str = "main",
) -> GitHubSyncService:
    """
    Factory function to create a GitHubSyncService.

    Args:
        db: Database session
        github_token: GitHub personal access token
        repo: Repository in "owner/repo" format
        branch: Branch to sync with

    Returns:
        Configured GitHubSyncService instance
    """
    return GitHubSyncService(
        db=db,
        github_token=github_token,
        repo=repo,
        branch=branch,
    )
