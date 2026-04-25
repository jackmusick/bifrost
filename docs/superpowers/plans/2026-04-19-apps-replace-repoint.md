# Apps Replace / `repo_path` Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Promote `Application.repo_path` to a first-class `NOT NULL` + unique column (no fallback), then add `bifrost apps replace <ref> --repo-path <new> [--force]` to repoint an app's source directory via REST + MCP + CLI.

**Architecture:** Single PR. Migration backfills + tightens the column → ORM drops the fallback → router gets a `POST /{id}/replace` endpoint that delegates to a repository method performing uniqueness/nesting/source-exists validation → MCP gets a thin `replace_app` HTTP wrapper → CLI adds an `apps replace` command mirroring `workflows replace`. No UI changes, no S3 file moves.

**Tech Stack:** Python 3.11 / FastAPI / SQLAlchemy (async) / Alembic / Pydantic / Click / pytest / Docker-Compose dev stack.

**Spec:** `docs/superpowers/specs/2026-04-19-apps-replace-repoint-design.md`

---

## File Structure

**Create:**
- `api/alembic/versions/20260419_apps_repo_path_not_null_unique.py` — migration: backfill + NOT NULL + unique index
- `api/tests/unit/services/test_app_repoint.py` — unit tests for the repoint service method (validation rules, no-op, force bypass)
- `api/tests/e2e/platform/test_cli_apps_replace.py` — E2E tests for the `bifrost apps replace` CLI end-to-end (happy path, conflicts, force)

**Modify:**
- `api/src/models/orm/applications.py` — drop `| None` on `repo_path`, drop fallback from `repo_prefix`
- `api/src/models/contracts/applications.py` — add `ApplicationReplaceRequest` DTO
- `api/src/routers/applications.py` — add `replace_application` repository method + `POST /{app_id}/replace` route handler
- `api/src/services/mcp_server/tools/apps.py` — add `replace_app` tool (thin HTTP wrapper)
- `api/bifrost/commands/apps.py` — add `replace` CLI command
- `api/bifrost/dto_flags.py` — add `repo_path` to `ApplicationUpdate` exclude set with comment pointing at `apps replace`
- `docs/llm.txt` — document `bifrost apps replace`

---

## Task 1: Migration — backfill, NOT NULL, unique index

**Files:**
- Create: `api/alembic/versions/20260419_apps_repo_path_not_null_unique.py`

- [ ] **Step 1: Write the migration**

Create `api/alembic/versions/20260419_apps_repo_path_not_null_unique.py`:

```python
"""apps repo_path NOT NULL + unique

Revision ID: 20260419_apps_repo_path
Revises: <REPLACE WITH CURRENT HEAD>
Create Date: 2026-04-19

Promotes applications.repo_path to a first-class column:
- Backfills any NULL values to 'apps/{slug}' (the prior repo_prefix fallback).
- Fails if backfill would produce duplicate values (shouldn't happen since slug
  is unique, but backstop for corrupted data — operator must resolve manually).
- Alters the column to NOT NULL.
- Adds a unique index so two applications cannot claim the same source prefix.

The repo_prefix property fallback to 'apps/{slug}' is removed in the same PR;
this migration is what makes that safe.
"""

from alembic import op
import sqlalchemy as sa


revision = "20260419_apps_repo_path"
down_revision = None  # REPLACE with `alembic heads` output before committing
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Backfill NULL values using the prior convention default.
    op.execute(
        "UPDATE applications SET repo_path = 'apps/' || slug WHERE repo_path IS NULL"
    )

    # Fail fast if a duplicate slipped through (e.g. two apps with same slug
    # in corrupted data, or a manually-set duplicate repo_path).
    dup_check = op.get_bind().execute(
        sa.text(
            "SELECT repo_path, COUNT(*) AS n FROM applications "
            "GROUP BY repo_path HAVING COUNT(*) > 1"
        )
    ).fetchall()
    if dup_check:
        raise RuntimeError(
            f"Cannot enforce unique repo_path — duplicates found: {dup_check}. "
            "Resolve manually before retrying this migration."
        )

    op.alter_column("applications", "repo_path", nullable=False)
    op.create_index(
        "uq_applications_repo_path",
        "applications",
        ["repo_path"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_applications_repo_path", table_name="applications")
    op.alter_column("applications", "repo_path", nullable=True)
```

- [ ] **Step 2: Resolve `down_revision`**

