"""
ASGI middleware that extracts agent_id from /mcp/{agent_id} paths.

Intercepts requests to /mcp/{uuid}, stores the agent_id in the ASGI scope
as scope["mcp_agent_id"], and rewrites the path to /mcp so FastMCP's
route matcher works. Non-UUID paths (including /mcp/callback) pass through.
"""

import re

# Match /mcp/{uuid} but not /mcp/callback or other non-UUID suffixes
_AGENT_PATH_RE = re.compile(
    r"^(/mcp)/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})(/.*)?$",
    re.IGNORECASE,
)


class AgentScopeMCPMiddleware:
    """ASGI middleware that rewrites /mcp/{agent_id} to /mcp."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] in ("http", "websocket"):
            path = scope.get("path", "")
            match = _AGENT_PATH_RE.match(path)
            if match:
                scope["mcp_agent_id"] = match.group(2)
                # Rewrite path to /mcp (preserving any trailing path like /mcp/sse)
                scope["path"] = match.group(1) + (match.group(3) or "")
        await self.app(scope, receive, send)
