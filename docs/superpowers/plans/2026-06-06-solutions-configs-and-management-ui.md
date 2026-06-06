# Solutions: configs ownership + management UI — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make configs a solution-owned entity (declaration-vs-value split) and build the operator-facing Solutions management UI (list, detail, drag-and-drop install, delete, install-local editing, read-only badge).

**Architecture:** Two passes, each independently green/shippable. **Part 1** (backend) adds a `SolutionConfigSchema` declaration table that travels in the bundle (no values, ever); install config *values* stay plain instance-owned `Config` rows. Deploy mirrors the existing `_upsert_tables` pattern exactly (ownership guard + uuid5 remap + scoped reconcile) and never touches values. **Part 2** (UI + lifecycle) adds the read endpoints, two-phase zip install (cheap preview → atomic deploy+values under the write-lock), install-local `PATCH`, cascade `DELETE`, and the React Solutions list/detail screens + the admin-only read-only badge.

**Tech Stack:** Python 3.11 / FastAPI / SQLAlchemy (async) / Alembic / Pydantic; React / TypeScript / Vite / shadcn-ui / openapi-react-query. Tests: pytest via `./test.sh`, vitest, Playwright.

**Spec:** `docs/superpowers/specs/2026-06-06-solutions-configs-and-management-ui-design.md`

**Worktree:** `/home/jack/GitHub/bifrost/.claude/worktrees/solutions-success-criteria` (branch `worktree-solutions-success-criteria`). All work happens here, never in the primary checkout.

**Conventions in this codebase (read before starting):**
- Datetime: always `datetime.now(timezone.utc)` with `DateTime(timezone=True)` columns. Never `datetime.utcnow()`.
- Migrations are applied by the `bifrost-init` container (debug) or by `./test.sh stack reset` (test). Set `down_revision` to the current head.
- Run backend tests ONLY via `./test.sh` (Dockerized stack). JUnit XML at `/tmp/bifrost-<project>/test-results.xml`.
- Three-surface parity (CLI / MCP / manifest) is enforced by tests — see CLAUDE.md "Keeping CLI, MCP, and manifest in sync."
- Org scoping goes through `OrgScopedRepository` — never inline `WHERE organization_id == x OR IS NULL`. Read `api/src/repositories/README.md` if touching scoped reads.

---

# PART 1 — Configs as a solution-owned entity (backend)

At the end of Part 1: a Solution can declare configs in `.bifrost/configs.yaml`, they deploy as `SolutionConfigSchema` rows (owned, scoped, remapped), redeploy is non-destructive to values, and runtime resolution finds the install's declaration. No UI yet. Tree green.

## Task 1: `SolutionConfigSchema` ORM model

**Files:**
- Create: `api/src/models/orm/solution_config_schema.py`
- Modify: `api/src/models/orm/__init__.py` (export the new model)
- Test: `api/tests/unit/test_solution_config_schema_model.py`

- [ ] **Step 1: Write the failing test**

```python
# api/tests/unit/test_solution_config_schema_model.py
"""SolutionConfigSchema ORM: a Solution-owned config DECLARATION (no value)."""
import pytest
from uuid import uuid4

from src.models.orm.solutions import Solution
from src.models.orm.solution_config_schema import SolutionConfigSchema


@pytest.mark.e2e
class TestSolutionConfigSchemaModel:
    async def test_insert_and_read_declaration(self, db_session) -> None:
        db = db_session
        sol = Solution(id=uuid4(), slug=f"cfg-{uuid4().hex[:8]}", name="CFG", organization_id=None)
        db.add(sol)
        await db.flush()

        decl = SolutionConfigSchema(
            id=uuid4(),
            solution_id=sol.id,
            key="STRIPE_KEY",
            type="secret",
            required=True,
            description="Stripe secret key",
            default=None,
            position=0,
        )
        db.add(decl)
        await db.flush()

        assert decl.key == "STRIPE_KEY"
        assert decl.required is True
        # The declaration has NO value column — it cannot carry a secret.
        assert not hasattr(decl, "value")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./test.sh tests/unit/test_solution_config_schema_model.py -v`
Expected: FAIL — `ModuleNotFoundError: src.models.orm.solution_config_schema`

- [ ] **Step 3: Write the model**

```python
# api/src/models/orm/solution_config_schema.py
"""SolutionConfigSchema: a Solution-owned config DECLARATION.

A Solution declares the config it NEEDS (key/type/required/description/default);
the INSTALL holds the value as a plain instance-owned ``Config`` row. This table
is portable — it travels in the bundle and round-trips through the manifest. It
has NO ``value`` column by design, so a developer cannot commit a secret.
"""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from src.models.orm.base import Base


class SolutionConfigSchema(Base):
    __tablename__ = "solution_config_schema"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    solution_id: Mapped[UUID] = mapped_column(
        ForeignKey("solutions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    key: Mapped[str] = mapped_column(String(255), nullable=False)
    # string | int | bool | json | secret (matches IntegrationConfigSchema.type)
    type: Mapped[str] = mapped_column(String(50), nullable=False)
    required: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    description: Mapped[str | None] = mapped_column(String(500), default=None, nullable=True)
    # Never set for secret type (a default secret would defeat the value split).
    default: Mapped[str | None] = mapped_column(Text, default=None, nullable=True)
    position: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=text("NOW()"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=text("NOW()"),
        onupdate=lambda: datetime.now(timezone.utc),
    )
```

Confirm the base import path matches the other ORM files (open `api/src/models/orm/config.py` and copy its `Base` import line exactly; if it imports from a different module than `src.models.orm.base`, use that). Then add the export:

```python
# api/src/models/orm/__init__.py — add alongside the other model exports
from src.models.orm.solution_config_schema import SolutionConfigSchema  # noqa: F401
```

- [ ] **Step 4: Create the migration**

First find the current head revision:

Run: `cd api && ls -t alembic/versions/*.py | head -3`
Then open the newest and read its `revision = "..."` line — that string is your `down_revision`. (As of this plan it is `20260606_table_name_sol_scope`, but VERIFY — a later migration may have landed.)

```python
# api/alembic/versions/20260606_solution_config_schema.py
"""solution_config_schema declaration table

Revision ID: 20260606_solution_config_schema
"""
from alembic import op
import sqlalchemy as sa

revision = "20260606_solution_config_schema"
down_revision = "20260606_table_name_sol_scope"  # VERIFY against current head
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "solution_config_schema",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "solution_id",
            sa.Uuid(),
            sa.ForeignKey("solutions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("key", sa.String(length=255), nullable=False),
        sa.Column("type", sa.String(length=50), nullable=False),
        sa.Column("required", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("default", sa.Text(), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
    )
    op.create_index(
        "ix_solution_config_schema_solution_id",
        "solution_config_schema",
        ["solution_id"],
    )
    # One declaration per key per install (solution-scoped uniqueness, mirrors
    # ix_tables_solution_name_unique). solution_id is NOT NULL here, so the
    # partial predicate is belt-and-suspenders / consistent with the table fix.
    op.create_index(
        "ix_solution_config_schema_sol_key_unique",
        "solution_config_schema",
        ["solution_id", "key"],
        unique=True,
        postgresql_where=sa.text("solution_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_solution_config_schema_sol_key_unique", table_name="solution_config_schema")
    op.drop_index("ix_solution_config_schema_solution_id", table_name="solution_config_schema")
    op.drop_table("solution_config_schema")
```

