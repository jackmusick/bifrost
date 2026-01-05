"""
Enumeration types used across the application.

These match the existing enums in shared/models.py for compatibility.
"""

from enum import Enum


class ExecutionStatus(str, Enum):
    """Workflow execution status"""
    PENDING = "Pending"
    RUNNING = "Running"
    SUCCESS = "Success"
    FAILED = "Failed"
    TIMEOUT = "Timeout"
    COMPLETED_WITH_ERRORS = "CompletedWithErrors"
    CANCELLING = "Cancelling"
    CANCELLED = "Cancelled"


class UserType(str, Enum):
    """User type - Platform admin, organization user, or system account"""
    PLATFORM = "PLATFORM"
    ORG = "ORG"
    SYSTEM = "SYSTEM"  # Hidden service accounts (API key executions)


class FormAccessLevel(str, Enum):
    """Form access control levels"""
    AUTHENTICATED = "authenticated"
    ROLE_BASED = "role_based"


class FormFieldType(str, Enum):
    """Form field types"""
    TEXT = "text"
    EMAIL = "email"
    NUMBER = "number"
    SELECT = "select"
    CHECKBOX = "checkbox"
    TEXTAREA = "textarea"
    RADIO = "radio"
    DATE = "date"
    DATETIME = "datetime"
    MARKDOWN = "markdown"
    HTML = "html"
    FILE = "file"


class ConfigType(str, Enum):
    """Configuration value types"""
    STRING = "string"
    INT = "int"
    BOOL = "bool"
    JSON = "json"
    SECRET = "secret"  # Value is encrypted


class MFAMethodType(str, Enum):
    """Supported MFA method types"""
    TOTP = "totp"
    SMS = "sms"
    EMAIL = "email"
    WEBAUTHN = "webauthn"


class MFAMethodStatus(str, Enum):
    """MFA method enrollment status"""
    PENDING = "pending"
    ACTIVE = "active"
    DISABLED = "disabled"


class GitStatus(str, Enum):
    """Git sync status for workspace files"""
    UNTRACKED = "untracked"
    SYNCED = "synced"
    MODIFIED = "modified"
    DELETED = "deleted"


class AgentAccessLevel(str, Enum):
    """Agent access control levels"""
    AUTHENTICATED = "authenticated"
    ROLE_BASED = "role_based"


class AppAccessLevel(str, Enum):
    """Application access control levels"""
    AUTHENTICATED = "authenticated"
    ROLE_BASED = "role_based"


class MessageRole(str, Enum):
    """Message roles in chat conversations"""
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"


class AgentChannel(str, Enum):
    """Supported agent communication channels"""
    CHAT = "chat"
    VOICE = "voice"
    TEAMS = "teams"
    SLACK = "slack"


class EventSourceType(str, Enum):
    """Event source types"""
    WEBHOOK = "webhook"
    SCHEDULE = "schedule"
    INTERNAL = "internal"


class EventStatus(str, Enum):
    """Event processing status"""
    RECEIVED = "received"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class EventDeliveryStatus(str, Enum):
    """Event delivery status to a workflow"""
    PENDING = "pending"
    QUEUED = "queued"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


class CodingModePermission(str, Enum):
    """
    Permission mode for coding mode sessions (Claude Agent SDK).

    Controls what actions the agent can take:
    - PLAN: Read-only planning mode, no file writes or tool execution
    - EXECUTE: Full execution mode with file writes and tool execution
    """
    PLAN = "plan"
    EXECUTE = "acceptEdits"
