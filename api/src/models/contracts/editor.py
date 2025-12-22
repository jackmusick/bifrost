"""
Code editor contract models for Bifrost.
"""

from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    pass


# ==================== EDITOR MODELS ====================


class FileType(str, Enum):
    """File or folder type"""
    FILE = "file"
    FOLDER = "folder"


class FileMetadata(BaseModel):
    """
    File or folder metadata
    Used in directory listing responses
    """
    path: str = Field(..., description="Relative path from /home/repo")
    name: str = Field(..., description="File or folder name")
    type: FileType = Field(..., description="File or folder")
    size: int | None = Field(default=None, description="Size in bytes (null for folders)")
    extension: str | None = Field(default=None, description="File extension (null for folders)")
    modified: str = Field(..., description="Last modified timestamp (ISO 8601)")
    is_workflow: bool = Field(default=False, description="True if file contains a @workflow decorator")
    is_data_provider: bool = Field(default=False, description="True if file contains a @data_provider decorator")

    model_config = ConfigDict(from_attributes=True)


class FileContentRequest(BaseModel):
    """Request to write file content"""
    path: str = Field(..., description="Relative path from /home/repo")
    content: str = Field(..., description="File content (plain text or base64 encoded)")
    encoding: str = Field(default="utf-8", description="Content encoding (utf-8 or base64)")
    expected_etag: str | None = Field(default=None, description="Expected ETag for conflict detection (optional)")

    model_config = ConfigDict(from_attributes=True)


class FileContentResponse(BaseModel):
    """Response with file content"""
    path: str = Field(..., description="Relative path from /home/repo")
    content: str = Field(..., description="File content")
    encoding: str = Field(..., description="Content encoding")
    size: int = Field(..., description="Content size in bytes")
    etag: str = Field(..., description="ETag for change detection")
    modified: str = Field(..., description="Last modified timestamp (ISO 8601)")
    content_modified: bool = Field(
        default=False,
        description="True if server modified content (e.g., injected IDs). Client should update editor buffer."
    )
    needs_indexing: bool = Field(
        default=False,
        description="True if file has decorators that need ID injection. Client should trigger indexing."
    )

    model_config = ConfigDict(from_attributes=True)


class FileConflictResponse(BaseModel):
    """Response when file write encounters a conflict"""
    reason: Literal["content_changed", "path_not_found"] = Field(..., description="Type of conflict")
    message: str = Field(..., description="Human-readable conflict description")

    model_config = ConfigDict(from_attributes=True)


class SearchRequest(BaseModel):
    """Search query request"""
    query: str = Field(..., min_length=1, description="Search text or regex pattern")
    case_sensitive: bool = Field(default=False, description="Case-sensitive matching")
    is_regex: bool = Field(default=False, description="Treat query as regex")
    include_pattern: str | None = Field(default="**/*", description="Glob pattern for files to search")
    max_results: int = Field(default=1000, ge=1, le=10000, description="Maximum results to return")

    model_config = ConfigDict(from_attributes=True)


class SearchResult(BaseModel):
    """Single search match result"""
    file_path: str = Field(..., description="Relative path to file containing match")
    line: int = Field(..., ge=1, description="Line number (1-indexed)")
    column: int = Field(..., ge=0, description="Column number (0-indexed)")
    match_text: str = Field(..., description="The matched text")
    context_before: str | None = Field(default=None, description="Line before match")
    context_after: str | None = Field(default=None, description="Line after match")

    model_config = ConfigDict(from_attributes=True)


class SearchResponse(BaseModel):
    """Search results response"""
    query: str = Field(..., description="Original search query")
    total_matches: int = Field(..., description="Total matches found")
    files_searched: int = Field(..., description="Number of files searched")
    results: list[SearchResult] = Field(..., description="Array of search results")
    truncated: bool = Field(..., description="Whether results were truncated")
    search_time_ms: int = Field(..., description="Search duration in milliseconds")

    model_config = ConfigDict(from_attributes=True)


class ScriptExecutionRequest(BaseModel):
    """Request model for executing a Python script"""
    code: str = Field(..., description="Python code to execute")
    timeout_seconds: int | None = Field(default=None, description="Optional timeout in seconds")


class ScriptExecutionResponse(BaseModel):
    """Response model for script execution"""
    execution_id: str = Field(..., description="Unique execution identifier")
    status: Literal["Success", "Failed"] = Field(..., description="Execution status")
    output: str = Field(..., description="Combined stdout/stderr output")
    result: dict[str, str] | None = Field(default=None, description="Execution result data")
    error: str | None = Field(default=None, description="Error message if execution failed")
    duration_ms: int = Field(..., description="Execution duration in milliseconds")
    started_at: datetime = Field(..., description="Execution start timestamp")
    completed_at: datetime = Field(..., description="Execution completion timestamp")
