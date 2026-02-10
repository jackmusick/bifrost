"""
GitHub Integration Router

Git/GitHub integration for workspace sync.
Provides endpoints for connecting to repos, syncing, and configuration management.
"""

import logging
import uuid

from fastapi import APIRouter, HTTPException, Query, status

from src.core.auth import Context, CurrentSuperuser
from src.core.database import DbSession
from src.core.pubsub import (
    publish_git_sync_preview_request,
    publish_git_sync_request,
)
from src.models import (
    CommitHistoryResponse,
    CommitInfo,
    CreateRepoRequest,
    CreateRepoResponse,
    GitHubBranchesResponse,
    GitHubBranchInfo,
    GitHubConfigRequest,
    GitHubConfigResponse,
    GitHubRepoInfo,
    GitHubReposResponse,
    GitHubSetupResponse,
    GitRefreshStatusResponse,
    SyncContentRequest,
    SyncContentResponse,
    SyncExecuteRequest,
    SyncExecuteResponse,
    SyncPreviewJobResponse,
    ValidateTokenRequest,
)
from src.services.github_api import GitHubAPIClient, GitHubAPIError
from src.services.github_config import (
    delete_github_config,
    get_github_config,
    save_github_config,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/github", tags=["GitHub"])


# =============================================================================
# Helper Functions
# =============================================================================


def _extract_repo_from_url(repo_url: str) -> str:
    """Extract owner/repo from GitHub URL."""
    if repo_url.startswith("https://github.com/"):
        return repo_url.replace("https://github.com/", "").rstrip(".git")
    return repo_url


# =============================================================================
# GitHub Configuration Endpoints
# =============================================================================


@router.get(
    "/config",
    response_model=GitHubConfigResponse,
    summary="Get GitHub configuration",
    description="Retrieve current GitHub integration configuration",
)
async def get_config_endpoint(
    ctx: Context,
    user: CurrentSuperuser,
    db: DbSession,
) -> GitHubConfigResponse:
    """Get current GitHub configuration."""
    try:
        config = await get_github_config(db, ctx.org_id)

        if not config:
            return GitHubConfigResponse(
                configured=False,
                token_saved=False,
                repo_url=None,
                branch=None,
                backup_path=None,
            )

        return GitHubConfigResponse(
            configured=bool(config.repo_url),
            token_saved=bool(config.token),
            repo_url=config.repo_url,
            branch=config.branch,
            backup_path=None,
        )

    except Exception as e:
        logger.error(f"Failed to get GitHub config: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get GitHub configuration",
        )


@router.get(
    "/status",
    response_model=GitRefreshStatusResponse,
    summary="Get GitHub sync status",
    description="Get current GitHub repository connection and sync status",
)
async def get_github_status(
    ctx: Context,
    user: CurrentSuperuser,
    db: DbSession,
) -> GitRefreshStatusResponse:
    """
    Get current GitHub status for the Source Control panel.

    Returns basic status information about GitHub configuration.
    For detailed sync preview (files to pull/push), use GET /api/github/sync.
    """
    try:
        config = await get_github_config(db, ctx.org_id)

        if not config or not config.token:
            # Not configured
            return GitRefreshStatusResponse(
                success=True,
                initialized=False,
                configured=False,
                current_branch=None,
                changed_files=[],
                conflicts=[],
                merging=False,
                commits_ahead=0,
                commits_behind=0,
                commit_history=[],
                last_synced=None,
                error=None,
            )

        if not config.repo_url:
            # Token saved but repo not configured
            return GitRefreshStatusResponse(
                success=True,
                initialized=False,
                configured=False,
                current_branch=None,
                changed_files=[],
                conflicts=[],
                merging=False,
                commits_ahead=0,
                commits_behind=0,
                commit_history=[],
                last_synced=None,
                error=None,
            )

        # Fully configured
        return GitRefreshStatusResponse(
            success=True,
            initialized=True,
            configured=True,
            current_branch=config.branch,
            changed_files=[],
            conflicts=[],
            merging=False,
            commits_ahead=0,
            commits_behind=0,
            commit_history=[],
            last_synced=config.last_synced_at,
            error=None,
        )

    except Exception as e:
        logger.error(f"Failed to get GitHub status: {e}", exc_info=True)
        return GitRefreshStatusResponse(
            success=False,
            initialized=False,
            configured=False,
            current_branch=None,
            changed_files=[],
            conflicts=[],
            merging=False,
            commits_ahead=0,
            commits_behind=0,
            commit_history=[],
            last_synced=None,
            error=str(e),
        )


@router.post(
    "/validate",
    response_model=GitHubReposResponse,
    summary="Validate GitHub token",
    description="Validate GitHub token and save to database, returns accessible repositories",
)
async def validate_github_token(
    request: ValidateTokenRequest,
    ctx: Context,
    user: CurrentSuperuser,
    db: DbSession,
) -> GitHubReposResponse:
    """Validate GitHub token, save to database, and list repositories."""
    try:
        if not request.token:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="GitHub token required",
            )

        logger.info("Validating GitHub token")

        # Test the token by listing repositories
        client = GitHubAPIClient(request.token)
        repo_list = await client.list_repositories()

        # Convert to GitHubRepoInfo models
        repositories = [
            GitHubRepoInfo(
                name=r["name"],
                full_name=r["full_name"],
                description=r["description"],
                url=r["url"],
                private=r["private"],
            )
            for r in repo_list
        ]

        # Save token to database (repo_url=None indicates not configured yet)
        await save_github_config(
            db=db,
            org_id=ctx.org_id,
            token=request.token,
            repo_url=None,
            branch="main",
            updated_by=user.email,
        )

        logger.info("GitHub token validated and saved successfully")

        return GitHubReposResponse(
            repositories=repositories,
            detected_repo=None,
        )

    except GitHubAPIError as e:
        logger.error(f"GitHub API error validating token: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid GitHub token: {e.message}",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to validate GitHub token: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to validate GitHub token: {str(e)}",
        )