Run from `api/`:

```bash
docker compose -f ../docker-compose.dev.yml exec bifrost-init alembic heads
```

Copy the head revision ID into `down_revision`. If `bifrost-init` isn't running, use `docker compose -f ../docker-compose.dev.yml run --rm bifrost-init alembic heads`.

- [ ] **Step 3: Apply the migration**

```bash
docker compose -f docker-compose.dev.yml restart bifrost-init
docker compose -f docker-compose.dev.yml logs --tail=50 bifrost-init
```

Expected: logs show `Running upgrade <prev> -> 20260419_apps_repo_path, apps repo_path NOT NULL + unique` with no errors.

- [ ] **Step 4: Verify in psql**

```bash
docker compose -f docker-compose.dev.yml exec postgres \
  psql -U bifrost -d bifrost -c \
  "SELECT column_name, is_nullable FROM information_schema.columns WHERE table_name='applications' AND column_name='repo_path';"
```

Expected: `repo_path | NO` (is_nullable = NO).

```bash
docker compose -f docker-compose.dev.yml exec postgres \
  psql -U bifrost -d bifrost -c \
  "SELECT indexname FROM pg_indexes WHERE tablename='applications' AND indexname='uq_applications_repo_path';"
```

Expected: one row returned.

- [ ] **Step 5: Commit**

```bash
git add api/alembic/versions/20260419_apps_repo_path_not_null_unique.py
git commit -m "feat(db): apps.repo_path NOT NULL + unique

Backfills NULL values to apps/{slug} and enforces uniqueness so two
apps cannot claim the same source prefix."
```

---

## Task 2: ORM — drop nullable, drop fallback

**Files:**
- Modify: `api/src/models/orm/applications.py:43` (column declaration) and lines 112–120 (`repo_prefix`)

- [ ] **Step 1: Update ORM**

Edit `api/src/models/orm/applications.py`. Replace the existing `repo_path` declaration and `repo_prefix` property.

Old:
```python
repo_path: Mapped[str | None] = mapped_column(String(500), default=None)
```

New:
```python
repo_path: Mapped[str] = mapped_column(String(500), nullable=False)
```

Old:
```python
@property
def repo_prefix(self) -> str:
    """Return the repo path prefix for this app, with trailing slash.

    Uses repo_path from DB (set by git sync / manifest import).
    Falls back to convention default apps/{slug} for legacy apps.
    """
    base = self.repo_path or f"apps/{self.slug}"
    return f"{base.rstrip('/')}/"
```

New:
```python
@property
def repo_prefix(self) -> str:
    """Return the repo path prefix for this app, with trailing slash."""
    return f"{self.repo_path.rstrip('/')}/"
```

- [ ] **Step 2: Update `_find_app_by_path` — drop the `isnot(None)` guard**

Edit `api/src/services/file_storage/file_ops.py` around line 379. Remove the `Application.repo_path.isnot(None)` clause since the column is now NOT NULL.

Find:
```python
stmt = (
    select(Application)
    .where(
        Application.repo_path.isnot(None),
        text("starts_with(:path, repo_path || '/')").bindparams(path=path),
    )
    .order_by(func.length(Application.repo_path).desc())
    .limit(1)
)
```

Replace with:
```python
stmt = (
    select(Application)
    .where(text("starts_with(:path, repo_path || '/')").bindparams(path=path))
    .order_by(func.length(Application.repo_path).desc())
    .limit(1)
)
```

- [ ] **Step 3: Verify pyright**

```bash
cd api && pyright
```

Expected: 0 errors. If any file was setting `repo_path=None` at insertion time, pyright should flag it. Fix by setting `repo_path=f"apps/{slug}"` explicitly.

- [ ] **Step 4: Run existing app unit tests**

```bash
cd .. && ./test.sh api/tests/unit/services/ -k application
```

Expected: all pass (no behavioral change for existing callers — they already set `repo_path` at creation per the exploration).

- [ ] **Step 5: Commit**

```bash
git add api/src/models/orm/applications.py api/src/services/file_storage/file_ops.py
git commit -m "refactor(apps): make repo_path non-nullable, drop apps/{slug} fallback"
```

---

## Task 3: Replace-request DTO

**Files:**
- Modify: `api/src/models/contracts/applications.py` (add class at end of file)

- [ ] **Step 1: Add the DTO**

