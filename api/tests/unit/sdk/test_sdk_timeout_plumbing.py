"""SDK helpers that accept ``timeout`` must forward it to the httpx call.

Without this, the SDK's hardcoded 30s client read-timeout tears the
connection down before the server can respond — even when the caller
explicitly asked for longer. Regression coverage for #301.
"""
from __future__ import annotations

import importlib
import sys
from unittest.mock import AsyncMock, MagicMock

import pytest


def _agents_module():
    if "bifrost.agents" not in sys.modules:
        importlib.import_module("bifrost.agents")
    return sys.modules["bifrost.agents"]


def _knowledge_module():
    if "bifrost.knowledge" not in sys.modules:
        importlib.import_module("bifrost.knowledge")
    return sys.modules["bifrost.knowledge"]


@pytest.mark.asyncio
async def test_agents_run_forwards_timeout_to_httpx_with_buffer(monkeypatch):
    """``agents.run(timeout=N)`` must pass ``timeout=N+10`` to ``client.post``
    so httpx waits long enough for the server-side cap to expire first."""
    mod = _agents_module()

    mock_response = MagicMock()
    mock_response.is_success = True
    mock_response.json.return_value = {"output": "ok", "status": "completed"}
    mock_response.status_code = 200

    mock_client = MagicMock()
    mock_client.post = AsyncMock(return_value=mock_response)
    monkeypatch.setattr(mod, "get_client", lambda: mock_client)

    await mod.agents.run("Foo", input={}, timeout=300)

    mock_client.post.assert_awaited_once()
    kwargs = mock_client.post.call_args.kwargs
    assert kwargs.get("timeout") == 310, (
        f"expected client.post(timeout=310), got {kwargs.get('timeout')!r}"
    )
    assert kwargs["json"]["timeout"] == 300, (
        "server-side cap must still be sent in the body"
    )


@pytest.mark.asyncio
async def test_agents_run_default_timeout_forwarded(monkeypatch):
    """Default ``timeout=1800`` must reach httpx as 1810, not silently 30."""
    mod = _agents_module()

    mock_response = MagicMock()
    mock_response.is_success = True
    mock_response.json.return_value = {"output": "ok"}
    mock_response.status_code = 200

    mock_client = MagicMock()
    mock_client.post = AsyncMock(return_value=mock_response)
    monkeypatch.setattr(mod, "get_client", lambda: mock_client)

    await mod.agents.run("Foo")

    kwargs = mock_client.post.call_args.kwargs
    assert kwargs.get("timeout") == 1810


@pytest.mark.asyncio
async def test_knowledge_store_many_forwards_default_timeout(monkeypatch):
    """``knowledge.store_many`` must default ``timeout=300`` to httpx."""
    mod = _knowledge_module()

    mock_response = MagicMock()
    mock_response.is_success = True
    mock_response.json.return_value = {"ids": ["a", "b"]}
    mock_response.status_code = 200

    mock_client = MagicMock()
    mock_client.post = AsyncMock(return_value=mock_response)
    monkeypatch.setattr(mod, "get_client", lambda: mock_client)
    monkeypatch.setattr(mod, "resolve_scope", lambda s: s)

    await mod.knowledge.store_many(
        [{"content": "x"}, {"content": "y"}],
        namespace="faq",
    )

    kwargs = mock_client.post.call_args.kwargs
    assert kwargs.get("timeout") == 300.0


@pytest.mark.asyncio
async def test_knowledge_store_many_respects_explicit_timeout(monkeypatch):
    """Explicit ``timeout=`` overrides the default."""
    mod = _knowledge_module()

    mock_response = MagicMock()
    mock_response.is_success = True
    mock_response.json.return_value = {"ids": []}
    mock_response.status_code = 200

    mock_client = MagicMock()
    mock_client.post = AsyncMock(return_value=mock_response)
    monkeypatch.setattr(mod, "get_client", lambda: mock_client)
    monkeypatch.setattr(mod, "resolve_scope", lambda s: s)

    await mod.knowledge.store_many([], namespace="faq", timeout=600.0)

    kwargs = mock_client.post.call_args.kwargs
    assert kwargs.get("timeout") == 600.0
