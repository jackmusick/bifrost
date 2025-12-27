"""
Agent and Chat contract models for Bifrost.
"""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_serializer


from src.models.enums import AgentAccessLevel, AgentChannel, MessageRole


# ==================== TOOL CALL MODELS ====================


class ToolCall(BaseModel):
    """Tool call from assistant message."""
    id: str = Field(..., description="Unique identifier for this tool call")
    name: str = Field(..., description="Name of the tool to call")
    arguments: dict[str, Any] = Field(default_factory=dict, description="Arguments to pass to the tool")


class ToolResult(BaseModel):
    """Result from tool execution."""
    tool_call_id: str = Field(..., description="ID of the tool call this responds to")
    tool_name: str = Field(..., description="Name of the tool that was called")
    result: Any = Field(..., description="Result from tool execution")
    error: str | None = Field(default=None, description="Error message if tool failed")
    duration_ms: int | None = Field(default=None, description="Execution duration in milliseconds")


# ==================== AGENT MODELS ====================


class AgentCreate(BaseModel):
    """Request model for creating an agent."""
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2000)
    system_prompt: str = Field(..., min_length=1, max_length=50000)
    channels: list[AgentChannel] = Field(default_factory=lambda: [AgentChannel.CHAT])
    access_level: AgentAccessLevel = Field(default=AgentAccessLevel.ROLE_BASED)
    organization_id: UUID | None = Field(
        default=None, description="Organization ID (null = global resource)"
    )
    tool_ids: list[str] = Field(default_factory=list, description="List of workflow IDs to use as tools")
    delegated_agent_ids: list[str] = Field(default_factory=list, description="List of agent IDs this agent can delegate to")
    role_ids: list[str] = Field(default_factory=list, description="List of role IDs that can access this agent (for role_based access)")
    knowledge_sources: list[str] = Field(default_factory=list, description="List of knowledge namespaces this agent can search")


class AgentUpdate(BaseModel):
    """Request model for updating an agent."""
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2000)
    system_prompt: str | None = Field(default=None, min_length=1, max_length=50000)
    channels: list[AgentChannel] | None = None
    access_level: AgentAccessLevel | None = None
    organization_id: UUID | None = Field(
        default=None, description="Organization ID (null = global resource)"
    )
    is_active: bool | None = None
    tool_ids: list[str] | None = Field(default=None, description="List of workflow IDs to use as tools")
    delegated_agent_ids: list[str] | None = Field(default=None, description="List of agent IDs this agent can delegate to")
    role_ids: list[str] | None = Field(default=None, description="List of role IDs that can access this agent (for role_based access)")
    knowledge_sources: list[str] | None = Field(default=None, description="List of knowledge namespaces this agent can search")


class AgentPublic(BaseModel):
    """Agent output for API responses."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    description: str | None = None
    system_prompt: str
    channels: list[str]
    access_level: AgentAccessLevel
    organization_id: UUID | None = None
    is_active: bool
    file_path: str | None = None
    created_by: str
    created_at: datetime
    updated_at: datetime
    # Populated from relationships
    tool_ids: list[str] = Field(default_factory=list)
    delegated_agent_ids: list[str] = Field(default_factory=list)
    role_ids: list[str] = Field(default_factory=list)
    knowledge_sources: list[str] = Field(default_factory=list)

    @field_serializer("id", "organization_id")
    def serialize_uuid(self, v: UUID | None) -> str | None:
        return str(v) if v else None

    @field_serializer("created_at", "updated_at")
    def serialize_dt(self, dt: datetime) -> str:
        return dt.isoformat()


class AgentSummary(BaseModel):
    """Lightweight agent summary for listings."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    description: str | None = None
    channels: list[str]
    is_active: bool

    @field_serializer("id")
    def serialize_uuid(self, v: UUID) -> str:
        return str(v)


# ==================== CONVERSATION MODELS ====================


class ConversationCreate(BaseModel):
    """Request model for creating a conversation."""
    agent_id: UUID | None = Field(default=None, description="ID of the agent to chat with (optional for agentless chat)")
    channel: AgentChannel = Field(default=AgentChannel.CHAT)
    title: str | None = Field(default=None, max_length=500)


