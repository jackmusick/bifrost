"""
GitHub Integration Router

Git/GitHub integration for workspace sync.
Provides endpoints for connecting to repos, pulling, pushing, and syncing.
"""

import logging
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query, status

from src.models.models import (
    ValidateTokenRequest,
    DetectedRepoInfo,
    GitHubConfigRequest,
    GitHubConfigResponse,
    GitHubReposResponse,
    GitHubBranchesResponse,
    PullFromGitHubRequest,
    PullFromGitHubResponse,
    PushToGitHubRequest,
    PushToGitHubResponse,
    GitRefreshStatusResponse,
    CommitHistoryResponse,
    DiscardUnpushedCommitsResponse,
    DiscardCommitRequest,
    WorkspaceAnalysisResponse,
    CreateRepoRequest,
    CreateRepoResponse,
)
from src.services.git_integration import GitIntegrationService
from src.core.auth import Context, CurrentSuperuser

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/github", tags=["GitHub"])


# =============================================================================
# Helper Functions
# =============================================================================


def get_git_service() -> GitIntegrationService:
    """Get or create git integration service."""
    return GitIntegrationService()


# =============================================================================
# HTTP Endpoints
# =============================================================================


@router.get(
    "/status",
    response_model=GitRefreshStatusResponse,
    summary="Get GitHub sync status",
    description="Get current GitHub repository connection and sync status",
)
async def get_github_status(
    ctx: Context,
    user: CurrentSuperuser,
) -> GitRefreshStatusResponse:
    """
    Get GitHub sync status.

    Returns:
        Current sync status and repository information
    """
    try:
        git_service = get_git_service()

        # Use get_repo_info to get repository status
        status_dict = await git_service.get_repo_info(ctx, fetch=False)

        logger.info(f"GitHub status retrieved")

        return GitRefreshStatusResponse(**status_dict)

    except Exception as e:
        logger.error(f"Error getting GitHub status: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get GitHub status",
        )


@router.post(
    "/refresh",
    response_model=GitRefreshStatusResponse,
    summary="Refresh Git status",
    description="Get complete Git status including local changes, conflicts, and commit history",
)
async def refresh_github_status(
    ctx: Context,
    user: CurrentSuperuser,
) -> GitRefreshStatusResponse:
    """
    Refresh Git status.

    Returns complete status including changed files, conflicts, ahead/behind counts,
    and commit history. Does not fetch from remote by default (fast operation).

    Returns:
        Complete Git status response
    """
    try:
        git_service = get_git_service()

        # Call refresh_status directly to get complete status including changed files
        status_dict = await git_service.refresh_status(ctx, fetch=False)

        logger.info("GitHub status refreshed")

        return GitRefreshStatusResponse(**status_dict)

    except Exception as e:
        logger.error(f"Error refreshing GitHub status: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to refresh GitHub status",
        )


@router.post(
    "/pull",
    response_model=PullFromGitHubResponse,
    summary="Pull from GitHub",
    description="Pull latest changes from the connected GitHub repository",
)
async def pull_from_github(
    ctx: Context,
    user: CurrentSuperuser,
    request: PullFromGitHubRequest | None = None,
) -> PullFromGitHubResponse:
    """
    Pull latest changes from GitHub.

    Returns:
        Pull response with pull status and any conflicts
    """
    try:
        git_service = get_git_service()

        # Pull from repository - pull() returns a dict with result info
        connection_id = request.connection_id if request else None
        result = await git_service.pull(ctx, connection_id)

        logger.info(f"Pulled from GitHub")

        return PullFromGitHubResponse(**result)

    except Exception as e:
        logger.error(f"Error pulling from GitHub: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to pull from GitHub",
        )


@router.post(
    "/push",
    response_model=PushToGitHubResponse,
    summary="Push to GitHub",
    description="Push local changes to the connected GitHub repository",
)
async def push_to_github(
    ctx: Context,
    user: CurrentSuperuser,
    request: PushToGitHubRequest,
) -> PushToGitHubResponse:
    """
    Push local changes to GitHub.

    Args:
        request: Commit message and author information

    Returns:
        Push response with confirmation
    """
    try:
        git_service = get_git_service()

        # Commit and push in one operation
        result = await git_service.commit_and_push(
            ctx,
            message=request.message or "Updated from Bifrost",
            connection_id=None
        )

        return PushToGitHubResponse(
            success=result.get("success", True),
            error=result.get("error")
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Error pushing to GitHub: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to push to GitHub",
        )