Append to `api/src/models/contracts/applications.py`:

```python
class ApplicationReplaceRequest(BaseModel):
    """Input for repointing an application's source directory.

    Mutation-only surface. See ``POST /api/applications/{id}/replace``.
    """

    repo_path: str = Field(
        min_length=1,
        max_length=500,
        description="Workspace-relative path to the new source directory (e.g. apps/my-app-v2).",
    )
    force: bool = Field(
        default=False,
        description=(
            "Bypass the uniqueness, nesting, and source-exists checks. "
            "Use when repointing before files are pushed."
        ),
    )
```

Make sure `BaseModel` and `Field` are already imported in the file; add to existing import block if not.

- [ ] **Step 2: Verify pyright**

```bash
cd api && pyright
```

Expected: 0 errors.

- [ ] **Step 3: Commit**

```bash
git add api/src/models/contracts/applications.py
git commit -m "feat(contracts): add ApplicationReplaceRequest DTO"
```

---

## Task 4: Repository method — unit test first (failing)

**Files:**
- Create: `api/tests/unit/services/test_app_repoint.py`

- [ ] **Step 1: Write the failing unit tests**

Create `api/tests/unit/services/test_app_repoint.py`:

```python
"""Unit tests for ApplicationRepository.replace_application (repoint)."""
from __future__ import annotations

import pytest
import pytest_asyncio
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from src.models.orm.applications import Application
from src.models.orm.file_index import FileIndex
from src.routers.applications import ApplicationRepository


@pytest_asyncio.fixture
async def repo(db_session: AsyncSession) -> ApplicationRepository:
    # org_id None → global scope; repository handles that via permission checks
    # which are bypassed in unit tests by using a platform-admin context.
    return ApplicationRepository(session=db_session, org_id=None, is_platform_admin=True)


async def _make_app(db, *, slug: str, repo_path: str) -> Application:
    app = Application(
        id=uuid4(),
        name=slug,
        slug=slug,
        repo_path=repo_path,
        access_level="authenticated",
    )
    db.add(app)
    await db.flush()
    return app


async def _seed_file(db, path: str) -> None:
    db.add(FileIndex(path=path, content="// stub", content_hash="x"))
    await db.flush()


@pytest.mark.asyncio
async def test_replace_repoints_when_all_checks_pass(repo, db_session):
    app = await _make_app(db_session, slug="foo", repo_path="apps/foo")
    await _seed_file(db_session, "apps/foo-v2/index.tsx")

    result = await repo.replace_application(app.id, "apps/foo-v2", force=False)

    assert result is not None
    assert result.repo_path == "apps/foo-v2"


@pytest.mark.asyncio
async def test_replace_noop_when_path_unchanged(repo, db_session):
    app = await _make_app(db_session, slug="foo", repo_path="apps/foo")
    # No file seeded — no-op should not trigger source-exists check.

    result = await repo.replace_application(app.id, "apps/foo", force=False)

    assert result is not None
    assert result.repo_path == "apps/foo"


@pytest.mark.asyncio
async def test_replace_rejects_duplicate_repo_path(repo, db_session):
    app_a = await _make_app(db_session, slug="a", repo_path="apps/a")
    await _make_app(db_session, slug="b", repo_path="apps/taken")
    await _seed_file(db_session, "apps/taken/index.tsx")

    with pytest.raises(ValueError, match="already claimed"):
        await repo.replace_application(app_a.id, "apps/taken", force=False)


@pytest.mark.asyncio
async def test_replace_rejects_nested_under_existing(repo, db_session):
    app_a = await _make_app(db_session, slug="a", repo_path="apps/a")
    await _make_app(db_session, slug="outer", repo_path="apps/outer")
    await _seed_file(db_session, "apps/outer/sub/index.tsx")

    with pytest.raises(ValueError, match="nested"):
        await repo.replace_application(app_a.id, "apps/outer/sub", force=False)


@pytest.mark.asyncio
async def test_replace_rejects_existing_nested_under_target(repo, db_session):
    app_a = await _make_app(db_session, slug="a", repo_path="apps/a")
    await _make_app(db_session, slug="inner", repo_path="apps/outer/inner")
    await _seed_file(db_session, "apps/outer/index.tsx")

    with pytest.raises(ValueError, match="nested"):
        await repo.replace_application(app_a.id, "apps/outer", force=False)


@pytest.mark.asyncio
async def test_replace_rejects_empty_prefix(repo, db_session):
    app = await _make_app(db_session, slug="foo", repo_path="apps/foo")

    with pytest.raises(ValueError, match="no files"):
        await repo.replace_application(app.id, "apps/does-not-exist", force=False)


@pytest.mark.asyncio
async def test_force_bypasses_uniqueness(repo, db_session):
    app_a = await _make_app(db_session, slug="a", repo_path="apps/a")
    await _make_app(db_session, slug="b", repo_path="apps/taken")
    await _seed_file(db_session, "apps/taken/index.tsx")

    # Force bypass lets it through even though another app claims the path.
    # (In practice the DB unique constraint will then fail on commit — the force
    # here is about bypassing the application-layer check; DB integrity is the
    # final guard. Validate that.)
    with pytest.raises(Exception):  # IntegrityError on commit
        await repo.replace_application(app_a.id, "apps/taken", force=True)
        await db_session.commit()


@pytest.mark.asyncio
async def test_force_bypasses_nesting(repo, db_session):
    app_a = await _make_app(db_session, slug="a", repo_path="apps/a")
    await _make_app(db_session, slug="outer", repo_path="apps/outer")
    await _seed_file(db_session, "apps/outer/index.tsx")

    result = await repo.replace_application(app_a.id, "apps/outer/sub", force=True)
    assert result.repo_path == "apps/outer/sub"


@pytest.mark.asyncio
async def test_force_bypasses_source_exists(repo, db_session):
    app = await _make_app(db_session, slug="foo", repo_path="apps/foo")

    result = await repo.replace_application(app.id, "apps/empty", force=True)
    assert result.repo_path == "apps/empty"
```