class ConversationPublic(BaseModel):
    """Conversation output for API responses."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    agent_id: UUID | None = None
    user_id: UUID
    channel: str
    title: str | None = None
    is_active: bool
    created_at: datetime
    updated_at: datetime
    # Computed fields (populated by query)
    message_count: int | None = None
    last_message_at: datetime | None = None
    agent_name: str | None = None

    @field_serializer("id", "user_id")
    def serialize_uuid(self, v: UUID) -> str:
        return str(v)

    @field_serializer("agent_id")
    def serialize_agent_id(self, v: UUID | None) -> str | None:
        return str(v) if v else None

    @field_serializer("created_at", "updated_at", "last_message_at")
    def serialize_dt(self, dt: datetime | None) -> str | None:
        return dt.isoformat() if dt else None


class ConversationSummary(BaseModel):
    """Lightweight conversation summary for sidebar listings."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    agent_id: UUID | None = None
    agent_name: str | None = None
    title: str | None = None
    updated_at: datetime
    last_message_preview: str | None = None

    @field_serializer("id")
    def serialize_uuid(self, v: UUID) -> str:
        return str(v)

    @field_serializer("agent_id")
    def serialize_agent_id(self, v: UUID | None) -> str | None:
        return str(v) if v else None

    @field_serializer("updated_at")
    def serialize_dt(self, dt: datetime) -> str:
        return dt.isoformat()


# ==================== MESSAGE MODELS ====================


class MessagePublic(BaseModel):
    """Message output for API responses."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    conversation_id: UUID
    role: MessageRole
    content: str | None = None
    tool_calls: list[ToolCall] | None = None
    tool_call_id: str | None = None
    tool_name: str | None = None
    execution_id: str | None = Field(default=None, description="Execution ID for tool results (for fetching logs)")
    token_count_input: int | None = None
    token_count_output: int | None = None
    model: str | None = None
    duration_ms: int | None = None
    sequence: int
    created_at: datetime

    @field_serializer("id", "conversation_id")
    def serialize_uuid(self, v: UUID) -> str:
        return str(v)

    @field_serializer("created_at")
    def serialize_dt(self, dt: datetime) -> str:
        return dt.isoformat()


# ==================== CHAT REQUEST/RESPONSE MODELS ====================


class ChatRequest(BaseModel):
    """Request for sending a chat message."""
    message: str = Field(..., min_length=1, max_length=100000)
    stream: bool = Field(default=True, description="Whether to stream the response")


class ChatResponse(BaseModel):
    """Response from chat completion (non-streaming)."""
    message_id: UUID
    content: str
    tool_calls: list[ToolCall] | None = None
    token_count_input: int | None = None
    token_count_output: int | None = None
    duration_ms: int | None = None

    @field_serializer("message_id")
    def serialize_uuid(self, v: UUID) -> str:
        return str(v)


class AgentSwitch(BaseModel):
    """Agent switch event during chat."""
    agent_id: str = Field(..., description="ID of the agent switched to")
    agent_name: str = Field(..., description="Name of the agent switched to")
    reason: str = Field(default="", description="Reason for the switch (e.g., '@mention', 'routed')")


class ToolProgressLog(BaseModel):
    """Log entry for tool execution progress."""
    level: str = Field(..., description="Log level: debug, info, warning, error")
    message: str = Field(..., description="Log message")


class ToolProgress(BaseModel):
    """Tool execution progress update."""
    tool_call_id: str = Field(..., description="ID of the tool call")
    execution_id: str | None = Field(default=None, description="Execution ID for tracking")
    status: str | None = Field(default=None, description="Status: pending, running, success, failed, timeout")
    log: ToolProgressLog | None = Field(default=None, description="Log entry if this is a log update")


class ChatStreamChunk(BaseModel):
    """Streaming chat response chunk."""
    type: str = Field(..., description="Chunk type: delta, tool_call, tool_progress, tool_result, agent_switch, done, error")
    content: str | None = None
    tool_call: ToolCall | None = None
    tool_progress: ToolProgress | None = None
    tool_result: ToolResult | None = None
    agent_switch: AgentSwitch | None = None
    message_id: str | None = None
    execution_id: str | None = Field(default=None, description="Execution ID for tool_call chunks")
    token_count_input: int | None = None
    token_count_output: int | None = None
    duration_ms: int | None = None
    error: str | None = None


# ==================== ROLE ASSIGNMENT MODELS ====================


class RoleAgentsResponse(BaseModel):
    """Response for getting agents assigned to a role."""
    agent_ids: list[str] = Field(default_factory=list)


class AssignAgentsToRoleRequest(BaseModel):
    """Request for assigning agents to a role."""
    agent_ids: list[str] = Field(..., min_length=1)


class AssignToolsToAgentRequest(BaseModel):
    """Request for assigning tools (workflows) to an agent."""
    workflow_ids: list[str] = Field(..., min_length=1)


class AssignDelegationsToAgentRequest(BaseModel):
    """Request for assigning delegation targets to an agent."""
    agent_ids: list[str] = Field(..., min_length=1)
