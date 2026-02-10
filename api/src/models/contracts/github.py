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
    additions: int | None = Field(default=None, description="Number of lines added")
    deletions: int | None = Field(default=None, description="Number of lines deleted")

    model_config = ConfigDict(from_attributes=True)


class ConflictInfo(BaseModel):
    """Information about conflicts in a file (no markers written to disk)"""
    file_path: str = Field(..., description="Relative path to conflicted file")
    current_content: str = Field(..., description="Local version of the file")
    incoming_content: str = Field(..., description="Remote version of the file")
    base_content: str | None = Field(default=None, description="Common ancestor version (if available)")

    model_config = ConfigDict(from_attributes=True)


class ValidateTokenRequest(BaseModel):
    """Request to validate GitHub token"""
    token: str = Field(..., description="GitHub personal access token to validate")

    model_config = ConfigDict(from_attributes=True)


class GitHubConfigRequest(BaseModel):
    """Request to configure GitHub integration - token must already be saved via /validate"""
    repo_url: str = Field(..., min_length=1, description="GitHub repository URL (e.g., https://github.com/user/repo)")
    branch: str = Field(default="main", description="Branch to sync with")

    model_config = ConfigDict(from_attributes=True)


class GitHubConfigResponse(BaseModel):
    """Response after configuring GitHub"""
    configured: bool = Field(..., description="Whether GitHub is fully configured")
    token_saved: bool = Field(default=False, description="Whether a GitHub token has been validated and saved")
    repo_url: str | None = Field(default=None, description="Configured repository URL")
    branch: str | None = Field(default=None, description="Configured branch")
    backup_path: str | None = Field(default=None, description="Path to backup directory if workspace was backed up")

    model_config = ConfigDict(from_attributes=True)


class GitHubRepoInfo(BaseModel):
    """GitHub repository information"""
    name: str = Field(..., description="Repository name (owner/repo)")
    full_name: str = Field(..., description="Full repository name")
    description: str | None = Field(default=None, description="Repository description")
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
    detected_repo: DetectedRepoInfo | None = Field(default=None, description="Auto-detected existing repository")

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
    existing_remote: str | None = Field(default=None, description="URL of existing Git remote (if any)")
    requires_confirmation: bool = Field(..., description="Whether user needs to confirm replacing workspace")
    backup_will_be_created: bool = Field(default=True, description="Indicates a backup will be created before replacing")

    model_config = ConfigDict(from_attributes=True)


class CreateRepoRequest(BaseModel):
    """Request to create a new GitHub repository"""
    name: str = Field(..., min_length=1, description="Repository name")
    description: str | None = Field(default=None, description="Repository description")
    private: bool = Field(default=True, description="Whether repository should be private")
    organization: str | None = Field(default=None, description="Organization name (if creating in an org)")

    model_config = ConfigDict(from_attributes=True)


class GitHubConfigEntity(BaseModel):
    """GitHub integration configuration stored in Config table"""
    status: Literal["disconnected", "token_saved", "configured"] = Field(
        ...,
        description="Integration status: disconnected (inactive), token_saved (validated), configured (ready)"
    )
    token_config_key: str | None = Field(default=None, description="Config key containing the encrypted GitHub token")
    repo_url: str | None = Field(default=None, description="Configured repository URL")
    production_branch: str | None = Field(default=None, description="Production branch to sync with")
    updated_at: datetime | None = Field(default=None, description="Last update timestamp")
    updated_by: str | None = Field(default=None, description="User who last updated configuration")

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
    error: str | None = Field(default=None, description="Error message if fetch failed")

    model_config = ConfigDict(from_attributes=True)


class CommitAndPushRequest(BaseModel):
    """Request to commit and push changes"""
    message: str = Field(..., min_length=1, description="Commit message")

    model_config = ConfigDict(from_attributes=True)


class CommitAndPushResponse(BaseModel):
    """Response after commit and push"""
    success: bool = Field(..., description="Whether operation succeeded")
    commit_sha: str | None = Field(default=None, description="SHA of created commit")
    files_committed: int = Field(..., description="Number of files committed")
    error: str | None = Field(default=None, description="Error message if operation failed")

    model_config = ConfigDict(from_attributes=True)


class PushToGitHubRequest(BaseModel):
    """Request to push to GitHub"""
    message: str | None = Field(default=None, description="Commit message")
    connection_id: str | None = Field(default=None, description="WebPubSub connection ID for streaming logs")

    model_config = ConfigDict(from_attributes=True)


class PushToGitHubResponse(BaseModel):
    """Response after pushing to GitHub"""
    success: bool = Field(..., description="Whether push succeeded")
    error: str | None = Field(default=None, description="Error message if push failed")

    model_config = ConfigDict(from_attributes=True)


