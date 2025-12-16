"""
SDK contract models for Bifrost (file operations, config, usage scanning).
"""

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


# ==================== SDK OAUTH OPERATIONS ====================


class SDKOAuthGetRequest(BaseModel):
    """Request to get OAuth connection data via SDK."""
    provider: str = Field(..., description="OAuth provider/connection name")
    org_id: str | None = Field(
        default=None, description="Organization ID (optional, uses context default)")

    model_config = ConfigDict(from_attributes=True)


class SDKOAuthGetResponse(BaseModel):
    """OAuth connection data response from SDK."""
    connection_name: str = Field(..., description="Connection/provider name")
    client_id: str = Field(..., description="OAuth client ID")
    client_secret: str | None = Field(None, description="OAuth client secret (decrypted)")
    authorization_url: str | None = Field(None, description="OAuth authorization URL")
    token_url: str | None = Field(None, description="OAuth token URL")
    scopes: list[str] = Field(default_factory=list, description="OAuth scopes")
    access_token: str | None = Field(None, description="Current access token (decrypted)")
    refresh_token: str | None = Field(None, description="Refresh token (decrypted)")
    expires_at: str | None = Field(None, description="Token expiration (ISO format)")

    model_config = ConfigDict(from_attributes=True)


