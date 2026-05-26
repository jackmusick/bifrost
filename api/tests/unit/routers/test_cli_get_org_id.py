"""Unit tests for ``_get_cli_org_id`` scope validation and authorization.

This function used to:
  1. Trust any scope string from any caller — including raw UUIDs — and
     pass it through to downstream queries without checking whether the
     caller was authorized to target that org. The 2026-05 org-scoping
     overhaul closed this gap by routing through
     ``shared.scope_resolver.resolve_effective_scope`` with the canonical
     four-rule table.
  2. Accept malformed input that flowed into raw SQL and surfaced as an
     asyncpg ``InvalidTextRepresentation`` 500. It now validates that
     ``scope`` is either ``"global"``, ``""``, a valid UUID, or null.

These tests assert the post-overhaul contract.
"""

from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException

from src.routers.cli import _get_cli_org_id


def _empty_dev_ctx_db():
    """Mock db.execute that returns no DeveloperContext (so caller has no default org)."""
    class FakeResult:
        def scalar_one_or_none(self):
            return None

    db = AsyncMock()
    db.execute = AsyncMock(return_value=FakeResult())
    return db


def _dev_ctx_db_with(default_org_id: UUID):
    """Mock db.execute that returns a DeveloperContext with the given default org."""
    class FakeDevCtx:
        pass
    ctx = FakeDevCtx()
    ctx.default_org_id = default_org_id

    class FakeResult:
        def scalar_one_or_none(self):
            return ctx

    db = AsyncMock()
    db.execute = AsyncMock(return_value=FakeResult())
    return db


# ---------------------------------------------------------------------------
# Authorization: platform admin can request any scope
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_platform_admin_global_returns_none():
    """``scope='global'`` is allowed for platform admins."""
    db = _empty_dev_ctx_db()
    result = await _get_cli_org_id(
        uuid4(), "global", db, is_platform_admin=True
    )
    assert result is None


@pytest.mark.asyncio
async def test_platform_admin_can_target_any_org():
    """A platform admin can pass any org UUID."""
    db = _empty_dev_ctx_db()
    target = str(uuid4())
    result = await _get_cli_org_id(
        uuid4(), target, db, is_platform_admin=True
    )
    assert result == target


# ---------------------------------------------------------------------------
# Authorization: non-admin cannot target other orgs
# (THIS IS THE SECURITY FIX. Pre-overhaul these tests would pass with
# the cross-org breach in place.)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_non_admin_cannot_request_global():
    """``scope='global'`` requires platform admin. Pre-overhaul this
    would have returned None without a check."""
    db = _empty_dev_ctx_db()
    with pytest.raises(HTTPException) as exc:
        await _get_cli_org_id(uuid4(), "global", db, is_platform_admin=False)
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_non_admin_cannot_target_other_org():
    """A non-admin caller cannot request an arbitrary org UUID.
    Pre-overhaul this would have silently leaked the other org's
    data — this is the cross-tenant traversal fix."""
    caller_org = uuid4()
    other_org = str(uuid4())
    db = _dev_ctx_db_with(caller_org)

    with pytest.raises(HTTPException) as exc:
        await _get_cli_org_id(uuid4(), other_org, db, is_platform_admin=False)
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_non_admin_can_target_own_org():
    """A non-admin caller CAN explicitly request their own org's UUID."""
    caller_org = uuid4()
    db = _dev_ctx_db_with(caller_org)

    result = await _get_cli_org_id(
        uuid4(), str(caller_org), db, is_platform_admin=False
    )
    assert result == str(caller_org)


# ---------------------------------------------------------------------------
# Default-org behavior
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_none_scope_uses_developer_context():
    """``scope=None`` falls back to the user's DeveloperContext default."""
    expected = uuid4()
    db = _dev_ctx_db_with(expected)
    result = await _get_cli_org_id(uuid4(), None, db, is_platform_admin=False)
    assert result == str(expected)


@pytest.mark.asyncio
async def test_none_scope_no_developer_context_returns_none():
    """``scope=None`` with no DeveloperContext returns None (no default org).

    Distinct from explicit ``scope='global'``: this is UNSET in resolver
    terms — the caller didn't ask for global, they just have no default.
    """
    db = _empty_dev_ctx_db()
    result = await _get_cli_org_id(uuid4(), None, db, is_platform_admin=False)
    assert result is None


@pytest.mark.asyncio
async def test_empty_string_treated_as_none():
    """Empty string scope is preserved as ``UNSET`` for CLI clients
    passing ``--scope ''``."""
    db = _empty_dev_ctx_db()
    result = await _get_cli_org_id(uuid4(), "", db, is_platform_admin=False)
    assert result is None


# ---------------------------------------------------------------------------
# Input validation (pre-overhaul behavior preserved)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_garbage_scope_raises_422():
    """Non-UUID, non-'global' scope raises 422 (not a downstream 500)."""
    db = _empty_dev_ctx_db()
    with pytest.raises(HTTPException) as exc:
        await _get_cli_org_id(uuid4(), "not-a-uuid", db)
    assert exc.value.status_code == 422
    assert "uuid" in exc.value.detail.lower() or "scope" in exc.value.detail.lower()


@pytest.mark.asyncio
async def test_uppercase_uuid_accepted_for_admin():
    """UUID parsing is case-insensitive. Platform admin can use uppercase
    representation of an arbitrary UUID."""
    db = _empty_dev_ctx_db()
    upper = str(uuid4()).upper()
    result = await _get_cli_org_id(uuid4(), upper, db, is_platform_admin=True)
    # The resolver normalizes to UUID(...) which formats lowercase, so
    # comparison must be UUID-equal, not string-equal.
    assert UUID(result) == UUID(upper)
