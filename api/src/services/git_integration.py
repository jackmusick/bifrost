"""
Git Integration Service

Handles GitHub repository synchronization with workspace.
Provides Git operations: clone, pull, push, conflict resolution.
Uses Dulwich (pure Python Git implementation) - works without git binary.

Git operations use a dedicated directory at /tmp/bifrost/git. This is separate
from the virtual module system - files are serialized from DB to git workspace
for push operations, and parsed from git workspace back to DB on pull.
"""

import asyncio
import logging
import os
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, TYPE_CHECKING

from dulwich import porcelain
from dulwich.repo import Repo as DulwichRepo
from dulwich.errors import NotGitRepository
from dulwich.objects import Commit as DulwichCommit, Blob, Tree, ShaFile
from github import Github, GithubException

from src.core.paths import GIT_WORKSPACE_PATH
from src.models import (
    FileChange,
    GitFileStatus,
    ConflictInfo,
    GitHubRepoInfo,
    GitHubBranchInfo,
    CommitInfo,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession
    from src.config import Settings

logger = logging.getLogger(__name__)

# Module-level lock to prevent concurrent Git fetch operations
# This prevents SMB lock file conflicts when multiple requests arrive simultaneously
_fetch_lock = asyncio.Lock()


def _get_settings() -> "Settings":
    """Lazy import of settings to avoid circular dependencies."""
    from src.config import get_settings
    return get_settings()


# Git workspace path - used for git clone/pull/push operations
# Files are serialized from DB to this location for push, and parsed back to DB on pull
WORKSPACE_PATH = GIT_WORKSPACE_PATH


def manual_copy_tree(
    src: Path,
    dest: Path,
    exclude_patterns: list[str] | None = None
) -> None:
    """
    Recursively copy directory tree with optional file exclusion.

    Args:
        src: Source directory path
        dest: Destination directory path
        exclude_patterns: List of filename patterns to exclude (e.g., ['.DS_Store', '._*'])
    """
    exclude_patterns = exclude_patterns or []

    # Create destination if it doesn't exist
    dest.mkdir(parents=True, exist_ok=True)

    for item in src.iterdir():
        # Check if item should be excluded
        should_exclude = any(
            item.name.endswith(pattern.lstrip('*.')) or
            (pattern.startswith('._') and item.name.startswith('._'))
            for pattern in exclude_patterns
        )

        if should_exclude:
            continue

        src_item = src / item.name
        dest_item = dest / item.name

        if src_item.is_dir():
            # Recursively copy subdirectories
            manual_copy_tree(src_item, dest_item, exclude_patterns)
        else:
            # Copy file
            shutil.copy2(src_item, dest_item)


class GitIntegrationService:
    """
    Service for Git/GitHub integration.

    Manages workspace synchronization with GitHub repository.
    Handles cloning, pulling, pushing, and conflict resolution.
    Uses Dulwich (pure Python) instead of GitPython.

    All operations work on /tmp/bifrost/workspace which is kept in sync
    with S3 by the WorkspaceSyncService.
    """

    def __init__(self):
        """Initialize Git integration service."""
        self.settings = _get_settings()
        self.workspace_path = WORKSPACE_PATH
        self.workspace_path.mkdir(parents=True, exist_ok=True)
        logger.info(f"Initialized Git integration service at: {self.workspace_path}")

    @staticmethod
    def _is_real_file(path: Path) -> bool:
        """
        Check if a path represents a real file (not SMB/macOS metadata).

        Filters out phantom files that appear in directory listings on SMB/Azure Files
        but aren't actually accessible (e.g., AppleDouble files like ._.packages).

        Args:
            path: Path to check

        Returns:
            False if this is a known metadata file that should be ignored, True otherwise
        """
        name = path.name
        # Skip AppleDouble files (macOS metadata on non-native filesystems)
        # These files start with ._ and often appear on SMB/Azure Files mounts
        if name.startswith('._'):
            logger.debug(f"Skipping AppleDouble metadata file: {name}")
            return False
        return True

    def is_connected(self) -> bool:
        """Check if workspace is a Git repository (connected to Git)"""
        try:
            DulwichRepo(str(self.workspace_path))
            return True
        except NotGitRepository:
            return False

    def is_git_repo(self) -> bool:
        """Alias for is_connected() for backwards compatibility"""
        return self.is_connected()

    def get_repo(self) -> DulwichRepo:
        """Get Dulwich repository instance"""
        if not self.is_git_repo():
            raise ValueError("Workspace is not a Git repository. Call initialize_repo() first.")
        return DulwichRepo(str(self.workspace_path))

    async def initialize_repo(
        self,
        token: str,
        repo_url: str,
        branch: str = "main"
    ) -> dict | None:
        """
        Initialize Git repository from GitHub.

        If workspace is empty: clone repository
        If workspace has files: backup and replace with repository

        In S3 mode: downloads workspace to temp dir, clones repo, uploads back to S3.

        Args:
            token: GitHub personal access token
            repo_url: GitHub repository URL or owner/repo format
            branch: Branch to clone (default: main)

        Returns:
            dict with backup_path if workspace was backed up, None otherwise

        Raises:
            ValueError: If repo_url is invalid
            Exception: If Git operations fail
        """
        logger.info(f"Initializing Git repo from {repo_url} (branch: {branch})")

        # Normalize repo URL - accept both full URLs and owner/repo format
        if not repo_url.startswith(('https://github.com/', 'git@github.com:')):
            # Assume it's in owner/repo format, convert to HTTPS URL
            repo_url = f"https://github.com/{repo_url}"
            logger.info(f"Normalized repo URL to: {repo_url}")

        # Validate normalized URL
        if not repo_url.startswith(('https://github.com/', 'git@github.com:')):
            raise ValueError("Invalid GitHub repository URL")

        # Convert HTTPS URL to use token authentication
        auth_url = self._insert_token_in_url(repo_url, token)

        # Check workspace state (filter out SMB metadata files)
        workspace = self.workspace_path
        workspace_empty = not any(
            self._is_real_file(item) for item in workspace.iterdir()
        ) if workspace.exists() else True
        is_git_repo = self.is_git_repo()

        result = None

        # Scenario 1: Already a Git repo - just update remote
        if is_git_repo:
            logger.info("Workspace is already a Git repository, updating configuration...")
            self._update_existing_repo(auth_url, branch)

        # Scenario 2: Empty workspace - just clone
        elif workspace_empty:
            logger.info("Workspace is empty, cloning repository...")
            self._clone_repo(auth_url, branch)

        # Scenario 3: Has files but no Git - backup and replace
        else:
            logger.info("Workspace has files, backing up and replacing with repository...")
            backup_path = await self._clear_and_clone(auth_url, branch)
            result = {"backup_path": backup_path}

        logger.info("Repository initialized successfully")
        return result

    def _insert_token_in_url(self, repo_url: str, token: str) -> str:
        """Insert GitHub token into HTTPS URL for authentication"""
        if repo_url.startswith('git@github.com:'):
            # Convert SSH to HTTPS with token
            repo_path = repo_url.replace('git@github.com:', '')
            return f'https://{token}@github.com/{repo_path}'

        # Insert token into URL
        return repo_url.replace('https://github.com/', f'https://{token}@github.com/')

    async def _get_authenticated_remote_url(self, context: Any) -> str | None:
        """
        Get authenticated remote URL with token from PostgreSQL.

        Args:
            context: Organization context

        Returns:
            Authenticated URL with token, or None if not configured
        """
        github_config = await self._get_github_config(context)

        if not github_config:
            return None

        repo_url = github_config.get("repo_url")
        token = github_config.get("token")

        if not repo_url or not token:
            return None

        if github_config.get("status") == "disconnected":
            return None

        # Normalize repo URL - accept both full URLs and owner/repo format
        if not repo_url.startswith(('https://github.com/', 'git@github.com:')):
            # Convert owner/repo format to HTTPS URL
            repo_url = f"https://github.com/{repo_url}"
            logger.debug(f"Normalized repo URL to: {repo_url}")

        # Build authenticated URL
        return self._insert_token_in_url(repo_url, token)

    async def _get_github_config(self, context: Any) -> dict | None:
        """
        Get GitHub configuration from PostgreSQL system_configs table.

        Args:
            context: Organization context with org_id

        Returns:
            Dict with repo_url, token, branch, status or None
        """
        from uuid import UUID
        from sqlalchemy import select
        from cryptography.fernet import Fernet
        import base64

        try:
            from src.config import get_settings
            from src.core.database import get_session_factory
            from src.models import SystemConfig

            settings = get_settings()
            session_factory = get_session_factory()

            # Get encryption key
            key_bytes = settings.secret_key.encode()[:32].ljust(32, b'0')
            fernet = Fernet(base64.urlsafe_b64encode(key_bytes))

            org_id = getattr(context, 'org_id', None) or getattr(context, 'scope', None)
            org_uuid = None
            if org_id and org_id != "GLOBAL":
                try:
                    org_uuid = UUID(org_id)
                except ValueError:
                    pass

            async with session_factory() as db:
                # Look for github integration config in system_configs table
                query = select(SystemConfig).where(
                    SystemConfig.category == "github",
                    SystemConfig.key == "integration",
                    SystemConfig.organization_id == org_uuid
                )
                result = await db.execute(query)
                config = result.scalars().first()

                if not config:
                    # Try GLOBAL fallback (organization_id = NULL)
                    query = select(SystemConfig).where(
                        SystemConfig.category == "github",
                        SystemConfig.key == "integration",
                        SystemConfig.organization_id.is_(None)
                    )
                    result = await db.execute(query)
                    config = result.scalars().first()

                if not config:
                    return None

                config_value = config.value_json or {}
                repo_url = config_value.get("repo_url")
                encrypted_token = config_value.get("encrypted_token")
                branch = config_value.get("branch", "main")
                status = config_value.get("status", "connected")

                # Decrypt token if present
                token = None
                if encrypted_token:
                    try:
                        token = fernet.decrypt(encrypted_token.encode()).decode()
                    except Exception as e:
                        logger.warning(f"Failed to decrypt GitHub token: {e}")

                return {
                    "repo_url": repo_url,
                    "token": token,
                    "branch": branch,
                    "status": status
                }
        except Exception as e:
            logger.error(f"Failed to get GitHub config: {e}")
            return None

    async def _save_github_config(
        self,
        context: Any,
        repo_url: str,
        token: str,
        branch: str,
        updated_by: str
    ) -> None:
        """
        Save GitHub configuration to system_configs table.

        Args:
            context: Organization context
            repo_url: GitHub repository URL
            token: GitHub personal access token (will be encrypted)
            branch: Branch name
            updated_by: Email of user making the change
        """
        from uuid import UUID, uuid4
        from sqlalchemy import select
        from cryptography.fernet import Fernet
        import base64
        from datetime import datetime

        from src.config import get_settings
        from src.core.database import get_session_factory
        from src.models import SystemConfig

        settings = get_settings()
        session_factory = get_session_factory()

        # Get encryption key
        key_bytes = settings.secret_key.encode()[:32].ljust(32, b'0')
        fernet = Fernet(base64.urlsafe_b64encode(key_bytes))

        # Encrypt token
        encrypted_token = fernet.encrypt(token.encode()).decode()

        org_id = getattr(context, 'org_id', None) or getattr(context, 'scope', None)
        org_uuid = None
        if org_id and org_id != "GLOBAL":
            try:
                org_uuid = UUID(org_id)
            except ValueError:
                pass

        async with session_factory() as db:
            # Check if config already exists
            query = select(SystemConfig).where(
                SystemConfig.category == "github",
                SystemConfig.key == "integration",
                SystemConfig.organization_id == org_uuid
            )
            result = await db.execute(query)
            existing = result.scalars().first()

            config_data = {
                "repo_url": repo_url,
                "encrypted_token": encrypted_token,
                "branch": branch,
                "status": "connected"
            }

            if existing:
                # Update existing
                existing.value_json = config_data
                existing.updated_at = datetime.utcnow()
                existing.updated_by = updated_by
            else:
                # Create new
                new_config = SystemConfig(
                    id=uuid4(),
                    category="github",
                    key="integration",
                    value_json=config_data,
                    value_bytes=None,
                    organization_id=org_uuid,
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow(),
                    created_by=updated_by,
                    updated_by=updated_by
                )
                db.add(new_config)

            await db.commit()
            logger.info(f"Saved GitHub config for org {org_uuid or 'GLOBAL'}")

    async def _delete_github_config(self, context: Any) -> None:
        """
        Delete GitHub configuration from system_configs table.

        Args:
            context: Organization context
        """
        from uuid import UUID
        from sqlalchemy import delete

        from src.core.database import get_session_factory
        from src.models import SystemConfig

        session_factory = get_session_factory()

        org_id = getattr(context, 'org_id', None) or getattr(context, 'scope', None)
        org_uuid = None
        if org_id and org_id != "GLOBAL":
            try:
                org_uuid = UUID(org_id)
            except ValueError:
                pass

        async with session_factory() as db:
            # Delete the config
            stmt = delete(SystemConfig).where(
                SystemConfig.category == "github",
                SystemConfig.key == "integration",
                SystemConfig.organization_id == org_uuid
            )
            await db.execute(stmt)
            await db.commit()
            logger.info(f"Deleted GitHub config for org {org_uuid or 'GLOBAL'}")

    def _clone_repo(self, auth_url: str, branch: str) -> None:
        """
        Clone repository using Dulwich.

        Uses a two-step process to work with Azure Files SMB limitations:
        1. Clone to /tmp (local disk - avoids chmod errors during clone)
        2. Copy entire repo (including .git) to workspace using manual_copy_tree

        After this, all Git operations work directly on the workspace.
        """
        logger.info(f"Cloning repository (branch: {branch})")

        # Clone to system /tmp (local disk, not Azure Files)
        tmp_clone_dir = Path(tempfile.gettempdir()) / f"bifrost_clone_{os.getpid()}_{id(self)}"

        try:
            logger.info(f"Step 1: Cloning to temporary directory: {tmp_clone_dir}")
            porcelain.clone(
                auth_url,
                str(tmp_clone_dir),
                checkout=True,
                branch=branch.encode('utf-8')
            )
            logger.info("Clone to /tmp completed")

            # Copy entire repo (including .git) to workspace
            logger.info(f"Step 2: Copying to workspace: {self.workspace_path}")
            manual_copy_tree(
                tmp_clone_dir,
                self.workspace_path,
                exclude_patterns=['.DS_Store', '._*']  # Exclude macOS metadata
            )
            logger.info("Repository cloned and copied to workspace successfully")

        finally:
            # Clean up temporary clone
            if tmp_clone_dir.exists():
                shutil.rmtree(tmp_clone_dir, ignore_errors=True)
                logger.debug(f"Cleaned up temporary clone directory: {tmp_clone_dir}")

    def _update_existing_repo(self, auth_url: str, branch: str) -> None:
        """Update an existing Git repository with new remote"""
        repo = self.get_repo()

        # Update or create origin remote
        config = repo.get_config()
        config.set((b'remote', b'origin'), b'url', auth_url.encode('utf-8'))
        config.set((b'remote', b'origin'), b'fetch', b'+refs/heads/*:refs/remotes/origin/*')
        config.write_to_path()

        # Fetch from remote (use 'origin' so Dulwich updates refs/remotes/origin/* automatically)
        porcelain.fetch(repo, remote_location='origin')

        # Checkout branch
        branch_ref = f'refs/heads/{branch}'.encode('utf-8')
        remote_ref = f'refs/remotes/origin/{branch}'.encode('utf-8')

        # Create local branch tracking remote
        repo.refs[branch_ref] = repo.refs[remote_ref]

        # Checkout the branch
        porcelain.reset(repo, "hard", branch_ref.decode('utf-8'))  # type: ignore[call-arg]

    async def _clear_and_clone(self, auth_url: str, branch: str) -> str:
        """
        Clear workspace, clone from remote, and install requirements.

        Returns:
            backup_dir: Path to backup directory
        """
        logger.info("Clearing workspace and cloning from remote")

        # Create temporary backup
        backup_dir = Path(tempfile.mkdtemp(prefix="bifrost_backup_"))
        logger.info(f"Creating backup at {backup_dir}")

        # Move all files to backup (skip SMB metadata files)
        for item in self.workspace_path.iterdir():
            # Skip AppleDouble and other SMB metadata files
            if not self._is_real_file(item):
                continue

            try:
                shutil.move(str(item), str(backup_dir / item.name))
            except FileNotFoundError:
                # Handle phantom files that appear in directory listings but don't exist
                # This can happen with SMB/Azure Files mounts
                logger.warning(f"Skipping phantom file that doesn't exist: {item.name}")
                continue

        # Clone repository
        self._clone_repo(auth_url, branch)

        logger.info(f"Replaced workspace with remote content. Backup available at {backup_dir}")

        # Install requirements if requirements.txt exists
        requirements_file = self.workspace_path / "requirements.txt"
        if requirements_file.exists():
            logger.info("Installing requirements from requirements.txt")
            from src.services.package_manager import PackageManager  # type: ignore[attr-defined]

            package_manager = PackageManager(workspace_path=self.workspace_path)
            try:
                # Note: We can't stream here since this is called from initialize_repo
                # Just run the install silently
                await package_manager.install_requirements_streaming()
                logger.info("Requirements installed successfully")
            except Exception as e:
                logger.warning(f"Failed to install requirements: {e}")
                # Don't fail the whole operation if requirements install fails

        return str(backup_dir)

    def _get_pushed_commit_shas(self) -> set[bytes]:
        """
        Get commits that exist in remote tracking branch using Dulwich.

        Returns:
            Set of commit SHAs (as bytes) that exist on remote
        """
        try:
            repo = self.get_repo()
            current_branch = self.get_current_branch() or 'main'
            remote_ref = f'refs/remotes/origin/{current_branch}'.encode('utf-8')

            # If remote ref doesn't exist, no commits are pushed
            if remote_ref not in repo.refs:
                logger.warning(f"Remote ref {remote_ref.decode()} not found")
                return set()

            # Walk all commits reachable from remote ref
            remote_commit = repo.refs[remote_ref]
            walker = repo.get_walker(include=[remote_commit])

            pushed_shas = set()
            for entry in walker:
                pushed_shas.add(entry.commit.id)

            logger.info(f"Found {len(pushed_shas)} commits in remote tracking branch")
            return pushed_shas

        except Exception as e:
            logger.warning(f"Failed to get pushed commit SHAs: {e}")
            return set()

    async def fetch_from_remote(self, context: Any) -> None:
        """
        Fetch latest refs from remote without merging.
        Lightweight operation to update remote tracking branches.

        Uses a module-level lock to prevent concurrent fetch operations that would
        cause SMB lock file conflicts on Azure Files/network mounts.

        Args:
            context: Organization context for retrieving GitHub configuration
        """
        if not self.is_git_repo():
            logger.warning("Not a git repo, skipping fetch")
            return

        # Get authenticated URL
        auth_url = await self._get_authenticated_remote_url(context)
        if not auth_url:
            logger.warning("No GitHub configuration found, cannot fetch")
            return

        # Acquire lock to prevent concurrent fetch operations
        # This prevents "main.lock already exists" errors on SMB mounts
        async with _fetch_lock:
            logger.info(f"Fetching from remote: {auth_url.replace(auth_url.split('@')[0].split('//')[1], '***') if '@' in auth_url else auth_url}")

            try:
                repo = self.get_repo()
                # Use 'origin' so Dulwich automatically updates refs/remotes/origin/*
                _result = porcelain.fetch(repo, remote_location='origin')
                logger.info(f"Fetched latest refs from remote. Refs: {_result.refs}")

            except Exception as e:
                logger.error(f"Failed to fetch from remote: {e}", exc_info=True)
                raise

    async def get_commits_ahead_behind(self) -> tuple[int, int]:
        """
        Get number of commits ahead/behind remote.

        Returns:
            Tuple of (commits_ahead, commits_behind)
        """
        if not self.is_git_repo():
            logger.warning("Not a git repo, returning (0, 0)")
            return (0, 0)

        try:
            repo = self.get_repo()

            # Get current branch name from symbolic ref
            head_path = repo.refs.read_ref(b'HEAD')
            if not head_path or not head_path.startswith(b'ref: '):
                logger.warning("HEAD is detached or invalid, returning (0, 0)")
                return (0, 0)

            branch_ref = head_path[5:].strip()  # Remove "ref: " prefix
            branch_name = branch_ref.split(b'/')[-1].decode('utf-8')
            logger.info(f"Current branch: {branch_name}")

            # Get remote tracking branch
            remote_ref = f'refs/remotes/origin/{branch_name}'.encode('utf-8')
            logger.info(f"Looking for remote ref: {remote_ref.decode('utf-8')}")

            # List all refs to debug
            all_refs = list(repo.refs.keys())
            logger.info(f"All refs in repo: {[r.decode('utf-8') for r in all_refs if b'remote' in r]}")

            if remote_ref not in repo.refs:
                logger.warning(f"Remote ref {remote_ref.decode('utf-8')} not found, returning (0, 0)")
                return (0, 0)

            local_commit = repo.refs[branch_ref]
            remote_commit = repo.refs[remote_ref]

            logger.info(f"Local commit: {local_commit.decode('utf-8')}")
            logger.info(f"Remote commit: {remote_commit.decode('utf-8')}")

            if local_commit == remote_commit:
                logger.info("Local and remote are at same commit")
                return (0, 0)

            # Walk commit graph to count commits ahead and behind
            # Ahead: commits in local that aren't in remote
            walker = repo.get_walker(include=[local_commit], exclude=[remote_commit])
            ahead = sum(1 for _ in walker)

            # Behind: commits in remote that aren't in local
            walker = repo.get_walker(include=[remote_commit], exclude=[local_commit])
            behind = sum(1 for _ in walker)

            logger.info(f"Commits ahead: {ahead}, behind: {behind}")
            return (ahead, behind)

        except Exception as e:
            logger.error(f"Failed to get commits ahead/behind: {e}", exc_info=True)
            return (0, 0)

    def get_current_branch(self) -> str | None:
        """
        Get the name of the current branch.

        Returns:
            Branch name or None if not in a Git repo or detached HEAD
        """
        if not self.is_git_repo():
            return None

        try:
            repo = self.get_repo()
            head_path = repo.refs.read_ref(b'HEAD')

            if not head_path or not head_path.startswith(b'ref: '):
                return None

            # Extract branch name from "ref: refs/heads/main"
            branch_ref = head_path[5:].strip()  # Remove "ref: " prefix
            if branch_ref.startswith(b'refs/heads/'):
                return branch_ref[11:].decode('utf-8')  # Remove "refs/heads/"

            return None

        except Exception as e:
            logger.warning(f"Failed to get current branch: {e}")
            return None

    def get_detected_repo_info(self) -> dict | None:
        """
        Extract repository URL and branch from existing .git folder.

        Returns:
            Dict with repo_url, repo_full_name, and branch, or None if no valid Git repo
        """
        if not self.is_git_repo():
            return None

        try:
            repo = self.get_repo()
            config = repo.get_config()

            # Get remote URL
            remote_url = config.get((b'remote', b'origin'), b'url')
            if not remote_url:
                logger.debug("No origin remote found in Git config")
                return None

            remote_url = remote_url.decode('utf-8')

            # Clean URL (remove existing token if present)
            if '@' in remote_url and 'github.com' in remote_url:
                # Extract github.com part after the token
                parts = remote_url.split('@')
                if len(parts) == 2:
                    remote_url = f"https://{parts[1]}"

            # Check if it's a GitHub URL
            if 'github.com' not in remote_url:
                logger.debug(f"Remote URL is not a GitHub repository: {remote_url}")
                return None

            # Normalize to HTTPS format and extract owner/repo
            if remote_url.startswith('git@github.com:'):
                # Convert SSH to HTTPS
                repo_path = remote_url.replace('git@github.com:', '').replace('.git', '')
                remote_url = f"https://github.com/{repo_path}"
            elif remote_url.startswith('https://github.com/'):
                repo_path = remote_url.replace('https://github.com/', '').replace('.git', '')
            else:
                logger.debug(f"Unexpected GitHub URL format: {remote_url}")
                return None

            # Get current branch
            branch = self.get_current_branch() or "main"

            return {
                "repo_url": f"https://github.com/{repo_path}",
                "repo_full_name": repo_path,
                "branch": branch
            }
        except Exception as e:
            logger.debug(f"Could not detect existing repo: {e}")
            return None

    async def get_commit_history(self, limit: int = 20, offset: int = 0) -> dict:
        """
        Get commit history for the current branch with pagination support.

        Args:
            limit: Maximum number of commits to return (default 20)
            offset: Number of commits to skip (default 0)

        Returns:
            Dict with:
                - commits: List of CommitInfo objects
                - total: Total number of commits
                - has_more: Whether there are more commits to load
        """
        if not self.is_git_repo():
            return {"commits": [], "total_commits": 0, "has_more": False}

        try:
            repo = self.get_repo()
            current_branch = self.get_current_branch()
            if not current_branch:
                return {"commits": [], "total_commits": 0, "has_more": False}

            # Get current HEAD commit
            head_ref = f'refs/heads/{current_branch}'.encode('utf-8')
            if head_ref not in repo.refs:
                return {"commits": [], "total_commits": 0, "has_more": False}

            head_commit_sha = repo.refs[head_ref]

            # Get pushed commit SHAs from remote tracking branch using Dulwich
            pushed_shas = self._get_pushed_commit_shas()

            # First, get total count by walking all commits
            total_walker = repo.get_walker(include=[head_commit_sha])
            total_count = sum(1 for _ in total_walker)

            # Walk the commit history with offset + limit
            commits = []
            walker = repo.get_walker(include=[head_commit_sha], max_entries=offset + limit)

            for i, entry in enumerate(walker):
                # Skip first 'offset' commits
                if i < offset:
                    continue

                commit = entry.commit
                commit_sha = commit.id

                # Parse commit message (first line)
                message_bytes = commit.message
                message = message_bytes.decode('utf-8').strip() if isinstance(message_bytes, bytes) else message_bytes.strip()

                # Parse author
                author_bytes = commit.author
                if isinstance(author_bytes, bytes):
                    author = author_bytes.decode('utf-8')
                else:
                    author = str(author_bytes)

                # Extract just the name part (before <email>)
                if '<' in author:
                    author = author.split('<')[0].strip()

                # Convert timestamp to ISO 8601
                from datetime import datetime, timezone
                timestamp = datetime.fromtimestamp(commit.commit_time, tz=timezone.utc).isoformat()

                # Check if this commit is pushed
                is_pushed = commit_sha in pushed_shas

                commits.append(CommitInfo(
                    sha=commit_sha.decode('utf-8') if isinstance(commit_sha, bytes) else commit_sha,
                    message=message,
                    author=author,
                    timestamp=timestamp,
                    is_pushed=is_pushed
                ))

            has_more = (offset + limit) < total_count

            return {
                "commits": commits,
                "total_commits": total_count,
                "has_more": has_more
            }

        except Exception as e:
            logger.error(f"Failed to get commit history: {e}", exc_info=True)
            return {"commits": [], "total_commits": 0, "has_more": False}

    async def get_changes(self) -> list[FileChange]:
        """
        Get list of changed files in workspace.

        Returns:
            List of FileChange objects with status and diff info
        """
        if not self.is_git_repo():
            return []
        repo = self.get_repo()
        changes = []

        # Get conflicted files to exclude them from changes
        conflicts = await self.get_conflicts()
        conflicted_paths = {c.file_path for c in conflicts}

        # Get status using Dulwich
        status = porcelain.status(repo)

        # Helper to decode path (handles both bytes and str)
        def decode_path(path):
            return path.decode('utf-8') if isinstance(path, bytes) else path

        # Staged changes (added to index)
        for path in status.staged['add']:
            decoded_path = decode_path(path)
            if self._is_real_file(Path(decoded_path)):
                changes.append(FileChange(
                    path=decoded_path,
                    status=GitFileStatus.ADDED,
                    additions=None,
                    deletions=None
                ))

        for path in status.staged['modify']:
            decoded_path = decode_path(path)
            if self._is_real_file(Path(decoded_path)):
                changes.append(FileChange(
                    path=decoded_path,
                    status=GitFileStatus.MODIFIED,
                    additions=None,
                    deletions=None
                ))

        for path in status.staged['delete']:
            decoded_path = decode_path(path)
            if self._is_real_file(Path(decoded_path)):
                changes.append(FileChange(
                    path=decoded_path,
                    status=GitFileStatus.DELETED,
                    additions=None,
                    deletions=None
                ))

        # Unstaged changes
        for path in status.unstaged:
            decoded_path = decode_path(path)
            if self._is_real_file(Path(decoded_path)) and decoded_path not in [f.path for f in changes]:
                changes.append(FileChange(
                    path=decoded_path,
                    status=GitFileStatus.MODIFIED,
                    additions=None,
                    deletions=None
                ))

        # Untracked files
        for path in status.untracked:
            decoded_path = decode_path(path)
            if self._is_real_file(Path(decoded_path)):
                changes.append(FileChange(
                    path=decoded_path,
                    status=GitFileStatus.UNTRACKED,
                    additions=None,
                    deletions=None
                ))

        # Filter out conflicted files - they should only appear in conflicts array
        return [c for c in changes if c.path not in conflicted_paths]

    async def get_changed_files(self) -> list[FileChange]:
        """Alias for get_changes() for backwards compatibility"""
        return await self.get_changes()

    async def get_conflicts(self) -> list[ConflictInfo]:
        """
        Get list of files with merge conflicts by checking Git index.

        Returns:
            List of ConflictInfo objects with ours/theirs/base content
        """
        if not self.is_git_repo():
            return []
        repo = self.get_repo()
        conflicts = []

        try:
            from dulwich.index import ConflictedIndexEntry

            # Check index for conflicted entries
            index = repo.open_index()

            for path_bytes, entry in index.items():
                # Check if this is a conflicted entry
                if isinstance(entry, ConflictedIndexEntry):
                    path_str = path_bytes.decode('utf-8', errors='replace')

                    # Get content from the three versions
                    base_content = None
                    if entry.ancestor:
                        base_blob_obj = repo.object_store[entry.ancestor.sha]
                        if isinstance(base_blob_obj, Blob):
                            base_content = base_blob_obj.data.decode('utf-8', errors='replace')

                    ours_content = ""
                    if entry.this:
                        ours_blob_obj = repo.object_store[entry.this.sha]
                        if isinstance(ours_blob_obj, Blob):
                            ours_content = ours_blob_obj.data.decode('utf-8', errors='replace')

                    theirs_content = ""
                    if entry.other:
                        theirs_blob_obj = repo.object_store[entry.other.sha]
                        if isinstance(theirs_blob_obj, Blob):
                            theirs_content = theirs_blob_obj.data.decode('utf-8', errors='replace')

                    conflicts.append(ConflictInfo(
                        file_path=path_str,
                        current_content=ours_content,  # "ours" version
                        incoming_content=theirs_content,  # "theirs" version
                        base_content=base_content,  # common ancestor
                    ))

        except Exception as e:
            logger.warning(f"Failed to check for conflicts: {e}", exc_info=True)
            return []

        return conflicts

    async def commit(self, message: str) -> dict:
        """
        Commit all changes locally without pushing to remote.

        In S3 mode: downloads workspace to temp dir, commits, uploads back.

        Args:
            message: Commit message

        Returns:
            dict with commit_sha, files_committed, success status
        """
        return await self._commit_impl(message)

    async def _commit_impl(self, message: str) -> dict:
        """Internal commit implementation."""
        if not self.is_git_repo():
            return {
                "success": False,
                "commit_sha": None,
                "files_committed": 0,
                "error": "Workspace is not a Git repository. Call initialize_repo() first.",
            }
        repo = self.get_repo()

        try:
            # Stage all changes
            porcelain.add(repo, paths=[b'.'])

            # Count files to be committed (before commit clears staging area)
            status = porcelain.status(repo)
            files_committed = (
                len(status.staged.get('add', [])) +
                len(status.staged.get('modify', [])) +
                len(status.staged.get('delete', []))
            )

            # Commit
            commit_sha = porcelain.commit(
                repo,
                message=message.encode('utf-8'),
                author=b'Bifrost <noreply@bifrost.io>',
                committer=b'Bifrost <noreply@bifrost.io>'
            )

            # If we were in a merge state, clean it up now that merge is complete
            from pathlib import Path
            merge_head_path = Path(repo.controldir()) / 'MERGE_HEAD'
            if merge_head_path.exists():
                merge_head_path.unlink()
                logger.info("Deleted MERGE_HEAD - merge complete")

                # Also clear saved conflicts
                conflicts_file = Path(repo.controldir()) / 'BIFROST_CONFLICTS'
                if conflicts_file.exists():
                    conflicts_file.unlink()
                    logger.info("Cleared saved conflicts file")

            return {
                "success": True,
                "commit_sha": commit_sha.decode('utf-8') if commit_sha else None,
                "files_committed": files_committed,
                "error": None
            }

        except Exception as e:
            logger.error(f"Failed to commit: {e}", exc_info=True)
            return {
                "success": False,
                "commit_sha": None,
                "files_committed": 0,
                "error": f"Failed to commit changes: {str(e)}"
            }

    async def commit_and_push(
        self,
        context: Any,
        message: str = "Updated from Bifrost",
        connection_id: str | None = None
    ) -> dict:
        """
        Commit all changes and push to remote in one operation.

        In S3 mode: downloads workspace to temp dir, commits, pushes, then uploads back.

        Args:
            context: Organization context for retrieving GitHub configuration
            message: Commit message (default: "Updated from Bifrost")
            connection_id: Optional WebPubSub connection ID for streaming logs

        Returns:
            dict with success status
        """
        # Check for changes
        changes = await self.get_changes()

        if not changes:
            return {
                "success": True,
                "commits_pushed": 0,
                "error": None
            }

        # Commit changes
        commit_result = await self._commit_impl(message=message)
        if not commit_result.get("success"):
            return commit_result

        # Push to remote
        return await self._push_impl(context, connection_id, self.workspace_path)

    async def push(self, context: Any, connection_id: str | None = None) -> dict:
        """
        Push local commits to remote using GitHub API.

        Args:
            context: Organization context for retrieving GitHub configuration
            connection_id: Optional WebPubSub connection ID for streaming logs

        Returns:
            dict with success status
        """
        return await self._push_impl(context, connection_id, self.workspace_path)

    async def _push_impl(self, context: Any, connection_id: str | None, workspace: Path) -> dict:
        """Internal push implementation."""
        if not self.is_git_repo():
            return {
                "success": False,
                "error": "Workspace is not a Git repository. Call initialize_repo() first.",
            }
        repo = self.get_repo()

        # Import pubsub manager for streaming logs via WebSocket
        from src.core.pubsub import manager as pubsub_manager

        async def send_log(message: str, level: str = "info"):
            """Send log message via WebSocket."""
            if connection_id:
                await pubsub_manager.broadcast(
                    f"git:{connection_id}",
                    {"type": "log", "level": level, "message": message},
                )

        try:
            # Serialize platform entities (workflows, forms, apps) from DB to workspace files
            # This generates clean Python code without IDs for portable git storage
            await send_log("Serializing platform entities to workspace...")
            try:
                serialized_paths = await self._serialize_platform_entities_to_workspace()
                if serialized_paths:
                    await send_log(f"Serialized {len(serialized_paths)} platform entities")
            except Exception as e:
                logger.warning(f"Failed to serialize platform entities: {e}")
                await send_log(f"Warning: Some platform entities could not be serialized: {e}", "warning")

            # Check for uncommitted changes before pushing
            await send_log("Checking for uncommitted changes...")
            status = porcelain.status(repo)
            has_changes = (
                status.staged.get('add') or
                status.staged.get('modify') or
                status.staged.get('delete') or
                status.unstaged or
                status.untracked
            )

            if has_changes:
                error_msg = "Cannot push: you have uncommitted changes. Please commit your changes first, then push."
                await send_log(error_msg, "error")
                return {
                    "success": False,
                    "error": error_msg
                }

            # Get GitHub configuration from PostgreSQL
            github_config = await self._get_github_config(context)

            if not github_config or not github_config.get("token") or not github_config.get("repo_url"):
                raise Exception("No GitHub configuration found")

            token = github_config["token"]

            # Parse repo owner/name from repo_url
            repo_url = github_config["repo_url"]
            if repo_url.startswith('https://github.com/'):
                repo_full_name = repo_url.replace('https://github.com/', '').replace('.git', '')
            elif repo_url.startswith('git@github.com:'):
                repo_full_name = repo_url.replace('git@github.com:', '').replace('.git', '')
            else:
                # Assume it's already in owner/repo format
                repo_full_name = repo_url

            await send_log(f"Pushing to GitHub repository: {repo_full_name}")

            # Get current branch
            current_branch = self.get_current_branch() or 'main'

            # Get authenticated remote URL
            auth_url = f"https://{token}@github.com/{repo_full_name}.git"

            # Get local and remote commit SHAs for counting commits to push
            local_ref = f'refs/heads/{current_branch}'.encode('utf-8')
            remote_ref = f'refs/remotes/origin/{current_branch}'.encode('utf-8')

            local_commit_sha = repo.refs[local_ref]
            local_commit_sha_str = local_commit_sha.decode('utf-8')

            try:
                remote_commit_sha = repo.refs[remote_ref]
                remote_commit_sha_str = remote_commit_sha.decode('utf-8')
                await send_log(f"Local: {local_commit_sha_str[:8]}, Remote: {remote_commit_sha_str[:8]}")
            except KeyError:
                await send_log("No remote tracking ref found, will create new branch")
                remote_commit_sha = None
                remote_commit_sha_str = None

            # If already up to date, nothing to push
            if remote_commit_sha and local_commit_sha == remote_commit_sha:
                await send_log("✓ Already up to date, nothing to push")
                return {
                    "success": True,
                    "commits_pushed": 0,
                    "error": None
                }

            # Count commits to push
            commits_to_push = []
            if remote_commit_sha:
                # Walk from local to remote to count commits
                walker = repo.get_walker(include=[local_commit_sha], exclude=[remote_commit_sha])
                commits_to_push = list(walker)
            else:
                # No remote ref, count all commits from HEAD
                walker = repo.get_walker(include=[local_commit_sha])
                commits_to_push = list(walker)

            commits_count = len(commits_to_push)
            await send_log(f"Pushing {commits_count} commit(s) to GitHub...")

            # Push using Dulwich porcelain.push() which preserves commit SHAs
            logger.info(f"Pushing to {auth_url}")
            await send_log("Uploading objects to GitHub...")

            try:
                # Use porcelain.push to push the current branch
                # This preserves local commit SHAs instead of recreating them
                def progress_callback(msg):
                    """Callback for push progress"""
                    logger.info(f"Push progress: {msg.decode('utf-8') if isinstance(msg, bytes) else msg}")

                push_result = porcelain.push(
                    repo.path,
                    remote_location=auth_url,
                    refspecs=[f"refs/heads/{current_branch}:refs/heads/{current_branch}".encode('utf-8')],
                    progress=progress_callback
                )

                logger.info(f"Push result: {push_result}")
                await send_log(f"Pushed {commits_count} commit(s) to GitHub")

                # Update local remote tracking ref to match local branch
                # This ensures the local tracking ref reflects what's actually on GitHub
                repo.refs[remote_ref] = local_commit_sha
                await send_log(f"Updated local tracking ref to {local_commit_sha_str[:8]}")

                return {
                    "success": True,
                    "commits_pushed": commits_count,
                    "error": None
                }

            except Exception as push_error:
                logger.error(f"Push failed: {str(push_error)}")
                raise

        except Exception as e:
            error_msg = f"Failed to push: {str(e)}"
            logger.error(error_msg, exc_info=True)
            await send_log(error_msg, "error")
            return {
                "success": False,
                "error": error_msg
            }

    async def pull(self, context: Any, connection_id: str | None = None) -> dict:
        """
        Pull changes from GitHub remote.

        Uses porcelain.merge_tree() to detect conflicts before attempting merge.

        Args:
            context: Organization context for retrieving GitHub configuration
            connection_id: Optional WebPubSub connection ID for streaming logs

        Returns:
            dict with updated_files, conflicts, success status
        """
        return await self._pull_impl(context, connection_id, self.workspace_path)

    async def _pull_impl(self, context: Any, connection_id: str | None, workspace: Path) -> dict:
        """Internal pull implementation."""
        if not self.is_git_repo():
            return {
                "success": False,
                "updated_files": [],
                "conflicts": [],
                "error": "Workspace is not a Git repository. Call initialize_repo() first.",
            }
        repo = self.get_repo()

        # Import pubsub manager for streaming logs via WebSocket
        from src.core.pubsub import manager as pubsub_manager

        async def send_log(message: str, level: str = "info"):
            """Send log message via WebSocket."""
            if connection_id:
                await pubsub_manager.broadcast(
                    f"git:{connection_id}",
                    {"type": "log", "level": level, "message": message},
                )

        # Check if we're already in a merge state
        from pathlib import Path
        merge_head_path = Path(repo.controldir()) / 'MERGE_HEAD'
        if merge_head_path.exists():
            # Already in a merge - check if there are still conflicts
            conflicts = await self.get_conflicts()
            if conflicts:
                # Still have conflicts - user must resolve them
                return {
                    "success": False,
                    "updated_files": [],
                    "conflicts": conflicts,
                    "error": "Repository has unresolved conflicts. Please resolve them and commit, or abort the merge."
                }
            else:
                # No conflicts remaining but merge not committed - clean up and allow pull
                logger.info("MERGE_HEAD exists but no conflicts - cleaning up incomplete merge state")
                merge_head_path.unlink()
                conflicts_file = Path(repo.controldir()) / 'BIFROST_CONFLICTS'
                if conflicts_file.exists():
                    conflicts_file.unlink()
                # Continue with normal pull
                logger.info("Cleaned up merge state, continuing with pull")

        try:
            await send_log("Starting pull from GitHub...")

            # Get authenticated URL
            auth_url = await self._get_authenticated_remote_url(context)
            if not auth_url:
                raise Exception("No GitHub configuration found")

            await send_log("Fetching changes from remote...")
            # Use 'origin' so Dulwich automatically updates refs/remotes/origin/*
            _result = porcelain.fetch(repo, remote_location='origin')
            await send_log("Fetch complete")

            # Get current branch
            current_branch = self.get_current_branch() or 'main'
            local_ref = f'refs/heads/{current_branch}'.encode('utf-8')
            remote_ref = f'refs/remotes/origin/{current_branch}'.encode('utf-8')

            # Get current commit and remote commit
            local_commit = repo.refs[local_ref]
            remote_commit = repo.refs[remote_ref] if remote_ref in repo.refs else None

            if not remote_commit:
                raise Exception(f"Remote branch {current_branch} not found")

            # If already up to date, return success
            if local_commit == remote_commit:
                await send_log("Already up to date", "success")
                return {
                    "success": True,
                    "updated_files": [],
                    "conflicts": [],
                    "error": None
                }

            # Find merge base (common ancestor)
            merge_bases = porcelain.merge_base(repo, committishes=[local_commit, remote_commit])
            base_commit_raw = repo[merge_bases[0]] if merge_bases else None
            base_commit = base_commit_raw if isinstance(base_commit_raw, DulwichCommit) else None

            # Check if local is ahead of remote (remote is ancestor of local)
            # If so, there's nothing to pull - user just needs to push
            if base_commit and base_commit.id == remote_commit:
                # Remote is behind local - nothing to pull
                await send_log("Local is ahead of remote, nothing to pull")
                return {
                    "success": True,
                    "updated_files": [],
                    "conflicts": [],
                    "error": None
                }

            await send_log("Checking for uncommitted changes...")

            # First, check for uncommitted changes that would conflict with incoming changes
            from dulwich.porcelain import status as git_status
            from dulwich.diff_tree import tree_changes

            git_status_result = git_status(repo)
            uncommitted_files = set()

            # Collect all uncommitted files (staged and unstaged)
            for file_list in [git_status_result.staged.get('add', []),
                             git_status_result.staged.get('modify', []),
                             git_status_result.staged.get('delete', [])]:
                uncommitted_files.update(f.decode('utf-8') if isinstance(f, bytes) else f for f in file_list)
            uncommitted_files.update(f.decode('utf-8') if isinstance(f, bytes) else f for f in git_status_result.unstaged)

            logger.info(f"Found {len(uncommitted_files)} uncommitted file(s): {uncommitted_files}")

            # Get files that will be changed by the pull (compare local HEAD with remote)
            local_commit_obj_raw = repo[local_commit]
            remote_commit_obj_raw = repo[remote_commit]

            # Cast to Commit type for type safety
            if not isinstance(local_commit_obj_raw, DulwichCommit) or not isinstance(remote_commit_obj_raw, DulwichCommit):
                raise Exception("Failed to retrieve commit objects")

            local_commit_obj = local_commit_obj_raw
            remote_commit_obj = remote_commit_obj_raw

            remote_changed_files = set()
            for change in tree_changes(repo.object_store, local_commit_obj.tree, remote_commit_obj.tree):
                if change.type != 'unchanged':
                    path_bytes = change.new.path if change.new and change.new.path else (change.old.path if change.old else None)
                    if path_bytes:
                        path = path_bytes.decode('utf-8')
                        remote_changed_files.add(path)

            logger.info(f"Remote will change {len(remote_changed_files)} file(s): {remote_changed_files}")

            # Find files with uncommitted changes that remote also wants to change
            uncommitted_conflicts = uncommitted_files & remote_changed_files

            if uncommitted_conflicts:
                logger.warning(f"Uncommitted changes conflict with incoming changes in {len(uncommitted_conflicts)} file(s): {uncommitted_conflicts}")

                conflict_list = ", ".join(sorted(uncommitted_conflicts))
                error_msg = f"Your local changes to the following files would be overwritten by pull: {conflict_list}. Please commit your changes or stash them before pulling."
                await send_log(f"✗ {error_msg}", "error")

                return {
                    "success": False,
                    "updated_files": [],
                    "conflicts": [],
                    "error": error_msg
                }

            await send_log("Checking for merge conflicts...")
            # Check for conflicts by comparing trees (don't write markers)
            from dulwich.merge import three_way_merge

            try:
                logger.info(f"Checking for conflicts: base={base_commit.id.decode('utf-8')[:8] if base_commit else 'None'}, ours={local_commit.decode('utf-8')[:8]}, theirs={remote_commit.decode('utf-8')[:8]}")

                # Perform tree-level merge to detect conflicted paths (but don't write markers)
                merged_tree, conflicted_paths = three_way_merge(
                    repo.object_store,
                    base_commit=base_commit,
                    ours_commit=local_commit_obj,
                    theirs_commit=remote_commit_obj
                )

                logger.info(f"Conflict detection result: {len(conflicted_paths)} conflicted path(s)")

                # For each conflicted path, collect local and remote content without writing markers
                conflicts_list = []

                def get_object_for_path(commit_obj: DulwichCommit | None, path_b: bytes | None) -> ShaFile | None:
                    """Get tree or blob object for a path"""
                    if not commit_obj:
                        return None
                    tree_obj_raw = repo[commit_obj.tree]
                    if not isinstance(tree_obj_raw, (Tree, Blob)):
                        return None
                    tree_obj: ShaFile = tree_obj_raw
                    if not path_b:  # Root
                        return tree_obj
                    parts = path_b.split(b'/')
                    for part in parts:
                        if not hasattr(tree_obj, '__getitem__'):
                            return None
                        mode, sha = tree_obj[part]  # type: ignore
                        obj = repo[sha]
                        if hasattr(obj, 'items'):  # It's a tree
                            tree_obj = obj
                        else:  # It's a blob
                            return obj
                    return tree_obj

                def process_conflicted_tree(path_prefix, base_tree, ours_tree, theirs_tree):
                    """Recursively process a conflicted tree to find actual file conflicts"""
                    # Get all file names from all three trees
                    base_entries = {name: (mode, sha) for name, mode, sha in base_tree.items()} if base_tree else {}
                    ours_entries = {name: (mode, sha) for name, mode, sha in ours_tree.items()} if ours_tree else {}
                    theirs_entries = {name: (mode, sha) for name, mode, sha in theirs_tree.items()} if theirs_tree else {}

                    all_names = set(base_entries.keys()) | set(ours_entries.keys()) | set(theirs_entries.keys())

                    for name in all_names:
                        file_path_bytes = path_prefix + b'/' + name if path_prefix else name
                        file_path_str = file_path_bytes.decode('utf-8')

                        base_entry = base_entries.get(name)
                        ours_entry = ours_entries.get(name)
                        theirs_entry = theirs_entries.get(name)

                        # Check if all three point to same SHA (no conflict)
                        if base_entry and ours_entry and theirs_entry:
                            if base_entry[1] == ours_entry[1] == theirs_entry[1]:
                                continue  # No conflict

                        # Get objects
                        base_obj = repo[base_entry[1]] if base_entry else None
                        ours_obj = repo[ours_entry[1]] if ours_entry else None
                        theirs_obj = repo[theirs_entry[1]] if theirs_entry else None

                        # Check if any is a tree (directory)
                        is_tree = any(hasattr(obj, 'items') for obj in [base_obj, ours_obj, theirs_obj] if obj)

                        if is_tree:
                            # Recursively process subdirectory
                            process_conflicted_tree(
                                file_path_bytes,
                                base_obj if hasattr(base_obj, 'items') else None,
                                ours_obj if hasattr(ours_obj, 'items') else None,
                                theirs_obj if hasattr(theirs_obj, 'items') else None
                            )
                        else:
                            # It's a file conflict - just collect the content from both sides
                            try:
                                current_content = ours_obj.as_raw_string().decode('utf-8', errors='replace') if ours_obj else ""
                                incoming_content = theirs_obj.as_raw_string().decode('utf-8', errors='replace') if theirs_obj else ""
                                base_content = base_obj.as_raw_string().decode('utf-8', errors='replace') if base_obj else None

                                conflicts_list.append({
                                    "file_path": file_path_str,
                                    "current_content": current_content,
                                    "incoming_content": incoming_content,
                                    "base_content": base_content,
                                })
                                logger.info(f"Found conflict in: {file_path_str}")

                            except Exception as e:
                                logger.warning(f"Failed to read content for {file_path_str}: {e}")

                for path_bytes in conflicted_paths:
                    path_str = path_bytes.decode('utf-8') if isinstance(path_bytes, bytes) else path_bytes
                    logger.info(f"Processing conflicted path: {path_str}")

                    try:
                        base_obj = get_object_for_path(base_commit, path_bytes) if base_commit else None
                        ours_obj = get_object_for_path(local_commit_obj, path_bytes)
                        theirs_obj = get_object_for_path(remote_commit_obj, path_bytes)

                        # Check if it's a tree or blob
                        if any(hasattr(obj, 'items') for obj in [base_obj, ours_obj, theirs_obj] if obj):
                            # It's a tree - recursively process
                            process_conflicted_tree(
                                path_bytes,
                                base_obj if hasattr(base_obj, 'items') else None,
                                ours_obj if hasattr(ours_obj, 'items') else None,
                                theirs_obj if hasattr(theirs_obj, 'items') else None
                            )
                        else:
                            # It's a blob - collect content
                            current_content = ours_obj.as_raw_string().decode('utf-8', errors='replace') if ours_obj else ""
                            incoming_content = theirs_obj.as_raw_string().decode('utf-8', errors='replace') if theirs_obj else ""
                            base_content = base_obj.as_raw_string().decode('utf-8', errors='replace') if base_obj else None

                            conflicts_list.append({
                                "file_path": path_str,
                                "current_content": current_content,
                                "incoming_content": incoming_content,
                                "base_content": base_content,
                            })
                            logger.info(f"Found conflict in: {path_str}")

                    except Exception as e:
                        logger.warning(f"Failed to process {path_str}: {e}")

                # If we have conflicts, write merge state to Git and return
                if conflicts_list:
                    await send_log(f"⚠️ Found {len(conflicts_list)} conflicting file(s)", "warning")
                    logger.warning(f"Pull detected {len(conflicts_list)} conflict(s) in files: {[c['file_path'] for c in conflicts_list]}")

                    # Write MERGE_HEAD to mark that we're in a merge state
                    from pathlib import Path
                    merge_head_path = Path(repo.controldir()) / 'MERGE_HEAD'
                    merge_head_path.write_text(remote_commit.decode('utf-8') + '\n')
                    logger.info(f"Wrote MERGE_HEAD: {remote_commit.decode('utf-8')[:8]}")

                    # Write conflicted files to index with multiple stages
                    # This makes Git recognize them as conflicts (like a real merge)
                    index = repo.open_index()
                    for conflict_path_str in [c['file_path'] for c in conflicts_list]:
                        conflict_path_b = conflict_path_str.encode('utf-8')

                        # Get the three versions from the trees
                        def get_blob_from_tree(tree_obj: ShaFile | None, path_b: bytes) -> Blob | None:
                            if not tree_obj:
                                return None
                            parts = path_b.split(b'/')
                            current_tree = tree_obj
                            for part in parts[:-1]:
                                try:
                                    if not hasattr(current_tree, '__getitem__'):
                                        return None
                                    mode, sha = current_tree[part]  # type: ignore
                                    current_tree = repo[sha]
                                except (KeyError, TypeError):
                                    return None
                            try:
                                if not hasattr(current_tree, '__getitem__'):
                                    return None
                                mode, sha = current_tree[parts[-1]]  # type: ignore
                                blob_obj = repo[sha]
                                return blob_obj if isinstance(blob_obj, Blob) else None
                            except (KeyError, TypeError):
                                return None

                        base_tree_obj = repo[base_commit.tree] if base_commit else None
                        ours_tree_obj = repo[local_commit_obj.tree]
                        theirs_tree_obj = repo[remote_commit_obj.tree]

                        base_blob = get_blob_from_tree(base_tree_obj, conflict_path_b)
                        ours_blob = get_blob_from_tree(ours_tree_obj, conflict_path_b)
                        theirs_blob = get_blob_from_tree(theirs_tree_obj, conflict_path_b)

                        # Remove stage 0 entry if it exists
                        if conflict_path_b in index:
                            del index[conflict_path_b]

                        # Create ConflictedIndexEntry with all three versions
                        from dulwich.index import IndexEntry, ConflictedIndexEntry
                        import time
                        import stat

                        def make_index_entry(blob: Blob | None) -> IndexEntry | None:
                            """Create an IndexEntry for a blob."""
                            if not blob or not isinstance(blob, Blob):
                                return None
                            return IndexEntry(
                                ctime=(int(time.time()), 0),
                                mtime=(int(time.time()), 0),
                                dev=0,
                                ino=0,
                                mode=stat.S_IFREG | 0o644,
                                uid=0,
                                gid=0,
                                size=len(blob.data),
                                sha=blob.id,
                                flags=len(conflict_path_b),  # No stage in flags for ConflictedIndexEntry
                            )

                        # Store as ConflictedIndexEntry so get_conflicts() can find it
                        conflicted_entry = ConflictedIndexEntry(
                            ancestor=make_index_entry(base_blob),  # stage 1
                            this=make_index_entry(ours_blob),      # stage 2
                            other=make_index_entry(theirs_blob)    # stage 3
                        )
                        index[conflict_path_b] = conflicted_entry

                    index.write()
                    logger.info(f"Wrote {len(conflicts_list)} conflicted files to index with stages")

                    # Write conflict markers to working directory files
                    from dulwich.merge import merge_blobs
                    files_with_markers = 0

                    # Get tree objects (need them for the loop below)
                    base_tree_for_markers = repo[base_commit.tree] if base_commit else None
                    ours_tree_for_markers = repo[local_commit_obj.tree]
                    theirs_tree_for_markers = repo[remote_commit_obj.tree]

                    for conflict_path_str in [c['file_path'] for c in conflicts_list]:
                        conflict_path_b = conflict_path_str.encode('utf-8')

                        # Get the three blob versions
                        base_blob = get_blob_from_tree(base_tree_for_markers, conflict_path_b)
                        ours_blob = get_blob_from_tree(ours_tree_for_markers, conflict_path_b)
                        theirs_blob = get_blob_from_tree(theirs_tree_for_markers, conflict_path_b)

                        # Use merge_blobs to create content with conflict markers
                        merged_content, had_conflicts = merge_blobs(
                            base_blob,
                            ours_blob,
                            theirs_blob,
                            path=conflict_path_b
                        )

                        # Write the merged content (with conflict markers) to working directory
                        workspace_path = Path(repo.path)
                        file_path = workspace_path / conflict_path_str
                        file_path.parent.mkdir(parents=True, exist_ok=True)
                        file_path.write_bytes(merged_content)
                        files_with_markers += 1
                        logger.info(f"Wrote conflict markers to {conflict_path_str}")

                    logger.info(f"Wrote conflict markers to {files_with_markers} file(s) in working directory")

                    return {
                        "success": False,
                        "updated_files": [],
                        "conflicts": conflicts_list,
                        "error": f"Merge conflicts in {len(conflicts_list)} file(s)"
                    }

                # Merge succeeded without conflicts - now actually perform the merge using Dulwich
                await send_log("No conflicts detected, applying changes...")
                logger.info("No conflicts detected, performing merge using Dulwich...")

                try:
                    # Check if this is a fast-forward merge (base == local)
                    if base_commit and base_commit.id == local_commit:
                        # Fast-forward: just update refs and working tree
                        logger.info("Fast-forward merge: updating refs")
                        await send_log("Fast-forwarding to remote commit...")

                        # Update local branch ref to point to remote commit
                        repo.refs[local_ref] = remote_commit

                        # Update working tree to match remote commit
                        # Use reset_index to update the working directory
                        from dulwich.index import build_index_from_tree
                        index_path = os.path.join(repo.controldir(), 'index')
                        remote_commit_obj_for_ff = repo[remote_commit]
                        if not isinstance(remote_commit_obj_for_ff, DulwichCommit):
                            raise Exception("Failed to retrieve remote commit object")
                        remote_tree = remote_commit_obj_for_ff.tree

                        with open(index_path, 'wb'):  # noqa: F841
                            build_index_from_tree(repo.path, index_path, repo.object_store, remote_tree)

                        # Get updated files by comparing trees
                        from dulwich.diff_tree import tree_changes
                        local_commit_obj_for_ff = repo[local_commit]
                        if not isinstance(local_commit_obj_for_ff, DulwichCommit):
                            raise Exception("Failed to retrieve local commit object")
                        old_tree = local_commit_obj_for_ff.tree
                        new_tree = remote_tree

                        updated_files = []
                        for change in tree_changes(repo.object_store, old_tree, new_tree):
                            if change.type != 'unchanged':
                                path_bytes = change.new.path if change.new and change.new.path else (change.old.path if change.old else None)
                                if path_bytes:
                                    updated_files.append(path_bytes.decode('utf-8'))

                        logger.info(f"Fast-forward completed: {len(updated_files)} file(s) updated")
                        await send_log(f"✓ Pull successful! Fast-forwarded {len(updated_files)} file(s)", "success")

                    else:
                        # True merge: stage the merged tree and create MERGE_HEAD state
                        # This allows the user to review changes and commit manually (GitHub Desktop-style)
                        logger.info("Staging merge with Dulwich")
                        await send_log("Staging merged changes...")

                        # Stage the merged tree in the index using build_index_from_tree
                        # This updates both the index and working tree
                        from dulwich.index import build_index_from_tree
                        index_path = os.path.join(repo.controldir(), 'index')

                        with open(index_path, 'wb'):  # noqa: F841
                            build_index_from_tree(repo.path, index_path, repo.object_store, merged_tree.id)

                        logger.info("Staged merged tree to index and updated working tree")

                        # Write MERGE_HEAD to mark merge in progress
                        from pathlib import Path
                        merge_head_path = Path(repo.controldir()) / 'MERGE_HEAD'
                        merge_head_path.write_text(remote_commit.decode('utf-8') + '\n')
                        logger.info(f"Wrote MERGE_HEAD: {remote_commit.decode('utf-8')[:8]}")

                        # Calculate which files changed in the merge
                        # We want the union of (local→merged) and (remote→merged) changes
                        from dulwich.diff_tree import tree_changes

                        local_changes = set()
                        for change in tree_changes(repo.object_store, local_commit_obj.tree, merged_tree.id):
                            if change.type != 'unchanged':
                                path_bytes = change.new.path if change.new and change.new.path else (change.old.path if change.old else None)
                                if path_bytes:
                                    local_changes.add(path_bytes.decode('utf-8'))

                        remote_changes = set()
                        for change in tree_changes(repo.object_store, remote_commit_obj.tree, merged_tree.id):
                            if change.type != 'unchanged':
                                path_bytes = change.new.path if change.new and change.new.path else (change.old.path if change.old else None)
                                if path_bytes:
                                    remote_changes.add(path_bytes.decode('utf-8'))

                        updated_files = list(local_changes | remote_changes)

                        logger.info(f"Merge staged successfully, {len(updated_files)} file(s) ready to commit")
                        await send_log(f"✓ Merge prepared! {len(updated_files)} file(s) staged. Review and commit to complete the merge.", "success")

                    # Parse and upsert platform entities from updated files to DB
                    # This syncs file changes (workflows, forms, apps) to the database
                    try:
                        await send_log("Syncing platform entities to database...")
                        await self._parse_and_upsert_platform_entities(updated_files)
                    except Exception as e:
                        logger.warning(f"Failed to parse platform entities: {e}")
                        await send_log(f"Warning: Some platform entities could not be synced: {e}", "warning")

                    # Scan updated Python files for missing SDK references
                    await self._scan_updated_files_for_sdk_issues(updated_files)

                    return {
                        "success": True,
                        "updated_files": updated_files,
                        "conflicts": [],
                        "error": None
                    }

                except Exception as e:
                    logger.error(f"Merge execution failed: {str(e)}")
                    raise

            except Exception as merge_error:
                # Unexpected merge error
                error_msg = str(merge_error)
                logger.error(f"Merge failed with error: {error_msg}")
                raise

        except Exception as e:
            logger.error(f"Failed to pull from GitHub: {e}", exc_info=True)

            # Try to get conflicts even on error
            try:
                conflicts = await self.get_conflicts()
                if conflicts:
                    conflict_files = [c.file_path for c in conflicts]
                    return {
                        "success": False,
                        "updated_files": [],
                        "conflicts": [c.model_dump() for c in conflicts],
                        "error": f"Merge conflicts occurred: {', '.join(conflict_files)}"
                    }
            except Exception as conflict_err:
                logger.warning(f"Failed to check for conflicts after pull error: {conflict_err}")

            # Format error message properly
            error_msg = str(e)
            # Clean up bytes representation in error messages
            if "b'" in error_msg:
                import re
                error_msg = re.sub(r"b'([^']+)'", r'\1', error_msg)

            # Send error to WebPubSub terminal
            full_error_msg = f"Failed to pull from GitHub: {error_msg}"
            await send_log(f"✗ {full_error_msg}", "error")

            return {
                "success": False,
                "updated_files": [],
                "conflicts": [],
                "error": full_error_msg
            }

    async def get_repo_info(self, context: Any, fetch: bool = False) -> dict:
        """
        Get repository information including connection status, branch, and repository details.

        This is a simpler version of refresh_status() focused on repo metadata.

        Args:
            context: Organization context for retrieving GitHub configuration
            fetch: If True, fetch from remote before getting status (default: False)

        Returns:
            dict with repository info
        """
        return await self.refresh_status(context, fetch)

    async def refresh_status(self, context: Any, fetch: bool = False) -> dict:
        """
        Get complete Git status including local changes, conflicts, and commit history.

        Args:
            context: Organization context for retrieving GitHub configuration
            fetch: If True, fetch from remote before getting status (default: False)
                   Set to True only when user explicitly requests sync/refresh

        Returns:
            dict with complete refresh status (GitRefreshStatusResponse format)
        """
        try:
            # Check if Git repo is initialized
            initialized = self.is_git_repo()

            # If not initialized, return early
            if not initialized:
                return {
                    "success": True,
                    "initialized": False,
                    "configured": False,
                    "current_branch": None,
                    "changed_files": [],
                    "conflicts": [],
                    "merging": False,
                    "commits_ahead": 0,
                    "commits_behind": 0,
                    "commit_history": [],
                    "last_synced": datetime.now(timezone.utc).isoformat(),
                    "error": None
                }

            # Check if GitHub is configured (has authenticated remote URL)
            # This is optional - local Git operations work without it
            configured = False
            try:
                auth_url = await self._get_authenticated_remote_url(context)
                configured = auth_url is not None
            except Exception:
                configured = False

            # 1. Optionally fetch from remote to update tracking refs
            # Only fetch when user explicitly requests it (fetch=True)
            # This prevents slow SMB operations on every status check
            if fetch:
                try:
                    await self.fetch_from_remote(context)
                except Exception as e:
                    logger.warning(f"Failed to fetch from remote during refresh: {e}")

            # 2. Get current branch
            current_branch = self.get_current_branch()

            # 3. Get local changes and conflicts
            changed_files = await self.get_changed_files()
            conflicts = await self.get_conflicts()

            # 4. Check if in merge state
            from pathlib import Path
            repo = self.get_repo()
            merge_head_path = Path(repo.controldir()) / 'MERGE_HEAD'
            merging = merge_head_path.exists()

            # 5. Get ahead/behind counts
            ahead, behind = await self.get_commits_ahead_behind()

            # 6. Get commit history (pass context for accurate pushed status)
            history_result = await self.get_commit_history(limit=20)

            return {
                "success": True,
                "initialized": initialized,
                "configured": configured,
                "current_branch": current_branch,
                "changed_files": changed_files,
                "conflicts": conflicts,
                "merging": merging,
                "commits_ahead": ahead,
                "commits_behind": behind,
                "commit_history": history_result["commits"],
                "last_synced": datetime.now(timezone.utc).isoformat(),
                "error": None
            }

        except Exception as e:
            logger.error(f"Failed to refresh status: {e}", exc_info=True)
            return {
                "success": False,
                "initialized": False,
                "configured": False,
                "current_branch": None,
                "changed_files": [],
                "conflicts": [],
                "merging": False,
                "commits_ahead": 0,
                "commits_behind": 0,
                "commit_history": [],
                "last_synced": datetime.now(timezone.utc).isoformat(),
                "error": f"Failed to refresh status: {str(e)}"
            }

    async def discard_unpushed_commits(self, context: Any = None) -> dict:
        """
        Discard all unpushed commits by resetting local branch to remote tracking ref.
        This is useful when local commits are causing issues or are no longer needed.

        Returns:
            dict with success status and list of discarded commits
        """
        if not self.is_git_repo():
            return {
                "success": False,
                "discarded_commits": [],
                "new_head": None,
                "error": "Workspace is not a Git repository. Call initialize_repo() first.",
            }
        repo = self.get_repo()

        try:
            # Get current branch
            current_branch = self.get_current_branch() or 'main'
            local_ref = f'refs/heads/{current_branch}'.encode('utf-8')
            remote_ref = f'refs/remotes/origin/{current_branch}'.encode('utf-8')

            # Check if remote ref exists
            if remote_ref not in repo.refs:
                return {
                    "success": False,
                    "discarded_commits": [],
                    "new_head": None,
                    "error": "No remote tracking branch found. Cannot discard commits without a remote reference."
                }

            local_commit = repo.refs[local_ref]
            remote_commit = repo.refs[remote_ref]

            # Get list of commits that will be discarded (commits in local but not in remote)
            discarded_commits = []
            if local_commit != remote_commit:
                # Get commits that are ahead (these will be discarded)
                walker = repo.get_walker(include=[local_commit], exclude=[remote_commit])

                for entry in walker:
                    commit = entry.commit
                    discarded_commits.append({
                        "sha": commit.id.decode('utf-8') if isinstance(commit.id, bytes) else commit.id,
                        "message": commit.message.decode('utf-8').strip(),
                        "author": commit.author.decode('utf-8') if isinstance(commit.author, bytes) else commit.author,
                        "timestamp": datetime.fromtimestamp(commit.commit_time, tz=timezone.utc).isoformat(),
                        "is_pushed": False
                    })

                # Reset local branch to remote
                repo.refs[local_ref] = remote_commit

                # Hard reset working directory to match (need tree ID, not commit ID)
                remote_commit_obj_raw = repo[remote_commit]
                if isinstance(remote_commit_obj_raw, DulwichCommit):
                    repo.reset_index(remote_commit_obj_raw.tree)
                else:
                    raise Exception("Failed to retrieve remote commit object")

                logger.info(f"Discarded {len(discarded_commits)} unpushed commit(s) on {current_branch}")

            return {
                "success": True,
                "discarded_commits": discarded_commits,
                "new_head": remote_commit.decode('utf-8') if isinstance(remote_commit, bytes) else remote_commit,
                "error": None
            }

        except Exception as e:
            logger.error(f"Failed to discard unpushed commits: {e}", exc_info=True)
            return {
                "success": False,
                "discarded_commits": [],
                "new_head": None,
                "error": f"Failed to discard unpushed commits: {str(e)}"
            }

    async def discard_commit(self, commit_sha: str, context: Any = None) -> dict:
        """
        Discard a specific commit and all commits newer than it.
        This resets the branch to the parent of the specified commit.

        Args:
            commit_sha: SHA of the commit to discard
            context: Optional context for async operations like fetch

        Returns:
            dict with success status and list of discarded commits
        """
        repo = self.get_repo()

        try:
            # Convert SHA to bytes if needed
            target_sha = commit_sha.encode('utf-8') if isinstance(commit_sha, str) else commit_sha

            # Verify the commit exists
            try:
                target_commit_raw = repo[target_sha]
                if not isinstance(target_commit_raw, DulwichCommit):
                    raise Exception("Retrieved object is not a commit")
                target_commit = target_commit_raw
            except (KeyError, Exception) as e:
                return {
                    "success": False,
                    "discarded_commits": [],
                    "new_head": None,
                    "error": f"Commit {commit_sha} not found in repository: {str(e)}"
                }

            # Get current branch
            current_branch = self.get_current_branch() or 'main'
            local_ref = f'refs/heads/{current_branch}'.encode('utf-8')
            current_commit = repo.refs[local_ref]

            # Get the parent of the target commit (this becomes the new HEAD)
            if not target_commit.parents:
                return {
                    "success": False,
                    "discarded_commits": [],
                    "new_head": None,
                    "error": "Cannot discard the initial commit (it has no parent)"
                }

            new_head = target_commit.parents[0]

            # Get list of commits that will be discarded
            discarded_commits = []
            walker = repo.get_walker(include=[current_commit], exclude=[new_head])

            for entry in walker:
                commit = entry.commit
                discarded_commits.append({
                    "sha": commit.id.decode('utf-8') if isinstance(commit.id, bytes) else commit.id,
                    "message": commit.message.decode('utf-8').strip(),
                    "author": commit.author.decode('utf-8') if isinstance(commit.author, bytes) else commit.author,
                    "timestamp": datetime.fromtimestamp(commit.commit_time, tz=timezone.utc).isoformat(),
                    "is_pushed": False
                })

            # Reset branch to parent of target commit
            repo.refs[local_ref] = new_head

            # Hard reset working directory to match (need tree ID, not commit ID)
            new_head_obj_raw = repo[new_head]
            if isinstance(new_head_obj_raw, DulwichCommit):
                repo.reset_index(new_head_obj_raw.tree)
            else:
                raise Exception("Failed to retrieve new HEAD commit object")

            logger.info(f"Discarded {len(discarded_commits)} commit(s) on {current_branch}, reset to {new_head.decode('utf-8') if isinstance(new_head, bytes) else new_head}")

            return {
                "success": True,
                "discarded_commits": discarded_commits,
                "new_head": new_head.decode('utf-8') if isinstance(new_head, bytes) else new_head,
                "error": None
            }

        except Exception as e:
            logger.error(f"Failed to discard commit {commit_sha}: {e}", exc_info=True)
            return {
                "success": False,
                "discarded_commits": [],
                "new_head": None,
                "error": f"Failed to discard commit: {str(e)}"
            }

    async def resolve_conflict(
        self,
        file_path: str,
        resolution: Literal["current", "incoming", "both", "manual"],
        manual_content: str | None = None
    ) -> int:
        """
        Resolve a merge conflict in a file by removing conflict stages from index.

        The file content should already be written by the caller.
        This method removes the conflict stages (1/2/3) and adds stage 0.

        Args:
            file_path: Path to conflicted file (already resolved)
            resolution: Resolution strategy (for logging)
            manual_content: Not used (kept for API compatibility)

        Returns:
            Number of remaining conflicts
        """
        full_path = self.workspace_path / file_path

        if not full_path.exists():
            raise ValueError(f"File not found: {file_path}")

        # Remove conflict stages and stage the resolved file
        # We need to manually manipulate the index to ensure the file is staged
        # even if content matches HEAD (which porcelain.add might skip)
        repo = self.get_repo()
        index = repo.open_index()
        file_path_bytes = file_path.encode('utf-8')

        # Remove all stages for this file (0, 1, 2, 3)
        # The index can have multiple entries for the same path with different stages
        entries_to_remove = []
        for path_bytes, entry in index.items():
            if path_bytes == file_path_bytes:
                entries_to_remove.append(path_bytes)

        for path_bytes in entries_to_remove:
            del index[path_bytes]

        # Now add the resolved file at stage 0
        # Force add it by creating an index entry manually
        from dulwich.index import IndexEntry
        import stat

        # Read the resolved file content
        with open(full_path, 'rb') as f:
            file_content = f.read()

        # Create blob object
        from dulwich.objects import Blob
        blob = Blob.from_string(file_content)
        repo.object_store.add_object(blob)

        # Create index entry at stage 0
        file_stat = full_path.stat()
        entry = IndexEntry(
            ctime=(int(file_stat.st_ctime), 0),
            mtime=(int(file_stat.st_mtime), 0),
            dev=file_stat.st_dev,
            ino=file_stat.st_ino,
            mode=stat.S_IFREG | 0o644,
            uid=file_stat.st_uid,
            gid=file_stat.st_gid,
            size=len(file_content),
            sha=blob.id,
            flags=len(file_path_bytes),  # Stage 0 (no stage bits set)
        )
        index[file_path_bytes] = entry
        index.write()

        logger.info(f"Staged resolved file: {file_path} (resolution: {resolution})")

        # Check remaining conflicts
        remaining_conflicts = await self.get_conflicts()
        logger.info(f"Remaining conflicts after staging: {len(remaining_conflicts)}")

        return len(remaining_conflicts)

    async def abort_merge(self) -> dict:
        """
        Abort an in-progress merge and return to pre-merge state.

        This clears MERGE_HEAD and conflict markers, and resets the index.
        Similar to `git merge --abort`.

        Returns:
            dict with success status
        """
        if not self.is_git_repo():
            return {
                "success": False,
                "error": "Workspace is not a Git repository. Call initialize_repo() first.",
            }
        repo = self.get_repo()

        from pathlib import Path
        merge_head_path = Path(repo.controldir()) / 'MERGE_HEAD'

        if not merge_head_path.exists():
            return {
                "success": False,
                "error": "No merge in progress"
            }

        try:
            # Delete MERGE_HEAD
            merge_head_path.unlink()
            logger.info("Deleted MERGE_HEAD")

            # Clear saved conflicts
            conflicts_file = Path(repo.controldir()) / 'BIFROST_CONFLICTS'
            if conflicts_file.exists():
                conflicts_file.unlink()
                logger.info("Cleared saved conflicts")

            # Reset index to HEAD (removes conflict stages)
            # This is equivalent to git reset --mixed HEAD
            index = repo.open_index()
            head_commit_raw = repo[repo.head()]
            if not isinstance(head_commit_raw, DulwichCommit):
                raise Exception("Failed to retrieve HEAD commit")
            head_tree = head_commit_raw.tree
            index.clear()

            # Rebuild index from HEAD tree
            # Using build_index_from_tree instead of manual iteration
            from dulwich.index import build_index_from_tree
            index_path = os.path.join(repo.controldir(), 'index')
            with open(index_path, 'wb'):  # noqa: F841
                build_index_from_tree(repo.path, index_path, repo.object_store, head_tree)

            logger.info("Reset index to HEAD")

            return {
                "success": True,
                "message": "Merge aborted successfully"
            }

        except Exception as e:
            logger.error(f"Failed to abort merge: {e}", exc_info=True)
            return {
                "success": False,
                "error": f"Failed to abort merge: {str(e)}"
            }

    async def _scan_updated_files_for_sdk_issues(self, updated_files: list[str]) -> None:
        """
        Scan updated Python files for missing SDK references after git pull.

        Creates platform admin notifications if issues are found.

        Args:
            updated_files: List of file paths that were updated during pull
        """
        python_files = [f for f in updated_files if f.endswith(".py")]
        if not python_files:
            return

        try:
            from src.core.database import get_session_factory
            from src.services.sdk_reference_scanner import SDKReferenceScanner
            from src.services.notification_service import get_notification_service
            from src.models.contracts.notifications import (
                NotificationCreate,
                NotificationCategory,
                NotificationStatus,
            )

            session_factory = get_session_factory()
            async with session_factory() as db:
                scanner = SDKReferenceScanner(db)
                all_issues = []

                for py_file in python_files:
                    file_path = self.workspace_path / py_file
                    if not file_path.exists():
                        continue

                    try:
                        content = file_path.read_text(encoding="utf-8")
                        issues = await scanner.scan_file(py_file, content)
                        all_issues.extend(issues)
                    except (OSError, UnicodeDecodeError) as e:
                        logger.warning(f"Failed to scan {py_file} for SDK issues: {e}")

                if not all_issues:
                    return

                # Create platform admin notification for all issues found in pull
                service = get_notification_service()

                # Build description with summary
                files_with_issues = len({i.file_path for i in all_issues})
                title = f"Missing SDK References: {files_with_issues} file(s) from Git pull"

                # Check for existing notification to avoid duplicates
                existing = await service.find_admin_notification_by_title(
                    title=title,
                    category=NotificationCategory.SYSTEM,
                )
                if existing:
                    logger.debug("SDK notification for git pull already exists")
                    return

                # Build description with first few issues
                issue_keys = [i.key for i in all_issues[:3]]
                description = f"{len(all_issues)} missing: {', '.join(issue_keys)}"
                if len(all_issues) > 3:
                    description += "..."

                await service.create_notification(
                    user_id="system",
                    request=NotificationCreate(
                        category=NotificationCategory.SYSTEM,
                        title=title,
                        description=description,
                        metadata={
                            "action": "view_file",
                            "file_path": all_issues[0].file_path,
                            "line_number": all_issues[0].line_number,
                            "issues": [
                                {
                                    "type": i.issue_type,
                                    "key": i.key,
                                    "line": i.line_number,
                                    "file": i.file_path,
                                }
                                for i in all_issues
                            ],
                        },
                    ),
                    for_admins=True,
                    initial_status=NotificationStatus.AWAITING_ACTION,
                )

                logger.info(
                    f"Created SDK issues notification for git pull: "
                    f"{len(all_issues)} issues in {files_with_issues} file(s)"
                )

        except Exception as e:
            logger.warning(f"Failed to scan files for SDK issues after git pull: {e}")

    # GitHub API methods (these use PyGithub, not Git)
    def list_repositories(self, token: str, max_repos: int = 500) -> list[GitHubRepoInfo]:
        """
        List accessible GitHub repositories using token.

        Args:
            token: GitHub personal access token
            max_repos: Maximum number of repositories to return (default: 500)
                       Prevents loading thousands of repos for org accounts

        Returns:
            List of GitHubRepoInfo objects (up to max_repos)
        """
        gh = Github(token, per_page=100)  # Use max per_page for fewer API calls
        repos = []

        try:
            for repo in gh.get_user().get_repos():
                repos.append(GitHubRepoInfo(
                    name=repo.name,
                    full_name=repo.full_name,
                    description=repo.description,
                    url=repo.html_url,
                    private=repo.private
                ))

                # Stop if we hit the limit
                if len(repos) >= max_repos:
                    logger.warning(f"Reached repository limit of {max_repos}. Some repositories may not be shown.")
                    break

        except GithubException as e:
            raise ValueError(f"Failed to list repositories: {e.data.get('message', str(e))}")

        return repos

    def list_branches(self, token: str, repo_full_name: str) -> list[GitHubBranchInfo]:
        """List branches in a repository"""
        gh = Github(token)

        try:
            repo = gh.get_repo(repo_full_name)
            branches = []

            for branch in repo.get_branches():
                branches.append(GitHubBranchInfo(
                    name=branch.name,
                    protected=branch.protected,
                    commit_sha=branch.commit.sha
                ))

            return branches
        except GithubException as e:
            raise ValueError(f"Failed to list branches: {e.data.get('message', str(e))}")

    def create_repository(
        self,
        token: str,
        name: str,
        description: str | None = None,
        private: bool = True,
        organization: str | None = None
    ) -> dict:
        """Create a new GitHub repository"""
        gh = Github(token)

        try:
            if organization:
                org = gh.get_organization(organization)
                repo = org.create_repo(
                    name=name,
                    description=description or "",
                    private=private
                )
            else:
                repo = gh.get_user().create_repo(  # type: ignore[attr-defined]
                    name=name,
                    description=description or "",
                    private=private
                )

            return {
                "full_name": repo.full_name,
                "url": repo.html_url,
                "clone_url": repo.clone_url
            }
        except GithubException as e:
            raise ValueError(f"Failed to create repository: {e.data.get('message', str(e))}")

    async def analyze_workspace(
        self,
        token: str,
        repo_url: str,
        branch: str = "main"
    ) -> dict:
        """
        Analyze workspace to determine if configuration will require replacing files.
        Simplified for replace-only strategy.

        Returns:
            Dictionary with workspace analysis results
        """
        # Count files in workspace (excluding .git)
        file_count = 0
        if self.workspace_path.exists():
            for item in self.workspace_path.rglob("*"):
                if item.is_file() and ".git" not in item.parts:
                    file_count += 1

        # Check if it's already a Git repo
        is_git = self.is_git_repo()
        existing_remote = None

        if is_git:
            try:
                repo = self.get_repo()
                config = repo.get_config()
                remote_url = config.get((b'remote', b'origin'), b'url')
                if remote_url:
                    existing_remote = remote_url.decode('utf-8')
                    # Remove token from URL if present
                    if '@' in existing_remote:
                        existing_remote = existing_remote.split('@', 1)[1]
                        existing_remote = f"https://{existing_remote}"
            except Exception:
                pass

        # Determine workspace status
        if file_count == 0:
            workspace_status = "empty"
        elif not is_git:
            workspace_status = "has_files_no_git"
        elif existing_remote and existing_remote != repo_url:
            workspace_status = "is_different_git_repo"
        else:
            workspace_status = "is_git_repo"

        # Always requires confirmation if there are files
        requires_confirmation = file_count > 0

        return {
            "workspace_status": workspace_status,
            "file_count": file_count,
            "existing_remote": existing_remote,
            "requires_confirmation": requires_confirmation,
            "backup_will_be_created": file_count > 0
        }

    # =========================================================================
    # Platform Entity Serialization (DB -> Files for Git Push)
    # =========================================================================

    async def _serialize_platform_entities_to_workspace(
        self, session: "AsyncSession | None" = None
    ) -> list[str]:
        """
        Serialize platform entities (workflows, forms, apps) from DB to workspace files.

        Used during git push to generate clean files from DB state.
        Workflows have their IDs stripped from decorators.
        Forms and apps are serialized as JSON without environment-specific fields.

        Args:
            session: Optional database session. If not provided, creates a new one.

        Returns:
            List of paths that were serialized
        """
        import json
        from contextlib import asynccontextmanager
        from sqlalchemy import select
        from src.core.database import get_session_factory
        from src.models.orm import Workflow, Form, FormField, Application
        from src.services.decorator_property_service import DecoratorPropertyService

        serialized_paths: list[str] = []
        decorator_service = DecoratorPropertyService()

        @asynccontextmanager
        async def get_db():
            if session is not None:
                yield session
            else:
                session_factory = get_session_factory()
                async with session_factory() as db:
                    yield db

        async with get_db() as db:
            # 1. Serialize workflows
            workflow_stmt = select(Workflow).where(
                Workflow.is_active == True,  # noqa: E712
                Workflow.code.isnot(None),
                Workflow.path.isnot(None),
            )
            workflow_result = await db.execute(workflow_stmt)
            workflows = workflow_result.scalars().all()

            # Group workflows by path - since all workflows in the same file have
            # the same code blob stored, we only need to write each file once
            workflows_by_path: dict[str, Workflow] = {}
            for workflow in workflows:
                if workflow.code and workflow.path:
                    # Use first workflow found for each path (they all have same code)
                    if workflow.path not in workflows_by_path:
                        workflows_by_path[workflow.path] = workflow

            for path, workflow in workflows_by_path.items():
                # Strip ID from decorator for clean git output
                # workflow.code is guaranteed to be non-None due to check on line 2613
                result = decorator_service.strip_ids(workflow.code)  # type: ignore[arg-type]
                clean_code = result.new_content

                # Write to workspace
                file_path = self.workspace_path / path
                file_path.parent.mkdir(parents=True, exist_ok=True)
                file_path.write_text(clean_code, encoding="utf-8")
                serialized_paths.append(path)
                logger.debug(f"Serialized workflow to {path}")

            # 2. Serialize forms
            form_stmt = select(Form).where(
                Form.is_active == True,  # noqa: E712
                Form.file_path.isnot(None),
            )
            form_result = await db.execute(form_stmt)
            forms = form_result.scalars().all()

            for form in forms:
                if not form.file_path:
                    continue

                # Load fields for this form
                fields_stmt = select(FormField).where(
                    FormField.form_id == form.id
                ).order_by(FormField.position)
                fields_result = await db.execute(fields_stmt)
                fields = fields_result.scalars().all()

                # Build form JSON (portable fields only, no env-specific data)
                form_data = {
                    "name": form.name,
                    "description": form.description,
                }

                # Include workflow reference by path+function for portability
                if form.workflow_path and form.workflow_function_name:
                    form_data["workflow_path"] = form.workflow_path
                    form_data["workflow_function_name"] = form.workflow_function_name
                elif form.workflow_id:
                    form_data["workflow_id"] = form.workflow_id

                if form.launch_workflow_id:
                    form_data["launch_workflow_id"] = form.launch_workflow_id

                if form.default_launch_params:
                    form_data["default_launch_params"] = form.default_launch_params

                if form.allowed_query_params:
                    form_data["allowed_query_params"] = form.allowed_query_params

                # Serialize form fields
                if fields:
                    form_data["form_schema"] = {
                        "fields": [
                            self._serialize_form_field(field)
                            for field in fields
                        ]
                    }

                # Write to workspace
                file_path = self.workspace_path / form.file_path
                file_path.parent.mkdir(parents=True, exist_ok=True)
                file_path.write_text(
                    json.dumps(form_data, indent=2, default=str),
                    encoding="utf-8"
                )
                serialized_paths.append(form.file_path)
                logger.debug(f"Serialized form to {form.file_path}")

            # 3. Serialize applications (only those with a published active_version)
            app_stmt = select(Application).where(
                Application.active_version_id.isnot(None),
            )
            app_result = await db.execute(app_stmt)
            apps = app_result.scalars().all()

            for app in apps:
                if not app.active_version_id:
                    continue

                # Derive file path from slug
                file_path_str = f"apps/{app.slug}.app.json"

                # Build app JSON (portable fields only)
                # Note: Full page/component definitions are in separate tables
                # and would need to be serialized separately if needed
                app_data = {
                    "name": app.name,
                    "slug": app.slug,
                    "description": app.description,
                    "icon": app.icon,
                    "navigation": app.navigation,
                    "global_data_sources": app.global_data_sources,
                    "global_variables": app.global_variables,
                }

                # Write to workspace
                file_path = self.workspace_path / file_path_str
                file_path.parent.mkdir(parents=True, exist_ok=True)
                file_path.write_text(
                    json.dumps(app_data, indent=2, default=str),
                    encoding="utf-8"
                )
                serialized_paths.append(file_path_str)
                logger.debug(f"Serialized app to {file_path_str}")

            # 4. Serialize modules from workspace_files.content
            from src.models.orm.workspace import WorkspaceFile

            module_stmt = select(WorkspaceFile).where(
                WorkspaceFile.entity_type == "module",
                WorkspaceFile.is_deleted == False,  # noqa: E712
                WorkspaceFile.content.isnot(None),
            )
            module_result = await db.execute(module_stmt)
            modules = module_result.scalars().all()

            for module in modules:
                if not module.content or not module.path:
                    continue

                # Write module to workspace
                file_path = self.workspace_path / module.path
                file_path.parent.mkdir(parents=True, exist_ok=True)
                file_path.write_text(module.content, encoding="utf-8")
                serialized_paths.append(module.path)
                logger.debug(f"Serialized module to {module.path}")

        logger.info(f"Serialized {len(serialized_paths)} platform entities to workspace")
        return serialized_paths

    def _serialize_form_field(self, field: Any) -> dict:
        """Serialize a FormField ORM object to a dictionary."""
        data: dict[str, Any] = {
            "name": field.name,
            "type": field.type,
            "required": field.required,
        }

        if field.label:
            data["label"] = field.label
        if field.placeholder:
            data["placeholder"] = field.placeholder
        if field.help_text:
            data["help_text"] = field.help_text
        if field.default_value is not None:
            data["default_value"] = field.default_value
        if field.options:
            data["options"] = field.options
        if field.data_provider_id:
            data["data_provider_id"] = str(field.data_provider_id)
        if field.data_provider_inputs:
            data["data_provider_inputs"] = field.data_provider_inputs
        if field.visibility_expression:
            data["visibility_expression"] = field.visibility_expression
        if field.validation:
            data["validation"] = field.validation
        if field.allowed_types:
            data["allowed_types"] = field.allowed_types
        if field.multiple is not None:
            data["multiple"] = field.multiple
        if field.max_size_mb:
            data["max_size_mb"] = field.max_size_mb
        if field.content:
            data["content"] = field.content

        return data

    # =========================================================================
    # Platform Entity Parsing (Files -> DB for Git Pull)
    # =========================================================================

    async def _parse_and_upsert_platform_entities(
        self,
        updated_files: list[str],
        session: "AsyncSession | None" = None,
    ) -> None:
        """
        Parse platform entity files and upsert to database.

        Used during git pull to sync file changes to DB.

        Args:
            updated_files: List of file paths that were updated during pull
            session: Optional database session. If not provided, creates a new one.
        """
        from contextlib import asynccontextmanager
        from src.core.database import get_session_factory
        from src.services.decorator_property_service import DecoratorPropertyService

        decorator_service = DecoratorPropertyService()

        @asynccontextmanager
        async def get_db():
            if session is not None:
                yield session
            else:
                session_factory = get_session_factory()
                async with session_factory() as db:
                    yield db

        async with get_db() as db:
            for file_path in updated_files:
                full_path = self.workspace_path / file_path

                if not full_path.exists():
                    # File was deleted in git - handle soft delete
                    try:
                        await self._handle_deleted_file(db, file_path)
                    except Exception as e:
                        logger.warning(f"Failed to handle deleted file {file_path}: {e}")
                    continue

                try:
                    if file_path.endswith(".py"):
                        await self._parse_python_file(
                            db, file_path, full_path, decorator_service
                        )
                    elif file_path.endswith(".form.json"):
                        await self._parse_form_file(db, file_path, full_path)
                    elif file_path.endswith(".app.json"):
                        await self._parse_app_file(db, file_path, full_path)
                except Exception as e:
                    logger.warning(f"Failed to parse {file_path}: {e}")
                    continue

            # Only commit if we created the session ourselves
            if session is None:
                await db.commit()
        logger.info(f"Parsed and upserted {len(updated_files)} files to database")

    async def _parse_python_file(
        self,
        db: Any,
        file_path: str,
        full_path: Path,
        decorator_service: Any,
    ) -> None:
        """Parse a Python file and upsert workflows or modules to database.

        Uses entity detection to determine if file is a workflow (has @workflow
        or @data_provider decorator) or a module (helper code). Workflows are
        stored in the workflows table, modules in workspace_files.content.

        When a file changes from module to workflow (decorator added) or
        workflow to module (decorator removed), the entity_type is updated
        accordingly.
        """
        from datetime import datetime
        from uuid import uuid4
        import hashlib
        from sqlalchemy.dialects.postgresql import insert
        from src.models.orm import Workflow
        from src.models.orm.workspace import WorkspaceFile
        from src.services.file_storage.entity_detector import detect_python_entity_type

        content = full_path.read_text(encoding="utf-8")
        content_bytes = content.encode("utf-8")

        # Detect entity type - will be "workflow" or "module"
        entity_type = detect_python_entity_type(content_bytes)

        # Calculate content hash
        content_hash = hashlib.sha256(content_bytes).hexdigest()
        now = datetime.utcnow()

        if entity_type == "module":
            # Upsert module to workspace_files.content
            await self._parse_module_file(db, file_path, content, content_hash, now)
            return

        # Otherwise process as workflow (entity_type == "workflow")
        # Read decorators from the file
        decorators = decorator_service.read_decorators(content)

        # Also update workspace_files to track the entity_type as "workflow"
        # This ensures proper routing for file reads
        ws_stmt = insert(WorkspaceFile).values(
            path=file_path,
            content_hash=content_hash,
            size_bytes=len(content_bytes),
            content_type="text/x-python",
            entity_type="workflow",
            is_deleted=False,
            created_at=now,
            updated_at=now,
        ).on_conflict_do_update(
            index_elements=[WorkspaceFile.path],
            set_={
                "content_hash": content_hash,
                "size_bytes": len(content_bytes),
                "entity_type": "workflow",
                "is_deleted": False,
                "updated_at": now,
                "content": None,  # Clear any module content
            },
        )
        await db.execute(ws_stmt)

        for dec in decorators:
            if dec.decorator_type not in ("workflow", "tool", "data_provider"):
                continue

            # Map decorator type to workflow type
            workflow_type = dec.decorator_type

            # Extract properties from decorator
            name = dec.properties.get("name", dec.function_name)
            description = dec.properties.get("description")
            schedule = dec.properties.get("schedule")
            tags = dec.properties.get("tags", [])
            category = dec.properties.get("category", "General")

            # For tools
            tool_description = dec.properties.get("tool_description")

            # For data providers
            cache_ttl = dec.properties.get("cache_ttl_seconds", 300)

            # Calculate code hash
            code_hash = hashlib.sha256(content.encode()).hexdigest()

            now = datetime.utcnow()

            # Upsert workflow - match by path + function_name
            stmt = insert(Workflow).values(
                id=uuid4(),
                name=name,
                function_name=dec.function_name,
                description=description,
                category=category,
                type=workflow_type,
                path=file_path,
                module_path=file_path.replace("/", ".").replace(".py", ""),
                code=content,
                code_hash=code_hash,
                schedule=schedule,
                tags=tags,
                is_active=True,
                last_seen_at=now,
                tool_description=tool_description,
                cache_ttl_seconds=cache_ttl,
                created_at=now,
                updated_at=now,
            ).on_conflict_do_update(
                constraint="workflows_path_function_key",
                set_={
                    "name": name,
                    "description": description,
                    "category": category,
                    "type": workflow_type,
                    "code": content,
                    "code_hash": code_hash,
                    "schedule": schedule,
                    "tags": tags,
                    "is_active": True,
                    "last_seen_at": now,
                    "tool_description": tool_description,
                    "cache_ttl_seconds": cache_ttl,
                    "updated_at": now,
                },
            )
            await db.execute(stmt)
            logger.debug(f"Upserted workflow {dec.function_name} from {file_path}")

    async def _parse_module_file(
        self,
        db: Any,
        file_path: str,
        content: str,
        content_hash: str,
        now: Any,
    ) -> None:
        """Parse and upsert a Python module file to workspace_files.content.

        Modules are Python files without @workflow or @data_provider decorators.
        They are stored in workspace_files.content for virtual import loading.

        Args:
            db: Database session
            file_path: Relative path to the file
            content: File content as string
            content_hash: SHA-256 hash of content
            now: Current timestamp
        """
        from sqlalchemy.dialects.postgresql import insert
        from src.models.orm.workspace import WorkspaceFile
        from src.core.module_cache import set_module

        content_bytes = content.encode("utf-8")

        # Upsert to workspace_files with content
        stmt = insert(WorkspaceFile).values(
            path=file_path,
            content=content,
            content_hash=content_hash,
            size_bytes=len(content_bytes),
            content_type="text/x-python",
            entity_type="module",
            is_deleted=False,
            created_at=now,
            updated_at=now,
        ).on_conflict_do_update(
            index_elements=[WorkspaceFile.path],
            set_={
                "content": content,
                "content_hash": content_hash,
                "size_bytes": len(content_bytes),
                "entity_type": "module",
                "is_deleted": False,
                "updated_at": now,
            },
        )
        await db.execute(stmt)

        # Update Redis cache for virtual imports
        await set_module(file_path, content, content_hash)

        logger.debug(f"Upserted module from git: {file_path}")

    async def _handle_deleted_file(
        self,
        db: Any,
        file_path: str,
    ) -> None:
        """Handle a file that was deleted in git.

        Soft-deletes the workspace_files record and invalidates caches.
        For modules, also clears the Redis cache.

        Args:
            db: Database session
            file_path: Relative path to the deleted file
        """
        from sqlalchemy import select, update
        from src.models.orm.workspace import WorkspaceFile
        from src.core.module_cache import invalidate_module

        # Find the existing record
        stmt = select(WorkspaceFile).where(
            WorkspaceFile.path == file_path,
            WorkspaceFile.is_deleted == False,  # noqa: E712
        )
        result = await db.execute(stmt)
        file_record = result.scalar_one_or_none()

        if not file_record:
            return  # Already doesn't exist or already deleted

        entity_type = file_record.entity_type

        # Soft delete the record and clear content
        update_stmt = (
            update(WorkspaceFile)
            .where(WorkspaceFile.path == file_path)
            .values(
                is_deleted=True,
                content=None,  # Clear content to save space
            )
        )
        await db.execute(update_stmt)

        # Invalidate module cache if it was a module
        if entity_type == "module":
            await invalidate_module(file_path)
            logger.debug(f"Soft-deleted module and invalidated cache: {file_path}")
        else:
            logger.debug(f"Soft-deleted file: {file_path}")

    async def _parse_form_file(
        self,
        db: Any,
        file_path: str,
        full_path: Path,
    ) -> None:
        """Parse a .form.json file and upsert to database."""
        import json
        from datetime import datetime
        from uuid import uuid4, UUID
        from sqlalchemy import select, delete
        from sqlalchemy.dialects.postgresql import insert
        from src.models.orm import Form, FormField

        content = full_path.read_text(encoding="utf-8")
        form_data = json.loads(content)

        name = form_data.get("name")
        if not name:
            logger.warning(f"Form file missing name: {file_path}")
            return

        now = datetime.utcnow()

        # Check if form exists at this path
        existing_stmt = select(Form).where(Form.file_path == file_path)
        existing_result = await db.execute(existing_stmt)
        existing_form = existing_result.scalar_one_or_none()

        if existing_form:
            form_id = existing_form.id
        else:
            form_id = uuid4()

        # Resolve workflow reference
        workflow_id = form_data.get("workflow_id")
        workflow_path = form_data.get("workflow_path")
        workflow_function_name = form_data.get("workflow_function_name")

        # If we have path+function but no ID, resolve it
        if not workflow_id and workflow_path and workflow_function_name:
            from src.models.orm import Workflow
            wf_stmt = select(Workflow.id).where(
                Workflow.path == workflow_path,
                Workflow.function_name == workflow_function_name,
            )
            wf_result = await db.execute(wf_stmt)
            wf_row = wf_result.scalar_one_or_none()
            if wf_row:
                workflow_id = str(wf_row)

        # Upsert form
        stmt = insert(Form).values(
            id=form_id,
            name=name,
            description=form_data.get("description"),
            workflow_id=workflow_id,
            workflow_path=workflow_path,
            workflow_function_name=workflow_function_name,
            launch_workflow_id=form_data.get("launch_workflow_id"),
            default_launch_params=form_data.get("default_launch_params"),
            allowed_query_params=form_data.get("allowed_query_params"),
            file_path=file_path,
            is_active=True,
            last_seen_at=now,
            created_by="git_sync",
            created_at=now,
            updated_at=now,
        ).on_conflict_do_update(
            index_elements=[Form.id],
            set_={
                "name": name,
                "description": form_data.get("description"),
                "workflow_id": workflow_id,
                "workflow_path": workflow_path,
                "workflow_function_name": workflow_function_name,
                "launch_workflow_id": form_data.get("launch_workflow_id"),
                "default_launch_params": form_data.get("default_launch_params"),
                "allowed_query_params": form_data.get("allowed_query_params"),
                "file_path": file_path,
                "is_active": True,
                "last_seen_at": now,
                "updated_at": now,
            },
        )
        await db.execute(stmt)

        # Sync form fields
        form_schema = form_data.get("form_schema")
        if form_schema and isinstance(form_schema, dict):
            fields_data = form_schema.get("fields", [])

            # Delete existing fields
            await db.execute(
                delete(FormField).where(FormField.form_id == form_id)
            )

            # Create new fields
            for position, field in enumerate(fields_data):
                if not isinstance(field, dict) or not field.get("name"):
                    continue

                # Handle data_provider_id
                dp_id = field.get("data_provider_id")
                if dp_id:
                    try:
                        dp_id = UUID(dp_id)
                    except (ValueError, TypeError):
                        dp_id = None

                field_orm = FormField(
                    form_id=form_id,
                    name=field.get("name"),
                    label=field.get("label"),
                    type=field.get("type", "text"),
                    required=field.get("required", False),
                    position=position,
                    placeholder=field.get("placeholder"),
                    help_text=field.get("help_text"),
                    default_value=field.get("default_value"),
                    options=field.get("options"),
                    data_provider_id=dp_id,
                    data_provider_inputs=field.get("data_provider_inputs"),
                    visibility_expression=field.get("visibility_expression"),
                    validation=field.get("validation"),
                    allowed_types=field.get("allowed_types"),
                    multiple=field.get("multiple"),
                    max_size_mb=field.get("max_size_mb"),
                    content=field.get("content"),
                )
                db.add(field_orm)

        logger.debug(f"Upserted form {name} from {file_path}")

    async def _parse_app_file(
        self,
        db: Any,
        file_path: str,
        full_path: Path,
    ) -> None:
        """Parse a .app.json file and upsert to database using new versioning system."""
        import json
        from sqlalchemy import select
        from src.models.orm import Application
        from src.services.app_builder_service import AppBuilderService

        content = full_path.read_text(encoding="utf-8")
        app_data = json.loads(content)

        name = app_data.get("name")
        slug = app_data.get("slug")
        if not name or not slug:
            logger.warning(f"App file missing name or slug: {file_path}")
            return

        # App files can have either 'definition' (legacy) or 'pages' (new format)
        pages = app_data.get("pages", [])
        if not pages:
            # Try legacy format
            definition = app_data.get("definition")
            if definition:
                # Convert legacy definition to pages format
                pages = definition.get("pages", [])

        if not pages:
            logger.warning(f"App file missing pages: {file_path}")
            return

        # Check if app exists with this slug
        existing_stmt = select(Application).where(Application.slug == slug)
        existing_result = await db.execute(existing_stmt)
        existing_app = existing_result.scalar_one_or_none()

        if existing_app:
            # Update existing app using import (which recreates pages)
            service = AppBuilderService(db)
            await service.import_application(
                data={
                    "name": name,
                    "slug": slug,
                    "description": app_data.get("description"),
                    "icon": app_data.get("icon"),
                    "navigation": app_data.get("navigation", {}),
                    "globalDataSources": app_data.get("globalDataSources", []),
                    "globalVariables": app_data.get("globalVariables", {}),
                    "permissions": app_data.get("permissions", {}),
                    "pages": pages,
                },
                organization_id=None,  # Global apps
                created_by="git_sync",
            )
            logger.debug(f"Updated app {name} from {file_path}")
        else:
            # Create new app using import
            service = AppBuilderService(db)
            await service.import_application(
                data={
                    "name": name,
                    "slug": slug,
                    "description": app_data.get("description"),
                    "icon": app_data.get("icon"),
                    "navigation": app_data.get("navigation", {}),
                    "globalDataSources": app_data.get("globalDataSources", []),
                    "globalVariables": app_data.get("globalVariables", {}),
                    "permissions": app_data.get("permissions", {}),
                    "pages": pages,
                },
                organization_id=None,  # Global apps
                created_by="git_sync",
            )
            logger.debug(f"Created app {name} from {file_path}")