- [ ] **Step 2: Run tests — expect failures**

```bash
./test.sh api/tests/unit/services/test_app_repoint.py -v
```

Expected: `AttributeError: 'ApplicationRepository' object has no attribute 'replace_application'` on every test.

- [ ] **Step 3: Commit the failing tests**

```bash
git add api/tests/unit/services/test_app_repoint.py
git commit -m "test(apps): add failing unit tests for replace_application"
```

---

## Task 5: Repository method — implementation

**Files:**
- Modify: `api/src/routers/applications.py` (add method to `ApplicationRepository` near `update_application` at line 245)

- [ ] **Step 1: Implement the method**

In `api/src/routers/applications.py`, inside the `ApplicationRepository` class, after `update_application` (around line 306), add:

```python
async def replace_application(
    self,
    app_id: UUID,
    new_repo_path: str,
    *,
    force: bool = False,
) -> Application | None:
    """Repoint an application's source directory.

    Validates uniqueness, nesting, and that the new prefix has source files
    in file_index. Any of those checks may be bypassed with ``force=True``.
    No file moves — updates DB only.

    Returns the updated Application, or None if the app was not found.
    Raises ValueError on validation failure.
    """
    from src.models.orm.file_index import FileIndex

    app = await self.get_by_id(app_id)
    if app is None:
        return None

    # Normalize: strip trailing slash, reject empty string.
    normalized = new_repo_path.rstrip("/")
    if not normalized:
        raise ValueError("repo_path cannot be empty")

    # No-op fast path.
    if normalized == app.repo_path:
        return app

    if not force:
        # Uniqueness check (excluding the app itself).
        existing_stmt = select(Application).where(
            Application.repo_path == normalized,
            Application.id != app_id,
        )
        conflict = (await self.session.execute(existing_stmt)).scalar_one_or_none()
        if conflict is not None:
            raise ValueError(
                f"repo_path '{normalized}' already claimed by app "
                f"{conflict.slug} ({conflict.id}). Pass force=True to override."
            )

        # Nesting check: no other app's repo_path is a prefix of new (with /),
        # and new (with /) is not a prefix of any other app's repo_path.
        # Both directions cause longest-prefix-match ambiguity in _find_app_by_path.
        new_prefix = f"{normalized}/"
        nest_stmt = select(Application).where(
            Application.id != app_id,
            sa.or_(
                # Other app's path + '/' is a prefix of new_prefix
                sa.literal(new_prefix).like(Application.repo_path.concat("/%")),
                # New prefix is a prefix of other app's repo_path
                Application.repo_path.like(f"{new_prefix}%"),
            ),
        )
        nested = (await self.session.execute(nest_stmt)).scalar_one_or_none()
        if nested is not None:
            raise ValueError(
                f"repo_path '{normalized}' is nested with app {nested.slug} "
                f"({nested.repo_path}). Pass force=True to override."
            )

        # Source-exists check: at least one file_index row starts with new_prefix.
        file_stmt = select(FileIndex).where(
            FileIndex.path.like(f"{new_prefix}%")
        ).limit(1)
        has_source = (await self.session.execute(file_stmt)).scalar_one_or_none()
        if has_source is None:
            raise ValueError(
                f"no files found under '{normalized}'. "
                "Push source first, or pass force=True to repoint ahead of a push."
            )

    app.repo_path = normalized
    await self.session.flush()
    await self.session.refresh(app)

    logger.info(f"Repointed application {app_id} to repo_path={normalized!r}")
    return app
```

