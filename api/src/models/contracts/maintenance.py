"""
Maintenance Models

Pydantic models for workspace maintenance operations.
"""

from datetime import datetime

from pydantic import BaseModel, Field


class MaintenanceStatus(BaseModel):
    """Current maintenance status of the workspace."""

    files_needing_ids: list[str] = Field(
        default_factory=list,
        description="List of Python files with decorators missing IDs",
    )
    total_files: int = Field(
        default=0,
        description="Total number of files in workspace",
    )
    last_reindex: datetime | None = Field(
        default=None,
        description="Timestamp of last reindex operation",
    )


class ReindexRequest(BaseModel):
    """Request to start a workspace reindex operation."""

    inject_ids: bool = Field(
        default=True,
        description="Whether to inject IDs into decorators that don't have them",
    )
    notification_id: str | None = Field(
        default=None,
        description="Optional notification ID to update with progress",
    )


class ReindexProgress(BaseModel):
    """Progress of a running reindex operation."""

    status: str = Field(
        description="Current status: pending, running, completed, failed"
    )
    files_processed: int = Field(
        default=0,
        description="Number of files processed so far",
    )
    total_files: int = Field(
        default=0,
        description="Total number of files to process",
    )
    ids_injected: int = Field(
        default=0,
        description="Number of files that had IDs injected",
    )
    error: str | None = Field(
        default=None,
        description="Error message if status is failed",
    )


class ReindexResponse(BaseModel):
    """Response from starting or completing a reindex operation."""

    status: str = Field(
        description="Operation status: started, completed, failed"
    )
    files_indexed: int = Field(
        default=0,
        description="Number of files indexed",
    )
    files_needing_ids: list[str] = Field(
        default_factory=list,
        description="Files that needed ID injection (for detection mode)",
    )
    ids_injected: int = Field(
        default=0,
        description="Number of files that had IDs injected (for inject mode)",
    )
    message: str | None = Field(
        default=None,
        description="Human-readable status message",
    )


class DocsIndexResponse(BaseModel):
    """Response from documentation indexing operation."""

    status: str = Field(
        description="Operation status: complete, skipped, failed"
    )
    files_indexed: int = Field(
        default=0,
        description="Number of documentation files that were indexed (new or changed)",
    )
    files_unchanged: int = Field(
        default=0,
        description="Number of files skipped because content was unchanged",
    )
    files_deleted: int = Field(
        default=0,
        description="Number of orphaned documents removed",
    )
    duration_ms: int = Field(
        default=0,
        description="Time taken to complete indexing in milliseconds",
    )
    message: str | None = Field(
        default=None,
        description="Human-readable status message or error description",
    )
