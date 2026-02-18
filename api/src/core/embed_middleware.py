"""
Embed Token Scope Middleware

Restricts embed tokens to only the API endpoints needed for rendering
an embedded app. Embed tokens are NOT superusers and should only access
app rendering, workflow execution, and related endpoints.

Also enforces execution scoping: embed tokens can only access executions
they created (tracked via Redis using the token's jti).
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

    # Form loading and execution
    r"^/api/forms/[^/]+$",              # GET /api/forms/{form_id}
    r"^/api/forms/[^/]+/execute$",      # POST /api/forms/{form_id}/execute
    r"^/api/forms/[^/]+/startup$",      # POST /api/forms/{form_id}/startup
    r"^/api/forms/[^/]+/upload$",       # POST /api/forms/{form_id}/upload
]

_COMPILED_PATTERNS = [re.compile(p) for p in EMBED_ALLOWED_PATTERNS]

# Pattern to extract execution_id from /api/executions/{id}... paths
_EXECUTION_PATH_RE = re.compile(r"^/api/executions/([0-9a-f-]{36})")


def _get_embed_payload(request: Request) -> dict | None:
    """Return the decoded JWT payload if this is an embed token, else None."""
    auth_header = request.headers.get("authorization", "")
    if not auth_header.lower().startswith("bearer "):
        return None

    token = auth_header[7:]  # Strip "Bearer "
    payload = decode_token(token)
    if payload is None:
        return None

    if payload.get("embed", False) is not True:
        return None

    return payload


def _path_allowed(path: str) -> bool:
    """Check if the path is in the embed allowlist."""
    return any(pattern.match(path) for pattern in _COMPILED_PATTERNS)


class EmbedScopeMiddleware(BaseHTTPMiddleware):
    """Restrict embed tokens to app-rendering endpoints only."""

    async def dispatch(self, request: Request, call_next):
        # Only check requests with Bearer tokens that have embed=true
        payload = _get_embed_payload(request)
        if payload is None:
            return await call_next(request)

        if not _path_allowed(request.url.path):
            logger.warning(
                f"Embed token denied access to {request.method} {request.url.path}"
            )
            return JSONResponse(
                status_code=403,
                content={"detail": "Embed tokens cannot access this endpoint"},
            )

        # Enforce execution scoping: embed tokens can only access their own executions
        match = _EXECUTION_PATH_RE.match(request.url.path)
        if match:
            execution_id = match.group(1)
            jti = payload.get("jti")
            if not jti:
                return JSONResponse(
                    status_code=403,
                    content={"detail": "Embed token missing session identifier"},
                )

            from src.core.cache.keys import embed_execution_key
            from src.core.cache.redis_client import get_redis

            async with get_redis() as r:
                exists = await r.exists(embed_execution_key(jti, execution_id))

            if not exists:
                return JSONResponse(
                    status_code=403,
                    content={"detail": "Access denied to this execution"},
                )

        return await call_next(request)
