"""Contract models for CLI file push/pull operations."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class FilePushRequest(BaseModel):
    """Request to push multiple files to _repo/."""
    files: dict[str, str] = Field(..., description="Map of repo_path to base64-encoded content")
    delete_missing_prefix: str | None = Field(
        default=None,
        description="If set, delete files under this prefix not in the push batch",
    )


class FilePushResponse(BaseModel):
    """Response for file push."""
    created: int = 0
    updated: int = 0
    deleted: int = 0
    unchanged: int = 0
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    manifest_applied: bool = False
    manifest_files: dict[str, str] = Field(default_factory=dict)
    modified_files: dict[str, str] = Field(default_factory=dict)


class FilePullRequest(BaseModel):
    """Request to pull files from server."""
    prefix: str = Field(..., description="Repo prefix to pull from")
    local_hashes: dict[str, str] = Field(
        default_factory=dict, description="Map of path to sha256 hash"
    )


class FilePullResponse(BaseModel):
    """Response for file pull."""
    files: dict[str, str] = Field(
        default_factory=dict,
        description="Map of path to base64-encoded content for changed files",
    )
    deleted: list[str] = Field(
        default_factory=list,
        description="Paths that exist locally but not on server",
    )
    manifest_files: dict[str, str] = Field(
        default_factory=dict,
        description="Regenerated .bifrost/*.yaml",
    )


class WatchSessionRequest(BaseModel):
    """Request to manage a CLI watch session."""
    action: Literal["start", "stop", "heartbeat"]
    prefix: str