- [ ] **Step 5: Apply the migration to the test stack and run the test**

Run: `./test.sh stack reset && ./test.sh tests/unit/test_solution_config_schema_model.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add api/src/models/orm/solution_config_schema.py api/src/models/orm/__init__.py \
  api/alembic/versions/20260606_solution_config_schema.py \
  api/tests/unit/test_solution_config_schema_model.py
git commit -m "feat(solutions): SolutionConfigSchema declaration table"
```

## Task 2: Uniqueness guard — duplicate key in one bundle → 409

**Files:**
- Test: `api/tests/unit/test_solution_config_schema_model.py` (add a test)

This locks the behavior the deploy upsert (Task 4) must produce: two declarations with the same key in one install violate `ix_solution_config_schema_sol_key_unique`. We assert the DB constraint here so Task 4's pre-check has a spec.

- [ ] **Step 1: Write the failing test**

```python
# append to TestSolutionConfigSchemaModel
    async def test_duplicate_key_same_solution_rejected(self, db_session) -> None:
        import sqlalchemy.exc
        db = db_session
        sol = Solution(id=uuid4(), slug=f"cfg-{uuid4().hex[:8]}", name="CFG", organization_id=None)
        db.add(sol)
        await db.flush()
        db.add(SolutionConfigSchema(id=uuid4(), solution_id=sol.id, key="DUP", type="string"))
        await db.flush()
        db.add(SolutionConfigSchema(id=uuid4(), solution_id=sol.id, key="DUP", type="string"))
        with pytest.raises(sqlalchemy.exc.IntegrityError):
            await db.flush()
```

- [ ] **Step 2: Run to verify** — Run: `./test.sh tests/unit/test_solution_config_schema_model.py::TestSolutionConfigSchemaModel::test_duplicate_key_same_solution_rejected -v` — Expected: PASS (the index from Task 1 already enforces this). If it FAILS, the partial index is wrong — fix the migration before continuing.

- [ ] **Step 3: Commit**

```bash
git add api/tests/unit/test_solution_config_schema_model.py
git commit -m "test(solutions): solution-scoped config key uniqueness"
```

## Task 3: Add `config_schemas` to `SolutionBundle`

**Files:**
- Modify: `api/src/services/solutions/deploy.py` (the `SolutionBundle` dataclass, ~line 172-187)
- Test: `api/tests/unit/test_solution_config_deploy.py` (new)

- [ ] **Step 1: Write the failing test**

```python
# api/tests/unit/test_solution_config_deploy.py
"""Deploy of solution-owned config DECLARATIONS (values never touched)."""
import pytest
from uuid import uuid4

from sqlalchemy import select

from src.models.orm.solutions import Solution
from src.models.orm.solution_config_schema import SolutionConfigSchema
from src.services.solutions.deploy import (
    SolutionBundle,
    SolutionDeployer,
    solution_entity_id,
)


def _cfg(cid: str, key: str, *, required: bool = False, ctype: str = "string") -> dict:
    return {"id": cid, "key": key, "type": ctype, "required": required,
            "description": f"{key} desc", "default": None, "position": 0}


async def _make_install(db, slug: str, org_id=None) -> Solution:
    sol = Solution(id=uuid4(), slug=slug, name=slug.upper(), organization_id=org_id)
    db.add(sol)
    await db.flush()
    return sol


@pytest.mark.e2e
class TestSolutionConfigDeploy:
    async def test_bundle_carries_config_schemas(self) -> None:
        # The dataclass must accept config_schemas; defaults to [].
        b = SolutionBundle(solution=None)  # type: ignore[arg-type]
        assert b.config_schemas == []
        b2 = SolutionBundle(solution=None, config_schemas=[_cfg(str(uuid4()), "K")])  # type: ignore[arg-type]
        assert b2.config_schemas[0]["key"] == "K"
```

- [ ] **Step 2: Run to verify it fails** — Run: `./test.sh tests/unit/test_solution_config_deploy.py::TestSolutionConfigDeploy::test_bundle_carries_config_schemas -v` — Expected: FAIL — `TypeError: __init__() got an unexpected keyword argument 'config_schemas'`

- [ ] **Step 3: Add the field**

```python
# api/src/services/solutions/deploy.py — inside the SolutionBundle dataclass, after `agents`
    config_schemas: list[dict[str, Any]] = field(default_factory=list)
```

- [ ] **Step 4: Run to verify** — Run same command — Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add api/src/services/solutions/deploy.py api/tests/unit/test_solution_config_deploy.py
git commit -m "feat(solutions): SolutionBundle.config_schemas field"
```

## Task 4: Remap + upsert config declarations on deploy

**Files:**
- Modify: `api/src/services/solutions/deploy.py` — `_remapped_bundle` (add config_schemas remap, ~line 307-340), `deploy()` (call new upsert, ~line 228), add `_upsert_config_schemas`, `_reconcile_deletions` (sweep config_schemas)
- Test: `api/tests/unit/test_solution_config_deploy.py`

- [ ] **Step 1: Write the failing tests**

```python
# append to TestSolutionConfigDeploy
    async def test_deploy_upserts_remapped_declarations(self, db_session) -> None:
        db = db_session
        sol = await _make_install(db, f"cfgdep-{uuid4().hex[:8]}")
        manifest_id = str(uuid4())
        await SolutionDeployer(db).deploy(
            SolutionBundle(solution=sol, config_schemas=[_cfg(manifest_id, "API_KEY", required=True, ctype="secret")])
        )
        await db.flush()
        rows = (await db.execute(
            select(SolutionConfigSchema).where(SolutionConfigSchema.solution_id == sol.id)
        )).scalars().all()
        assert len(rows) == 1
        # id is uuid5(install, manifest_id), NOT the manifest id (per-install identity)
        assert rows[0].id == solution_entity_id(sol.id, manifest_id)
        assert rows[0].key == "API_KEY" and rows[0].required is True

    async def test_redeploy_removes_dropped_declaration(self, db_session) -> None:
        db = db_session
        sol = await _make_install(db, f"cfgrec-{uuid4().hex[:8]}")
        a, b = str(uuid4()), str(uuid4())
        await SolutionDeployer(db).deploy(
            SolutionBundle(solution=sol, config_schemas=[_cfg(a, "A"), _cfg(b, "B")])
        )
        await db.flush()
        await SolutionDeployer(db).deploy(
            SolutionBundle(solution=sol, config_schemas=[_cfg(a, "A")])
        )
        await db.flush()
        keys = {r.key for r in (await db.execute(
            select(SolutionConfigSchema).where(SolutionConfigSchema.solution_id == sol.id)
        )).scalars().all()}
        assert keys == {"A"}

    async def test_duplicate_key_in_bundle_is_409(self, db_session) -> None:
        from src.services.solutions.deploy import SolutionDeployConflict
        db = db_session
        sol = await _make_install(db, f"cfgdup-{uuid4().hex[:8]}")
        with pytest.raises(SolutionDeployConflict):
            await SolutionDeployer(db).deploy(
                SolutionBundle(solution=sol, config_schemas=[_cfg(str(uuid4()), "X"), _cfg(str(uuid4()), "X")])
            )
