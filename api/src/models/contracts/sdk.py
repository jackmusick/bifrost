"""
SDK contract models for Bifrost (file operations, config, usage scanning).
"""

from enum import Enum
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    pass


# ==================== SDK FILE OPERATIONS ====================


class SDKFileReadRequest(BaseModel):
    """Request to read a file via SDK."""
    path: str = Field(..., description="Relative path to file")
    location: Literal["temp", "workspace"] = Field(
        default="workspace", description="Storage location")

    model_config = ConfigDict(from_attributes=True)


class SDKFileWriteRequest(BaseModel):
    """Request to write a file via SDK."""
    path: str = Field(..., description="Relative path to file")
    content: str = Field(..., description="File content (text)")
    location: Literal["temp", "workspace"] = Field(
        default="workspace", description="Storage location")

    model_config = ConfigDict(from_attributes=True)


class SDKFileListRequest(BaseModel):
    """Request to list files in a directory via SDK."""
    directory: str = Field(default="", description="Directory path (relative)")
    location: Literal["temp", "workspace"] = Field(
        default="workspace", description="Storage location")

    model_config = ConfigDict(from_attributes=True)


class SDKFileDeleteRequest(BaseModel):
    """Request to delete a file or directory via SDK."""
    path: str = Field(..., description="Path to file or directory")
    location: Literal["temp", "workspace"] = Field(
        default="workspace", description="Storage location")

    model_config = ConfigDict(from_attributes=True)


# ==================== SDK CONFIG OPERATIONS ====================


class SDKConfigGetRequest(BaseModel):
    """Request to get a config value via SDK."""
    key: str = Field(..., description="Configuration key")
    org_id: str | None = Field(
        default=None, description="Organization ID (optional, uses context default)")

    model_config = ConfigDict(from_attributes=True)


class SDKConfigSetRequest(BaseModel):
    """Request to set a config value via SDK."""
    key: str = Field(..., description="Configuration key")
    value: Any = Field(..., description="Configuration value")
    org_id: str | None = Field(
        default=None, description="Organization ID (optional, uses context default)")
    is_secret: bool = Field(
        default=False, description="Whether to encrypt the value")

    model_config = ConfigDict(from_attributes=True)


class SDKConfigListRequest(BaseModel):
    """Request to list config values via SDK."""
    org_id: str | None = Field(
        default=None, description="Organization ID (optional, uses context default)")

    model_config = ConfigDict(from_attributes=True)


class SDKConfigDeleteRequest(BaseModel):
    """Request to delete a config value via SDK."""
    key: str = Field(..., description="Configuration key")
    org_id: str | None = Field(
        default=None, description="Organization ID (optional, uses context default)")

    model_config = ConfigDict(from_attributes=True)


class SDKConfigValue(BaseModel):
    """Config value response from SDK."""
    key: str = Field(..., description="Configuration key")
    value: Any = Field(..., description="Configuration value")
    config_type: str = Field(..., description="Type of the config (string, int, bool, json, secret)")

    model_config = ConfigDict(from_attributes=True)


# ==================== SDK USAGE SCANNING ====================


class SDKUsageType(str, Enum):
    """Type of SDK usage"""
    CONFIG = "config"
    SECRET = "secret"
    OAUTH = "oauth"


class SDKUsageIssue(BaseModel):
    """
    Represents a missing SDK dependency found in a workflow file.

    This is returned when scanning workspace files for config.get(),
    secrets.get(), or oauth.get_token() calls that reference
    non-existent configurations.
    """
    file_path: str = Field(..., description="Relative path to the file in workspace")
    file_name: str = Field(..., description="Name of the file")
    type: SDKUsageType = Field(..., description="Type of SDK call (config, secret, oauth)")
    key: str = Field(..., description="The missing key/provider name")
    line_number: int = Field(..., description="Line number where the call is made")

    model_config = ConfigDict(from_attributes=True)


class WorkspaceScanRequest(BaseModel):
    """Request to scan workspace for SDK usage issues"""
    # No fields needed - scans entire workspace
    pass

    model_config = ConfigDict(from_attributes=True)


class FileScanRequest(BaseModel):
    """Request to scan a single file for SDK usage issues"""
    file_path: str = Field(..., min_length=1, description="Relative path to file in workspace")
    content: str | None = Field(None, description="Optional file content (if not provided, reads from disk)")

    model_config = ConfigDict(from_attributes=True)


# ==================== FORM VALIDATION SCANNING ====================


class FormValidationIssue(BaseModel):
    """
    Represents a validation error found when loading a form definition.

    This is returned when scanning workspace form files (*.form.json, form.json)
    that have schema validation errors preventing them from loading.
    """
    file_path: str = Field(..., description="Relative path to the form file in workspace")
    file_name: str = Field(..., description="Name of the form file")
    form_name: str | None = Field(None, description="Name of the form if parseable")
    error_message: str = Field(..., description="Validation error message")
    field_name: str | None = Field(None, description="Name of the field with the error, if applicable")
    field_index: int | None = Field(None, description="Index of the field with the error, if applicable")

    model_config = ConfigDict(from_attributes=True)


class WorkspaceScanResponse(BaseModel):
    """Response from scanning workspace for SDK usage and form validation issues"""
    issues: list[SDKUsageIssue] = Field(default_factory=list, description="List of SDK usage issues found")
    scanned_files: int = Field(..., description="Number of Python files scanned")
    # Form validation issues (added to existing response for unified scanning)
    form_issues: list[FormValidationIssue] = Field(
        default_factory=list, description="List of form validation issues found")
    scanned_forms: int = Field(default=0, description="Number of form files scanned")
    valid_forms: int = Field(default=0, description="Number of valid forms loaded")

    model_config = ConfigDict(from_attributes=True)


class FormScanResponse(BaseModel):
    """Response from scanning workspace for form validation issues"""
    issues: list[FormValidationIssue] = Field(default_factory=list, description="List of form validation issues found")
    scanned_forms: int = Field(..., description="Number of form files scanned")
    valid_forms: int = Field(..., description="Number of valid forms loaded")

    model_config = ConfigDict(from_attributes=True)
