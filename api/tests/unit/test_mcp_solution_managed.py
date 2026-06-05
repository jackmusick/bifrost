"""MCP direct-ORM mutation tools refuse solution-managed entities with the
locked read-only message (criterion 6, MCP surface).

The MCP tools for tables/agents/forms/events mutate the ORM object directly
(e.g. ``table.name = ...``) and rely on the session-wide before_flush backstop
(``install_solution_write_guard``), which fires on AsyncSession flush. The tool's
``except Exception`` wraps the raised ``SolutionManagedWriteError`` — whose
message IS the locked wording — into a clean ``error_result``. So an MCP edit of
a managed entity returns the same read-only message the REST guard returns, not
a generic 500.
"""
from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest

from src.services.solutions.guard import (
    SOLUTION_MANAGED_MESSAGE,
    install_solution_write_guard,
)

pytestmark = pytest.mark.e2e


@pytest.fixture(autouse=True)
def _guard_installed():
    install_solution_write_guard()
    yield


async def _managed_table(db) -> uuid.UUID:
    from src.models.orm.solutions import Solution
    from src.models.orm.tables import Table

    sol = Solution(id=uuid.uuid4(), slug=f"mcp-{uuid.uuid4().hex[:8]}", name="MCP", organization_id=None)
    db.add(sol)
    await db.flush()
    tid = uuid.uuid4()
    db.add(Table(
        id=tid, name=f"t_{uuid.uuid4().hex[:8]}", organization_id=None,
        solution_id=sol.id, schema={"columns": []}, access={"policies": []},
    ))
    await db.flush()
    return tid


async def test_mcp_update_table_refuses_managed(db_session, monkeypatch):
    from contextlib import asynccontextmanager

    from src.services.mcp_server.tools import tables as mcp_tables

    tid = await _managed_table(db_session)

    # Point the MCP tool's db at this test session (it normally opens its own).
    @asynccontextmanager
    async def _fake_tool_db(_context):
        yield db_session

    monkeypatch.setattr(mcp_tables, "get_tool_db", _fake_tool_db)

    context = SimpleNamespace(is_platform_admin=True, org_id=None, user_id=uuid.uuid4())
    result = await mcp_tables.update_table(context, table_id=str(tid), name="hijacked-via-mcp")

    # The tool returns an error result carrying the locked read-only message.
    payload = result.model_dump() if hasattr(result, "model_dump") else result
    text = str(payload)
    assert SOLUTION_MANAGED_MESSAGE in text, text
