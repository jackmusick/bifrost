"""Contract models for CLI file push/pull operations."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


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


class ManifestImportResponse(BaseModel):
    """Response for manifest import from S3 into DB."""
    applied: bool = False
    dry_run: bool = False
    warnings: list[str] = Field(default_factory=list)
    manifest_files: dict[str, str] = Field(default_factory=dict)
    modified_files: dict[str, str] = Field(default_factory=dict)
    deleted_entities: list[str] = Field(default_factory=list)
    entity_changes: list[dict[str, str]] = Field(default_factory=list)


class WatchSessionRequest(BaseModel):
    """Request to manage a CLI watch session."""
    action: Literal["start", "stop", "heartbeat"]
    prefix: str