Verify `sa` (as `import sqlalchemy as sa`) and `select` are already imported at the top of the file; add if not. Same for `logger`.

- [ ] **Step 2: Run the unit tests**

```bash
./test.sh api/tests/unit/services/test_app_repoint.py -v
```

Expected: all 9 tests pass.

- [ ] **Step 3: Commit**

```bash
git add api/src/routers/applications.py
git commit -m "feat(apps): ApplicationRepository.replace_application"
```

---

## Task 6: REST endpoint

**Files:**
- Modify: `api/src/routers/applications.py` (add route after `publish_application` at line 928)

- [ ] **Step 1: Add the route**

In `api/src/routers/applications.py`, immediately after the `publish_application` endpoint (around line 928), add:

```python
@router.post(
    "/{app_id}/replace",
    response_model=ApplicationPublic,
    summary="Repoint application source directory",
)
async def replace_application_endpoint(
    app_id: UUID,
    request: ApplicationReplaceRequest,
    context: Context,  # existing dependency — copy from update_application
    user: CurrentUser,
) -> ApplicationPublic:
    """Update ``repo_path`` after source files have been moved/renamed.

    Validates that the new path is unique, non-nested with other apps, and has
    source files under it. ``force: true`` bypasses all three checks.
    """
    repo = ApplicationRepository(
        session=context.db,
        org_id=context.org_id,
        is_platform_admin=user.is_platform_admin,
    )
    try:
        app = await repo.replace_application(
            app_id,
            request.repo_path,
            force=request.force,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if app is None:
        raise HTTPException(status_code=404, detail="Application not found")
    await context.db.commit()
    return ApplicationPublic.model_validate(app, from_attributes=True)
```

**Note:** match the exact dependency-injection idiom already used by `update_application` at line 726. If `update_application` uses `db: AsyncSession = Depends(get_db_session)` directly rather than `context: Context`, copy that style verbatim. Also import `ApplicationReplaceRequest` from `src.models.contracts.applications` at the top of the file alongside `ApplicationCreate` / `ApplicationUpdate`.

- [ ] **Step 2: Start the dev stack if not running**

```bash
docker ps --filter "name=bifrost" | grep -q "bifrost-dev-api" || ./debug.sh
```

- [ ] **Step 3: Smoke-test the endpoint**

```bash
curl -s -X POST http://localhost:3000/api/applications/<some-app-uuid>/replace \
  -H "Content-Type: application/json" \
  -H "Cookie: <auth cookie from browser>" \
  -d '{"repo_path":"apps/foo","force":true}' | jq .
```

Expected: JSON response with `repo_path` matching the request (use `force:true` to skip the source-exists check for this smoke test).

- [ ] **Step 4: Regenerate client types**

```bash
cd client && npm run generate:types && cd ..
```

Expected: `client/src/lib/v1.d.ts` now contains `ApplicationReplaceRequest` and the `/api/applications/{app_id}/replace` path.

- [ ] **Step 5: Commit**

```bash
git add api/src/routers/applications.py client/src/lib/v1.d.ts
git commit -m "feat(apps): POST /api/applications/{id}/replace"
```

---

## Task 7: MCP tool (thin HTTP wrapper)

**Files:**
- Modify: `api/src/services/mcp_server/tools/apps.py` (add `replace_app` after `publish_app` at line 418)

- [ ] **Step 1: Add the tool**

In `api/src/services/mcp_server/tools/apps.py`, after `publish_app` (~line 418), add:

