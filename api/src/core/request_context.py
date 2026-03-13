"""
Request-scoped context variables for user attribution and session tracking.

These ContextVars are set by middleware and read by ORM hooks / service code
to attribute changes to the requesting user without threading params everywhere.
"""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RequestUser:
    """Minimal user identity for attribution."""
    user_id: str
    user_name: str


# Current authenticated user (set by middleware from JWT)
_request_user: ContextVar[RequestUser | None] = ContextVar("_request_user", default=None)

# Watch session ID from X-Bifrost-Watch-Session header (if present)
_request_session_id: ContextVar[str | None] = ContextVar("_request_session_id", default=None)


def get_request_user() -> RequestUser | None:
    """Get the current request's authenticated user."""
    return _request_user.get()


def set_request_user(user: RequestUser | None) -> None:
    """Set the current request's authenticated user."""
    _request_user.set(user)


def get_request_session_id() -> str | None:
    """Get the current request's watch session ID."""
    return _request_session_id.get()


def set_request_session_id(session_id: str | None) -> None:
    """Set the current request's watch session ID."""
    _request_session_id.set(session_id)
