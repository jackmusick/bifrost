"""
Workflow Error Handling
Standardized error types and exception handling for workflows
"""

from typing import Any


class WorkflowError(Exception):
    """Base exception for workflow errors."""

    def __init__(self, error_type: str, message: str, details: dict[str, Any] | None = None):
        self.error_type = error_type
        self.message = message
        self.details = details or {}
        super().__init__(message)

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dict."""
        return {
            "error": self.error_type,
            "message": self.message,
            "details": self.details
        }


class ValidationError(WorkflowError):
    """Raised when input validation fails."""

    def __init__(self, message: str, field: str | None = None):
        super().__init__(
            "ValidationError",
            message,
            {"field": field} if field else None
        )


class IntegrationError(WorkflowError):
    """Raised when external API call fails."""

    def __init__(self, integration: str, message: str, status_code: int | None = None):
        super().__init__(
            "IntegrationError",
            message,
            {"integration": integration, "status_code": status_code} if status_code else {"integration": integration}
        )


class TimeoutError(WorkflowError):
    """Raised when workflow exceeds timeout."""

    def __init__(self, timeout_seconds: int):
        super().__init__(
            "TimeoutError",
            f"Workflow exceeded timeout of {timeout_seconds} seconds",
            {"timeout_seconds": timeout_seconds}
        )


class ConfigurationError(WorkflowError):
    """Raised when organization configuration is missing or invalid."""

    def __init__(self, message: str, config_key: str | None = None):
        super().__init__(
            "ConfigurationError",
            message,
            {"config_key": config_key} if config_key else None
        )


class PermissionError(WorkflowError):
    """Raised when user lacks required permissions."""

    def __init__(self, message: str, required_permission: str | None = None):
        super().__init__(
            "PermissionError",
            message,
            {"required_permission": required_permission} if required_permission else None
        )