```

- [ ] **Step 2: Run to verify they fail** — Run: `./test.sh tests/unit/test_solution_config_deploy.py -v` — Expected: FAIL (declarations not deployed; no upsert wired)

- [ ] **Step 3: Implement**

In `_remapped_bundle`, deep-copy + remap config_schemas (own id only — declarations have no cross-refs):

```python
# in _remapped_bundle, alongside the other deep-copies (~line 311):
        config_schemas = [copy.deepcopy(e) for e in bundle.config_schemas]
# in Pass 1, include them in the id-remap loop (~line 314):
        for entry in workflows + tables + apps + forms + agents + config_schemas:
# in the returned SolutionBundle(...) (~line 332), add:
            config_schemas=config_schemas,
```

In `deploy()`, call the new upsert (after `_upsert_agents`, ~line 231):

```python
        await self._upsert_config_schemas(solution, rb.config_schemas)
```

Add the upsert method (mirror `_upsert_tables`):

```python
    async def _upsert_config_schemas(
        self, solution: Solution, config_schemas: list[dict[str, Any]]
    ) -> None:
        """Upsert this install's config DECLARATIONS (key/type/required/desc/
        default). Config VALUES are never written here — they are instance-owned
        Config rows set by the operator. Mirrors :meth:`_upsert_tables`:
        solution-scoped key uniqueness, ownership guard, full-replace.
        """
        sid = solution.id

        # Key is unique per install (ix_solution_config_schema_sol_key_unique).
        # Two declarations sharing a key in THIS bundle would hit the index as an
        # IntegrityError → 500. Catch deterministically as a 409.
        seen: set[str] = set()
        for entry in config_schemas:
            k = str(entry.get("key"))
            if k in seen:
                raise SolutionDeployConflict(
                    f"two config declarations named '{k}' in this Solution bundle; "
                    f"config keys must be unique within an install"
                )
            seen.add(k)

        for entry in config_schemas:
            cid = UUID(entry["id"])
            await self._guard_owner(SolutionConfigSchema, cid, sid)  # see below
            values: dict[str, Any] = {
                "solution_id": sid,
                "key": entry["key"],
                "type": entry["type"],
                "required": bool(entry.get("required", False)),
                "description": entry.get("description"),
                "default": entry.get("default"),
                "position": int(entry.get("position", 0)),
            }
            await Upsert(
                model=SolutionConfigSchema, id=cid, values=values, match_on="id"
            ).execute(self.db)
```

There is an existing ownership-guard helper near line 943 (`_guard_owner` / the inline guard used by tables/forms). Open it and reuse the SAME helper. If tables use an inline guard rather than a shared method, copy the inline pattern instead:

```python
            row = (await self.db.execute(
                select(SolutionConfigSchema.solution_id).where(SolutionConfigSchema.id == cid)
            )).first()
            if row is not None and row[0] != sid:
                owner = row[0]
                raise SolutionDeployConflict(
                    f"config declaration {cid} is already owned by "
                    f"{'_repo/' if owner is None else f'solution {owner}'}; "
                    f"a bundle may not reuse another owner's entity id"
                )
```

Add config_schemas to `_reconcile_deletions` (~line 959): query existing `SolutionConfigSchema.id WHERE solution_id == sid`, delete those `NOT IN {remapped bundle ids}`. Follow the exact shape used for tables in that method. **Decision (do this, don't deliberate):** perform the delete inside `_reconcile_deletions` but do NOT add a new count to the returned tuple or to `DeployResult` — the reconcile test asserts behavior (the dropped key is gone), not a count, and threading a 6th count through `deploy()`'s tuple-unpacking + `DeployResult` is churn with no consumer. Import `SolutionConfigSchema` at the top of `deploy.py`.

Add the import near the other ORM imports in `deploy.py`:

```python
from src.models.orm.solution_config_schema import SolutionConfigSchema
```

- [ ] **Step 4: Run to verify** — Run: `./test.sh tests/unit/test_solution_config_deploy.py -v` — Expected: PASS (all four)

- [ ] **Step 5: Verify existing deploy tests still pass**

Run: `./test.sh tests/unit/test_solution_deploy_reconcile.py -v`
Expected: PASS (reconcile change didn't break tables/workflows)

- [ ] **Step 6: Commit**

```bash
git add api/src/services/solutions/deploy.py api/tests/unit/test_solution_config_deploy.py
git commit -m "feat(solutions): deploy config declarations (remap + scoped upsert + reconcile)"
```

## Task 5: Manifest model + generator + collector for `configs.yaml`

**Files:**
- Modify: `api/bifrost/manifest.py` (add `ManifestSolutionConfigSchema`)
- Modify: `api/bifrost/commands/solution.py` (add `_collect_config_schemas`, wire into the bundle build)
- Modify: `api/src/services/manifest_generator.py` (serialize declarations) — **only if** the platform generates `configs.yaml`; if Part-1 deploy reads `configs.yaml` purely from the workspace, generator support can be deferred to where solution export is generated. Check how tables flow and match it.
- Test: `api/tests/unit/test_solution_config_manifest.py` (new)

- [ ] **Step 1: Write the failing test**

```python
# api/tests/unit/test_solution_config_manifest.py
"""configs.yaml round-trip: declarations only, never a value."""
import pathlib
import textwrap
import pytest

from bifrost.commands.solution import _collect_config_schemas


def test_collect_config_schemas_reads_declarations(tmp_path: pathlib.Path) -> None:
    bdir = tmp_path / ".bifrost"
    bdir.mkdir()
    (bdir / "configs.yaml").write_text(textwrap.dedent("""
        configs:
          STRIPE_KEY:
            id: 11111111-1111-1111-1111-111111111111
            key: STRIPE_KEY
            type: secret
            required: true
            description: Stripe secret key
          REGION:
            id: 22222222-2222-2222-2222-222222222222
            key: REGION
            type: string
            required: false
            default: us-east
            description: Region
    """))
    entries = _collect_config_schemas(tmp_path)
    by_key = {e["key"]: e for e in entries}
    assert by_key["STRIPE_KEY"]["required"] is True
    assert by_key["STRIPE_KEY"]["type"] == "secret"
    assert "value" not in by_key["STRIPE_KEY"]  # never a value
    assert by_key["REGION"]["default"] == "us-east"


def test_collect_config_schemas_missing_file_returns_empty(tmp_path: pathlib.Path) -> None:
    assert _collect_config_schemas(tmp_path) == []