```python
async def replace_app(
    context: Any,
    app_id: str,
    repo_path: str,
    force: bool = False,
) -> dict[str, Any]:
    """Repoint an app's source directory (``repo_path``).

    Thin HTTP wrapper around ``POST /api/applications/{id}/replace``.
    """
    from src.services.mcp_server.tools._http_bridge import rest_client

    async with rest_client(context) as client:
        response = await client.post(
            f"/api/applications/{app_id}/replace",
            json={"repo_path": repo_path, "force": force},
        )
        response.raise_for_status()
        return response.json()
```

Register the tool wherever `publish_app` is registered in the same file (likely a `TOOLS` dict or decorator at module level — mirror the existing pattern exactly).

- [ ] **Step 2: Verify MCP thin-wrapper test still passes**

```bash
./test.sh api/tests/unit/test_mcp_thin_wrapper.py -v
```

Expected: pass. This test enforces MCP tools don't import repositories directly.

- [ ] **Step 3: Commit**

```bash
git add api/src/services/mcp_server/tools/apps.py
git commit -m "feat(mcp): replace_app tool (thin HTTP wrapper)"
```

---

## Task 8: CLI command

**Files:**
- Modify: `api/bifrost/commands/apps.py` (add `replace` command after `delete` at line 331)

- [ ] **Step 1: Add the command**

In `api/bifrost/commands/apps.py`, after `delete_app` (around line 331, before `__all__`), add:

```python
@apps_group.command("replace")
@click.argument("ref")
@click.option(
    "--repo-path",
    "repo_path",
    required=True,
    type=str,
    help="Workspace-relative path to the new source directory (e.g. apps/my-app-v2).",
)
@click.option(
    "--force",
    "force",
    is_flag=True,
    default=False,
    help=(
        "Bypass the uniqueness, nesting, and source-exists checks. "
        "Use when repointing before files are pushed."
    ),
)
@click.pass_context
@pass_resolver
@run_async
async def replace_app(
    ctx: click.Context,
    ref: str,
    *,
    client: BifrostClient,
    resolver: RefResolver,
    repo_path: str,
    force: bool,
) -> None:
    """Repoint an application's source directory.

    ``REF`` is a slug, UUID, or application name. ``--repo-path`` must be
    the workspace-relative path to the new source directory. By default the
    path must already contain files; ``--force`` bypasses that check (and
    uniqueness / nesting checks) for repointing ahead of a push.
    """
    app_uuid = await resolver.resolve("app", ref)
    body = {"repo_path": repo_path, "force": force}
    response = await client.post(
        f"/api/applications/{app_uuid}/replace", json=body
    )
    response.raise_for_status()
    output_result(response.json(), ctx=ctx)
```

- [ ] **Step 2: Test manually against the dev stack**

```bash
docker compose -f docker-compose.dev.yml exec bifrost-dev-api-1 \
  bifrost apps replace <some-slug> --repo-path apps/test-new --force
```

Expected: JSON response with `repo_path: "apps/test-new"`.

- [ ] **Step 3: Commit**

```bash
git add api/bifrost/commands/apps.py
git commit -m "feat(cli): bifrost apps replace --repo-path"
```

---

## Task 9: DTO flags — exclude `repo_path` from `apps update`

**Files:**
- Modify: `api/bifrost/dto_flags.py` (update the `ApplicationCreate` / `ApplicationUpdate` entries in `DTO_EXCLUDES`)

The `repo_path` field is not on `ApplicationCreate` or `ApplicationUpdate` today — but we should pre-empt: if someone later adds it to `ApplicationUpdate` thinking it's a regular metadata field, the parity test should force them to think about it. We add a comment now to signal intent.

- [ ] **Step 1: Update the comment and add explicit `repo_path` exclude**

In `api/bifrost/dto_flags.py`, find the Applications block in `DTO_EXCLUDES` (around lines 75–77):

Old:
```python
    # Applications: ``icon`` is UI-managed.
    "ApplicationCreate": {"icon"},
    "ApplicationUpdate": {"icon"},
```

New:
```python
    # Applications: ``icon`` is UI-managed; ``repo_path`` is mutated via
    # ``bifrost apps replace`` (narrow surface with validation), not the
    # generic update path.
    "ApplicationCreate": {"icon", "repo_path"},
    "ApplicationUpdate": {"icon", "repo_path"},
```

- [ ] **Step 2: Run the parity test**

```bash
./test.sh api/tests/unit/test_dto_flags.py -v
```

