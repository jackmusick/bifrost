"""Orphaned config VALUES are invisible to RUNTIME config resolution.

Non-destructive uninstall stamps orphan provenance on config VALUE rows
(``orphaned_at`` set, ``origin_solution_slug`` set; the Config row survives
because it has no ``solution_id`` FK). Tables already get the full "invisible
until reattach" invariant via the org-scoped name cascade. Config must match:
no runtime read path (``merged_for_sdk``, ``get_config_strict``, ``get_config``)
may return an orphaned value, and a re-set in scope (or reattach) heals it.

A fresh ``uuid4`` org has an empty Redis config cache, so ``merged_for_sdk``
hits the DB directly — these tests exercise the DB resolution, not a stale
cache. (The uninstall path separately invalidates the cache so a stamped value
isn't served from Redis until TTL; see ``delete_solution`` in
``src/routers/solutions.py``.)
"""

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from src.models.contracts.config import SetConfigRequest
from src.models.orm.config import Config, ConfigType
from src.models.orm.organizations import Organization
from src.repositories.config import ConfigRepository


async def _make_org(db) -> Organization:
    org = Organization(id=uuid4(), name=f"Org-{uuid4().hex[:6]}", created_by="op@test")
    db.add(org)
    await db.flush()
    return org


async def _set_value(db, org_id, key, value) -> None:
    repo = ConfigRepository(db, org_id=org_id, is_superuser=True)
    await repo.set_config(
        SetConfigRequest(
            key=key, value=value, type=ConfigType.STRING, organization_id=org_id
        ),
        updated_by="op@test",
    )
    await db.flush()


async def _orphan(db, org_id, key, slug="some-install") -> None:
    """Simulate uninstall: stamp the row's orphan provenance directly, then
    invalidate the config cache exactly as ``delete_solution`` does (the orphan
    stamp is a Core update that never bumps the cache version on its own).
    """
    from sqlalchemy import select

    from src.core.cache import invalidate_all_config

    row = (
        await db.execute(
            select(Config).where(
                Config.organization_id == org_id,
                Config.key == key,
            )
        )
    ).scalar_one()
    row.orphaned_at = datetime.now(timezone.utc)
    row.origin_solution_slug = slug
    await db.flush()
    await invalidate_all_config(str(org_id) if org_id is not None else None)


@pytest.mark.e2e
async def test_orphaned_config_value_not_resolved_by_sdk(db_session) -> None:
    db = db_session
    org = await _make_org(db)

    await _set_value(db, org.id, "REGION", "us-west")
    # Before orphaning, the SDK sees it.
    reader = ConfigRepository(db, org_id=org.id, is_superuser=True)
    assert (await reader.merged_for_sdk())["REGION"]["value"] == "us-west"

    await _orphan(db, org.id, "REGION")

    # After orphaning, merged_for_sdk must NOT contain the key.
    reader2 = ConfigRepository(db, org_id=org.id, is_superuser=True)
    merged = await reader2.merged_for_sdk()
    assert "REGION" not in merged


@pytest.mark.e2e
async def test_orphaned_global_config_value_not_resolved_by_sdk(db_session) -> None:
    """The global (NULL-org) leg of merged_for_sdk also excludes orphaned."""
    db = db_session

    # Global config row (organization_id = None), then orphan it.
    repo = ConfigRepository(db, org_id=None, is_superuser=True)
    await repo.set_config(
        SetConfigRequest(
            key="GLOBALKEY", value="g", type=ConfigType.STRING, organization_id=None
        ),
        updated_by="op@test",
    )
    await db.flush()
    await _orphan(db, None, "GLOBALKEY", slug="g-install")

    org = await _make_org(db)
    reader = ConfigRepository(db, org_id=org.id, is_superuser=True)
    merged = await reader.merged_for_sdk()
    assert "GLOBALKEY" not in merged


@pytest.mark.e2e
async def test_get_config_strict_skips_orphaned(db_session) -> None:
    db = db_session
    org = await _make_org(db)

    await _set_value(db, org.id, "REGION", "us-west")
    await _orphan(db, org.id, "REGION")

    repo = ConfigRepository(db, org_id=org.id, is_superuser=True)
    assert await repo.get_config_strict("REGION") is None


@pytest.mark.e2e
async def test_get_config_cascade_skips_orphaned(db_session) -> None:
    """get_config delegates to the org_scoped name cascade, which now excludes
    orphaned for any orphan-capable model (Config has no solution_id, so this
    only works because the exclusion is gated on orphaned_at independently)."""
    db = db_session
    org = await _make_org(db)

    await _set_value(db, org.id, "REGION", "us-west")
    await _orphan(db, org.id, "REGION")

    repo = ConfigRepository(db, org_id=org.id, is_superuser=True)
    assert await repo.get_config("REGION") is None


@pytest.mark.e2e
async def test_reattach_makes_config_resolvable_again(db_session) -> None:
    """Reattach = clear orphaned_at AND invalidate the org config cache.

    Both real reattach paths do exactly this pair (deploy's post-commit
    finalize and the uninstall router). The stamp-clear alone is NOT enough:
    merged_for_sdk is cache-backed, and the post-orphan read below caches the
    orphan-era state — without the invalidation the reattached value stays
    invisible until the cache version moves (the bug this test caught).
    """
    from sqlalchemy import select

    db = db_session
    org = await _make_org(db)

    await _set_value(db, org.id, "REGION", "us-west")
    await _orphan(db, org.id, "REGION")

    reader = ConfigRepository(db, org_id=org.id, is_superuser=True)
    assert "REGION" not in await reader.merged_for_sdk()

    # Simulate reattach exactly as the real paths do: stamp-clear + invalidate.
    row = (
        await db.execute(
            select(Config).where(
                Config.organization_id == org.id, Config.key == "REGION"
            )
        )
    ).scalar_one()
    row.orphaned_at = None
    row.origin_solution_slug = None
    await db.flush()

    from src.core.cache import invalidate_all_config

    await invalidate_all_config(str(org.id))

    reader2 = ConfigRepository(db, org_id=org.id, is_superuser=True)
    assert (await reader2.merged_for_sdk())["REGION"]["value"] == "us-west"


@pytest.mark.e2e
async def test_reset_in_scope_heals_orphaned_value(db_session) -> None:
    """Re-entering a value via set_config heals the orphaned row (clears the
    orphan stamp) instead of colliding with the unique (org, key) index."""
    db = db_session
    org = await _make_org(db)

    await _set_value(db, org.id, "REGION", "us-west")
    await _orphan(db, org.id, "REGION")

    # Re-set the same key in the same scope.
    await _set_value(db, org.id, "REGION", "eu-central")

    reader = ConfigRepository(db, org_id=org.id, is_superuser=True)
    merged = await reader.merged_for_sdk()
    assert merged["REGION"]["value"] == "eu-central"

    # And the orphan stamp is cleared.
    repo = ConfigRepository(db, org_id=org.id, is_superuser=True)
    healed = await repo.get_config_strict("REGION")
    assert healed is not None
    assert healed.orphaned_at is None
    assert healed.origin_solution_slug is None
