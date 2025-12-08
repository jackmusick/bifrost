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
    """User type - Platform admin or organization user"""
    PLATFORM = "PLATFORM"
    ORG = "ORG"


class FormAccessLevel(str, Enum):
    """Form access control levels"""
    PUBLIC = "public"
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
