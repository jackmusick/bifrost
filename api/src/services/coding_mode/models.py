"""
Coding Mode Models

Pydantic models for coding mode communication.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from src.models.contracts.agents import ToolCall, ToolProgress, ToolResult


class CodingModeSession(BaseModel):
    """Represents a coding mode session."""

    session_id: str
    user_id: str
    created_at: datetime
    last_activity: datetime


class CodingModeChunk(BaseModel):
    """
    Streaming chunk from coding mode.

    Designed to be compatible with existing ChatStreamChunk format
    so frontend can reuse existing components.
    """

    type: Literal[
        "session_start",
        "delta",
        "tool_call",
        "tool_progress",
        "tool_result",
        "done",
        "error",
    ]

    # Session info (for session_start)
    session_id: str | None = None

    # Text content (for delta)
    content: str | None = None

    # Nested objects to match ChatStreamChunk format (frontend expects these)
    tool_call: ToolCall | None = None
    tool_progress: ToolProgress | None = None
    tool_result: ToolResult | None = None
    execution_id: str | None = None

    # Error info (for error)
    error_message: str | None = None

    # Usage metrics (for done)
    input_tokens: int | None = None
    output_tokens: int | None = None
    cost_usd: float | None = None
    duration_ms: int | None = None