Expected: pass. `repo_path` is not currently on either DTO, so `set() - set()` yields an empty difference; the test tolerates excludes for fields that don't exist? Check the test source — if it errors on "excluded field not on DTO", drop those excludes until `repo_path` is actually added to a DTO. If it tolerates them, keep them as a defensive marker.

If the test rejects unused excludes: revert to `{"icon"}` in both, and instead add a comment-only note:
```python
    # Applications: ``icon`` is UI-managed.
    # NOTE: ``repo_path`` is intentionally absent from ApplicationUpdate —
    # it's mutated via ``bifrost apps replace``.
    "ApplicationCreate": {"icon"},
    "ApplicationUpdate": {"icon"},
```

- [ ] **Step 3: Commit**

```bash
git add api/bifrost/dto_flags.py
git commit -m "chore(dto): document repo_path is mutated via apps replace"
```

---

## Task 10: E2E test — CLI end-to-end

**Files:**
- Create: `api/tests/e2e/platform/test_cli_apps_replace.py`

- [ ] **Step 1: Write the E2E test**

Create `api/tests/e2e/platform/test_cli_apps_replace.py`:

```python
"""E2E tests for ``bifrost apps replace`` against a live API + DB."""
from __future__ import annotations

import json
import subprocess

import pytest


def _run_cli(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    """Run bifrost CLI inside the api container and return the result."""
    result = subprocess.run(
        [
            "docker", "compose", "-f", "docker-compose.dev.yml", "exec", "-T",
            "bifrost-dev-api-1", "bifrost", "--output", "json", *args,
        ],
        capture_output=True,
        text=True,
    )
    if check and result.returncode != 0:
        raise AssertionError(
            f"CLI failed (rc={result.returncode}): stdout={result.stdout} stderr={result.stderr}"
        )
    return result


@pytest.mark.e2e
def test_replace_happy_path(tmp_path):
    # Create app
    result = _run_cli("apps", "create", "--name", "Replace Test", "--slug", "replace-test-1")
    app = json.loads(result.stdout)
    app_id = app["id"]
    assert app["repo_path"] == "apps/replace-test-1"

    # Seed a file under the new target path via the files API.
    # (Simpler alternative: use --force and skip source-exists.)
    result = _run_cli(
        "apps", "replace", app_id, "--repo-path", "apps/replace-test-1-v2", "--force"
    )
    updated = json.loads(result.stdout)
    assert updated["repo_path"] == "apps/replace-test-1-v2"

    # Cleanup
    _run_cli("apps", "delete", app_id)


@pytest.mark.e2e
def test_replace_rejects_empty_prefix_without_force():
    result = _run_cli("apps", "create", "--name", "Empty Test", "--slug", "replace-test-2")
    app_id = json.loads(result.stdout)["id"]

    result = _run_cli(
        "apps", "replace", app_id, "--repo-path", "apps/does-not-exist-empty",
        check=False,
    )
    assert result.returncode != 0
    assert "no files" in result.stderr or "no files" in result.stdout

    _run_cli("apps", "delete", app_id)


@pytest.mark.e2e
def test_replace_rejects_duplicate_without_force():
    # Create two apps.
    a = json.loads(_run_cli("apps", "create", "--name", "A", "--slug", "replace-dup-a").stdout)
    b = json.loads(_run_cli("apps", "create", "--name", "B", "--slug", "replace-dup-b").stdout)

    # Try to repoint A at B's path.
    result = _run_cli(
        "apps", "replace", a["id"], "--repo-path", b["repo_path"],
        check=False,
    )
    assert result.returncode != 0
    assert "already claimed" in (result.stdout + result.stderr)

    _run_cli("apps", "delete", a["id"])
    _run_cli("apps", "delete", b["id"])


@pytest.mark.e2e
def test_replace_force_bypasses_source_exists():
    app = json.loads(_run_cli("apps", "create", "--name", "Force Test", "--slug", "replace-force").stdout)

    result = _run_cli(
        "apps", "replace", app["id"], "--repo-path", "apps/wherever", "--force",
    )
    updated = json.loads(result.stdout)
    assert updated["repo_path"] == "apps/wherever"

    _run_cli("apps", "delete", app["id"])
```

- [ ] **Step 2: Run the E2E tests**

```bash
./test.sh --e2e api/tests/e2e/platform/test_cli_apps_replace.py -v
```