```

- [ ] **Step 2: Run to verify it fails** — Run: `./test.sh tests/unit/test_solution_config_manifest.py -v` — Expected: FAIL — `ImportError: cannot import name '_collect_config_schemas'`

- [ ] **Step 3: Implement the collector (mirror `_collect_tables`)**

```python
# api/bifrost/commands/solution.py — new function near _collect_tables (~line 400)
def _collect_config_schemas(workspace: pathlib.Path) -> list[dict]:
    """Read config DECLARATIONS from .bifrost/configs.yaml (keyed by key/UUID).

    Declarations ONLY — there is no ``value`` field by design. Config values are
    instance-owned and supplied at install time; local dev reads them from .env.
    """
    cfg_file = workspace / ".bifrost" / "configs.yaml"
    if not cfg_file.is_file():
        return []
    data = yaml.safe_load(cfg_file.read_text()) or {}
    raw = data.get("configs", {})
    entries: list[dict] = []
    for key, body in raw.items():
        if not isinstance(body, dict):
            continue
        entries.append({
            "id": body.get("id", key),
            "key": body.get("key") or key,
            "type": body.get("type", "string"),
            "required": bool(body.get("required", False)),
            "description": body.get("description"),
            "default": body.get("default"),
            "position": int(body.get("position", 0)),
        })
    return entries
```

Wire it into wherever the CLI builds the `SolutionBundle` / deploy request (find where `_collect_tables(workspace)` is called and add `config_schemas=_collect_config_schemas(workspace)` to the same payload). The deploy request DTO is free-form for entity lists (like `tables`), so pass it through identically.

Add the manifest model (mirror `ManifestConfig` shape, declarations only):

```python
# api/bifrost/manifest.py — near ManifestConfig
class ManifestSolutionConfigSchema(BaseModel):
    """A solution-owned config DECLARATION (portable; never a value)."""
    id: str
    key: str
    type: str = "string"
    required: bool = False
    description: str | None = None
    default: str | None = None
    position: int = 0
```

- [ ] **Step 4: Run to verify** — Run: `./test.sh tests/unit/test_solution_config_manifest.py -v` — Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add api/bifrost/manifest.py api/bifrost/commands/solution.py \
  api/tests/unit/test_solution_config_manifest.py
git commit -m "feat(solutions): configs.yaml declaration collector + manifest model"
```

## Task 6: Server-side deploy request wiring (config_schemas reach the deployer)

**Files:**
- Modify: `api/src/routers/solutions.py` and/or the deploy request DTO + the request→SolutionBundle mapping (find where the deploy endpoint builds `SolutionBundle` from the request: it maps `request.tables` → `bundle.tables`, etc.)
- Test: `api/tests/e2e/platform/test_solution_config_e2e.py` (new)

- [ ] **Step 1: Write the failing E2E test**

```python
# api/tests/e2e/platform/test_solution_config_e2e.py
"""E2E: declare a config in a Solution, deploy it, see the declaration land."""
import pytest
from uuid import uuid4


@pytest.mark.e2e
async def test_deploy_solution_with_config_declaration(async_client, superuser_headers) -> None:
    # create install
    r = await async_client.post("/api/solutions", headers=superuser_headers,
        json={"slug": f"e2ecfg-{uuid4().hex[:8]}", "name": "E2E CFG"})
    assert r.status_code in (200, 201), r.text
    sid = r.json()["id"]

    # deploy with a config declaration
    r = await async_client.post(f"/api/solutions/{sid}/deploy", headers=superuser_headers,
        json={"config_schemas": [{
            "id": str(uuid4()), "key": "API_KEY", "type": "secret",
            "required": True, "description": "needed", "position": 0,
        }]})
    assert r.status_code == 200, r.text

    # read it back (Part 2 adds /entities; for Part 1 assert via deploy response
    # or a direct list endpoint if present). At minimum: deploy returns 200.
```

Use the existing fixtures from a sibling test (`grep -l "superuser_headers\|async_client" api/tests/e2e/platform/test_solution_*.py` and copy the exact fixture names/signatures that file uses — fixture names vary by suite).

- [ ] **Step 2: Run to verify it fails** — Run: `./test.sh tests/e2e/platform/test_solution_config_e2e.py -v` — Expected: FAIL (deploy ignores `config_schemas` — the request DTO drops it)

- [ ] **Step 3: Implement** — In the deploy endpoint's request model, add `config_schemas: list[dict[str, Any]] = []` (mirror how `tables` is typed). In the request→`SolutionBundle` mapping, add `config_schemas=request.config_schemas`. If the DTO uses a typed model per entity, add `ManifestSolutionConfigSchema` import server-side; if it passes raw dicts (like tables), match that.

- [ ] **Step 4: Run to verify** — Run same command — Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add api/src/routers/solutions.py api/tests/e2e/platform/test_solution_config_e2e.py
git commit -m "feat(solutions): deploy endpoint accepts config_schemas"
```

## Task 7: Solution-first config resolution at runtime

**Files:**
- Modify: `api/src/repositories/config.py` — add solution-scope awareness to the read path used by the SDK, mirroring how tables resolve via the install's `solution_id`.
- Test: `api/tests/unit/test_solution_config_resolution.py` (new)

**Read first:** how tables do solution-first resolution — `grep -n "_resolve_solution_table_by_name\|solution_id" api/src/routers/tables.py` and `api/src/repositories/README.md`. The config value still comes from the instance `Config` row; the declaration only confirms *which* key belongs to the install. The minimal Part-1 requirement: an install's declared key resolves to that install's value when the caller is in the install's scope, falling through to org→global otherwise. **Reuse `OrgScopedRepository`; do not write an inline `OR organization_id IS NULL` query.**

- [ ] **Step 1: Write the failing test**

```python
# api/tests/unit/test_solution_config_resolution.py
"""An install's config value resolves for that install's scope."""
import pytest
from uuid import uuid4

from src.models.orm.solutions import Solution
from src.models.orm.solution_config_schema import SolutionConfigSchema
from src.repositories.config import ConfigRepository
from src.models.contracts.config import SetConfigRequest
from src.models.orm.config import ConfigType


@pytest.mark.e2e
async def test_install_value_resolves_in_install_scope(db_session) -> None:
    db = db_session
    org_id = uuid4()
    sol = Solution(id=uuid4(), slug=f"res-{uuid4().hex[:8]}", name="R", organization_id=org_id)
    db.add(sol)
    db.add(SolutionConfigSchema(id=uuid4(), solution_id=sol.id, key="REGION", type="string"))
    await db.flush()

    # operator sets the value (instance-owned Config row in the install's org)
    repo = ConfigRepository(db, org_id=org_id, is_superuser=True)
    await repo.set_config(
        SetConfigRequest(key="REGION", value="us-west", type=ConfigType.STRING, organization_id=org_id),
        updated_by="op@test",
    )
    await db.flush()

    # a reader in the install's org gets the value
    reader = ConfigRepository(db, org_id=org_id, is_superuser=True)
    merged = await reader.merged_for_sdk()
    assert merged.get("REGION") == "us-west"
