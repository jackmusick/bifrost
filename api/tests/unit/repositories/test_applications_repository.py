"""ApplicationRepository.create_application must serialize against solution
deploys of the same slug.

deploy.py takes `pg_advisory_xact_lock(hashtext('bifrost:appslug:' || slug))`
precisely to make the SELECT-then-INSERT atomic across concurrent same-slug
writers. create_application does the same SELECT-then-INSERT into a DISJOINT
partial unique index — without taking the same lock, a racing pair lands two
same-slug rows and every subsequent /apps/{slug} open 500s with
MultipleResultsFound. Mirrors test_deploy_takes_advisory_lock_on_slug.
"""
from __future__ import annotations

import uuid

import pytest

from src.models.contracts.applications import ApplicationCreate
from src.models.orm.applications import Application
from src.repositories.applications import ApplicationRepository

pytestmark = pytest.mark.e2e


async def test_create_application_takes_slug_advisory_lock_first(db_session, monkeypatch):
    """The FIRST statement create_application executes is the per-slug advisory
    lock — BEFORE the duplicate-check SELECT, so a racing deploy/create pair
    blocks instead of both passing the check."""
    db = db_session
    slug = f"dash-{uuid.uuid4().hex[:8]}"
    # Pre-existing app with this slug → create_application raises ValueError
    # AFTER the lock + duplicate-check SELECT (keeps the test off the
    # file-scaffolding path; the lock-ordering claim is identical).
    db.add(Application(
        id=uuid.uuid4(), name="Existing", slug=slug, repo_path=f"apps/{slug}",
        organization_id=None, solution_id=None,
    ))
    await db.flush()

    statements: list[tuple[str, str | None]] = []
    orig_execute = db.execute

    async def _spy_execute(stmt, params=None, *a, **k):
        statements.append((str(stmt), (params or {}).get("s") if isinstance(params, dict) else None))
        return await orig_execute(stmt, params, *a, **k)

    monkeypatch.setattr(db, "execute", _spy_execute)

    repo = ApplicationRepository(db, org_id=None, user_id=None, is_superuser=True)
    with pytest.raises(ValueError, match="already exists"):
        await repo.create_application(
            ApplicationCreate(name="Dup", slug=slug), created_by="dev@x"
        )

    assert statements, "create_application executed no statements"
    first_sql, first_param = statements[0]
    assert "pg_advisory_xact_lock" in first_sql, (
        f"first statement was not the advisory lock: {first_sql}"
    )
    assert "bifrost:appslug:" in first_sql
    assert first_param == slug
    # The duplicate-check SELECT happens AFTER the lock.
    assert any(
        "pg_advisory_xact_lock" not in sql and "applications" in sql.lower()
        for sql, _ in statements[1:]
    ), "duplicate-check SELECT not found after the lock"
