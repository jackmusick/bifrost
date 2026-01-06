"""
Coding Mode Models

Pydantic models for coding mode communication.

Note: Most chunk-related models (ChatStreamChunk, TodoItem, AskUserQuestion, etc.)
are now defined in src.models.contracts.agents for consistency across all agent types.
This module re-exports them for backward compatibility and contains session-specific models.
"""

from datetime import datetime

from pydantic import BaseModel

from src.models.contracts.agents import (
    AskUserQuestion,
    AskUserQuestionOption,
    ChatStreamChunk,
    TodoItem,
)
from src.models.enums import CodingModePermission

# Re-export for backward compatibility
__all__ = [
    "AskUserQuestion",
    "AskUserQuestionOption",
    "ChatStreamChunk",
    "CodingModeSession",
    "TodoItem",
]


class CodingModeSession(BaseModel):
    """Represents a coding mode session."""

    session_id: str
    user_id: str
    permission_mode: CodingModePermission = CodingModePermission.EXECUTE
    created_at: datetime
    last_activity: datetime