```

- [ ] **Step 2: Run to verify** — Run: `./test.sh tests/unit/test_solution_config_resolution.py -v` — Expected: this may already PASS (value is a normal org-scoped Config). If it passes, the Part-1 resolution requirement is met by the existing cascade — **document that** and skip implementation. If a Solution-scoped read needs the declaration to gate visibility, implement the solution-first lookup mirroring `tables.py`. Only add code if a test fails.

- [ ] **Step 3: Commit (test + any code)**

```bash
git add api/tests/unit/test_solution_config_resolution.py api/src/repositories/config.py
git commit -m "test(solutions): install config value resolves in install scope"
```

## Task 8: DTO-parity + Part-1 verification

**Files:** none new — verification gate.

- [ ] **Step 1: Run the DTO-parity test** — Run: `./test.sh tests/unit/test_dto_flags.py -v` — Expected: PASS. If it fails because a config-schema field is missing from a CLI command/MCP tool, either add it or add to `DTO_EXCLUDES` in `api/bifrost/dto_flags.py` with a one-line reason.

- [ ] **Step 2: Run the full solution suite** — Run: `./test.sh tests/unit/test_solution_*.py tests/unit/test_solution_config_*.py` then `./test.sh tests/e2e/platform/test_solution_*.py` — Expected: all PASS.

- [ ] **Step 3: Quality gates** — Run: `cd api && ruff check . && pyright` — Expected: clean (the known aiobotocore host false-positive aside).

- [ ] **Step 4: Commit any fixes**

```bash
git add -A && git commit -m "chore(solutions): Part 1 verification — configs ownership green"
```

---

# PART 2 — Solutions management UI + lifecycle (backend endpoints + React)

At the end of Part 2: an admin sees `/solutions`, drags a zip to install (preview → scope → values → deploy), opens an install to see everything it owns, navigates to entities and back, edits install-local fields, deletes with a guarded cascade, and sees the read-only badge (admin-only, linking to the owning solution) on all entity list pages.

## Task 9: `solution_id` on the five public response models

**Files:**
- Modify: the five Pydantic public models — find each with `grep -rn "is_solution_managed" api/shared/models.py api/src/models/contracts/`. Add `solution_id: UUID | None = None` next to `is_solution_managed` on `AgentPublic`, `ApplicationPublic`, `FormPublic`, `TablePublic`, `WorkflowMetadata`.
- Modify: wherever each is built from its ORM row (the response serializers) to populate `solution_id`.
- Test: extend an existing public-model serialization test per entity, or add `api/tests/unit/test_solution_id_on_public_models.py`.

- [ ] **Step 1: Write the failing test**

```python
# api/tests/unit/test_solution_id_on_public_models.py
"""Public entity models expose solution_id so the UI badge can link to the owner."""
from shared.models import TablePublic  # adjust import to actual location


def test_table_public_has_solution_id() -> None:
    assert "solution_id" in TablePublic.model_fields
```

Add one assertion per model (Agent/Application/Form/Table/Workflow) importing each from its real module (resolve with the grep above).

- [ ] **Step 2: Run to verify it fails** — Run: `./test.sh tests/unit/test_solution_id_on_public_models.py -v` — Expected: FAIL (`solution_id` not a field)

- [ ] **Step 3: Implement** — Add `solution_id: UUID | None = None` to each model and populate it in each serializer. `solution_id` is a response-only env field; confirm it is NOT added to any portable/manifest model or scrub rule (it must not appear in `api/bifrost/portable.py` or `ManifestX`).

- [ ] **Step 4: Run to verify** — Run same command — Expected: PASS

- [ ] **Step 5: Regenerate types**

Run: `cd client && OPENAPI_URL=<dev-or-test-api-url>/openapi.json npm run generate:types` (get URL from `./debug.sh status`; under netbird use the worktree test-stack API per the worktree-type-gen memory).
Then: `grep -n "solution_id" client/src/lib/v1.d.ts` — Expected: present on the five public types.

- [ ] **Step 6: Commit**

```bash
git add api/ client/src/lib/v1.d.ts api/tests/unit/test_solution_id_on_public_models.py
git commit -m "feat(solutions): expose solution_id on public entity models for badge linking"
```

## Task 10: `GET /api/solutions/{id}/entities` aggregate endpoint

**Files:**
- Modify: `api/src/routers/solutions.py` (new endpoint)
- Modify: `api/src/models/contracts/solutions.py` (response model `SolutionEntities`)
- Test: `api/tests/e2e/platform/test_solution_entities_endpoint.py` (new)

- [ ] **Step 1: Write the failing test**

```python
# api/tests/e2e/platform/test_solution_entities_endpoint.py
import pytest
from uuid import uuid4


