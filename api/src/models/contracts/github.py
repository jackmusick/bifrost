"""
GitHub integration contract models for Bifrost.
"""

from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

if TYPE_CHECKING:
    pass


# ==================== GIT & GITHUB MODELS ====================


class GitFileStatus(str, Enum):
    """Git file status"""
    MODIFIED = "M"      # Modified file
    ADDED = "A"         # New file (untracked or staged)
    DELETED = "D"       # Deleted file
    UNTRACKED = "U"     # Untracked file
    CONFLICTED = "C"    # File with merge conflicts


class FileChange(BaseModel):
    """Represents a changed file in Git"""
    path: str = Field(..., description="Relative path from workspace root")
    status: GitFileStatus = Field(..., description="Git status of the file")
    additions: int | None = Field(None, description="Number of lines added")
    deletions: int | None = Field(None, description="Number of lines deleted")

    model_config = ConfigDict(from_attributes=True)


class ConflictInfo(BaseModel):
    """Information about conflicts in a file (no markers written to disk)"""
    file_path: str = Field(..., description="Relative path to conflicted file")
    current_content: str = Field(..., description="Local version of the file")
    incoming_content: str = Field(..., description="Remote version of the file")
    base_content: str | None = Field(None, description="Common ancestor version (if available)")

    model_config = ConfigDict(from_attributes=True)


class ValidateTokenRequest(BaseModel):
    """Request to validate GitHub token"""
    token: str = Field(..., description="GitHub personal access token to validate")

    model_config = ConfigDict(from_attributes=True)


class GitHubConfigRequest(BaseModel):
    """Request to configure GitHub integration - will always replace workspace with remote"""
    repo_url: str = Field(..., min_length=1, description="GitHub repository URL (e.g., https://github.com/user/repo)")
    auth_token: str = Field(..., description="GitHub personal access token")
    branch: str = Field(default="main", description="Branch to sync with")

    model_config = ConfigDict(from_attributes=True)


class GitHubConfigResponse(BaseModel):
    """Response after configuring GitHub"""
    configured: bool = Field(..., description="Whether GitHub is fully configured")
    token_saved: bool = Field(default=False, description="Whether a GitHub token has been validated and saved")
    repo_url: str | None = Field(None, description="Configured repository URL")
    branch: str | None = Field(None, description="Configured branch")
    backup_path: str | None = Field(None, description="Path to backup directory if workspace was backed up")

    model_config = ConfigDict(from_attributes=True)


class GitHubRepoInfo(BaseModel):
    """GitHub repository information"""
    name: str = Field(..., description="Repository name (owner/repo)")
    full_name: str = Field(..., description="Full repository name")
    description: str | None = Field(None, description="Repository description")
    url: str = Field(..., description="Repository URL")
    private: bool = Field(..., description="Whether repository is private")

    model_config = ConfigDict(from_attributes=True)


class DetectedRepoInfo(BaseModel):
    """Information about auto-detected existing repository"""
    full_name: str = Field(..., description="Repository full name (owner/repo)")
    branch: str = Field(..., description="Current branch")

    model_config = ConfigDict(from_attributes=True)


class GitHubReposResponse(BaseModel):
    """Response with list of GitHub repositories"""
    repositories: list[GitHubRepoInfo] = Field(..., description="List of accessible repositories")
    detected_repo: DetectedRepoInfo | None = Field(None, description="Auto-detected existing repository")

    model_config = ConfigDict(from_attributes=True)


class GitHubBranchInfo(BaseModel):
    """GitHub branch information"""
    name: str = Field(..., description="Branch name")
    protected: bool = Field(..., description="Whether branch is protected")
    commit_sha: str = Field(..., description="Latest commit SHA")

    model_config = ConfigDict(from_attributes=True)


class GitHubBranchesResponse(BaseModel):
    """Response with list of branches"""
    branches: list[GitHubBranchInfo] = Field(..., description="List of branches in repository")

    model_config = ConfigDict(from_attributes=True)


class WorkspaceAnalysisResponse(BaseModel):
    """Response with workspace analysis - simplified for replace-only strategy"""
    workspace_status: Literal["empty", "has_files_no_git", "is_git_repo", "is_different_git_repo"] = Field(
        ...,
        description="Current state of the workspace directory"
    )
    file_count: int = Field(..., description="Number of files in workspace (excluding .git)")
    existing_remote: str | None = Field(None, description="URL of existing Git remote (if any)")
    requires_confirmation: bool = Field(..., description="Whether user needs to confirm replacing workspace")
    backup_will_be_created: bool = Field(default=True, description="Indicates a backup will be created before replacing")

    model_config = ConfigDict(from_attributes=True)


