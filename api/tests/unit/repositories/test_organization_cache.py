"""Unit tests for ``OrganizationRepository.get_with_cache``.

``get_with_cache`` is new code on the 2026-05 consolidation branch: it
absorbed ``ConfigResolver.get_organization`` (deleted in Phase 5) and is now
the org-rehydration step on the workflow-execution hot path. The
``workflow_execution`` consumer calls it with the caller's ``org_id`` and
serializes the returned ``is_provider`` into the worker's execution context,
where the SDK-side ``resolve_scope`` C2 gate reads it.

If ``get_with_cache`` ever drops ``is_provider`` — most plausibly on the
**cache-hit** path, where the field is read back out of a JSON blob — a
non-admin provider-org member would silently lose their scope-bypass inside
workflows. These tests pin ``is_provider`` across all three internal paths:

  1. cache hit       — value comes from the cached JSON dict
  2. cache miss      — value comes from the DB row
  3. write-through   — the DB-read path repopulates the cache WITH is_provider

The session and Redis helpers are mocked: the contract under test is "does
the method preserve is_provider through each path," not "does SQLAlchemy /
Redis work." End-to-end coverage (through the real engine) lives in
``tests/e2e/api/test_org_scoping_scenarios.py::
TestScenario2b_ProviderOrgBypass::test_provider_member_cross_org_read_through_engine``.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest

from src.repositories.organizations import OrganizationRepository


ORG_ID = UUID("11111111-1111-1111-1111-111111111111")


def _orm_org(*, is_provider: bool) -> MagicMock:
    """A stand-in ORM Organization row with the fields get_with_cache reads."""
    org = MagicMock()
    org.id = ORG_ID
    org.name = "Provider Co"
    org.domain = "provider.example"
    org.is_active = True
    org.is_provider = is_provider
    return org


def _db_returning(org) -> MagicMock:
    """Wrap a value in the ``execute().scalar_one_or_none()`` shape."""
    result = MagicMock()
    result.scalar_one_or_none = MagicMock(return_value=org)
    return result


def _repo_with_session(org_row) -> OrganizationRepository:
    session = MagicMock()
    session.execute = AsyncMock(return_value=_db_returning(org_row))
    return OrganizationRepository(session)


@pytest.mark.asyncio
async def test_cache_hit_preserves_is_provider_true():
    """Cache-hit path must read is_provider back out of the cached blob."""
    repo = _repo_with_session(None)  # session must not be touched on a hit
    repo._get_from_cache = AsyncMock(
        return_value={
            "id": str(ORG_ID),
            "name": "Provider Co",
            "is_active": True,
            "is_provider": True,
        }
    )

    org = await repo.get_with_cache(str(ORG_ID))

    assert org is not None
    assert org.is_provider is True
    # served from cache, no DB hit
    session_execute = repo.session.execute
    assert isinstance(session_execute, AsyncMock)
    session_execute.assert_not_called()


@pytest.mark.asyncio
async def test_cache_hit_missing_is_provider_defaults_false():
    """A legacy cached blob without is_provider must not crash; defaults False.

    Guards the ``cached.get("is_provider", False)`` access — a cache entry
    written before is_provider existed should degrade safely, not KeyError.
    """
    repo = _repo_with_session(None)
    repo._get_from_cache = AsyncMock(
        return_value={"id": str(ORG_ID), "name": "Old", "is_active": True}
    )

    org = await repo.get_with_cache(str(ORG_ID))

    assert org is not None
    assert org.is_provider is False


@pytest.mark.asyncio
async def test_cache_miss_reads_is_provider_from_db():
    """Cache-miss path must carry is_provider from the DB row."""
    repo = _repo_with_session(_orm_org(is_provider=True))
    repo._get_from_cache = AsyncMock(return_value=None)
    repo._set_cache = AsyncMock()

    org = await repo.get_with_cache(str(ORG_ID))

    assert org is not None
    assert org.is_provider is True


@pytest.mark.asyncio
async def test_cache_miss_writes_through_with_is_provider():
    """After a DB read, the cache must be repopulated WITH is_provider."""
    repo = _repo_with_session(_orm_org(is_provider=True))
    repo._get_from_cache = AsyncMock(return_value=None)
    repo._set_cache = AsyncMock()

    await repo.get_with_cache(str(ORG_ID))

    repo._set_cache.assert_awaited_once()
    # is_provider is passed as a kwarg in the write-through call.
    _, kwargs = repo._set_cache.call_args
    assert kwargs["is_provider"] is True


@pytest.mark.asyncio
async def test_non_provider_org_stays_false_through_db():
    """A non-provider org must not be promoted to is_provider=True anywhere."""
    repo = _repo_with_session(_orm_org(is_provider=False))
    repo._get_from_cache = AsyncMock(return_value=None)
    repo._set_cache = AsyncMock()

    org = await repo.get_with_cache(str(ORG_ID))

    assert org is not None
    assert org.is_provider is False
    _, kwargs = repo._set_cache.call_args
    assert kwargs["is_provider"] is False


@pytest.mark.asyncio
async def test_legacy_org_scope_string_is_parsed():
    """The ``ORG:<uuid>`` legacy scope-string form must resolve, not error."""
    repo = _repo_with_session(_orm_org(is_provider=True))
    repo._get_from_cache = AsyncMock(return_value=None)
    repo._set_cache = AsyncMock()

    org = await repo.get_with_cache(f"ORG:{ORG_ID}")

    assert org is not None
    assert org.is_provider is True


@pytest.mark.asyncio
async def test_missing_org_returns_none():
    """A nonexistent org returns None (not a fabricated provider org)."""
    repo = _repo_with_session(None)
    repo._get_from_cache = AsyncMock(return_value=None)
    repo._set_cache = AsyncMock()

    org = await repo.get_with_cache(str(ORG_ID))

    assert org is None