@pytest.mark.e2e
async def test_entities_endpoint_returns_owned_and_config_status(async_client, superuser_headers) -> None:
    r = await async_client.post("/api/solutions", headers=superuser_headers,
        json={"slug": f"ent-{uuid4().hex[:8]}", "name": "ENT", "organization_id": None})
    sid = r.json()["id"]
    await async_client.post(f"/api/solutions/{sid}/deploy", headers=superuser_headers,
        json={"config_schemas": [{"id": str(uuid4()), "key": "API_KEY", "type": "secret",
                                  "required": True, "description": "x", "position": 0}]})

    r = await async_client.get(f"/api/solutions/{sid}/entities", headers=superuser_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert "workflows" in body and "apps" in body and "forms" in body
    assert "agents" in body and "tables" in body and "configs" in body
    # the required, unset declaration shows up as needing a value
    assert "API_KEY" in body["required_configs_unset"]
    cfg = next(c for c in body["configs"] if c["key"] == "API_KEY")
    assert cfg["required"] is True and cfg["value_set"] is False
```

- [ ] **Step 2: Run to verify it fails** — Run: `./test.sh tests/e2e/platform/test_solution_entities_endpoint.py -v` — Expected: FAIL (404 — endpoint missing)

- [ ] **Step 3: Implement** — Add the response model and endpoint. Query each owned-entity table `WHERE solution_id == sid` (these are identity-style direct queries, not cascade reads). For configs: list `SolutionConfigSchema WHERE solution_id == sid`; for each, check whether an instance `Config` value exists for `(install.organization_id, key)` → `value_set`. Compute `required_configs_unset = [key for decl if decl.required and not value_set]`. Gate the endpoint `CurrentSuperuser`.

```python
# api/src/models/contracts/solutions.py
class SolutionConfigStatus(BaseModel):
    id: UUID
    key: str
    type: str
    required: bool
    description: str | None = None
    value_set: bool

class SolutionEntities(BaseModel):
    solution: Solution
    workflows: list[dict] = Field(default_factory=list)
    apps: list[dict] = Field(default_factory=list)
    forms: list[dict] = Field(default_factory=list)
    agents: list[dict] = Field(default_factory=list)
    tables: list[dict] = Field(default_factory=list)
    configs: list[SolutionConfigStatus] = Field(default_factory=list)
    required_configs_unset: list[str] = Field(default_factory=list)
```

(For the entity lists, return the existing public models for each type rather than raw dicts if convenient — match what the list pages already consume so the UI reuses card components.)

- [ ] **Step 4: Run to verify** — Run same command — Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add api/src/routers/solutions.py api/src/models/contracts/solutions.py \
  api/tests/e2e/platform/test_solution_entities_endpoint.py
git commit -m "feat(solutions): GET /solutions/{id}/entities aggregate"
```

## Task 11: Zip install — preview endpoint

**Files:**
- Modify: `api/src/routers/solutions.py` (`POST /api/solutions/install/preview`)
- Create: `api/src/services/solutions/zip_install.py` (unzip-to-temp + manifest parse; no build, no persist)
- Test: `api/tests/unit/test_solution_zip_install.py` + e2e

- [ ] **Step 1: Write the failing test**

```python
# api/tests/unit/test_solution_zip_install.py
"""Preview parses a zipped workspace's manifests without persisting anything."""
import io
import zipfile
import pytest

from src.services.solutions.zip_install import preview_zip


def _zip_workspace(files: dict[str, str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, content in files.items():
            z.writestr(name, content)
    return buf.getvalue()


def test_preview_lists_entities_and_configs() -> None:
    data = _zip_workspace({
        ".bifrost/configs.yaml": "configs:\n  API_KEY:\n    key: API_KEY\n    type: secret\n    required: true\n    description: needed\n",
        "workflows/main.py": "def run():\n    return 1\n",
    })
    preview = preview_zip(data)
    assert preview.config_schemas[0]["key"] == "API_KEY"
    assert preview.config_schemas[0]["required"] is True
    assert any(w for w in preview.workflows)  # found the workflow file
    # nothing persisted — preview is pure parse
```

- [ ] **Step 2: Run to verify it fails** — Run: `./test.sh tests/unit/test_solution_zip_install.py -v` — Expected: FAIL (`ModuleNotFoundError`)

- [ ] **Step 3: Implement** `preview_zip(data: bytes) -> PreviewResult` — extract to a temp dir (use `tempfile.TemporaryDirectory`; validate against zip-slip by rejecting members whose resolved path escapes the temp root), then reuse the Part-1 collectors (`_collect_config_schemas`, `_collect_tables`, the workflow/app/form/agent collectors) against the temp workspace. Return a dataclass/Pydantic `PreviewResult` with the entity lists + `config_schemas`. **No DB writes, no S3, no build.**

Add the endpoint:

```python
@router.post("/api/solutions/install/preview", response_model=...)
async def install_preview(file: UploadFile, ctx: Context, user: CurrentSuperuser):
    data = await file.read()
    return preview_zip(data)
```

- [ ] **Step 4: Run to verify** — Run same command — Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add api/src/services/solutions/zip_install.py api/src/routers/solutions.py \
  api/tests/unit/test_solution_zip_install.py
git commit -m "feat(solutions): zip install preview (parse-only, zip-slip safe)"
```

## Task 12: Zip install — commit endpoint (atomic deploy + values under lock)

**Files:**
- Modify: `api/src/routers/solutions.py` (`POST /api/solutions/install`)
- Modify: `api/src/services/solutions/zip_install.py` (`install_zip(...)`)
- Test: e2e `api/tests/e2e/platform/test_solution_zip_install_e2e.py`

- [ ] **Step 1: Write the failing E2E test**

```python
# api/tests/e2e/platform/test_solution_zip_install_e2e.py
import io, zipfile
import pytest
from uuid import uuid4


def _zip(files):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for n, c in files.items():
            z.writestr(n, c)
    return buf.getvalue()


@pytest.mark.e2e
async def test_install_zip_creates_install_and_sets_required_value(async_client, superuser_headers) -> None:
    data = _zip({
        ".bifrost/solution.yaml": f"slug: zipsol-{uuid4().hex[:8]}\nname: ZipSol\n",
        ".bifrost/configs.yaml": "configs:\n  API_KEY:\n    key: API_KEY\n    type: secret\n    required: true\n    description: needed\n",
        "workflows/main.py": "def run():\n    return 1\n",
    })
    r = await async_client.post(
        "/api/solutions/install", headers=superuser_headers,
        files={"file": ("sol.zip", data, "application/zip")},
        data={"organization_id": "", "config_values": '{"API_KEY": "sk_live_x"}'},
    )
    assert r.status_code in (200, 201), r.text
    sid = r.json()["id"]
    ent = (await async_client.get(f"/api/solutions/{sid}/entities", headers=superuser_headers)).json()
    # the required value was applied atomically → not in unset
    assert "API_KEY" not in ent["required_configs_unset"]
```

(Match the exact multipart field convention the endpoint expects; adjust `data`/`files` after implementing. Read how an existing upload endpoint in the codebase accepts `UploadFile` + form fields for the exact pattern.)

- [ ] **Step 2: Run to verify it fails** — Run: `./test.sh tests/e2e/platform/test_solution_zip_install_e2e.py -v` — Expected: FAIL

- [ ] **Step 3: Implement** `install_zip(db, data, *, organization_id, config_values, slug?, name?)`:
  1. Acquire the per-install `solution_write_lock` (reuse `api/src/services/solutions/write_lock.py`).
  2. Resolve-or-create the `Solution` (slug from `.bifrost/solution.yaml` or request; scope from `organization_id`).
  3. Build the `SolutionBundle` from the temp workspace (the Part-1 collectors), run `SolutionDeployer.deploy`, commit, `finalize_s3`.
  4. **In the same locked section, after deploy:** for each `(key, value)` in `config_values`, call `ConfigRepository(db, org_id=solution.organization_id, is_superuser=True).set_config(SetConfigRequest(key=key, value=value, type=<from declaration>, organization_id=solution.organization_id), updated_by=user.email)`. Look up the declaration's `type` to pass the right `ConfigType` (secret → encrypted automatically).
  5. Return the `SolutionDTO`.

The endpoint reads the `UploadFile`, parses `config_values` (JSON string in the multipart form), and calls `install_zip`. Map `SolutionDeployConflict` → 409 (the router already has this mapping for deploy — reuse it).

- [ ] **Step 4: Run to verify** — Run same command — Expected: PASS

- [ ] **Step 5: Add the CLI parity command**

In `api/bifrost/commands/solution.py`, add `bifrost solution install <zip> --org <uuid>` that POSTs the zip to `/api/solutions/install`. Add a smoke test in `api/tests/unit/test_solution_cli.py` (or the existing CLI test file) asserting the command builds the right request.

- [ ] **Step 6: Commit**

```bash
git add api/ api/tests/e2e/platform/test_solution_zip_install_e2e.py
git commit -m "feat(solutions): atomic zip install (deploy + config values under write-lock) + CLI"
```

## Task 13: `PATCH /api/solutions/{id}` — install-local fields only

**Files:**
- Modify: `api/src/routers/solutions.py`
- Modify: `api/src/models/contracts/solutions.py` (`SolutionUpdate`)
- Test: e2e `api/tests/e2e/platform/test_solution_patch.py`

- [ ] **Step 1: Write the failing test**

```python
# api/tests/e2e/platform/test_solution_patch.py
import pytest
from uuid import uuid4


@pytest.mark.e2e
async def test_patch_updates_install_local_fields(async_client, superuser_headers) -> None:
    r = await async_client.post("/api/solutions", headers=superuser_headers,
        json={"slug": f"patch-{uuid4().hex[:8]}", "name": "Old", "organization_id": None})
    sid = r.json()["id"]
    r = await async_client.patch(f"/api/solutions/{sid}", headers=superuser_headers,
        json={"name": "New", "global_repo_access": True})
    assert r.status_code == 200, r.text
    assert r.json()["name"] == "New"
    assert r.json()["global_repo_access"] is True
```

- [ ] **Step 2: Run to verify it fails** — Run: `./test.sh tests/e2e/platform/test_solution_patch.py -v` — Expected: FAIL (405/404 — no PATCH)

- [ ] **Step 3: Implement** — `SolutionUpdate` with optional `name`, `organization_id`, `global_repo_access`, `git_repo_url`, `git_connected`. The endpoint updates only these fields. **Changing `organization_id`** must re-stamp owned entities' `organization_id` (they inherit the install's scope) under the write-lock — add this and a test asserting an owned table's org follows. If scope-change cascade is large, split it into Task 13b; do not ship a PATCH that silently leaves entities on the old org.

- [ ] **Step 4: Run to verify** — Run same command — Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add api/ api/tests/e2e/platform/test_solution_patch.py
git commit -m "feat(solutions): PATCH install-local fields (scope re-stamps owned entities)"
```

## Task 14: `DELETE /api/solutions/{id}` — cascade with summary

**Files:**
- Modify: `api/src/routers/solutions.py`
- Test: e2e `api/tests/e2e/platform/test_solution_delete.py`

- [ ] **Step 1: Write the failing test**

```python
# api/tests/e2e/platform/test_solution_delete.py
import pytest
from uuid import uuid4


@pytest.mark.e2e
async def test_delete_removes_install_and_owned_entities(async_client, superuser_headers) -> None:
    r = await async_client.post("/api/solutions", headers=superuser_headers,
        json={"slug": f"del-{uuid4().hex[:8]}", "name": "DEL", "organization_id": None})
    sid = r.json()["id"]
    await async_client.post(f"/api/solutions/{sid}/deploy", headers=superuser_headers,
        json={"config_schemas": [{"id": str(uuid4()), "key": "K", "type": "string", "position": 0}]})

    r = await async_client.delete(f"/api/solutions/{sid}", headers=superuser_headers)
    assert r.status_code in (200, 204), r.text
    assert (await async_client.get(f"/api/solutions/{sid}", headers=superuser_headers)).status_code == 404
```

- [ ] **Step 2: Run to verify it fails** — Run: `./test.sh tests/e2e/platform/test_solution_delete.py -v` — Expected: FAIL (no DELETE)

- [ ] **Step 3: Implement** — DELETE removes the `Solution` row; `solution_id` FKs are `ondelete=CASCADE` so owned entities go with it. Also sweep the install's S3 prefix (`_solutions/{id}/`, `_apps/{id}/`) — reuse the storage helpers the deployer uses. Return a small summary (counts) for the UI to have echoed what it deleted. Do NOT touch any git repo.

- [ ] **Step 4: Run to verify** — Run same command — Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add api/ api/tests/e2e/platform/test_solution_delete.py
git commit -m "feat(solutions): DELETE install (cascade + S3 sweep, git untouched)"
```

## Task 15: Shared `SolutionManagedBadge` (admin-only, links to solution)

**Files:**
- Create: `client/src/components/solutions/SolutionManagedBadge.tsx`
- Test: `client/src/components/solutions/SolutionManagedBadge.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
// client/src/components/solutions/SolutionManagedBadge.test.tsx
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, it, expect, vi } from "vitest";
import { SolutionManagedBadge } from "./SolutionManagedBadge";