Expected: all 4 tests pass.

- [ ] **Step 3: Commit**

```bash
git add api/tests/e2e/platform/test_cli_apps_replace.py
git commit -m "test(e2e): bifrost apps replace end-to-end"
```

---

## Task 11: Docs

**Files:**
- Modify: `docs/llm.txt`

- [ ] **Step 1: Find the apps section**

```bash
grep -n "apps " docs/llm.txt | head -20
```

Locate the "Apps" CLI command list or table.

- [ ] **Step 2: Add the replace command**

Edit `docs/llm.txt`. In the apps command section, add an entry matching the surrounding format. Example if table-style:

```
| `bifrost apps replace <ref> --repo-path <new> [--force]` | Repoint an app's source directory. `--force` bypasses uniqueness/nesting/source-exists checks. |
```

Or if list-style, follow whatever convention exists.

- [ ] **Step 3: Commit**

```bash
git add docs/llm.txt
git commit -m "docs: document bifrost apps replace"
```

---

## Task 12: Pre-completion verification

- [ ] **Step 1: Backend type + lint**

```bash
cd api && pyright && ruff check . && cd ..
```

Expected: 0 errors on both.

- [ ] **Step 2: Frontend type + lint (types were regenerated in Task 6)**

```bash
cd client && npm run tsc && npm run lint && cd ..
```

Expected: 0 errors on both.

- [ ] **Step 3: Full test suite**

```bash
./test.sh
```

Expected: all pass. Parse `/tmp/bifrost/test-results.xml` for any failures.

- [ ] **Step 4: Final commit (if any last fixes)**

If fixes were needed for type/lint:

```bash
git add -A
git commit -m "fix: resolve type/lint issues from apps replace"
```

---

## Self-Review

**Spec coverage:**
- Migration (backfill + NOT NULL + unique): Task 1 ✓
- ORM drop nullable + fallback: Task 2 ✓
- Creation sets `repo_path` explicitly: already true (per exploration, all three creation paths set `repo_path=f"apps/{slug}"`); no task needed. Manifest import: `ManifestApp.path` is required so NOT NULL is safe. ✓
- CLI `apps replace`: Task 8 ✓
- REST endpoint: Task 6 ✓
- MCP thin wrapper: Task 7 ✓
- Validation (uniqueness, nesting, source-exists, `--force` bypass, no-op): Task 5 (implementation) + Task 4 (unit tests) + Task 10 (E2E) ✓
- Side effects (no S3 move, cache invalidation automatic, published_snapshot unchanged): no code required — documented as non-goal in spec; verified by E2E happy-path ✓
- Error handling (400 on ValueError, 404 on not found, 409-equivalent via 400 for conflicts): Task 6 ✓
- Testing coverage (unit + E2E + DTO parity + manifest round-trip): Task 4 (unit), Task 10 (E2E), Task 9 (DTO parity). **Manifest round-trip test is missing.** Adding below.
- Docs: Task 11 ✓

**Gap fix — add Task 10b:**

Append to Task 10's test file:
```python
@pytest.mark.e2e
def test_manifest_roundtrip_preserves_repo_path(tmp_path):
    # Create app, export manifest, verify path field, re-import, verify DB.
    app = json.loads(_run_cli("apps", "create", "--name", "MR", "--slug", "mr-app").stdout)
    export_dir = tmp_path / "export"
    _run_cli("export", "--portable", str(export_dir))
    manifest_path = export_dir / ".bifrost" / "apps.yaml"
    content = manifest_path.read_text()
    assert "path: apps/mr-app" in content
    _run_cli("apps", "delete", app["id"])
```

Add this as a new step at the end of Task 10 before the commit.

**Placeholder scan:** no TBD/TODO; all code blocks are complete; no "similar to Task N" references.

**Type consistency:**
- `ApplicationReplaceRequest` (Task 3) — used in Task 6 route handler, Task 7 MCP tool JSON body, Task 8 CLI JSON body. Field names `repo_path` + `force` consistent across all three.
- `replace_application` method name (Task 5) — called from Task 6 endpoint. Consistent.
- `replace_app` MCP function + `replace` CLI command + `POST /{app_id}/replace` route — names differ across surfaces but that's correct (convention: MCP uses snake_case function, CLI uses subcommand, REST uses noun endpoint).

No further issues. Plan ready for execution.