@router.get(
    "/changes",
    response_model=GitRefreshStatusResponse,
    summary="Get local changes",
    description="List local changes not yet pushed to GitHub",
)
async def get_changes(
    ctx: Context,
    user: CurrentSuperuser,
) -> GitRefreshStatusResponse:
    """
    Get list of local changes.

    Returns:
        Local file changes not yet pushed
    """
    try:
        git_service = get_git_service()

        # Use get_repo_info to get complete status including changes
        status_dict = await git_service.get_repo_info(ctx, fetch=False)

        logger.info(f"Retrieved local changes")

        return GitRefreshStatusResponse(**status_dict)

    except Exception as e:
        logger.error(f"Error getting changes: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get changes",
        )


@router.post(
    "/init",
    response_model=GitRefreshStatusResponse,
    summary="Initialize Git repository",
    description="Initialize workspace as a Git repository with remote (stub)",
)
async def init_repo(
    request: GitHubConfigRequest,
    ctx: Context,
    user: CurrentSuperuser,
) -> GitRefreshStatusResponse:
    """
    Initialize the workspace as a Git repository.

    This is a stub endpoint for API compatibility.
    """
    try:
        git_service = get_git_service()

        # Get token from request (should be provided)
        if not request.auth_token:
            raise ValueError("auth_token is required to initialize repository")

        # Initialize repository with the provided config
        result = await git_service.initialize_repo(
            token=request.auth_token,
            repo_url=request.repo_url,
            branch=request.branch or "main",
        )

        logger.info(f"Initialized git repository: {request.repo_url}")

        # Get current status after initialization
        status_dict = await git_service.get_repo_info(ctx, fetch=False)
        return GitRefreshStatusResponse(**status_dict)

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Error initializing repo: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to initialize repository",
        )


@router.post(
    "/commit",
    summary="Commit local changes",
    description="Commit staged changes with a message (stub)",
)
async def commit_changes(
    request: PushToGitHubRequest,
    ctx: Context,
    user: CurrentSuperuser,
) -> dict:
    """
    Commit local changes.

    This is a stub endpoint for API compatibility.
    The push endpoint handles commit + push together.
    """
    try:
        git_service = get_git_service()

        # Get changes
        changes = await git_service.get_changes()

        if not changes:
            return {
                "message": "No changes to commit",
                "commit_hash": None,
            }

        # Commit the changes
        result = await git_service.commit(message=request.message or "Update from Bifrost")

        logger.info(f"Committed {len(changes)} changes")

        return result

    except Exception as e:
        logger.error(f"Error committing changes: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to commit changes",
        )


@router.get(
    "/commits",
    response_model=CommitHistoryResponse,
    summary="Get commit history",
    description="Get commit history with pagination",
)
async def get_commits(
    ctx: Context,
    user: CurrentSuperuser,
    limit: int = Query(20, description="Number of commits to return"),
    offset: int = Query(0, description="Offset for pagination"),
) -> CommitHistoryResponse:
    """
    Get commit history with pagination support.

    Returns commit history with pushed/unpushed status and pagination info.
    """
    try:
        git_service = get_git_service()

        result = await git_service.get_commit_history(
            limit=limit,
            offset=offset
        )

        return CommitHistoryResponse(**result)

    except Exception as e:
        logger.error(f"Error getting commits: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get commit history",
        )


@router.get(
    "/conflicts",
    summary="Get merge conflicts",
    description="List files with merge conflicts (stub)",
)
async def get_conflicts(
    ctx: Context,
    user: CurrentSuperuser,
) -> dict:
    """
    Get files with merge conflicts.

    This is a stub endpoint for API compatibility.
    """
    try:
        git_service = get_git_service()

        conflicts = await git_service.get_conflicts()

        return {
            "conflicts": conflicts,
            "count": len(conflicts),
        }

    except Exception as e:
        logger.error(f"Error getting conflicts: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get conflicts",
        )


@router.post(
    "/abort-merge",
    summary="Abort merge",
    description="Abort current merge operation (stub)",
)
async def abort_merge(
    ctx: Context,
    user: CurrentSuperuser,
) -> dict:
    """
    Abort a merge operation.

    This is a stub endpoint for API compatibility.
    """
    try:
        git_service = get_git_service()

        await git_service.abort_merge()

        logger.info("Aborted merge operation")

        return {
            "message": "Merge aborted successfully",
            "status": "success",
        }

    except Exception as e:
        logger.error(f"Error aborting merge: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to abort merge",
        )


