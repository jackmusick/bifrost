"""
Embed Token Scope Middleware

Restricts embed tokens to only the API endpoints needed for rendering
an embedded app. Embed tokens are NOT superusers and should only access
app rendering, workflow execution, and related endpoints.
"""

import logging
import re

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from src.core.security import decode_token

logger = logging.getLogger(__name__)

# Paths that embed tokens are allowed to access.
# Uses regex patterns to support path parameters.
EMBED_ALLOWED_PATTERNS = [
    # App loading and rendering
    r"^/api/applications/[^/]+$",          # GET /api/applications/{slug}
    r"^/api/applications/[^/]+/render$",   # GET /api/applications/{app_id}/render
    r"^/api/applications/[^/]+/files",     # GET /api/applications/{app_id}/files/...
    r"^/api/applications/[^/]+/dependencies$",  # GET /api/applications/{app_id}/dependencies

    # Workflow execution
    r"^/api/workflows/execute$",           # POST /api/workflows/execute
    r"^/api/executions/",                  # GET /api/executions/{id}...

    # Auth status (SPA checks this on load)
    r"^/auth/status$",

    # Branding (SPA loads this for theming)
    r"^/api/branding$",

    # WebSocket for execution streaming
    r"^/ws",

    # Health check
    r"^/health$",
]

_COMPILED_PATTERNS = [re.compile(p) for p in EMBED_ALLOWED_PATTERNS]


def _is_embed_token(request: Request) -> bool:
    """Check if the request uses an embed token (Bearer with embed=true claim)."""
    auth_header = request.headers.get("authorization", "")
    if not auth_header.lower().startswith("bearer "):
        return False

    token = auth_header[7:]  # Strip "Bearer "
    payload = decode_token(token)
    if payload is None:
        return False

    return payload.get("embed", False) is True


def _path_allowed(path: str) -> bool:
    """Check if the path is in the embed allowlist."""
    return any(pattern.match(path) for pattern in _COMPILED_PATTERNS)


class EmbedScopeMiddleware(BaseHTTPMiddleware):
    """Restrict embed tokens to app-rendering endpoints only."""

    async def dispatch(self, request: Request, call_next):
        # Only check requests with Bearer tokens that have embed=true
        if not _is_embed_token(request):
            return await call_next(request)

        if not _path_allowed(request.url.path):
            logger.warning(
                f"Embed token denied access to {request.method} {request.url.path}"
            )
            return JSONResponse(
                status_code=403,
                content={"detail": "Embed tokens cannot access this endpoint"},
            )

        return await call_next(request)