@router.post(
    "/configure",
    response_model=GitHubSetupResponse,
    summary="Configure GitHub integration",
    description="Save GitHub repository configuration. Syncing happens via /sync endpoints.",
)
async def configure_github(
    request: GitHubConfigRequest,
    ctx: Context,
    user: CurrentSuperuser,
    db: DbSession,
) -> GitHubSetupResponse:
    """
    Configure GitHub integration.

    Saves the GitHub repository configuration (repo URL, branch) to the database.
    Use the /sync endpoints to pull/push changes.
    """
    try:
        # Normalize repo_url - accept both full URL and owner/repo format
        repo_url = request.repo_url.strip()
        if not repo_url.startswith("http"):
            repo_url = f"https://github.com/{repo_url}"

        logger.info(f"Configuring GitHub for repo: {repo_url}")

        # Get existing config to retrieve token
        existing_config = await get_github_config(db, ctx.org_id)

        if not existing_config or not existing_config.token:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="GitHub token not found. Please validate your token first.",
            )

        # Save the updated configuration
        await save_github_config(
            db=db,
            org_id=ctx.org_id,
            token=existing_config.token,
            repo_url=repo_url,
            branch=request.branch or "main",
            updated_by=user.email,
        )

        logger.info(f"GitHub configuration saved for repo: {repo_url}")

        return GitHubSetupResponse(
            job_id=None,
            notification_id=None,
            status="configured",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to configure GitHub: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to configure GitHub: {str(e)}",
        )


@router.get(
    "/repositories",
    response_model=GitHubReposResponse,
    summary="List GitHub repositories",
    description="List accessible repositories using the saved GitHub token",
)
async def list_github_repos(
    ctx: Context,
    user: CurrentSuperuser,
    db: DbSession,
) -> GitHubReposResponse:
    """List user's GitHub repositories using saved token."""
    try:
        config = await get_github_config(db, ctx.org_id)

        if not config or not config.token:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="GitHub token not found. Please validate your token first.",
            )

        client = GitHubAPIClient(config.token)
        repo_list = await client.list_repositories()

        repositories = [
            GitHubRepoInfo(
                name=r["name"],
                full_name=r["full_name"],
                description=r["description"],
                url=r["url"],
                private=r["private"],
            )
            for r in repo_list
        ]

        return GitHubReposResponse(repositories=repositories, detected_repo=None)

    except GitHubAPIError as e:
        logger.error(f"GitHub API error listing repositories: {e}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"GitHub API error: {e.message}",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to list repositories: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list repositories",
        )