@router.post(
    "/discard-unpushed",
    response_model=DiscardUnpushedCommitsResponse,
    summary="Discard unpushed commits",
    description="Discard all unpushed commits and reset to remote",
)
async def discard_unpushed_commits(
    ctx: Context,
    user: CurrentSuperuser,
) -> DiscardUnpushedCommitsResponse:
    """
    Discard all unpushed commits.

    Resets the local branch to match the remote tracking branch,
    discarding any local commits that haven't been pushed.

    Returns:
        Response with list of discarded commits
    """
    try:
        git_service = get_git_service()

        result = await git_service.discard_unpushed_commits(ctx)

        logger.info(f"Discarded {len(result.get('discarded_commits', []))} unpushed commits")

        return DiscardUnpushedCommitsResponse(**result)

    except Exception as e:
        logger.error(f"Error discarding unpushed commits: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to discard unpushed commits",
        )


@router.post(
    "/discard-commit",
    response_model=DiscardUnpushedCommitsResponse,
    summary="Discard specific commit",
    description="Discard a specific commit and all newer commits",
)
async def discard_commit(
    ctx: Context,
    user: CurrentSuperuser,
    request: DiscardCommitRequest,
) -> DiscardUnpushedCommitsResponse:
    """
    Discard a specific commit and all newer commits.

    Resets the branch to the parent of the specified commit,
    effectively removing the commit and all commits after it.

    Returns:
        Response with list of discarded commits
    """
    try:
        git_service = get_git_service()

        result = await git_service.discard_commit(request.commit_sha, ctx)

        logger.info(f"Discarded commit {request.commit_sha} and {len(result.get('discarded_commits', []))} commits")

        return DiscardUnpushedCommitsResponse(**result)

    except Exception as e:
        logger.error(f"Error discarding commit: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to discard commit",
        )


# =============================================================================
# GitHub Configuration Endpoints
# =============================================================================


@router.get(
    "/config",
    response_model=GitHubConfigResponse,
    summary="Get GitHub configuration",
    description="Retrieve current GitHub integration configuration",
)
async def get_github_config(
    ctx: Context,
    user: CurrentSuperuser,
) -> GitHubConfigResponse:
    """Get current GitHub configuration."""
    try:
        git_service = get_git_service()

        # Check if configured by trying to get config
        github_config = await git_service._get_github_config(ctx)

        if not github_config:
            # No configuration exists yet
            return GitHubConfigResponse(
                configured=False,
                token_saved=False,
                repo_url=None,
                branch=None,
                backup_path=None
            )

        # Return configuration
        return GitHubConfigResponse(
            configured=True,
            token_saved=True,
            repo_url=github_config.get("repo_url"),
            branch=github_config.get("branch"),
            backup_path=None
        )

    except Exception as e:
        logger.error(f"Failed to get GitHub config: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get GitHub configuration",
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
) -> GitHubReposResponse:
    """Validate GitHub token, save to database, and list repositories."""
    try:
        if not request.token:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="GitHub token required"
            )

        logger.info("Validating GitHub token")

        # Test the token by listing repositories
        git_service = get_git_service()
        repositories = git_service.list_repositories(request.token)

        # Detect existing Git repository configuration
        detected_repo = None
        detected_info = git_service.get_detected_repo_info()

        if detected_info:
            # Verify token has access to the detected repo
            repo_full_name = detected_info["repo_full_name"]
            has_access = any(r.full_name == repo_full_name for r in repositories)

            if has_access:
                detected_repo = DetectedRepoInfo(
                    full_name=repo_full_name,
                    branch=detected_info["branch"]
                )
                logger.info(f"Detected existing repo: {repo_full_name} (branch: {detected_info['branch']})")

                # Save token with detected repo info
                await git_service._save_github_config(
                    context=ctx,
                    repo_url=detected_info["repo_url"],
                    token=request.token,
                    branch=detected_info["branch"],
                    updated_by=user.email
                )
            else:
                logger.warning(f"Detected repo {repo_full_name} but token doesn't have access")
                # Save token without repo info
                await git_service._save_github_config(
                    context=ctx,
                    repo_url="",
                    token=request.token,
                    branch="main",
                    updated_by=user.email
                )
        else:
            # No existing repo detected, save token only
            await git_service._save_github_config(
                context=ctx,
                repo_url="",
                token=request.token,
                branch="main",
                updated_by=user.email
            )

        logger.info("GitHub token validated and saved successfully")

        return GitHubReposResponse(
            repositories=repositories,
            detected_repo=detected_repo
        )

    except Exception as e:
        logger.error(f"Failed to validate GitHub token: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to validate GitHub token: {str(e)}",
        )


