"""
Failing-first leak proofs for MCP tools that hand-rolled the org cascade
(EXT-1 adversarial review LEAK #3 and siblings).

MCP authenticates as the user, so list/get tools for execution-resolution
entities (agents, apps, forms, tables) must drop the global tier for an
external, non-bypass principal. Each test injects a mock session via
``context.session`` (get_tool_db yields it directly) and asserts the executed
statement does NOT contain an ``organization_id IS NULL`` arm for externals,
but DOES for a normal org user.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.services.mcp_server.tools import agents as agents_tool
from src.services.mcp_server.tools import apps as apps_tool
from src.services.mcp_server.tools import forms as forms_tool
from src.services.mcp_server.tools import knowledge as knowledge_tool
from src.services.mcp_server.tools import tables as tables_tool


def _ctx(*, is_external, is_platform_admin=False, org_id=...):
    session = AsyncMock()
    session.execute = AsyncMock()
    # default: empty result shapes the tools tolerate
    result = MagicMock()
    result.scalars.return_value.all.return_value = []
    result.scalar_one_or_none = MagicMock(return_value=None)
    result.scalar = MagicMock(return_value=0)
    result.all = MagicMock(return_value=[])
    session.execute.return_value = result
    return SimpleNamespace(
        user_id=uuid4(),
        org_id=uuid4() if org_id is ... else org_id,
        is_platform_admin=is_platform_admin,
        is_external=is_external,
        user_email="x@y.z",
        user_name="X",
        session=session,
        accessible_namespaces=[],
        enabled_system_tools=[],
    )


def _executed_sql(ctx) -> str:
    """Concatenated SQL of every statement the tool executed."""
    out = []
    for call in ctx.session.execute.await_args_list:
        stmt = call.args[0]
        try:
            out.append(str(stmt.compile(compile_kwargs={"literal_binds": True})))
        except Exception:
            out.append(str(stmt))
    return "\n".join(out)


@pytest.mark.asyncio
class TestMCPListToolsExternal:
    async def test_list_tables_external_drops_global(self):
        ctx = _ctx(is_external=True)
        await tables_tool.list_tables(ctx)
        assert "organization_id IS NULL" not in _executed_sql(ctx)

    async def test_list_tables_normal_keeps_global(self):
        ctx = _ctx(is_external=False)
        await tables_tool.list_tables(ctx)
        assert "organization_id IS NULL" in _executed_sql(ctx)

    async def test_list_apps_external_drops_global(self):
        ctx = _ctx(is_external=True)
        await apps_tool.list_apps(ctx)
        assert "organization_id IS NULL" not in _executed_sql(ctx)

    async def test_list_apps_normal_keeps_global(self):
        ctx = _ctx(is_external=False)
        await apps_tool.list_apps(ctx)
        assert "organization_id IS NULL" in _executed_sql(ctx)


@pytest.mark.asyncio
class TestMCPGetToolsExternal:
    async def test_get_table_external_drops_global(self):
        ctx = _ctx(is_external=True)
        await tables_tool.get_table(ctx, table_id=str(uuid4()))
        assert "organization_id IS NULL" not in _executed_sql(ctx)

    async def test_get_table_normal_keeps_global(self):
        ctx = _ctx(is_external=False)
        await tables_tool.get_table(ctx, table_id=str(uuid4()))
        assert "organization_id IS NULL" in _executed_sql(ctx)

    async def test_get_app_external_drops_global(self):
        ctx = _ctx(is_external=True)
        await apps_tool.get_app(ctx, app_id=str(uuid4()))
        assert "organization_id IS NULL" not in _executed_sql(ctx)

    async def test_get_form_by_id_external_drops_global(self):
        ctx = _ctx(is_external=True)
        await forms_tool.get_form(ctx, form_id=str(uuid4()))
        assert "organization_id IS NULL" not in _executed_sql(ctx)

    async def test_get_form_by_name_external_drops_global(self):
        ctx = _ctx(is_external=True)
        await forms_tool.get_form(ctx, form_name="some-form")
        assert "organization_id IS NULL" not in _executed_sql(ctx)

    async def test_get_form_by_name_normal_keeps_global(self):
        ctx = _ctx(is_external=False)
        await forms_tool.get_form(ctx, form_name="some-form")
        assert "organization_id IS NULL" in _executed_sql(ctx)

    async def test_get_agent_by_id_external_drops_global(self):
        ctx = _ctx(is_external=True)
        await agents_tool.get_agent(ctx, agent_id=str(uuid4()))
        assert "organization_id IS NULL" not in _executed_sql(ctx)

    async def test_get_agent_by_name_external_drops_global(self):
        ctx = _ctx(is_external=True)
        await agents_tool.get_agent(ctx, agent_name="some-agent")
        assert "organization_id IS NULL" not in _executed_sql(ctx)

    async def test_get_agent_by_name_normal_keeps_global(self):
        ctx = _ctx(is_external=False)
        await agents_tool.get_agent(ctx, agent_name="some-agent")
        assert "organization_id IS NULL" in _executed_sql(ctx)


@pytest.mark.asyncio
class TestMCPSearchKnowledgeExternal:
    """LEAK #6: MCP search_knowledge forced fallback=True (org + global). An
    external caller must search org-only — no global KB document content."""

    async def _run(self, ctx, captured):
        ctx.accessible_namespaces = ["ns"]
        embed = MagicMock()
        embed.embed_single = AsyncMock(return_value=[0.0] * 8)
        repo = MagicMock()

        async def _search(**kwargs):
            captured["fallback"] = kwargs.get("fallback")
            return []

        repo.search = _search
        with (
            patch(
                "src.services.embeddings.get_embedding_client",
                new=AsyncMock(return_value=embed),
            ),
            patch(
                "src.repositories.knowledge.KnowledgeRepository",
                return_value=repo,
            ),
        ):
            await knowledge_tool.search_knowledge(ctx, query="q")

    async def test_external_forces_no_global_fallback(self):
        captured: dict = {}
        await self._run(_ctx(is_external=True), captured)
        assert captured["fallback"] is False

    async def test_normal_user_keeps_fallback(self):
        captured: dict = {}
        await self._run(_ctx(is_external=False), captured)
        assert captured["fallback"] is True