@router.get(
    "/branches",
    response_model=GitHubBranchesResponse,
    summary="List repository branches",
    description="List branches in a GitHub repository using saved token",
)
async def list_github_branches(
    ctx: Context,
    user: CurrentSuperuser,
    db: DbSession,
    repo: str = Query(..., description="Repository full name (owner/repo)"),
) -> GitHubBranchesResponse:
    """List branches in a repository using saved token."""
    try:
        if not repo:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Repository name required",
            )

        config = await get_github_config(db, ctx.org_id)

        if not config or not config.token:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="GitHub token not found. Please validate your token first.",
            )

        client = GitHubAPIClient(config.token)
        branch_list = await client.list_branches(repo)

        branches = [
            GitHubBranchInfo(
                name=b["name"],
                protected=b["protected"],
                commit_sha=b["commit_sha"],
            )
            for b in branch_list
        ]

        return GitHubBranchesResponse(branches=branches)

    except GitHubAPIError as e:
        logger.error(f"GitHub API error listing branches: {e}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"GitHub API error: {e.message}",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to list branches: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list branches",
        )


@router.post(
    "/create-repository",
    response_model=CreateRepoResponse,
    summary="Create GitHub repository",
    description="Create a new GitHub repository using saved token",
)
async def create_github_repository(
    request: CreateRepoRequest,
    ctx: Context,
    user: CurrentSuperuser,
    db: DbSession,
) -> CreateRepoResponse:
    """Create new GitHub repository."""
    try:
        config = await get_github_config(db, ctx.org_id)

        if not config or not config.token:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="GitHub token not found. Please validate your token first.",
            )

        client = GitHubAPIClient(config.token)
        result = await client.create_repository(
            name=request.name,
            description=request.description,
            private=request.private,
            organization=request.organization,
        )

        return CreateRepoResponse(**result)

    except GitHubAPIError as e:
        logger.error(f"GitHub API error creating repository: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to create repository: {e.message}",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create repository: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create repository",
        )


@router.post(
    "/disconnect",
    summary="Disconnect GitHub integration",
    description="Remove GitHub integration configuration",
)
async def disconnect_github(
    ctx: Context,
    user: CurrentSuperuser,
    db: DbSession,
) -> dict:
    """Disconnect GitHub integration."""
    try:
        await delete_github_config(db, ctx.org_id)

        logger.info("GitHub integration disconnected")

        return {"success": True, "message": "GitHub integration disconnected"}

    except Exception as e:
        logger.error(f"Failed to disconnect GitHub: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to disconnect GitHub",
        )


# =============================================================================
# Commit History Endpoint
# =============================================================================


@router.get(
    "/commits",
    response_model=CommitHistoryResponse,
    summary="Get commit history",
    description="Get commit history with pagination",
)
async def get_commits(
    ctx: Context,
    user: CurrentSuperuser,
    db: DbSession,
    limit: int = Query(20, description="Number of commits to return"),
    offset: int = Query(0, description="Offset for pagination"),
) -> CommitHistoryResponse:
    """
    Get commit history with pagination support.

    Uses GitHub API directly to fetch commits from the configured repository.
    """
    try:
        config = await get_github_config(db, ctx.org_id)

        if not config or not config.token:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="GitHub token not found. Please validate your token first.",
            )

        if not config.repo_url:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="GitHub repository not configured.",
            )

        repo = _extract_repo_from_url(config.repo_url)
        client = GitHubAPIClient(config.token)

        # Calculate pagination - GitHub uses page-based, we expose offset-based
        page = (offset // limit) + 1 if limit > 0 else 1
        per_page = min(limit, 100)  # GitHub max is 100

        github_commits = await client.list_commits(
            repo=repo,
            sha=config.branch,
            per_page=per_page,
            page=page,
        )

        # Map GitHub API response to our CommitInfo model
        commits = [
            CommitInfo(
                sha=c.sha,
                message=c.commit.message.split("\n")[0],  # First line only
                author=c.commit.author.name,
                timestamp=c.commit.author.date,
                is_pushed=True,
            )
            for c in github_commits
        ]

        has_more = len(github_commits) == per_page

        return CommitHistoryResponse(
            commits=commits,
            total_commits=offset + len(commits) + (1 if has_more else 0),
            has_more=has_more,
        )

    except GitHubAPIError as e:
        logger.error(f"GitHub API error getting commits: {e}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"GitHub API error: {e.message}",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting commits: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get commit history",
        )


# =============================================================================
# API-Based Sync Endpoints
# =============================================================================


@router.get(
    "/sync",
    response_model=SyncPreviewJobResponse,
    summary="Queue sync preview job",
    description="Queue a background job to preview sync changes. Subscribe to git:{job_id} WebSocket channel for progress and results.",
)
async def get_sync_preview(
    ctx: Context,
    user: CurrentSuperuser,
    db: DbSession,
) -> SyncPreviewJobResponse:
    """
    Queue a sync preview as a background job.

    Returns immediately with a job_id. The client should subscribe to the
    WebSocket channel git:{job_id} to receive:
    - Progress updates (git_progress messages with phases like 'cloning', 'scanning')
    - Completion with full preview data (git_preview_complete message)

    The preview compares local DB state with remote GitHub state and returns:
    - Files to pull from GitHub
    - Files to push to GitHub
    - Files with conflicts requiring resolution
    - Workflows that will become orphaned
    """
    try:
        config = await get_github_config(db, ctx.org_id)

        if not config or not config.token:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="GitHub token not found. Please validate your token first.",
            )

        if not config.repo_url:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="GitHub repository not configured.",
            )

        # Generate job ID for tracking
        job_id = str(uuid.uuid4())

        # Queue the preview job to the scheduler
        await publish_git_sync_preview_request(
            job_id=job_id,
            org_id=str(ctx.org_id) if ctx.org_id else "",
            user_id=str(user.user_id),
            user_email=user.email,
        )

        return SyncPreviewJobResponse(
            job_id=job_id,
            status="queued",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error queueing sync preview: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to queue sync preview",
        )


