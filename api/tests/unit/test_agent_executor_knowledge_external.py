"""
LEAK #6 (interactive chat half): AgentExecutor._execute_knowledge_search
forced fallback=True. A chat owned by an EXTERNAL user must search org-only —
no global KB document content. The autonomous executor is a separate class and
stays full-cascade.
"""

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.services.agent_executor import AgentExecutor


def _executor():
    return AgentExecutor(session_factory=MagicMock())


@pytest.mark.asyncio
class TestResolveCallerIsExternal:
    async def test_none_caller_is_false(self):
        ex = _executor()
        assert await ex._resolve_caller_is_external(None) is False

    async def test_delegates_to_resolve_external_claim(self):
        ex = _executor()
        user = SimpleNamespace(is_external=True, is_superuser=False, organization_id=uuid4())
        session = AsyncMock()
        session.get = AsyncMock(return_value=user)

        @asynccontextmanager
        async def _db():
            yield session

        with (
            patch.object(ex, "_db", _db),
            patch(
                "shared.external_access.resolve_external_claim",
                new=AsyncMock(return_value=True),
            ),
        ):
            assert await ex._resolve_caller_is_external(uuid4()) is True

    async def test_unknown_user_is_false(self):
        ex = _executor()
        session = AsyncMock()
        session.get = AsyncMock(return_value=None)

        @asynccontextmanager
        async def _db():
            yield session

        with patch.object(ex, "_db", _db):
            assert await ex._resolve_caller_is_external(uuid4()) is False


@pytest.mark.asyncio
class TestKnowledgeSearchFallbackFromCaller:
    async def _run(self, *, caller_external, captured):
        ex = _executor()
        agent = SimpleNamespace(
            knowledge_sources=["ns"], organization_id=uuid4()
        )
        tool_call = SimpleNamespace(id="t1", name="search_knowledge", arguments={"query": "q"})

        session = AsyncMock()

        @asynccontextmanager
        async def _db():
            yield session

        embed = MagicMock()
        embed.embed_single = AsyncMock(return_value=[0.0] * 8)
        repo = MagicMock()

        async def _search(**kwargs):
            captured["fallback"] = kwargs.get("fallback")
            return []

        repo.search = _search

        with (
            patch.object(ex, "_db", _db),
            patch.object(
                ex, "_resolve_caller_is_external",
                new=AsyncMock(return_value=caller_external),
            ),
            patch(
                "src.services.embeddings.get_embedding_client",
                new=AsyncMock(return_value=embed),
            ),
            patch(
                "src.repositories.knowledge.KnowledgeRepository",
                return_value=repo,
            ),
        ):
            await ex._execute_knowledge_search(
                tool_call, agent, caller_user_id=uuid4()
            )

    async def test_external_caller_forces_org_only(self):
        captured: dict = {}
        await self._run(caller_external=True, captured=captured)
        assert captured["fallback"] is False

    async def test_normal_caller_keeps_global(self):
        captured: dict = {}
        await self._run(caller_external=False, captured=captured)
        assert captured["fallback"] is True