class PullFromGitHubRequest(BaseModel):
    """Request to pull from GitHub"""
    connection_id: str | None = Field(default=None, description="WebPubSub connection ID for streaming logs")

    model_config = ConfigDict(from_attributes=True)


class GitHubSyncRequest(BaseModel):
    """Request to sync with GitHub (pull + push)"""
    connection_id: str | None = Field(default=None, description="WebPubSub connection ID for streaming logs")

    model_config = ConfigDict(from_attributes=True)


class GitHubSyncResponse(BaseModel):
    """Response after queueing a git sync job"""
    job_id: str = Field(..., description="Job ID for tracking the sync operation")
    status: str = Field(..., description="Job status (queued, processing, completed, failed)")

    model_config = ConfigDict(from_attributes=True)


class GitHubSetupResponse(BaseModel):
    """Response after configuring GitHub integration"""
    job_id: str | None = Field(default=None, description="Job ID for tracking the setup operation (deprecated)")
    notification_id: str | None = Field(default=None, description="Notification ID for watching progress via WebSocket (deprecated)")
    status: str = Field(default="configured", description="Configuration status")

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
    current_branch: str | None = Field(default=None, description="Current branch name")

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
    last_synced: str | None = Field(default=None, description="ISO timestamp of last successful sync")
    error: str | None = Field(default=None, description="Error message if sync failed")

    model_config = ConfigDict(from_attributes=True)


class DiscardUnpushedCommitsResponse(BaseModel):
    """Response after discarding unpushed commits"""
    success: bool = Field(..., description="Whether discard was successful")
    discarded_commits: list[CommitInfo] = Field(default_factory=list, description="List of commits that were discarded")
    new_head: str | None = Field(default=None, description="New HEAD commit SHA after discard")
    error: str | None = Field(default=None, description="Error message if operation failed")

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
    old_content: str | None = Field(default=None, description="Previous file content (None if new file)")
    new_content: str = Field(..., description="Current file content")
    additions: int = Field(..., description="Number of lines added")
    deletions: int = Field(..., description="Number of lines deleted")

    model_config = ConfigDict(from_attributes=True)


class ResolveConflictRequest(BaseModel):
    """Request to resolve a conflict"""
    file_path: str = Field(..., min_length=1, description="Relative path to conflicted file")
    resolution: Literal["current", "incoming", "both", "manual"] = Field(..., description="How to resolve conflict")
    manual_content: str | None = Field(default=None, description="Manual resolution content (required if resolution='manual')")

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


# ==================== API-BASED SYNC MODELS ====================


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


class SyncConflictInfo(BaseModel):
    """Information about a conflict between local and remote."""
    path: str = Field(..., description="File path with conflict")
    local_content: str | None = Field(default=None, description="Local content")
    remote_content: str | None = Field(default=None, description="Remote content")
    local_sha: str = Field(..., description="SHA of local content")
    remote_sha: str = Field(..., description="SHA of remote content")
    # Entity metadata for UI display (same as SyncAction)
    display_name: str | None = Field(default=None, description="Human-readable entity name")
    entity_type: str | None = Field(default=None, description="Entity type: form, agent, app, app_file, workflow")
    parent_slug: str | None = Field(default=None, description="For app_file: parent app slug")

    model_config = ConfigDict(from_attributes=True)


class SyncContentRequest(BaseModel):
    """Request to fetch content for diff preview."""
    path: str = Field(..., description="File path to fetch content for")
    source: Literal["local", "remote"] = Field(..., description="Which side to fetch")

    model_config = ConfigDict(from_attributes=True)


class SyncContentResponse(BaseModel):
    """Response with file content for diff preview."""
    path: str = Field(..., description="File path")
    content: str | None = Field(default=None, description="File content (null if not found)")

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


class SyncPreviewResponse(BaseModel):
    """Preview of sync operations before execution."""
    to_pull: list[SyncAction] = Field(
        default_factory=list,
        description="Files to pull from GitHub"
    )
    to_push: list[SyncAction] = Field(
        default_factory=list,
        description="Files to push to GitHub"
    )
    conflicts: list[SyncConflictInfo] = Field(
        default_factory=list,
        description="Files with conflicts"
    )
    preflight: PreflightResult = Field(
        default_factory=lambda: PreflightResult(valid=True),
        description="Preflight validation results (syntax, lint, refs, orphans, manifest)"
    )
    is_empty: bool = Field(
        default=False,
        description="True if no changes to sync"
    )

    model_config = ConfigDict(from_attributes=True)