@router.post(
    "/sync",
    response_model=SyncExecuteResponse,
    summary="Execute sync",
    description="Queue sync execution with user's conflict resolutions",
)
async def execute_sync(
    request: SyncExecuteRequest,
    ctx: Context,
    user: CurrentSuperuser,
    db: DbSession,
) -> SyncExecuteResponse:
    """
    Queue the sync execution with user's conflict resolutions.

    Publishes a request to Redis pubsub for the scheduler to process.
    Progress is streamed via WebSocket to the git:{job_id} channel.

    Requires:
    - Conflict resolutions for all conflicted files
    - Confirmation if workflows will be orphaned
    """
    try:
        config = await get_github_config(db, ctx.org_id)

        if not config or not config.token:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="GitHub token not found. Please validate your token first.",
            )

        if not config.repo_url:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="GitHub repository not configured.",
            )

        job_id = str(uuid.uuid4())

        logger.info(f"Queueing git sync execute job: {job_id}")

        await publish_git_sync_request(
            job_id=job_id,
            org_id=str(ctx.org_id) if ctx.org_id else "",
            user_id=str(user.user_id),
            user_email=user.email,
            conflict_resolutions=request.conflict_resolutions,
            confirm_orphans=request.confirm_orphans,
        )

        logger.info(f"Git sync execute job queued via Redis pubsub: {job_id}")

        return SyncExecuteResponse(
            success=True,
            job_id=job_id,
            status="queued",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error queueing sync execute: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to queue sync execute: {str(e)}",
        )


@router.post(
    "/sync/content",
    response_model=SyncContentResponse,
    summary="Get content for diff preview",
    description="Fetch local or remote content for a file to display in diff view",
)
async def get_sync_content(
    request: SyncContentRequest,
    ctx: Context,
    user: CurrentSuperuser,
    db: DbSession,
) -> SyncContentResponse:
    """
    Fetch file content for diff preview.

    - source="local": Read from file_index (platform state)
    - source="remote": Read from git repo
    """
    from src.services.file_index_service import FileIndexService
    from src.services.repo_storage import RepoStorage

    try:
        config = await get_github_config(db, ctx.org_id)

        if not config or not config.token:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="GitHub not configured",
            )

        if not config.repo_url:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="GitHub repository not configured",
            )

        if request.source == "local":
            # Read from file_index (platform state)
            file_index = FileIndexService(db, RepoStorage())
            content = await file_index.read(request.path)
        else:
            # Read from git repo via clone
            from src.services.github_sync import GitHubSyncService

            repo_url = config.repo_url
            if not repo_url.endswith(".git"):
                # Build authenticated clone URL
                repo_url = f"https://x-access-token:{config.token}@github.com/{_extract_repo_from_url(repo_url)}.git"

            sync_service = GitHubSyncService(
                db=db,
                repo_url=repo_url,
                branch=config.branch,
            )
            # Use preview to get remote content — it clones and reads
            preview = await sync_service.preview()
            # Find the file in pull actions or conflicts
            content = None
            for conflict in preview.conflicts:
                if conflict.path == request.path:
                    content = conflict.remote_content
                    break

        return SyncContentResponse(path=request.path, content=content)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching sync content: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch content",
        )
