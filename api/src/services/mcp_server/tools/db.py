"""
Database session helper for MCP system tools.

Reuses the executor's session when available (delegation context),
falls back to get_db_context() for standalone MCP server usage.
"""

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

if TYPE_CHECKING:
    from src.services.mcp_server.server import MCPContext


@asynccontextmanager
async def get_tool_db(context: "MCPContext") -> AsyncGenerator[AsyncSession, None]:
    """
    Get a database session for tool execution.

    If the context carries an existing session (executor context),
    yield it directly without managing its lifecycle.
    Otherwise, create a fresh session via get_db_context().
    """
    if context.session is not None:
        yield context.session
    else:
        from src.core.database import get_db_context

        async with get_db_context() as db:
            yield db