vi.mock("@/contexts/AuthContext", () => ({ useAuth: () => ({ isPlatformAdmin: true }) }));

describe("SolutionManagedBadge", () => {
  it("renders a link to the owning solution for admins", () => {
    render(
      <MemoryRouter>
        <SolutionManagedBadge solutionId="abc-123" />
      </MemoryRouter>,
    );
    const link = screen.getByRole("link", { name: /managed/i });
    expect(link).toHaveAttribute("href", "/solutions/abc-123");
  });
});
```

Add a second test file variant or `vi.mock` override asserting that when `isPlatformAdmin` is false, the component renders nothing (`container.firstChild` is null).

- [ ] **Step 2: Run to verify it fails** — Run: `./test.sh client unit src/components/solutions/SolutionManagedBadge.test.tsx` — Expected: FAIL (module missing)

- [ ] **Step 3: Implement** — mirror the badge JSX from `Applications.tsx` (Lock icon + "Managed", `bg-muted` chip), wrap in a react-router `<Link to={`/solutions/${solutionId}`}>`, gate the whole render on `useAuth().isPlatformAdmin`. Props: `{ solutionId: string | null | undefined }` — render null if no `solutionId` or not admin.

- [ ] **Step 4: Run to verify** — Run same command — Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add client/src/components/solutions/SolutionManagedBadge.tsx \
  client/src/components/solutions/SolutionManagedBadge.test.tsx
git commit -m "feat(client): shared admin-only SolutionManagedBadge linking to owner"
```

## Task 16: Wire the badge into Applications/Forms/Workflows/Fleet + enlarge app cards

**Files:**
- Modify: `client/src/pages/Applications.tsx` (replace inline badge with shared component; enlarge grid min-width), `Forms.tsx`, `Workflows.tsx`, `agents/FleetPage.tsx`
- Test: extend each page's existing `*.test.tsx` (or add) to assert badge presence for a managed entity as admin, and edit/delete hidden for managed entities.

- [ ] **Step 1: Write the failing test (one page shown; repeat per page)**

```tsx
// in Forms.test.tsx — managed form shows badge (admin) and no edit/delete
it("hides edit/delete and shows badge for solution-managed forms (admin)", () => {
  // render Forms with a fixture form where is_solution_managed=true, solution_id="s1"
  // assert: no "Edit"/"Delete" buttons for that row; SolutionManagedBadge link present
});
```

Use each page's existing test setup (query client / router wrappers) — copy the harness from a sibling test in the same dir.

- [ ] **Step 2: Run to verify it fails** — Run: `./test.sh client unit src/pages/Forms.test.tsx` — Expected: FAIL

- [ ] **Step 3: Implement** — On Forms/Workflows/Fleet: render `<SolutionManagedBadge solutionId={entity.solution_id} />` and hide Edit/Delete when `entity.is_solution_managed`. On Applications: replace the inline badge with the shared component (this also fixes its all-users visibility) and bump the grid `minmax(260px,…)` to a roomier value (e.g. `minmax(320px,1fr)`) with slightly larger gap. Keep Forms/Workflows visually consistent if they look off beside the new app cards.