class CreateRepoRequest(BaseModel):
    """Request to create a new GitHub repository"""
    name: str = Field(..., min_length=1, description="Repository name")
    description: str | None = Field(None, description="Repository description")
    private: bool = Field(default=True, description="Whether repository should be private")
    organization: str | None = Field(None, description="Organization name (if creating in an org)")

    model_config = ConfigDict(from_attributes=True)


class GitHubConfigEntity(BaseModel):
    """GitHub integration configuration stored in Config table"""
    status: Literal["disconnected", "token_saved", "configured"] = Field(
        ...,
        description="Integration status: disconnected (inactive), token_saved (validated), configured (ready)"
    )
    token_config_key: str | None = Field(None, description="Config key containing the encrypted GitHub token")
    repo_url: str | None = Field(None, description="Configured repository URL")
    production_branch: str | None = Field(None, description="Production branch to sync with")
    updated_at: datetime | None = Field(None, description="Last update timestamp")
    updated_by: str | None = Field(None, description="User who last updated configuration")

    model_config = ConfigDict(from_attributes=True)


class CreateRepoResponse(BaseModel):
    """Response after creating a new repository"""
    full_name: str = Field(..., description="Full repository name (owner/repo)")
    url: str = Field(..., description="Repository URL")
    clone_url: str = Field(..., description="HTTPS clone URL")

    model_config = ConfigDict(from_attributes=True)


class FetchFromGitHubResponse(BaseModel):
    """Response after fetching from remote"""
    success: bool = Field(..., description="Whether fetch was successful")
    commits_ahead: int = Field(default=0, description="Number of local commits ahead of remote")
    commits_behind: int = Field(default=0, description="Number of commits behind remote")
    error: str | None = Field(None, description="Error message if fetch failed")

    model_config = ConfigDict(from_attributes=True)


class CommitAndPushRequest(BaseModel):
    """Request to commit and push changes"""
    message: str = Field(..., min_length=1, description="Commit message")

    model_config = ConfigDict(from_attributes=True)


class CommitAndPushResponse(BaseModel):
    """Response after commit and push"""
    success: bool = Field(..., description="Whether operation succeeded")
    commit_sha: str | None = Field(None, description="SHA of created commit")
    files_committed: int = Field(..., description="Number of files committed")
    error: str | None = Field(None, description="Error message if operation failed")

    model_config = ConfigDict(from_attributes=True)


class PushToGitHubRequest(BaseModel):
    """Request to push to GitHub"""
    message: str | None = Field(None, description="Commit message")
    connection_id: str | None = Field(None, description="WebPubSub connection ID for streaming logs")

    model_config = ConfigDict(from_attributes=True)


class PushToGitHubResponse(BaseModel):
    """Response after pushing to GitHub"""
    success: bool = Field(..., description="Whether push succeeded")
    error: str | None = Field(None, description="Error message if push failed")

    model_config = ConfigDict(from_attributes=True)


class PullFromGitHubRequest(BaseModel):
    """Request to pull from GitHub"""
    connection_id: str | None = Field(None, description="WebPubSub connection ID for streaming logs")

    model_config = ConfigDict(from_attributes=True)


class PullFromGitHubResponse(BaseModel):
    """Response after pulling from GitHub"""
    success: bool = Field(..., description="Whether pull succeeded")
    updated_files: list[str] = Field(default_factory=list, description="List of updated file paths")
    conflicts: list[ConflictInfo] = Field(default_factory=list, description="List of conflicts (if any)")
    error: str | None = Field(None, description="Error message if pull failed")

    model_config = ConfigDict(from_attributes=True)


class GitHubSyncRequest(BaseModel):
    """Request to sync with GitHub (pull + push)"""
    connection_id: str | None = Field(None, description="WebPubSub connection ID for streaming logs")

    model_config = ConfigDict(from_attributes=True)


class GitHubSyncResponse(BaseModel):
    """Response after queueing a git sync job"""
    job_id: str = Field(..., description="Job ID for tracking the sync operation")
    status: str = Field(..., description="Job status (queued, processing, completed, failed)")

    model_config = ConfigDict(from_attributes=True)


