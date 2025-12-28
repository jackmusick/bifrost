"""
MCP Configuration Contracts

Pydantic models for MCP configuration API requests and responses.
"""

from datetime import datetime

from pydantic import BaseModel, Field


class MCPConfigResponse(BaseModel):
    """Response model for MCP configuration (no sensitive data)."""

    enabled: bool = Field(
        description="Whether external MCP access is enabled"
    )
    require_platform_admin: bool = Field(
        description="Whether only platform admins can access MCP"
    )
    allowed_tool_ids: list[str] | None = Field(
        default=None,
        description="List of allowed tool IDs (None = all tools allowed)"
    )
    blocked_tool_ids: list[str] = Field(
        default_factory=list,
        description="List of blocked tool IDs"
    )
    is_configured: bool = Field(
        description="Whether MCP has been explicitly configured"
    )
    configured_at: datetime | None = Field(
        default=None,
        description="When the configuration was last updated"
    )
    configured_by: str | None = Field(
        default=None,
        description="Email of user who last configured"
    )


class MCPConfigRequest(BaseModel):
    """Request model for updating MCP configuration."""

    enabled: bool = Field(
        default=True,
        description="Whether external MCP access is enabled"
    )
    require_platform_admin: bool = Field(
        default=True,
        description="Whether only platform admins can access MCP"
    )
    allowed_tool_ids: list[str] | None = Field(
        default=None,
        description="List of allowed tool IDs (None = all tools allowed)"
    )
    blocked_tool_ids: list[str] = Field(
        default_factory=list,
        description="List of blocked tool IDs"
    )


class MCPToolInfo(BaseModel):
    """Information about an available MCP tool."""

    id: str = Field(description="Tool identifier")
    name: str = Field(description="Tool display name")
    description: str = Field(description="Tool description")
    is_system: bool = Field(
        default=True,
        description="Whether this is a built-in system tool"
    )


class MCPToolsResponse(BaseModel):
    """Response model for listing MCP tools."""

    tools: list[MCPToolInfo] = Field(description="List of available MCP tools")