- [ ] **Step 4: Run to verify** — Run the four page test files — Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add client/src/pages/Applications.tsx client/src/pages/Forms.tsx \
  client/src/pages/Workflows.tsx client/src/pages/agents/FleetPage.tsx client/src/pages/*.test.tsx
git commit -m "feat(client): read-only badge across entity lists; enlarge app cards"
```

## Task 17: Solutions service + hooks (client API layer)

**Files:**
- Create: `client/src/services/solutions.ts` (typed wrappers: list, getEntities, installPreview, install, patch, remove)
- Test: `client/src/services/solutions.test.ts`

- [ ] **Step 1: Write the failing test**

```ts
// client/src/services/solutions.test.ts
import { describe, it, expect, vi } from "vitest";
import * as svc from "./solutions";

describe("solutions service", () => {
  it("getSolutionEntities calls the entities endpoint", async () => {
    const get = vi.fn().mockResolvedValue({ data: { workflows: [] } });
    // inject/mocked apiClient per the project's test pattern (copy a sibling service test)
    const res = await svc.getSolutionEntities("s1", { get } as any);
    expect(get).toHaveBeenCalledWith("/api/solutions/s1/entities");
    expect(res.workflows).toEqual([]);
  });
});
```

Match the exact `apiClient` wrapper pattern from an existing `client/src/services/*.ts` (the CLAUDE.md example shows `apiClient.get<T>(...)`). If services don't take an injectable client, mock `@/lib/api-client` per a sibling test.

- [ ] **Step 2: Run to verify it fails** — Run: `./test.sh client unit src/services/solutions.test.ts` — Expected: FAIL

- [ ] **Step 3: Implement** the service wrappers using `apiClient` and the generated `components["schemas"]` types (`SolutionEntities`, `Solution`, `SolutionUpdate`).

- [ ] **Step 4: Run to verify** — Run same command — Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add client/src/services/solutions.ts client/src/services/solutions.test.ts
git commit -m "feat(client): solutions API service"
```

## Task 18: Solutions list page + routes + drag-and-drop install

**Files:**
- Create: `client/src/pages/Solutions.tsx`
- Modify: `client/src/App.tsx` (add `/solutions` and `/solutions/:solutionId` routes, `requirePlatformAdmin`)
- Modify: the nav/sidebar component (add a Solutions entry, admin-only) — find it via `grep -rn "to=\"/roles\"" client/src`
- Test: `client/src/pages/Solutions.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
// client/src/pages/Solutions.test.tsx
import { render, screen } from "@testing-library/react";
// render Solutions with a mocked list of 2 installs (one git-connected, one with
// required_configs_unset) → assert both names render, source chips show, and the
// "2 configs need values" warning chip appears for the second.
```

- [ ] **Step 2: Run to verify it fails** — Run: `./test.sh client unit src/pages/Solutions.test.tsx` — Expected: FAIL

- [ ] **Step 3: Implement** — list cards (name, slug, scope chip, source chip, entity counts, unset-config warning chip); whole-page drag-over overlay + "Install Solution" header button → preview dialog (entities + scope picker + inline config-value fields, required marked, missing-required = warning not block) → confirm → `install` → navigate to the new install's detail. Delete via row menu → type-to-confirm dialog with cascade summary. Empty state. Follow modern shadcn patterns (look at `IntegrationDetail.tsx`/`RoleDetail.tsx` for component choices). Add the two routes wrapped in `ProtectedRoute requirePlatformAdmin` (copy the exact prop name from an existing admin route in `App.tsx`).

- [ ] **Step 4: Run to verify** — Run same command — Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add client/src/pages/Solutions.tsx client/src/App.tsx client/src/pages/Solutions.test.tsx client/src/<nav-file>
git commit -m "feat(client): Solutions list page, routes, drag-and-drop install, delete"
```

## Task 19: Solution detail view (RoleDetail-style tabs + configs tab + back-nav)

**Files:**
- Create: `client/src/pages/SolutionDetail.tsx`
- Modify: the single-entity pages to honor `?from=solution:{id}` in their back-link (Table/Agent/Form/Workflow/App detail pages — small change each)
- Test: `client/src/pages/SolutionDetail.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
// client/src/pages/SolutionDetail.test.tsx
// render SolutionDetail for an install whose /entities returns 1 table + 1 required
// unset config → assert: breadcrumb "Solutions / <name>"; a Tables tab with count 1;
// a Configs tab; the unset-required warning banner; the table row links to
// /tables/<id>?from=solution:<sid>.
```

- [ ] **Step 2: Run to verify it fails** — Run: `./test.sh client unit src/pages/SolutionDetail.test.tsx` — Expected: FAIL

- [ ] **Step 3: Implement** — breadcrumb (`Solutions / {name}`, Pattern A from RoleDetail), header with Edit (scope/settings dialog → `patch`) + Delete, conditional unset-config warning banner, tabs (Workflows/Apps/Forms/Agents/Tables/Configs) with count badges. Entity rows link to the existing detail pages with `?from=solution:{sid}`. Configs tab: each declaration with description/type/required + value status; secret fields are write-only inputs that call `POST /api/config` for the install org on save. For the back-link change: in each entity detail page, read `from` from the query string; if it's `solution:{id}`, render the back-link as "← Back to {Solution}" to `/solutions/{id}`; otherwise keep the existing default ("Back to Tables" etc.).

- [ ] **Step 4: Run to verify** — Run same command — Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add client/src/pages/SolutionDetail.tsx client/src/pages/SolutionDetail.test.tsx \
  client/src/pages/TableDetail.tsx client/src/pages/agents/AgentDetailPage.tsx \
  client/src/pages/FormBuilder.tsx client/src/pages/ExecuteWorkflow.tsx client/src/pages/AppCodeEditorPage.tsx
git commit -m "feat(client): Solution detail view + ?from back-nav on entity pages"
```

## Task 20: Playwright happy-path + full verification

**Files:**
- Create: `client/e2e/solutions.spec.ts`

- [ ] **Step 1: Write the happy-path spec** — install a zip → it appears in the list → open detail → set a config value → navigate to an owned entity and back → delete the install. Use the existing Playwright auth/setup from a sibling `client/e2e/*.spec.ts`.

- [ ] **Step 2: Run it** — Run: `./test.sh client e2e e2e/solutions.spec.ts` — Expected: PASS (boot debug stack in port mode first; netbird can't drive the browser).

- [ ] **Step 3: Full pre-completion verification (CLAUDE.md sequence)**

```bash
cd api && pyright && ruff check .
cd ../client && npm run generate:types && npm run tsc && npm run lint
cd .. && ./test.sh all && ./test.sh client unit
./test.sh client e2e e2e/solutions.spec.ts
```
Expected: all green; the full solution suite (Part 1 + Part 2) passes.

- [ ] **Step 4: Commit**

```bash
git add client/e2e/solutions.spec.ts
git commit -m "test(solutions): Playwright happy-path; full verification green"
```

---

## Update project docs after both parts land

- [ ] Update `docs/plans/2026-06-05-solutions-RESUME.md` "WHAT TO DO NEXT" — mark configs + management UI as built; note the badge gap is closed.
- [ ] Update `docs/llm.txt` if the new `bifrost solution install` command or endpoints should be known to Claude.

## Self-review notes (author)

Spec coverage check vs. `2026-06-06-solutions-configs-and-management-ui-design.md`:
- §1 configs ownership → Tasks 1–8. §2 backend surface → Tasks 9–14 (no new config endpoint; values via `POST /api/config` in Task 12). §3 list page → Task 18. §4 detail view → Task 19. §5 badge + card sizing → Tasks 15–16. Non-goals (provider-org, content-edit, stored state) honored — nothing builds them.
- Atomic install (spec decision) → Task 12 step 3.4. Warn-not-block (spec) → Task 10 (`required_configs_unset` is derived/displayed; no endpoint blocks).
- Open verification points flagged inline (not placeholders): current head revision (Task 1.4), whether resolution needs code (Task 7.2), multipart field convention (Task 12.1), nav file path (Task 18). These are "confirm against live code" steps, each with the exact command to resolve them.