@router.post(
    "/configure",
    response_model=GitHubConfigResponse,
    summary="Configure GitHub integration",
    description="Save GitHub repository configuration and initialize sync",
)
async def configure_github(
    request: GitHubConfigRequest,
    ctx: Context,
    user: CurrentSuperuser,
) -> GitHubConfigResponse:
    """Configure GitHub integration."""
    try:
        logger.info(f"Configuring GitHub integration for repo: {request.repo_url}")

        # Get existing config to retrieve token
        git_service = get_git_service()
        existing_config = await git_service._get_github_config(ctx)

        if not existing_config or not existing_config.get("token"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="GitHub token not found. Please validate your token first."
            )

        token = existing_config["token"]

        # First, try to initialize the Git repository
        backup_info = None
        try:
            backup_info = await git_service.initialize_repo(
                token=token,
                repo_url=request.repo_url,
                branch=request.branch or "main"
            )
        except Exception as git_error:
            logger.error(f"Git initialization failed: {git_error}")
            raise

        # Only save configuration if Git initialization succeeded
        await git_service._save_github_config(
            context=ctx,
            repo_url=request.repo_url,
            token=token,
            branch=request.branch or "main",
            updated_by=user.email
        )

        logger.info("GitHub integration configured successfully")

        return GitHubConfigResponse(
            configured=True,
            backup_path=backup_info.get("backup_path") if backup_info else None,
            token_saved=True,
            repo_url=request.repo_url,
            branch=request.branch or "main"
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
) -> GitHubReposResponse:
    """List user's GitHub repositories using saved token."""
    try:
        # Get token from database
        git_service = get_git_service()
        github_config = await git_service._get_github_config(ctx)

        if not github_config or not github_config.get("token"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="GitHub token not found. Please validate your token first."
            )

        repositories = git_service.list_repositories(github_config["token"])

        return GitHubReposResponse(repositories=repositories, detected_repo=None)

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
    repo: str = Query(..., description="Repository full name (owner/repo)"),
) -> GitHubBranchesResponse:
    """List branches in a repository using saved token."""
    try:
        if not repo:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Repository name required"
            )

        # Get token from database
        git_service = get_git_service()
        github_config = await git_service._get_github_config(ctx)

        if not github_config or not github_config.get("token"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="GitHub token not found. Please validate your token first."
            )

        branches = git_service.list_branches(github_config["token"], repo)

        return GitHubBranchesResponse(branches=branches)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to list branches: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list branches",
        )


@router.post(
    "/analyze-workspace",
    response_model=WorkspaceAnalysisResponse,
    summary="Analyze workspace",
    description="Analyze workspace for potential conflicts before configuring GitHub",
)
async def analyze_workspace(
    request: GitHubConfigRequest,
    ctx: Context,
    user: CurrentSuperuser,
) -> WorkspaceAnalysisResponse:
    """Analyze workspace before configuring GitHub."""
    try:
        git_service = get_git_service()
        result = await git_service.analyze_workspace(
            token=request.auth_token,
            repo_url=request.repo_url,
            branch=request.branch
        )

        return WorkspaceAnalysisResponse(**result)

    except Exception as e:
        logger.error(f"Failed to analyze workspace: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to analyze workspace",
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
) -> CreateRepoResponse:
    """Create new GitHub repository."""
    try:
        # Get token from database
        git_service = get_git_service()
        github_config = await git_service._get_github_config(ctx)

        if not github_config or not github_config.get("token"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="GitHub token not found. Please validate your token first."
            )

        result = git_service.create_repository(
            token=github_config["token"],
            name=request.name,
            description=request.description,
            private=request.private,
            organization=request.organization
        )

        return CreateRepoResponse(**result)

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
) -> dict:
    """Disconnect GitHub integration."""
    try:
        git_service = get_git_service()
        await git_service._delete_github_config(ctx)

        logger.info("GitHub integration disconnected")

        return {"success": True, "message": "GitHub integration disconnected"}

    except Exception as e:
        logger.error(f"Failed to disconnect GitHub: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to disconnect GitHub",
        )