class CommitInfo(BaseModel):
    """Information about a single commit"""
    sha: str = Field(..., description="Commit SHA")
    message: str = Field(..., description="Commit message")
    author: str = Field(..., description="Commit author")
    timestamp: str = Field(..., description="ISO 8601 timestamp")
    is_pushed: bool = Field(..., description="Whether commit is pushed to remote")

    model_config = ConfigDict(from_attributes=True)


class GitRefreshStatusResponse(BaseModel):
    """
    Unified response after fetching and getting complete Git status.
    This combines fetch + status + commit history into a single response.
    """
    success: bool = Field(..., description="Whether refresh was successful")
    initialized: bool = Field(..., description="Whether Git repository is initialized")
    configured: bool = Field(..., description="Whether GitHub integration is configured")
    current_branch: str | None = Field(None, description="Current branch name")

    # Local changes
    changed_files: list[FileChange] = Field(default_factory=list, description="List of locally changed files")
    conflicts: list[ConflictInfo] = Field(default_factory=list, description="List of merge conflicts")
    merging: bool = Field(default=False, description="Whether repository is in merge state (MERGE_HEAD exists)")

    # Remote sync status
    commits_ahead: int = Field(default=0, description="Number of local commits ahead of remote (ready to push)")
    commits_behind: int = Field(default=0, description="Number of commits behind remote (ready to pull)")

    # Commit history
    commit_history: list[CommitInfo] = Field(default_factory=list, description="Recent commit history with pushed/unpushed status")

    # Metadata
    last_synced: str = Field(..., description="ISO timestamp of when sync was performed")
    error: str | None = Field(None, description="Error message if sync failed")

    model_config = ConfigDict(from_attributes=True)


class DiscardUnpushedCommitsResponse(BaseModel):
    """Response after discarding unpushed commits"""
    success: bool = Field(..., description="Whether discard was successful")
    discarded_commits: list[CommitInfo] = Field(default_factory=list, description="List of commits that were discarded")
    new_head: str | None = Field(None, description="New HEAD commit SHA after discard")
    error: str | None = Field(None, description="Error message if operation failed")

    model_config = ConfigDict(from_attributes=True)


class DiscardCommitRequest(BaseModel):
    """Request to discard a specific commit and all newer commits"""
    commit_sha: str = Field(..., min_length=1, description="SHA of the commit to discard (this commit and all newer commits will be discarded)")

    model_config = ConfigDict(from_attributes=True)


class FileDiffRequest(BaseModel):
    """Request to get file diff"""
    file_path: str = Field(..., min_length=1, description="Relative path to file")

    model_config = ConfigDict(from_attributes=True)


class FileDiffResponse(BaseModel):
    """Response with file diff information"""
    file_path: str = Field(..., description="Relative path to file")
    old_content: str | None = Field(None, description="Previous file content (None if new file)")
    new_content: str = Field(..., description="Current file content")
    additions: int = Field(..., description="Number of lines added")
    deletions: int = Field(..., description="Number of lines deleted")

    model_config = ConfigDict(from_attributes=True)


class ResolveConflictRequest(BaseModel):
    """Request to resolve a conflict"""
    file_path: str = Field(..., min_length=1, description="Relative path to conflicted file")
    resolution: Literal["current", "incoming", "both", "manual"] = Field(..., description="How to resolve conflict")
    manual_content: str | None = Field(None, description="Manual resolution content (required if resolution='manual')")

    @model_validator(mode='after')
    def validate_manual_content(self):
        if self.resolution == "manual" and not self.manual_content:
            raise ValueError("manual_content is required when resolution is 'manual'")
        return self

    model_config = ConfigDict(from_attributes=True)


class ResolveConflictResponse(BaseModel):
    """Response after resolving conflict"""
    success: bool = Field(..., description="Whether resolution succeeded")
    file_path: str = Field(..., description="Path to resolved file")
    remaining_conflicts: int = Field(..., description="Number of remaining conflicts in file")

    model_config = ConfigDict(from_attributes=True)


class CommitHistoryResponse(BaseModel):
    """Response with commit history and pagination"""
    commits: list[CommitInfo] = Field(default_factory=list, description="List of commits (newest first)")
    total_commits: int = Field(..., description="Total number of commits in the entire history")
    has_more: bool = Field(..., description="Whether there are more commits to load")

    model_config = ConfigDict(from_attributes=True)