class SyncPreviewJobResponse(BaseModel):
    """Response when sync preview is queued as a background job.

    Note: The API returns a job_id in the response. The client should subscribe
    to WebSocket channel git:{job_id} AFTER receiving the response to receive
    streaming progress and completion messages (git_preview_complete).
    """
    job_id: str = Field(..., description="Job ID for tracking progress via WebSocket")
    status: str = Field(default="queued", description="Status: 'queued'")

    model_config = ConfigDict(from_attributes=True)


class SyncExecuteRequest(BaseModel):
    """Request to execute sync with conflict resolutions.

    Note: The API returns a job_id in the response. The client should subscribe
    to WebSocket channel git:{job_id} AFTER receiving the response to receive
    streaming progress and completion messages.
    """
    conflict_resolutions: dict[str, Literal["keep_local", "keep_remote", "skip"]] = Field(
        default_factory=dict,
        description="Resolution for each conflicted file path. 'skip' excludes the entity from sync."
    )
    confirm_orphans: bool = Field(
        default=False,
        description="User acknowledges orphan workflows"
    )

    model_config = ConfigDict(from_attributes=True)


class SyncExecuteResponse(BaseModel):
    """Result of sync execution (queued job)."""
    success: bool = Field(..., description="Whether job was queued successfully")
    job_id: str | None = Field(default=None, description="Job ID for tracking (when queued)")
    status: str = Field(default="queued", description="Status: 'queued', 'success', 'error'")
    # These fields are populated via WebSocket completion message, not initial response
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


# ==================== ORPHAN MANAGEMENT MODELS ====================


class OrphanedWorkflowInfo(BaseModel):
    """Orphaned workflow with metadata and references."""

    id: str = Field(..., description="Workflow UUID")
    name: str = Field(..., description="Workflow display name")
    function_name: str = Field(..., description="Python function name")
    last_path: str = Field(..., description="Last known file path")
    code: str | None = Field(default=None, description="Stored code snapshot")
    used_by: list[WorkflowReference] = Field(
        default_factory=list,
        description="Entities using this workflow"
    )
    orphaned_at: datetime | None = Field(default=None, description="When workflow became orphaned")

    model_config = ConfigDict(from_attributes=True)


class OrphanedWorkflowsResponse(BaseModel):
    """Response containing list of orphaned workflows."""

    workflows: list[OrphanedWorkflowInfo] = Field(
        default_factory=list,
        description="List of orphaned workflows"
    )

    model_config = ConfigDict(from_attributes=True)


class CompatibleReplacement(BaseModel):
    """Potential replacement for an orphaned workflow."""

    path: str = Field(..., description="File path containing the replacement function")
    function_name: str = Field(..., description="Function name")
    signature: str = Field(..., description="Human-readable function signature")
    compatibility: Literal["exact", "compatible"] = Field(
        ...,
        description="Compatibility level: exact (perfect match) or compatible (can be used)"
    )

    model_config = ConfigDict(from_attributes=True)


class CompatibleReplacementsResponse(BaseModel):
    """Response containing compatible replacements for an orphaned workflow."""

    replacements: list[CompatibleReplacement] = Field(
        default_factory=list,
        description="List of compatible replacement functions"
    )

    model_config = ConfigDict(from_attributes=True)


class ReplaceWorkflowRequest(BaseModel):
    """Request to replace an orphaned workflow with content from existing file."""

    source_path: str = Field(..., min_length=1, description="Path to file containing replacement function")
    function_name: str = Field(..., min_length=1, description="Name of function to use as replacement")

    model_config = ConfigDict(from_attributes=True)


class ReplaceWorkflowResponse(BaseModel):
    """Response after replacing an orphaned workflow."""

    success: bool = Field(..., description="Whether replacement succeeded")
    workflow_id: str = Field(..., description="UUID of the updated workflow")
    new_path: str = Field(..., description="New file path for the workflow")

    model_config = ConfigDict(from_attributes=True)


class RecreateFileResponse(BaseModel):
    """Response after recreating file from orphaned workflow's code."""

    success: bool = Field(..., description="Whether file recreation succeeded")
    workflow_id: str = Field(..., description="UUID of the workflow")
    path: str = Field(..., description="Path where file was recreated")

    model_config = ConfigDict(from_attributes=True)


class DeactivateWorkflowResponse(BaseModel):
    """Response after deactivating an orphaned workflow."""

    success: bool = Field(..., description="Whether deactivation succeeded")
    workflow_id: str = Field(..., description="UUID of the deactivated workflow")
    warning: str | None = Field(
        default=None,
        description="Warning message if workflow is still referenced by other entities"
    )

    model_config = ConfigDict(from_attributes=True)
