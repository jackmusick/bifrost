# Agent Management Redesign (Milestone 1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the flat agent list + dialog pattern with a health-first fleet dashboard and an agent detail page that makes observability, review, and AI-assisted prompt tuning first-class. Verdicts captured on every completed run become training signal for a tuning conversation that proposes, dry-runs, and applies prompt changes.

**Architecture:** Backend adds run-level summary/verdict/metadata columns, two new tables (per-flag conversations, prompt history), and a tsvector column for search. Exposes via `/api/agents/{id}/stats`, `/api/agent-runs/{id}/verdict`, `/api/agent-runs/{id}/flag-conversation`, `/api/agent-runs/{id}/dry-run`, and `/api/agents/{id}/tuning-session`. Summarization and tuning LLM calls are **enqueued to RabbitMQ** (new queues `agent-summarization` and `agent-tuning-chat`) and consumed by the existing worker — this isolates AI latency/retry from the HTTP API and scales separately. Summarization uses Haiku; tuning uses Sonnet; dry-run is one Sonnet call that reasons about the recorded transcript without re-executing tools. All AI calls land in the existing `AIUsage` table tagged with the originating `agent_run_id`, so per-run and per-agent cost rolls up unchanged. Paused agents return HTTP 200 with `{"status": "paused"}` — a graceful response, not an error. Frontend ships one variant-aware `RunReviewPanel`, a slide-over `Sheet`, a shared `ChatComposer`, a pill-style `Tabs`, and a `RunCard` list. The existing `Agents.tsx` + `AgentDialog.tsx` + `AgentRunDetail.tsx` are replaced with fleet dashboard + agent detail page (tabs) + redesigned run detail using the shared panel; the agent dialog is removed entirely — `/agents/new` uses the detail page in create mode.

**Tech Stack:** FastAPI + SQLAlchemy 2.x + Alembic + Anthropic SDK (backend); React 18 + Vite + shadcn/ui + TanStack Query + Radix primitives (frontend); Vitest + Playwright (tests); Postgres `tsvector` + GIN indexes for search; Redis Streams for step buffering (already used by the executor).

---

## Companion documents

- **Design narrative:** `/home/jack/GitHub/bifrost/docs/plans/2026-04-21-ui-narrative-agent-redesign.md` — principles, patterns, CSS class inventory. Reference when implementing visual components.
- **Mockup:** `/tmp/agent-mockup/` — Vite app serving the approved design on `0.0.0.0:5555`. Pages referenced in this plan map to files there:
  - Fleet: `src/pages/FleetPage.tsx`
  - Agent detail: `src/pages/AgentDetailPage.tsx`
  - Run detail: `src/pages/RunDetailPage.tsx`
  - Flipbook review: `src/pages/ReviewFlipbookPage.tsx`
  - Tuning: `src/pages/TuneChatPage.tsx`
  - Shared panel: `src/components/RunReviewPanel.tsx`
  - Sheet: `src/components/Sheet.tsx`
  - Composer: `src/components/FlagConversation.tsx` (composer section)
- **Design system notes:** `/tmp/agent-mockup/PLAN_NOTES.md` — data model, permission matrix, pause semantics.

---

## Global conventions

These apply to **every task** unless the task says otherwise.

### Testing: `bifrost-testing` skill is authoritative

**Before running or writing any test in this plan, invoke the `bifrost-testing` skill** to refresh on the project's current testing conventions, stack lifecycle, and tooling. The skill governs test strategy for this plan.

Rules the skill enforces that are critical here:
- Backend tests **must** use `./test.sh` (not direct `pytest` on host). The script manages the Dockerized test stack.
- Boot the stack once per worktree with `./test.sh stack up`; it stays up across test runs. State auto-resets before each run.
- Frontend vitest runs on the host via `./test.sh client unit`.
- Playwright e2e runs in containers via `./test.sh client e2e` (add `--screenshots` during iteration to capture step-by-step images for visual review).
- Test results are written to `/tmp/bifrost/test-results.xml` — parse this for pass/fail, don't grep stdout.
- Logs land in `/tmp/bifrost-<project>/*.log` after runs — each worktree has its own directory.
- Every functional frontend module under `client/src/lib/**` or `client/src/services/**` that exports functions needs a sibling `*.test.ts` covering the public API. Pure type/constant files are exempt.
- Every user-facing feature gets at least one happy-path Playwright spec.

At any task that introduces substantial new test code (T11 summarizer, T15 flag-conversation endpoints, T16 dry-run, T17 consolidated tuning, T20 backend e2e, T37–T41 Playwright specs), invoke `bifrost-testing` again if there's any uncertainty about conventions — it takes precedence over anything in this plan.

### Other conventions

- **Worktree:** all work happens inside `/home/jack/GitHub/bifrost/.claude/worktrees/agent-management-m1/` (current worktree). Never touch the main clone.
- **Backend tests:** before any task involving DB, call `./test.sh stack up` once (idempotent). Before running tests in a task, the runner resets state automatically — no manual reset needed.
- **Commit cadence:** every numbered task ends with a commit. Commits use Conventional Commits prefixes (`feat:`, `fix:`, `test:`, `chore:`). One task = one logical commit. Do NOT squash.
- **Datetime:** always `datetime.now(timezone.utc)`. `DateTime(timezone=True)` on ORM columns. Tests check this via `api/tests/unit/test_datetime_consistency.py` — do not bypass it.
- **Pyright + ruff:** zero errors required before commit. Frontend: `npm run tsc` + `npm run lint` zero errors.
- **Type generation:** after any backend Pydantic model change, run `cd client && npm run generate:types` while the dev stack is up. Check the resulting `client/src/lib/v1.d.ts` diff into the same commit as the backend change.
- **No new Pydantic models outside `api/src/models/contracts/`.** No new ORM models outside `api/src/models/orm/`.
- **Frontend API calls:** use `$api` (TanStack + OpenAPI-typed) for typed endpoints. Use `authFetch` only for streaming endpoints (SSE) where the OpenAPI codegen doesn't help.
- **Naming:** all new frontend pages under `client/src/pages/agents/` (new subdirectory). Shared UI under `client/src/components/ui/` or `client/src/components/agents/` depending on domain-specificity.

---

## File structure

### Backend (new/modified files)

```
api/
├── alembic/versions/
│   ├── 20260421a_run_summaries_metadata_confidence.py       [NEW]
│   ├── 20260421b_run_verdicts_and_history.py                [NEW]
│   ├── 20260421c_flag_conversations.py                      [NEW]
│   ├── 20260421d_agent_prompt_history.py                    [NEW]
│   └── 20260421e_run_tsvector_search.py                     [NEW]
├── src/
│   ├── models/
│   │   ├── orm/
│   │   │   ├── agent_runs.py                                [MODIFY: add asked/did/metadata/confidence/confidence_reason/verdict/verdict_note/verdict_set_at/verdict_set_by/summary_generated_at]
│   │   │   ├── agent_run_verdict_history.py                 [NEW]
│   │   │   ├── agent_run_flag_conversations.py              [NEW]
│   │   │   ├── agent_prompt_history.py                      [NEW]
│   │   │   └── __init__.py                                  [MODIFY: re-export new models]
│   │   └── contracts/
│   │       ├── agent_runs.py                                [MODIFY: add new fields to response models + VerdictRequest + VerdictResponse]
│   │       ├── agent_run_flag_conversations.py              [NEW]
│   │       ├── agent_stats.py                               [NEW]
│   │       ├── agent_tuning.py                              [NEW]
│   │       └── agents.py                                    [MODIFY: AgentUpdate.is_active behavior, owner visibility surface]
│   ├── routers/
│   │   ├── agents.py                                        [MODIFY: add /{id}/stats, /{id}/tuning-session endpoints; gate budget writes behind admin]
│   │   ├── agent_runs.py                                    [MODIFY: add search param, metadata filter, verdict CRUD, flag-conversation CRUD, dry-run endpoint]
│   │   └── agent_tuning.py                                  [NEW: tuning session endpoints]
│   ├── services/
│   │   ├── execution/
│   │   │   ├── autonomous_agent_executor.py                 [MODIFY: pause check at entry, post-run summary/confidence hook, metadata write]
│   │   │   ├── model_selection.py                           [NEW: get_summarization_client / get_tuning_client — reads LLM config overrides]
│   │   │   ├── run_summarizer.py                            [NEW: asked/did/confidence generator]
│   │   │   ├── tuning_service.py                            [NEW: per-flag diagnosis + consolidated tuning]
│   │   │   └── dry_run.py                                   [NEW: "would you make the same decision" transcript evaluator]
│   │   └── agent_stats.py                                   [NEW: fleet + per-agent stats with 60s cache]
│   └── tests/
│       ├── unit/
│       │   ├── test_run_summaries_field_validation.py       [NEW]
│       │   ├── test_verdict_endpoint.py                     [NEW]
│       │   ├── test_verdict_audit_history.py                [NEW]
│       │   ├── test_flag_conversation_endpoints.py          [NEW]
│       │   ├── test_runs_search_and_metadata_filter.py      [NEW]
│       │   ├── test_agent_stats_service.py                  [NEW]
│       │   ├── test_pause_semantics.py                      [NEW]
│       │   ├── test_budget_visibility_permissions.py        [NEW]
│       │   └── test_tuning_service.py                       [NEW]
│       └── e2e/
│           ├── test_agent_management_m1.py                  [NEW: full flow]
│           └── test_tuning_dry_run.py                       [NEW]
```

### Frontend (new/modified files)

```
client/src/
├── components/
│   ├── ui/
│   │   ├── chat-composer.tsx                                [NEW: standard rounded pill with embedded send]
│   │   ├── verdict-toggle.tsx                               [NEW: animated 👍/👎]
│   │   └── pill-tabs.tsx                                    [NEW: restyled tabs — separate from existing shadcn Tabs]
│   └── agents/
│       ├── RunReviewPanel.tsx                               [NEW: variant-aware review body]
│       ├── RunCard.tsx                                      [NEW: card-row for runs]
│       ├── RunReviewSheet.tsx                               [NEW: slide-over with review+tune tabs]
│       ├── FlagConversation.tsx                             [NEW: per-flag chat component]
│       ├── FleetStats.tsx                                   [NEW: top stat strip]
│       ├── AgentOverviewTab.tsx                             [NEW]
│       ├── AgentRunsTab.tsx                                 [NEW]
│       ├── AgentSettingsTab.tsx                             [NEW: full-page form, replaces AgentDialog]
│       ├── AgentDialog.tsx                                  [DELETE: replaced by settings tab]
│       ├── AgentDialog.test.tsx                             [DELETE]
│       ├── AgentRunsTable.tsx                               [DELETE: replaced by card list]
│       ├── NeedsReviewCard.tsx                              [NEW]
│       ├── QueueBanner.tsx                                  [NEW]
│       ├── TuningChat.tsx                                   [NEW: consolidated tuning view]
│       ├── ReviewFlipbook.tsx                               [NEW]
│       └── QueryHighlight.tsx                               [NEW: highlight match chips]
├── pages/
│   ├── agents/
│   │   ├── FleetPage.tsx                                    [NEW: replaces Agents.tsx]
│   │   ├── AgentDetailPage.tsx                              [NEW]
│   │   ├── AgentRunDetailPage.tsx                           [NEW: replaces AgentRunDetail.tsx]
│   │   ├── AgentReviewPage.tsx                              [NEW: flipbook route]
│   │   └── AgentTunePage.tsx                                [NEW]
│   ├── Agents.tsx                                           [DELETE]
│   └── AgentRunDetail.tsx                                   [DELETE]
├── services/
│   ├── agents.ts                                            [MODIFY: stats, pause, tuning]
│   ├── agentRuns.ts                                         [MODIFY: search/metadata/verdict/flagConversation]
│   └── agentTuning.ts                                       [NEW]
├── hooks/
│   └── useAgentRunStream.ts                                 [REFACTOR if needed for SSE tuning]
├── lib/
│   └── v1.d.ts                                              [REGENERATED]
└── App.tsx                                                  [MODIFY: routes for /agents/* new page tree]

client/e2e/
├── agents-fleet.admin.spec.ts                               [NEW]
├── agents-detail-runs.admin.spec.ts                         [NEW]
├── agents-review-verdict.admin.spec.ts                      [NEW]
├── agents-tuning.admin.spec.ts                              [NEW]
└── agents-owner-budget-hidden.user.spec.ts                  [NEW]
```

---

## Summarization & Tuning Model Selection

All AI calls are logged to `AIUsage` with `agent_run_id` populated, so per-run cost reflects summarization + tuning + dry-run spending without any new cost pipeline.

**Model selection is dynamic** — resolved from system settings at call time, not baked in as constants. Two new optional fields on the LLM config (`system_configs.value_json` with category=`"llm"`):

- `summarization_model` — optional override; if unset, falls back to the default `model`
- `tuning_model` — optional override for tuning chat + dry-run; if unset, falls back to the default

The **provider is always the default provider** (OpenAI or Anthropic as configured). Overrides only change the model name, not the provider or API key. This keeps the current single-provider-at-a-time contract simple while letting admins point summarization at a cheaper model (e.g. `gpt-4o-mini` or `claude-haiku-4-5`) and tuning at a stronger model.

| Task | Resolved model |
|------|----------------|
| `asked`/`did`/`confidence` generation | `llm_config.summarization_model` OR `llm_config.model` |
| Per-flag diagnosis | `llm_config.tuning_model` OR `llm_config.model` |
| Consolidated tuning proposal | `llm_config.tuning_model` OR `llm_config.model` |
| Dry-run evaluation | `llm_config.tuning_model` OR `llm_config.model` |
| Agent execution (unchanged) | `agent.llm_model` OR `llm_config.model` |

Resolution helper lives in `api/src/services/execution/model_selection.py` (new file). Functions: `get_summarization_client(db)`, `get_tuning_client(db)` — each returns a `(client, resolved_model_name)` tuple. Callers pass `resolved_model_name` to `client.complete(..., model=resolved_model_name)`.

---

## Sequencing & parallelism

Tasks are numbered in a dependency-respecting order. Tasks marked **[PARALLEL]** can be done concurrently with the previous task if you're using subagent-driven-development (different subagents, different files).

Phase 1 (Backend foundation): T1–T9
Phase 2 (Backend behavior): T10–T20
Phase 3 (Frontend primitives): T21–T27
Phase 4 (Frontend pages): T28–T36
Phase 5 (E2E and polish): T37–T44
Phase 6 (Plan 2 stubs — unchecked, unimplemented): T45–T53

---

## Phase 1 — Backend foundation (schema, migrations, minimal endpoints)

### Task 1: Add run summary/metadata/confidence columns

**Files:**
- Create: `api/alembic/versions/20260421a_run_summaries_metadata_confidence.py`
- Modify: `api/src/models/orm/agent_runs.py:16-73`

- [ ] **Step 1: Write the failing test**

Create `api/tests/unit/test_run_summaries_field_validation.py`:

```python
"""Validate new AgentRun columns: asked, did, metadata, confidence, confidence_reason, summary_generated_at."""
from datetime import datetime, timezone
from uuid import uuid4
import pytest
from sqlalchemy import select
from src.models.orm.agent_runs import AgentRun
from src.models.orm.agents import Agent


@pytest.mark.asyncio
async def test_agent_run_accepts_new_summary_fields(db_session, seed_agent):
    run = AgentRun(
        id=uuid4(),
        agent_id=seed_agent.id,
        trigger_type="test",
        status="completed",
        iterations_used=1,
        tokens_used=100,
        asked="How do I reset my password?",
        did="Routed to Support team",
        metadata={"ticket_id": "4821", "customer": "Acme"},
        confidence=0.87,
        confidence_reason="High keyword match with known-good routing",
        summary_generated_at=datetime.now(timezone.utc),
    )
    db_session.add(run)
    await db_session.flush()

    result = await db_session.execute(select(AgentRun).where(AgentRun.id == run.id))
    reloaded = result.scalar_one()
    assert reloaded.asked == "How do I reset my password?"
    assert reloaded.did == "Routed to Support team"
    assert reloaded.metadata == {"ticket_id": "4821", "customer": "Acme"}
    assert reloaded.confidence == 0.87
    assert reloaded.confidence_reason.startswith("High keyword")
    assert reloaded.summary_generated_at is not None


@pytest.mark.asyncio
async def test_agent_run_metadata_defaults_to_empty_dict(db_session, seed_agent):
    run = AgentRun(
        id=uuid4(), agent_id=seed_agent.id, trigger_type="test", status="queued",
        iterations_used=0, tokens_used=0,
    )
    db_session.add(run)
    await db_session.flush()
    await db_session.refresh(run)
    assert run.metadata == {}


@pytest.mark.asyncio
async def test_agent_run_confidence_is_not_db_constrained(db_session, seed_agent):
    """Confidence is clamped at write time in the summarizer, not enforced by DB."""
    run = AgentRun(
        id=uuid4(), agent_id=seed_agent.id, trigger_type="test", status="completed",
        iterations_used=1, tokens_used=1, confidence=1.5,
    )
    db_session.add(run)
    await db_session.flush()  # should not raise
    await db_session.refresh(run)
    assert run.confidence == 1.5  # stored as-is; summarizer clamps before write


@pytest.mark.asyncio
async def test_summary_status_defaults_to_pending(db_session, seed_agent):
    run = AgentRun(
        id=uuid4(), agent_id=seed_agent.id, trigger_type="test", status="queued",
        iterations_used=0, tokens_used=0,
    )
    db_session.add(run)
    await db_session.flush()
    await db_session.refresh(run)
    assert run.summary_status == "pending"


@pytest.mark.asyncio
async def test_summary_status_check_constraint_rejects_invalid(db_session, seed_agent):
    from sqlalchemy.exc import IntegrityError
    run = AgentRun(
        id=uuid4(), agent_id=seed_agent.id, trigger_type="test", status="queued",
        iterations_used=0, tokens_used=0, summary_status="bogus",
    )
    db_session.add(run)
    with pytest.raises(IntegrityError):
        await db_session.flush()
```

(Add fixtures in `api/tests/conftest.py` if `seed_agent` doesn't exist. Follow existing fixture patterns — see `api/tests/unit/conftest.py` for examples of `db_session` and seeded models.)

- [ ] **Step 2: Run test to verify it fails**

Run: `./test.sh tests/unit/test_run_summaries_field_validation.py -v`
Expected: FAIL with `AttributeError` or `CompileError` — `asked` column doesn't exist.

- [ ] **Step 3: Write the Alembic migration**

`api/alembic/versions/20260421a_run_summaries_metadata_confidence.py`:

```python
"""add run summaries, metadata, confidence fields

Revision ID: 20260421a_run_summaries_metadata_confidence
Revises: <INSERT: most recent revision ID from alembic heads>
Create Date: 2026-04-21 ...
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260421a_run_summaries_metadata_confidence"
down_revision = "<REPLACE: find via `alembic heads` or look at latest in api/alembic/versions/>"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("agent_runs", sa.Column("asked", sa.Text(), nullable=True))
    op.add_column("agent_runs", sa.Column("did", sa.Text(), nullable=True))
    op.add_column("agent_runs", sa.Column(
        "metadata",
        postgresql.JSONB(astext_type=sa.Text()),
        nullable=False,
        server_default=sa.text("'{}'::jsonb"),
    ))
    op.add_column("agent_runs", sa.Column("confidence", sa.Float(), nullable=True))
    op.add_column("agent_runs", sa.Column("confidence_reason", sa.Text(), nullable=True))
    op.add_column("agent_runs", sa.Column(
        "summary_generated_at",
        sa.DateTime(timezone=True),
        nullable=True,
    ))
    op.add_column("agent_runs", sa.Column(
        "summary_status",
        sa.String(length=20),
        nullable=False,
        server_default=sa.text("'pending'"),
    ))
    op.add_column("agent_runs", sa.Column("summary_error", sa.Text(), nullable=True))
    op.create_check_constraint(
        "ck_agent_runs_summary_status_values",
        "agent_runs",
        "summary_status IN ('pending', 'generating', 'completed', 'failed', 'skipped')",
    )
    # No CHECK on confidence — values are clamped to [0.0, 1.0] at write time.
    # If the summarizer returns an out-of-range value, we store None and mark summary_status='failed'.

    # GIN index on metadata for jsonb path queries
    op.create_index(
        "ix_agent_runs_metadata_gin",
        "agent_runs",
        ["metadata"],
        postgresql_using="gin",
        postgresql_ops={"metadata": "jsonb_path_ops"},
    )


def downgrade() -> None:
    op.drop_index("ix_agent_runs_metadata_gin", table_name="agent_runs")
    op.drop_constraint("ck_agent_runs_summary_status_values", "agent_runs", type_="check")
    op.drop_column("agent_runs", "summary_error")
    op.drop_column("agent_runs", "summary_status")
    op.drop_column("agent_runs", "summary_generated_at")
    op.drop_column("agent_runs", "confidence_reason")
    op.drop_column("agent_runs", "confidence")
    op.drop_column("agent_runs", "metadata")
    op.drop_column("agent_runs", "did")
    op.drop_column("agent_runs", "asked")
```

Find the current head: `docker exec bifrost-dev-api alembic -c alembic.ini heads` (or look at the latest file in `api/alembic/versions/`).

- [ ] **Step 4: Add columns to ORM**

In `api/src/models/orm/agent_runs.py`, add to `class AgentRun` after the existing `llm_model` field:

```python
asked: Mapped[str | None] = mapped_column(sa.Text(), nullable=True, default=None)
did: Mapped[str | None] = mapped_column(sa.Text(), nullable=True, default=None)
metadata: Mapped[dict] = mapped_column(
    postgresql.JSONB,
    nullable=False,
    default=dict,
    server_default=sa.text("'{}'::jsonb"),
)
confidence: Mapped[float | None] = mapped_column(sa.Float(), nullable=True, default=None)
confidence_reason: Mapped[str | None] = mapped_column(sa.Text(), nullable=True, default=None)
summary_generated_at: Mapped[datetime | None] = mapped_column(
    sa.DateTime(timezone=True), nullable=True, default=None
)
summary_status: Mapped[str] = mapped_column(
    sa.String(20), nullable=False, default="pending", server_default=sa.text("'pending'"),
)
summary_error: Mapped[str | None] = mapped_column(sa.Text(), nullable=True, default=None)
```

Add to imports at the top of file if missing:
```python
from sqlalchemy.dialects import postgresql
import sqlalchemy as sa
```

- [ ] **Step 5: Apply migration, restart api**

Run: `docker restart bifrost-dev-bifrost-init` (runs alembic), wait 5s, `docker restart bifrost-dev-api`.

- [ ] **Step 6: Run test to verify it passes**

Run: `./test.sh tests/unit/test_run_summaries_field_validation.py -v`
Expected: all tests PASS.

- [ ] **Step 7: Regenerate types**

Run: `cd client && npm run generate:types`
Verify `client/src/lib/v1.d.ts` now has `asked`, `did`, `metadata`, `confidence`, `confidence_reason`, `summary_generated_at` on `AgentRunResponse` and `AgentRunDetailResponse`. (Types only regenerate if the Pydantic response models are updated — that comes in Task 3.)

- [ ] **Step 8: Commit**

```bash
git add api/alembic/versions/20260421a_run_summaries_metadata_confidence.py \
        api/src/models/orm/agent_runs.py \
        api/tests/unit/test_run_summaries_field_validation.py
git commit -m "feat(agent-runs): add summary, metadata, and confidence columns"
```

---

### Task 2: Add verdict columns and audit history table

**Files:**
- Create: `api/alembic/versions/20260421b_run_verdicts_and_history.py`
- Modify: `api/src/models/orm/agent_runs.py`
- Create: `api/src/models/orm/agent_run_verdict_history.py`
- Modify: `api/src/models/orm/__init__.py`

- [ ] **Step 1: Write the failing test**

Create `api/tests/unit/test_verdict_audit_history.py`:

```python
"""Verdict column + audit history."""
from datetime import datetime, timezone
from uuid import uuid4
import pytest
from sqlalchemy import select

from src.models.orm.agent_runs import AgentRun
from src.models.orm.agent_run_verdict_history import AgentRunVerdictHistory


@pytest.mark.asyncio
async def test_agent_run_accepts_verdict_fields(db_session, seed_agent):
    run = AgentRun(
        id=uuid4(), agent_id=seed_agent.id, trigger_type="test",
        status="completed", iterations_used=1, tokens_used=100,
        verdict="up",
        verdict_note="looks right",
        verdict_set_at=datetime.now(timezone.utc),
        verdict_set_by=None,
    )
    db_session.add(run)
    await db_session.flush()
    await db_session.refresh(run)
    assert run.verdict == "up"


@pytest.mark.asyncio
async def test_verdict_only_accepts_up_down_null(db_session, seed_agent):
    from sqlalchemy.exc import IntegrityError
    run = AgentRun(
        id=uuid4(), agent_id=seed_agent.id, trigger_type="test",
        status="completed", iterations_used=1, tokens_used=100,
        verdict="sideways",
    )
    db_session.add(run)
    with pytest.raises(IntegrityError):
        await db_session.flush()


@pytest.mark.asyncio
async def test_verdict_history_row_fields(db_session, seed_agent, seed_user):
    run = AgentRun(
        id=uuid4(), agent_id=seed_agent.id, trigger_type="test",
        status="completed", iterations_used=1, tokens_used=100,
    )
    db_session.add(run)
    await db_session.flush()

    h = AgentRunVerdictHistory(
        id=uuid4(),
        run_id=run.id,
        previous_verdict=None,
        new_verdict="down",
        changed_by=seed_user.id,
        changed_at=datetime.now(timezone.utc),
        note="wrong route",
    )
    db_session.add(h)
    await db_session.flush()
    result = await db_session.execute(
        select(AgentRunVerdictHistory).where(AgentRunVerdictHistory.run_id == run.id)
    )
    assert result.scalar_one().note == "wrong route"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./test.sh tests/unit/test_verdict_audit_history.py -v`
Expected: FAIL (no `verdict` column, no `AgentRunVerdictHistory` class).

- [ ] **Step 3: Write the migration**

`api/alembic/versions/20260421b_run_verdicts_and_history.py`:

```python
"""add verdict columns + audit history

Revision ID: 20260421b_run_verdicts_and_history
Revises: 20260421a_run_summaries_metadata_confidence
Create Date: 2026-04-21 ...
"""
from alembic import op
import sqlalchemy as sa


revision = "20260421b_run_verdicts_and_history"
down_revision = "20260421a_run_summaries_metadata_confidence"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("agent_runs", sa.Column("verdict", sa.String(length=10), nullable=True))
    op.add_column("agent_runs", sa.Column("verdict_note", sa.Text(), nullable=True))
    op.add_column("agent_runs", sa.Column("verdict_set_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("agent_runs", sa.Column(
        "verdict_set_by",
        sa.dialects.postgresql.UUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    ))
    op.create_check_constraint(
        "ck_agent_runs_verdict_values",
        "agent_runs",
        "verdict IS NULL OR verdict IN ('up', 'down')",
    )
    op.create_index(
        "ix_agent_runs_agent_verdict_status",
        "agent_runs",
        ["agent_id", "verdict", "status"],
    )

    op.create_table(
        "agent_run_verdict_history",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "run_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("agent_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("previous_verdict", sa.String(length=10), nullable=True),
        sa.Column("new_verdict", sa.String(length=10), nullable=True),
        sa.Column(
            "changed_by",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
    )
    op.create_index("ix_verdict_history_run_id", "agent_run_verdict_history", ["run_id"])


def downgrade() -> None:
    op.drop_index("ix_verdict_history_run_id", table_name="agent_run_verdict_history")
    op.drop_table("agent_run_verdict_history")
    op.drop_index("ix_agent_runs_agent_verdict_status", table_name="agent_runs")
    op.drop_constraint("ck_agent_runs_verdict_values", "agent_runs", type_="check")
    op.drop_column("agent_runs", "verdict_set_by")
    op.drop_column("agent_runs", "verdict_set_at")
    op.drop_column("agent_runs", "verdict_note")
    op.drop_column("agent_runs", "verdict")
```

- [ ] **Step 4: Add `AgentRunVerdictHistory` ORM model**

`api/src/models/orm/agent_run_verdict_history.py`:

```python
"""Verdict change audit trail."""
from datetime import datetime
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import Base


class AgentRunVerdictHistory(Base):
    __tablename__ = "agent_run_verdict_history"

    id: Mapped[UUID] = mapped_column(postgresql.UUID(as_uuid=True), primary_key=True, default=uuid4)
    run_id: Mapped[UUID] = mapped_column(
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("agent_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    previous_verdict: Mapped[str | None] = mapped_column(sa.String(10), nullable=True)
    new_verdict: Mapped[str | None] = mapped_column(sa.String(10), nullable=True)
    changed_by: Mapped[UUID | None] = mapped_column(
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    changed_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False)
    note: Mapped[str | None] = mapped_column(sa.Text(), nullable=True)
```

Register in `api/src/models/orm/__init__.py`:

```python
from src.models.orm.agent_run_verdict_history import AgentRunVerdictHistory  # noqa: F401
```

- [ ] **Step 5: Add verdict columns to `AgentRun`**

In `api/src/models/orm/agent_runs.py`, after `summary_generated_at`:

```python
verdict: Mapped[str | None] = mapped_column(sa.String(10), nullable=True, default=None)
verdict_note: Mapped[str | None] = mapped_column(sa.Text(), nullable=True, default=None)
verdict_set_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True, default=None)
verdict_set_by: Mapped[UUID | None] = mapped_column(
    postgresql.UUID(as_uuid=True),
    sa.ForeignKey("users.id", ondelete="SET NULL"),
    nullable=True,
    default=None,
)
```

- [ ] **Step 6: Apply migration**

Run: `docker restart bifrost-dev-bifrost-init`, wait 5s, `docker restart bifrost-dev-api`.

- [ ] **Step 7: Run test to verify passes**

Run: `./test.sh tests/unit/test_verdict_audit_history.py -v`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add api/alembic/versions/20260421b_run_verdicts_and_history.py \
        api/src/models/orm/agent_run_verdict_history.py \
        api/src/models/orm/agent_runs.py \
        api/src/models/orm/__init__.py \
        api/tests/unit/test_verdict_audit_history.py
git commit -m "feat(agent-runs): add verdict columns and audit history table"
```

---

### Task 3: Expose new run fields in Pydantic contracts

**Files:**
- Modify: `api/src/models/contracts/agent_runs.py`

- [ ] **Step 1: Write the failing test**

Create `api/tests/unit/test_agent_run_response_includes_new_fields.py`:

```python
"""AgentRunResponse + AgentRunDetailResponse include new fields."""
from src.models.contracts.agent_runs import AgentRunResponse, AgentRunDetailResponse


def test_agent_run_response_has_new_fields():
    fields = AgentRunResponse.model_fields
    for name in (
        "asked", "did", "metadata", "confidence", "confidence_reason",
        "verdict", "verdict_note", "verdict_set_at", "verdict_set_by",
    ):
        assert name in fields, f"missing {name} on AgentRunResponse"


def test_agent_run_detail_response_inherits_new_fields():
    fields = AgentRunDetailResponse.model_fields
    for name in (
        "asked", "did", "metadata", "confidence",
        "verdict", "verdict_note",
    ):
        assert name in fields
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./test.sh tests/unit/test_agent_run_response_includes_new_fields.py -v`
Expected: FAIL.

- [ ] **Step 3: Add fields to contracts**

In `api/src/models/contracts/agent_runs.py`, in `AgentRunResponse` after `llm_model`:

```python
asked: str | None = None
did: str | None = None
metadata: dict[str, str] = Field(default_factory=dict)
confidence: float | None = None
confidence_reason: str | None = None
verdict: str | None = None
verdict_note: str | None = None
verdict_set_at: datetime | None = None
verdict_set_by: UUID | None = None
```

Add imports at top if missing (`from pydantic import Field`).

`AgentRunDetailResponse` inherits from `AgentRunResponse` — it will pick these up automatically. Verify the class definition still inherits properly.

- [ ] **Step 4: Update `_run_to_response` and detail response in router**

In `api/src/routers/agent_runs.py:44-72`, add new field kwargs to `AgentRunResponse(...)` call:

```python
asked=run.asked,
did=run.did,
metadata=run.metadata or {},
confidence=run.confidence,
confidence_reason=run.confidence_reason,
verdict=run.verdict,
verdict_note=run.verdict_note,
verdict_set_at=run.verdict_set_at,
verdict_set_by=run.verdict_set_by,
```

Add same fields to the `AgentRunDetailResponse(...)` call at line 254.

- [ ] **Step 5: Run test to verify passes**

Run: `./test.sh tests/unit/test_agent_run_response_includes_new_fields.py -v`
Expected: PASS.

- [ ] **Step 6: Regenerate frontend types**

Run: `cd client && npm run generate:types`
Verify `AgentRunResponse` in `client/src/lib/v1.d.ts` now includes the new fields.

- [ ] **Step 7: Commit**

```bash
git add api/src/models/contracts/agent_runs.py \
        api/src/routers/agent_runs.py \
        api/tests/unit/test_agent_run_response_includes_new_fields.py \
        client/src/lib/v1.d.ts
git commit -m "feat(agent-runs): expose new run fields in Pydantic contracts"
```

---

### Task 4: Flag conversation table

**Files:**
- Create: `api/alembic/versions/20260421c_flag_conversations.py`
- Create: `api/src/models/orm/agent_run_flag_conversations.py`
- Modify: `api/src/models/orm/__init__.py`
- Create: `api/src/models/contracts/agent_run_flag_conversations.py`
- Create: `api/tests/unit/test_flag_conversation_model.py`

- [ ] **Step 1: Write the failing test**

```python
"""Per-flag tuning conversation."""
from datetime import datetime, timezone
from uuid import uuid4
import pytest
from sqlalchemy import select

from src.models.orm.agent_run_flag_conversations import AgentRunFlagConversation
from src.models.contracts.agent_run_flag_conversations import (
    FlagConversationMessage,
    UserTurn,
    AssistantTurn,
)


@pytest.mark.asyncio
async def test_flag_conversation_persists_messages(db_session, seed_agent):
    from src.models.orm.agent_runs import AgentRun
    run = AgentRun(
        id=uuid4(), agent_id=seed_agent.id, trigger_type="test",
        status="completed", iterations_used=1, tokens_used=1, verdict="down",
    )
    db_session.add(run)
    await db_session.flush()

    conv = AgentRunFlagConversation(
        id=uuid4(),
        run_id=run.id,
        messages=[
            {"kind": "user", "content": "wrong route", "at": datetime.now(timezone.utc).isoformat()},
            {"kind": "assistant", "content": "I see why. Let me investigate.", "at": datetime.now(timezone.utc).isoformat()},
        ],
        created_at=datetime.now(timezone.utc),
        last_updated_at=datetime.now(timezone.utc),
    )
    db_session.add(conv)
    await db_session.flush()

    result = await db_session.execute(select(AgentRunFlagConversation).where(AgentRunFlagConversation.run_id == run.id))
    reloaded = result.scalar_one()
    assert len(reloaded.messages) == 2
    assert reloaded.messages[0]["content"] == "wrong route"


def test_flag_conversation_message_contract_validates():
    msg = UserTurn(content="wrong route")
    assert msg.kind == "user"
    assert msg.content == "wrong route"
    asst = AssistantTurn(content="I'll investigate")
    assert asst.kind == "assistant"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./test.sh tests/unit/test_flag_conversation_model.py -v`
Expected: FAIL (no module).

- [ ] **Step 3: Write migration**

`api/alembic/versions/20260421c_flag_conversations.py`:

```python
"""add per-flag tuning conversations

Revision ID: 20260421c_flag_conversations
Revises: 20260421b_run_verdicts_and_history
Create Date: 2026-04-21 ...
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260421c_flag_conversations"
down_revision = "20260421b_run_verdicts_and_history"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_run_flag_conversations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("agent_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "messages",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_flag_conversations_run_id",
        "agent_run_flag_conversations",
        ["run_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_flag_conversations_run_id", table_name="agent_run_flag_conversations")
    op.drop_table("agent_run_flag_conversations")
```

- [ ] **Step 4: Write ORM**

`api/src/models/orm/agent_run_flag_conversations.py`:

```python
"""Per-flag tuning conversation log."""
from datetime import datetime
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import Base


class AgentRunFlagConversation(Base):
    __tablename__ = "agent_run_flag_conversations"

    id: Mapped[UUID] = mapped_column(postgresql.UUID(as_uuid=True), primary_key=True, default=uuid4)
    run_id: Mapped[UUID] = mapped_column(
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("agent_runs.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    messages: Mapped[list[dict]] = mapped_column(
        postgresql.JSONB,
        nullable=False,
        default=list,
        server_default=sa.text("'[]'::jsonb"),
    )
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False)
    last_updated_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False)
```

Register in `__init__.py`.

- [ ] **Step 5: Write contracts**

`api/src/models/contracts/agent_run_flag_conversations.py`:

```python
"""Flag conversation message contracts."""
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class UserTurn(BaseModel):
    kind: Literal["user"] = "user"
    content: str
    at: datetime = Field(default_factory=lambda: datetime.utcnow())


class AssistantTurn(BaseModel):
    kind: Literal["assistant"] = "assistant"
    content: str
    at: datetime = Field(default_factory=lambda: datetime.utcnow())


class DiffOperation(BaseModel):
    op: Literal["add", "keep", "remove"]
    text: str


class ProposalTurn(BaseModel):
    kind: Literal["proposal"] = "proposal"
    summary: str
    diff: list[DiffOperation]
    at: datetime = Field(default_factory=lambda: datetime.utcnow())


class DryRunTurn(BaseModel):
    kind: Literal["dryrun"] = "dryrun"
    before: str
    after: str
    predicted: Literal["up", "down"]
    at: datetime = Field(default_factory=lambda: datetime.utcnow())


FlagConversationMessage = UserTurn | AssistantTurn | ProposalTurn | DryRunTurn


class FlagConversationResponse(BaseModel):
    id: UUID
    run_id: UUID
    messages: list[UserTurn | AssistantTurn | ProposalTurn | DryRunTurn]
    created_at: datetime
    last_updated_at: datetime


class SendFlagMessageRequest(BaseModel):
    content: str = Field(min_length=1, max_length=2000)
```

- [ ] **Step 6: Run test, apply migration**

Run: `docker restart bifrost-dev-bifrost-init`, wait 5s, `docker restart bifrost-dev-api`, then `./test.sh tests/unit/test_flag_conversation_model.py -v`.
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add api/alembic/versions/20260421c_flag_conversations.py \
        api/src/models/orm/agent_run_flag_conversations.py \
        api/src/models/orm/__init__.py \
        api/src/models/contracts/agent_run_flag_conversations.py \
        api/tests/unit/test_flag_conversation_model.py
git commit -m "feat(agent-runs): add per-flag tuning conversation table and contracts"
```

---

### Task 5: Agent prompt history table (for tuning audit)

**Files:**
- Create: `api/alembic/versions/20260421d_agent_prompt_history.py`
- Create: `api/src/models/orm/agent_prompt_history.py`
- Modify: `api/src/models/orm/__init__.py`
- Create: `api/tests/unit/test_agent_prompt_history_model.py`

- [ ] **Step 1: Write the failing test**

```python
"""Agent prompt version history."""
from datetime import datetime, timezone
from uuid import uuid4
import pytest
from sqlalchemy import select

from src.models.orm.agent_prompt_history import AgentPromptHistory


@pytest.mark.asyncio
async def test_prompt_history_persists(db_session, seed_agent, seed_user):
    h = AgentPromptHistory(
        id=uuid4(),
        agent_id=seed_agent.id,
        previous_prompt="Old prompt",
        new_prompt="New prompt with clarification rules",
        changed_by=seed_user.id,
        changed_at=datetime.now(timezone.utc),
        tuning_session_id=None,
        reason="Pattern: over-aggressive duplicate matching",
    )
    db_session.add(h)
    await db_session.flush()
    result = await db_session.execute(
        select(AgentPromptHistory).where(AgentPromptHistory.agent_id == seed_agent.id)
    )
    assert result.scalar_one().reason.startswith("Pattern")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./test.sh tests/unit/test_agent_prompt_history_model.py -v`
Expected: FAIL.

- [ ] **Step 3: Write migration**

`api/alembic/versions/20260421d_agent_prompt_history.py`:

```python
"""add agent prompt history

Revision ID: 20260421d_agent_prompt_history
Revises: 20260421c_flag_conversations
Create Date: 2026-04-21 ...
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260421d_agent_prompt_history"
down_revision = "20260421c_flag_conversations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_prompt_history",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "agent_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("agents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("previous_prompt", sa.Text(), nullable=False),
        sa.Column("new_prompt", sa.Text(), nullable=False),
        sa.Column(
            "changed_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("tuning_session_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
    )
    op.create_index("ix_prompt_history_agent_id_changed_at", "agent_prompt_history", ["agent_id", "changed_at"])


def downgrade() -> None:
    op.drop_index("ix_prompt_history_agent_id_changed_at", table_name="agent_prompt_history")
    op.drop_table("agent_prompt_history")
```

- [ ] **Step 4: Write ORM**

`api/src/models/orm/agent_prompt_history.py`:

```python
"""Agent prompt change history."""
from datetime import datetime
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import Base


class AgentPromptHistory(Base):
    __tablename__ = "agent_prompt_history"

    id: Mapped[UUID] = mapped_column(postgresql.UUID(as_uuid=True), primary_key=True, default=uuid4)
    agent_id: Mapped[UUID] = mapped_column(
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("agents.id", ondelete="CASCADE"),
        nullable=False,
    )
    previous_prompt: Mapped[str] = mapped_column(sa.Text(), nullable=False)
    new_prompt: Mapped[str] = mapped_column(sa.Text(), nullable=False)
    changed_by: Mapped[UUID | None] = mapped_column(
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    changed_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False)
    tuning_session_id: Mapped[UUID | None] = mapped_column(postgresql.UUID(as_uuid=True), nullable=True)
    reason: Mapped[str | None] = mapped_column(sa.Text(), nullable=True)
```

Register in `__init__.py`.

- [ ] **Step 5: Apply migration, run test**

Run: restart init + api; then `./test.sh tests/unit/test_agent_prompt_history_model.py -v`.
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add api/alembic/versions/20260421d_agent_prompt_history.py \
        api/src/models/orm/agent_prompt_history.py \
        api/src/models/orm/__init__.py \
        api/tests/unit/test_agent_prompt_history_model.py
git commit -m "feat(agents): add agent prompt version history table"
```

---

### Task 6: Full-text search tsvector + GIN

**Files:**
- Create: `api/alembic/versions/20260421e_run_tsvector_search.py`
- Create: `api/tests/unit/test_runs_full_text_search_schema.py`

- [ ] **Step 1: Write the failing test**

```python
"""Full-text search column exists and is indexed."""
import pytest
from sqlalchemy import text


@pytest.mark.asyncio
async def test_agent_runs_has_search_tsv_column(db_session):
    result = await db_session.execute(text("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'agent_runs' AND column_name = 'search_tsv'
    """))
    assert result.scalar_one_or_none() == "search_tsv"


@pytest.mark.asyncio
async def test_agent_runs_has_gin_index_on_search_tsv(db_session):
    result = await db_session.execute(text("""
        SELECT indexname FROM pg_indexes
        WHERE tablename = 'agent_runs' AND indexname = 'ix_agent_runs_search_tsv_gin'
    """))
    assert result.scalar_one_or_none() == "ix_agent_runs_search_tsv_gin"
```

- [ ] **Step 2: Run test, verify fail**

Run: `./test.sh tests/unit/test_runs_full_text_search_schema.py -v`
Expected: FAIL.

- [ ] **Step 3: Write migration**

`api/alembic/versions/20260421e_run_tsvector_search.py`:

```python
"""add tsvector full-text search column on agent_runs

Revision ID: 20260421e_run_tsvector_search
Revises: 20260421d_agent_prompt_history
Create Date: 2026-04-21 ...
"""
from alembic import op
import sqlalchemy as sa


revision = "20260421e_run_tsvector_search"
down_revision = "20260421d_agent_prompt_history"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Generated column concatenating searchable text fields
    op.execute("""
        ALTER TABLE agent_runs ADD COLUMN search_tsv tsvector
        GENERATED ALWAYS AS (
            to_tsvector('english',
                coalesce(asked, '') || ' ' ||
                coalesce(did, '') || ' ' ||
                coalesce(error, '') || ' ' ||
                coalesce(caller_email, '') || ' ' ||
                coalesce(caller_name, '') || ' ' ||
                coalesce(metadata::text, '')
            )
        ) STORED
    """)
    op.create_index(
        "ix_agent_runs_search_tsv_gin",
        "agent_runs",
        ["search_tsv"],
        postgresql_using="gin",
    )


def downgrade() -> None:
    op.drop_index("ix_agent_runs_search_tsv_gin", table_name="agent_runs")
    op.execute("ALTER TABLE agent_runs DROP COLUMN search_tsv")
```

- [ ] **Step 4: Apply migration, run test**

Restart init + api; `./test.sh tests/unit/test_runs_full_text_search_schema.py -v`.
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add api/alembic/versions/20260421e_run_tsvector_search.py \
        api/tests/unit/test_runs_full_text_search_schema.py
git commit -m "feat(agent-runs): add tsvector full-text search column and GIN index"
```

---

### Task 7: Verdict endpoint (POST/DELETE)

**Files:**
- Modify: `api/src/routers/agent_runs.py`
- Modify: `api/src/models/contracts/agent_runs.py`
- Create: `api/tests/unit/test_verdict_endpoint.py`

- [ ] **Step 1: Write the failing test**

```python
"""POST/DELETE /api/agent-runs/{id}/verdict."""
from uuid import uuid4
import pytest

from src.models.orm.agent_run_verdict_history import AgentRunVerdictHistory
from sqlalchemy import select


@pytest.mark.asyncio
async def test_set_verdict_up(client_as_admin, seed_completed_run):
    res = await client_as_admin.post(
        f"/api/agent-runs/{seed_completed_run.id}/verdict",
        json={"verdict": "up"},
    )
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["verdict"] == "up"


@pytest.mark.asyncio
async def test_set_verdict_down_with_note(client_as_admin, seed_completed_run):
    res = await client_as_admin.post(
        f"/api/agent-runs/{seed_completed_run.id}/verdict",
        json={"verdict": "down", "note": "Wrong routing"},
    )
    assert res.status_code == 200
    assert res.json()["verdict_note"] == "Wrong routing"


@pytest.mark.asyncio
async def test_set_verdict_on_non_completed_returns_409(client_as_admin, seed_running_run):
    res = await client_as_admin.post(
        f"/api/agent-runs/{seed_running_run.id}/verdict",
        json={"verdict": "up"},
    )
    assert res.status_code == 409


@pytest.mark.asyncio
async def test_clear_verdict(client_as_admin, seed_completed_run_with_verdict):
    res = await client_as_admin.delete(
        f"/api/agent-runs/{seed_completed_run_with_verdict.id}/verdict"
    )
    assert res.status_code == 200
    assert res.json()["verdict"] is None


@pytest.mark.asyncio
async def test_verdict_change_creates_audit_row(client_as_admin, seed_completed_run, db_session):
    await client_as_admin.post(
        f"/api/agent-runs/{seed_completed_run.id}/verdict",
        json={"verdict": "down", "note": "nope"},
    )
    result = await db_session.execute(
        select(AgentRunVerdictHistory).where(AgentRunVerdictHistory.run_id == seed_completed_run.id)
    )
    rows = result.scalars().all()
    assert len(rows) == 1
    assert rows[0].new_verdict == "down"
    assert rows[0].previous_verdict is None
```

(Fixtures `client_as_admin`, `seed_completed_run`, `seed_running_run`, `seed_completed_run_with_verdict` — add to `api/tests/unit/conftest.py` following existing patterns.)

- [ ] **Step 2: Run test, verify fail**

Run: `./test.sh tests/unit/test_verdict_endpoint.py -v`
Expected: FAIL (404 — endpoint doesn't exist).

- [ ] **Step 3: Add contract**

In `api/src/models/contracts/agent_runs.py`:

```python
class VerdictRequest(BaseModel):
    verdict: Literal["up", "down"]
    note: str | None = Field(default=None, max_length=2000)


class VerdictResponse(BaseModel):
    run_id: UUID
    verdict: str | None
    verdict_note: str | None
    verdict_set_at: datetime | None
    verdict_set_by: UUID | None
```

Add `Literal` and `Field` to imports if missing.

- [ ] **Step 4: Add endpoints**

In `api/src/routers/agent_runs.py`, add after `cancel_agent_run`:

```python
@router.post("/{run_id}/verdict", response_model=VerdictResponse)
async def set_verdict(
    run_id: UUID,
    request: VerdictRequest,
    db: DbSession,
    user: CurrentActiveUser,
) -> VerdictResponse:
    """Set a verdict on a completed run.

    Only allowed on status='completed' runs. Records an audit row.
    """
    query = select(AgentRun).where(AgentRun.id == run_id)
    if not user.is_superuser and user.organization_id:
        query = query.where(AgentRun.org_id == user.organization_id)
    result = await db.execute(query)
    run = result.scalar_one_or_none()
    if not run:
        raise HTTPException(404, f"Agent run {run_id} not found")
    if run.status != "completed":
        raise HTTPException(
            status_code=409,
            detail=f"Verdict can only be set on completed runs (current status: {run.status})",
        )

    from src.models.orm.agent_run_verdict_history import AgentRunVerdictHistory
    now = datetime.now(timezone.utc)
    previous = run.verdict
    run.verdict = request.verdict
    run.verdict_note = request.note
    run.verdict_set_at = now
    run.verdict_set_by = user.user_id

    db.add(AgentRunVerdictHistory(
        run_id=run.id,
        previous_verdict=previous,
        new_verdict=request.verdict,
        changed_by=user.user_id,
        changed_at=now,
        note=request.note,
    ))
    await db.flush()

    return VerdictResponse(
        run_id=run.id,
        verdict=run.verdict,
        verdict_note=run.verdict_note,
        verdict_set_at=run.verdict_set_at,
        verdict_set_by=run.verdict_set_by,
    )


@router.delete("/{run_id}/verdict", response_model=VerdictResponse)
async def clear_verdict(
    run_id: UUID,
    db: DbSession,
    user: CurrentActiveUser,
) -> VerdictResponse:
    query = select(AgentRun).where(AgentRun.id == run_id)
    if not user.is_superuser and user.organization_id:
        query = query.where(AgentRun.org_id == user.organization_id)
    result = await db.execute(query)
    run = result.scalar_one_or_none()
    if not run:
        raise HTTPException(404, f"Agent run {run_id} not found")

    from src.models.orm.agent_run_verdict_history import AgentRunVerdictHistory
    now = datetime.now(timezone.utc)
    previous = run.verdict
    run.verdict = None
    run.verdict_note = None
    run.verdict_set_at = now
    run.verdict_set_by = user.user_id

    db.add(AgentRunVerdictHistory(
        run_id=run.id,
        previous_verdict=previous,
        new_verdict=None,
        changed_by=user.user_id,
        changed_at=now,
        note=None,
    ))
    await db.flush()

    return VerdictResponse(
        run_id=run.id, verdict=None, verdict_note=None,
        verdict_set_at=now, verdict_set_by=user.user_id,
    )
```

Import `VerdictRequest` and `VerdictResponse` at the top.

- [ ] **Step 5: Run test, verify pass**

Run: `./test.sh tests/unit/test_verdict_endpoint.py -v`
Expected: PASS.

- [ ] **Step 6: Regenerate types, commit**

```bash
cd client && npm run generate:types && cd ..
git add api/src/routers/agent_runs.py \
        api/src/models/contracts/agent_runs.py \
        api/tests/unit/test_verdict_endpoint.py \
        api/tests/unit/conftest.py \
        client/src/lib/v1.d.ts
git commit -m "feat(agent-runs): add verdict set/clear endpoints with audit history"
```

---

### Task 8: Pause semantics — executor + HTTP response

**Files:**
- Modify: `api/src/services/execution/autonomous_agent_executor.py`
- Modify: `api/src/routers/agent_runs.py` (execute endpoint)
- Modify: `api/src/models/contracts/agent_runs.py` (add `PausedResult` to response union)
- Create: `api/tests/unit/test_pause_semantics.py`

**Design:** Paused agents do not broadcast failure. The API returns **HTTP 200** with a structured body indicating the paused state. This lets downstream systems (webhook senders, SDK consumers) handle pause as a graceful, expected condition rather than an error.

Response shape:
```json
{
    "status": "paused",
    "message": "Agent 'Ticket Triage' is paused. Request not processed.",
    "agent_id": "abc-...",
    "accepted": false
}
```

The executor itself returns `status="paused"` from `run(...)` so run-recording code short-circuits without creating an `AgentRun` row (no wasted AI usage rows, no confusing "paused" run history).

**In-flight runs finish normally.** The pause check is at executor entry only — if a run is already past `if not agent.is_active:` when pause is flipped, it completes. Matches the mockup's note about not killing active work.

- [ ] **Step 1: Write the failing test**

```python
"""Pausing an agent causes new runs to short-circuit; HTTP returns 200 with structured body."""
import pytest
from uuid import uuid4

from src.services.execution.autonomous_agent_executor import AutonomousAgentExecutor


@pytest.mark.asyncio
async def test_paused_agent_executor_returns_paused_status(db_session_factory, seed_agent_paused):
    executor = AutonomousAgentExecutor(session_factory=db_session_factory)
    result = await executor.run(seed_agent_paused, input_data={"foo": "bar"})
    assert result["status"] == "paused"
    assert result.get("accepted") is False


@pytest.mark.asyncio
async def test_execute_paused_agent_returns_200_with_paused_body(client_as_admin, seed_agent_paused):
    res = await client_as_admin.post(
        "/api/agent-runs/execute",
        json={"agent_name": seed_agent_paused.name, "input": {}},
    )
    assert res.status_code == 200  # graceful, not an error
    body = res.json()
    assert body["status"] == "paused"
    assert body["accepted"] is False
    assert "paused" in body["message"].lower()


@pytest.mark.asyncio
async def test_in_flight_run_completes_after_pause(db_session_factory, seed_agent_active):
    # Hard to fully simulate in a unit test without mocks — document as an assertion
    # against the code structure: the pause check occurs at executor entry, not mid-loop.
    import inspect
    source = inspect.getsource(AutonomousAgentExecutor.run)
    # Pause check must be before the main loop
    pause_pos = source.find("if not agent.is_active")
    loop_pos = source.find("while iterations_used")
    assert pause_pos > 0 and loop_pos > 0 and pause_pos < loop_pos, \
        "Pause check must occur before the main execution loop"
```

- [ ] **Step 2: Run test, verify fail**

Run: `./test.sh tests/unit/test_pause_semantics.py -v`
Expected: FAIL.

- [ ] **Step 3: Add pause check at executor start**

In `api/src/services/execution/autonomous_agent_executor.py`, inside `async def run(...)` at line 95 immediately after `run_id = run_id or str(uuid4())`:

```python
if not agent.is_active:
    return {
        "output": None,
        "iterations_used": 0,
        "tokens_used": 0,
        "status": "paused",
        "accepted": False,
        "message": f"Agent '{agent.name}' is paused. Request not processed.",
        "llm_model": agent.llm_model,
    }
```

- [ ] **Step 4: Add pause response to execute endpoint**

In `api/src/routers/agent_runs.py`, add a contract:

```python
# In api/src/models/contracts/agent_runs.py
class PausedResponse(BaseModel):
    status: Literal["paused"] = "paused"
    accepted: Literal[False] = False
    message: str
    agent_id: UUID
```

In `api/src/routers/agent_runs.py:400-441` (the `/execute` endpoint), after `agent = result.scalar_one_or_none()`:

```python
if not agent.is_active:
    return {
        "status": "paused",
        "accepted": False,
        "message": f"Agent '{agent.name}' is paused. Request not processed.",
        "agent_id": str(agent.id),
    }
```

(Keep the endpoint's return type as `dict` since execute already returns a generic dict. Don't change the return type annotation — callers discriminate on `status`.)

- [ ] **Step 5: Update the SDK client wrapper**

The SDK's `execute_agent` helper (if one exists — grep for it; likely in `api/bifrost/client.py` or similar) must handle `status="paused"` responses by raising a typed exception rather than returning the paused dict as a success. Check:

```bash
grep -rn "agent-runs/execute" api/bifrost/ 2>/dev/null || echo "no SDK helper found"
```

If a helper exists, add:

```python
if isinstance(response, dict) and response.get("status") == "paused":
    raise AgentPausedError(response.get("message"), agent_id=response.get("agent_id"))
```

Define `AgentPausedError` in the same module as the other SDK exceptions. Add a unit test.

If no SDK helper exists, skip this step.

- [ ] **Step 6: Run tests, commit**

```bash
./test.sh tests/unit/test_pause_semantics.py -v
git add api/src/services/execution/autonomous_agent_executor.py \
        api/src/routers/agent_runs.py \
        api/src/models/contracts/agent_runs.py \
        api/tests/unit/test_pause_semantics.py
[ -f api/bifrost/client.py ] && git add api/bifrost/client.py
git commit -m "feat(agent-runs): graceful pause via HTTP 200 + status='paused' body"
```

---

### Task 9: Runs search + metadata filter

**Files:**
- Modify: `api/src/routers/agent_runs.py`
- Create: `api/tests/unit/test_runs_search_and_metadata_filter.py`

- [ ] **Step 1: Write the failing test**

```python
"""Full-text search and metadata filter on agent-runs list."""
import pytest


@pytest.mark.asyncio
async def test_search_by_ticket_id(client_as_admin, seed_runs_with_metadata):
    # seed_runs_with_metadata: creates 3 runs with metadata.ticket_id = "4821", "4822", "4823"
    res = await client_as_admin.get("/api/agent-runs?q=4821")
    assert res.status_code == 200
    items = res.json()["items"]
    assert len(items) == 1
    assert items[0]["metadata"]["ticket_id"] == "4821"


@pytest.mark.asyncio
async def test_search_across_asked_and_did(client_as_admin, seed_runs_with_summaries):
    res = await client_as_admin.get("/api/agent-runs?q=password")
    assert res.status_code == 200
    items = res.json()["items"]
    assert any("password" in (r["asked"] or "").lower() for r in items)


@pytest.mark.asyncio
async def test_metadata_filter_exact_match(client_as_admin, seed_runs_with_metadata):
    res = await client_as_admin.get('/api/agent-runs?metadata_filter={"customer":"Acme"}')
    assert res.status_code == 200
    items = res.json()["items"]
    assert all(r["metadata"].get("customer") == "Acme" for r in items)


@pytest.mark.asyncio
async def test_verdict_filter(client_as_admin, seed_runs_mixed_verdicts):
    res = await client_as_admin.get("/api/agent-runs?verdict=down")
    assert res.status_code == 200
    items = res.json()["items"]
    assert all(r["verdict"] == "down" for r in items)
```

- [ ] **Step 2: Run test, verify fail**

Run: `./test.sh tests/unit/test_runs_search_and_metadata_filter.py -v`
Expected: FAIL.

- [ ] **Step 3: Add params and filter logic**

In `api/src/routers/agent_runs.py:75-124`, add after existing Query params:

```python
q: str | None = Query(None, description="Full-text search across asked/did/error/metadata"),
verdict: str | None = Query(None, description="Filter by verdict: 'up', 'down', or 'unreviewed'"),
metadata_filter: str | None = Query(None, description='JSON object of key-value pairs to match, e.g. {"customer":"Acme"}'),
```

Add filter clauses after existing filter block:

```python
if q:
    from sqlalchemy import func as sa_func
    query = query.where(
        sa_func.to_tsvector('english',
            sa_func.coalesce(AgentRun.asked, '') + ' ' +
            sa_func.coalesce(AgentRun.did, '') + ' ' +
            sa_func.coalesce(AgentRun.error, '') + ' ' +
            sa_func.coalesce(AgentRun.caller_email, '') + ' ' +
            sa_func.coalesce(AgentRun.caller_name, '') + ' ' +
            sa_func.coalesce(sa_func.cast(AgentRun.metadata, sa.Text), '')
        ).op('@@')(sa_func.plainto_tsquery('english', q))
    )

if verdict is not None:
    if verdict == "unreviewed":
        query = query.where(AgentRun.verdict.is_(None)).where(AgentRun.status == "completed")
    elif verdict in ("up", "down"):
        query = query.where(AgentRun.verdict == verdict)
    else:
        raise HTTPException(422, f"Invalid verdict filter: {verdict}")

if metadata_filter:
    import json as _json
    try:
        md = _json.loads(metadata_filter)
    except ValueError:
        raise HTTPException(422, "metadata_filter must be valid JSON")
    for k, v in md.items():
        query = query.where(AgentRun.metadata[k].astext == str(v))
```

- [ ] **Step 4: Run test, verify pass, commit**

```bash
./test.sh tests/unit/test_runs_search_and_metadata_filter.py -v
cd client && npm run generate:types && cd ..
git add api/src/routers/agent_runs.py \
        api/tests/unit/test_runs_search_and_metadata_filter.py \
        client/src/lib/v1.d.ts
git commit -m "feat(agent-runs): add full-text search, verdict filter, metadata filter"
```

---

## Phase 2 — Backend behavior (summarization, tuning, stats, dry-run)

### Task 10: LLM config — summarization + tuning model overrides

**Files:**
- Modify: `api/src/models/contracts/llm.py` (add optional `summarization_model` + `tuning_model` fields to `LLMConfigRequest` and `LLMConfigResponse`)
- Modify: `api/src/services/llm_config_service.py` (read/write the new fields in the stored `value_json`)
- Create: `api/src/services/execution/model_selection.py`
- Create: `api/tests/unit/test_model_selection.py`
- Modify: `client/src/pages/admin/AIConfigPage.tsx` (or equivalent — grep for where the AI config form lives) to add two optional inputs: "Summarization model override" and "Tuning model override," each with placeholder text "Defaults to the primary model"

**Design:** No new table — extends the existing LLM config stored at `system_configs` (category=`"llm"`, key=`"provider_config"`, value_json). Both new fields are nullable strings; null means "use default."

- [ ] **Step 1: Write the failing test**

```python
"""Dynamic model resolution from system settings."""
import pytest


@pytest.mark.asyncio
async def test_summarization_falls_back_to_default_model(db_session):
    from src.services.execution.model_selection import get_summarization_client
    # Seed LLM config with model="gpt-4o", no summarization_model override
    await seed_llm_config(db_session, model="gpt-4o")
    client, resolved_model = await get_summarization_client(db_session)
    assert resolved_model == "gpt-4o"


@pytest.mark.asyncio
async def test_summarization_uses_override_when_set(db_session):
    from src.services.execution.model_selection import get_summarization_client
    await seed_llm_config(db_session, model="gpt-4o", summarization_model="gpt-4o-mini")
    client, resolved_model = await get_summarization_client(db_session)
    assert resolved_model == "gpt-4o-mini"


@pytest.mark.asyncio
async def test_tuning_falls_back_to_default_model(db_session):
    from src.services.execution.model_selection import get_tuning_client
    await seed_llm_config(db_session, model="claude-sonnet-4-6")
    client, resolved_model = await get_tuning_client(db_session)
    assert resolved_model == "claude-sonnet-4-6"


@pytest.mark.asyncio
async def test_tuning_uses_override_when_set(db_session):
    from src.services.execution.model_selection import get_tuning_client
    await seed_llm_config(db_session, model="gpt-4o", tuning_model="gpt-4o")  # same model different role
    client, resolved_model = await get_tuning_client(db_session)
    assert resolved_model == "gpt-4o"


@pytest.mark.asyncio
async def test_provider_always_comes_from_default_config(db_session):
    """Override only affects model name, not provider or API key."""
    from src.services.execution.model_selection import get_summarization_client
    await seed_llm_config(db_session, provider="anthropic", model="claude-sonnet-4-6", summarization_model="claude-haiku-4-5")
    client, _ = await get_summarization_client(db_session)
    # Client is still the Anthropic client, not a switched provider
    from src.services.llm.anthropic_client import AnthropicClient
    assert isinstance(client, AnthropicClient)
```

(Helper `seed_llm_config` — add to `api/tests/unit/conftest.py` — writes a `SystemConfig` row with the appropriate `value_json`.)

- [ ] **Step 2: Run test, verify fail**

- [ ] **Step 3: Extend LLM config contracts**

In `api/src/models/contracts/llm.py`, add to `LLMConfigRequest` and `LLMConfigResponse`:

```python
summarization_model: str | None = Field(
    default=None,
    description="Model override for post-run summarization. Falls back to primary model if unset.",
)
tuning_model: str | None = Field(
    default=None,
    description="Model override for tuning chat + dry-run. Falls back to primary model if unset.",
)
```

- [ ] **Step 4: Persist new fields in `LLMConfigService`**

Update `get_config()` and `set_config()` in `api/src/services/llm_config_service.py` to read/write `summarization_model` and `tuning_model` in the stored `value_json` dict. Default to `None` if missing.

- [ ] **Step 5: Implement `model_selection.py`**

```python
"""Dynamic model resolution for summarization + tuning.

Reads overrides from LLMConfigService; falls back to the default model.
Provider is always the default provider.
"""
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.llm import BaseLLMClient, get_llm_client
from src.services.llm_config_service import LLMConfigService


async def get_summarization_client(db: AsyncSession) -> tuple[BaseLLMClient, str]:
    """Return (llm_client, resolved_model_name) for summarization calls."""
    service = LLMConfigService(db)
    config = await service.get_config()
    if config is None:
        raise RuntimeError("No LLM config; cannot summarize")
    model = config.summarization_model or config.model
    client = await get_llm_client(db)
    return client, model


async def get_tuning_client(db: AsyncSession) -> tuple[BaseLLMClient, str]:
    """Return (llm_client, resolved_model_name) for tuning/dry-run calls."""
    service = LLMConfigService(db)
    config = await service.get_config()
    if config is None:
        raise RuntimeError("No LLM config; cannot tune")
    model = config.tuning_model or config.model
    client = await get_llm_client(db)
    return client, model
```

- [ ] **Step 6: Wire the client UI**

Grep for the existing LLM config page:

```bash
grep -rn "LLMConfigRequest\|llm_config\|provider_config" client/src/pages/ client/src/components/ | head -10
```

Add two labeled text inputs under the current "Model" field:
- "Summarization model (optional)" — placeholder "Leave blank to use primary model"
- "Tuning model (optional)" — same placeholder

Both bind to the new optional fields. Save the whole config together, including these when set.

- [ ] **Step 7: Run tests, regenerate types, commit**

```bash
./test.sh tests/unit/test_model_selection.py -v
cd client && npm run generate:types && cd ..
git add api/src/models/contracts/llm.py \
        api/src/services/llm_config_service.py \
        api/src/services/execution/model_selection.py \
        api/tests/unit/test_model_selection.py \
        api/tests/unit/conftest.py \
        client/src/lib/v1.d.ts \
        client/src/pages/admin/AIConfigPage.tsx  # (or actual filename)
git commit -m "feat(llm): add summarization_model + tuning_model config overrides"
```

---

### Task 11: Worker message types for summarize + tune

**Files:**
- Modify: `api/src/jobs/agent_run_worker.py` (or equivalent — grep for the existing `agent-runs` queue consumer)
- Create: `api/src/jobs/summarize_worker.py` OR extend existing worker with new handlers
- Create: `api/tests/unit/test_worker_message_types.py`

**Context:** The existing `agent-runs` RabbitMQ queue carries `{run_id, agent_id, trigger_type, sync}` messages to the worker (see `api/src/services/execution/agent_run_service.py:60-66`). To move summarization and tuning out of the API process, we extend the worker to accept two new message kinds on the same queue (or a dedicated queue — see Step 1).

**Design decision — one queue or two?** Using a second queue (`agent-summarization`, `agent-tuning`) isolates summarization retries from execution retries. A slow summarization worker won't block the main execution queue. Going with **separate queues** — `agent-summarization` and `agent-tuning-chat`. Minimal infra change (RabbitMQ auto-creates queues on first publish).

- [ ] **Step 1: Find the existing worker entry point**

Run:
```bash
grep -rn "QUEUE_NAME = \"agent-runs\"" api/src/ | head -5
grep -rn "agent-runs" api/src/jobs/ | head -10
```

Identify the file that consumes the `agent-runs` queue (likely `api/src/jobs/agent_run_worker.py` or `api/src/jobs/workers.py`). Add its path to this task before proceeding.

- [ ] **Step 2: Write the failing test**

```python
"""Worker handles summarize + tune message types."""
import pytest
from unittest.mock import AsyncMock, patch


@pytest.mark.asyncio
async def test_summarize_message_calls_summarizer():
    from src.jobs.summarize_worker import handle_summarize_message
    with patch("src.jobs.summarize_worker.summarize_run") as mock:
        mock.return_value = None
        await handle_summarize_message({"run_id": "abc-123"})
        mock.assert_called_once()


@pytest.mark.asyncio
async def test_tune_chat_message_appends_and_replies():
    from src.jobs.summarize_worker import handle_tune_chat_message
    with patch("src.jobs.summarize_worker.append_user_message_and_reply") as mock:
        mock.return_value = None
        await handle_tune_chat_message({"run_id": "abc-123", "content": "wrong route"})
        mock.assert_called_once()
```

- [ ] **Step 3: Run test, verify fail**

- [ ] **Step 4: Implement the worker handlers**

`api/src/jobs/summarize_worker.py`:

```python
"""Worker consumers for post-run summarization and per-flag tuning chat."""
import logging
from uuid import UUID

from src.core.database import async_session_factory
from src.services.execution.run_summarizer import summarize_run
from src.services.execution.tuning_service import append_user_message_and_reply

logger = logging.getLogger(__name__)

SUMMARIZE_QUEUE = "agent-summarization"
TUNE_CHAT_QUEUE = "agent-tuning-chat"


async def handle_summarize_message(message: dict) -> None:
    """Consume a {run_id} message; generate summary. RabbitMQ retries on unhandled exceptions."""
    run_id = UUID(message["run_id"])
    try:
        await summarize_run(run_id, async_session_factory)
    except Exception as e:
        logger.exception(f"Summarization failed for run {run_id}")
        # Mark run as summary_status='failed' with the error so UI can offer regenerate
        async with async_session_factory() as db:
            from sqlalchemy import select
            from src.models.orm.agent_runs import AgentRun
            run = (await db.execute(select(AgentRun).where(AgentRun.id == run_id))).scalar_one_or_none()
            if run is not None:
                run.summary_status = "failed"
                run.summary_error = str(e)[:500]
                await db.commit()
        # Don't re-raise — we've recorded the failure state. User can retry from UI.


async def handle_tune_chat_message(message: dict) -> None:
    """Consume a {run_id, content} message; append user turn + assistant reply."""
    run_id = UUID(message["run_id"])
    content = message["content"]
    async with async_session_factory() as db:
        await append_user_message_and_reply(run_id, content, db)
```

Wire handlers into the worker bootstrap (in the file identified in Step 1). Follow the existing pattern used for the `agent-runs` queue — typically a `consume(queue_name, handler)` call.

- [ ] **Step 5: Add `publish_summarize_message` and `publish_tune_chat_message` helpers**

In `api/src/services/execution/run_summarizer.py`:

```python
from src.jobs.rabbitmq import publish_message

async def enqueue_summarize(run_id: UUID) -> None:
    await publish_message("agent-summarization", {"run_id": str(run_id)})
```

In `api/src/services/execution/tuning_service.py`:

```python
async def enqueue_tune_chat(run_id: UUID, content: str) -> None:
    await publish_message("agent-tuning-chat", {"run_id": str(run_id), "content": content})
```

- [ ] **Step 6: Run test, verify pass, commit**

```bash
./test.sh tests/unit/test_worker_message_types.py -v
git add api/src/jobs/summarize_worker.py \
        api/src/services/execution/run_summarizer.py \
        api/src/services/execution/tuning_service.py \
        api/tests/unit/test_worker_message_types.py \
        <worker-bootstrap-file-identified-in-step-1>
git commit -m "feat(workers): add summarize + tune-chat queue consumers"
```

---

### Task 12: Summarization service

**Files:**
- Create: `api/src/services/execution/run_summarizer.py`
- Modify: `api/src/services/execution/autonomous_agent_executor.py` (enqueue post-run)
- Create: `api/tests/unit/test_run_summarizer.py`

**Depends on:** Task 10 (`get_summarization_client`).

The summarizer takes a completed `AgentRun` + its steps and populates `asked`, `did`, `confidence`, `confidence_reason`, `metadata` (if the agent emitted it). Uses the resolved summarization model (default config model OR `llm_config.summarization_model` override — see Task 10), records one AIUsage row, sets `summary_generated_at`, updates `summary_status`.

**Execution path:** called by the worker via the `agent-summarization` queue (see Task 10). The executor does NOT run summarization directly — it enqueues a message after the run completes. This gives us retry semantics (RabbitMQ nack + requeue) and isolates summarization cost/latency from execution.

**State machine:**

```
pending   ── (worker picks up message) ──→ generating
generating ── (LLM success + parse OK) ──→ completed
generating ── (LLM fails or unparseable) ──→ failed (stores reason in summary_error)
failed    ── (regenerate endpoint called) ──→ pending (requeued)
pending   ── (regenerate-all batch) ──→ skipped (if too old / too expensive)
```

**Confidence clamping:** invalid confidence values (out of [0, 1], non-numeric) are dropped to `None` at write time. No DB constraint. Schema is permissive; application is strict.

- [ ] **Step 1: Write the failing test**

```python
"""Summarize a completed run."""
import pytest
from unittest.mock import AsyncMock, patch

from src.services.execution.run_summarizer import summarize_run


@pytest.mark.asyncio
async def test_summarize_run_populates_asked_did(db_session_factory, seed_completed_run_with_steps):
    with patch("src.services.execution.run_summarizer.get_llm_client") as mock_llm:
        mock_client = AsyncMock()
        mock_client.complete.return_value.content = (
            '{"asked": "reset my password", "did": "routed to Support", '
            '"confidence": 0.9, "confidence_reason": "clear intent"}'
        )
        mock_client.complete.return_value.input_tokens = 200
        mock_client.complete.return_value.output_tokens = 40
        mock_client.complete.return_value.model = "claude-haiku-4-5"
        mock_llm.return_value = mock_client

        await summarize_run(seed_completed_run_with_steps.id, db_session_factory)

    # Re-fetch
    async with db_session_factory() as db:
        from sqlalchemy import select
        from src.models.orm.agent_runs import AgentRun
        from src.models.orm.ai_usage import AIUsage
        run = (await db.execute(select(AgentRun).where(AgentRun.id == seed_completed_run_with_steps.id))).scalar_one()
        assert run.asked == "reset my password"
        assert run.did == "routed to Support"
        assert run.confidence == 0.9
        assert run.summary_generated_at is not None
        usage = (await db.execute(select(AIUsage).where(AIUsage.agent_run_id == run.id))).scalars().all()
        assert any(u.model == "claude-haiku-4-5" for u in usage)
```

- [ ] **Step 2: Run test, verify fail**

- [ ] **Step 3: Implement summarizer**

`api/src/services/execution/run_summarizer.py`:

```python
"""Summarize an agent run — populates asked, did, confidence, confidence_reason."""
import json
import logging
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession

from src.models.orm.agent_runs import AgentRun, AgentRunStep
from src.models.orm.ai_usage import AIUsage
from src.services.llm import LLMMessage
from src.services.execution.model_selection import get_summarization_client

logger = logging.getLogger(__name__)

SUMMARIZE_SYSTEM_PROMPT = """You summarize the behavior of an AI agent on a single run.
Given the agent's input, the tool calls it made, and the output it produced, produce a JSON object with:
  - asked: one short sentence (<100 chars) describing what the user asked for, in the user's voice
  - did: one short sentence (<100 chars) describing what the agent did, third person
  - confidence: float 0.0-1.0 — how confident the agent's output appears to be
  - confidence_reason: one sentence explaining the confidence assessment
  - metadata: object of k/v pairs (string -> string) extracting notable entities (ticket IDs, customer names, severity, etc.) — max 8 entries
Return ONLY the JSON object, no prose."""


def _clamp_confidence(value) -> float | None:
    """Clamp an LLM-returned confidence to [0.0, 1.0], or return None if invalid."""
    if value is None:
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    if f < 0.0 or f > 1.0:
        # Clamp rather than discard — "1.2" is most likely "very confident"
        return max(0.0, min(1.0, f))
    return f


async def summarize_run(run_id: UUID, session_factory: async_sessionmaker[AsyncSession]) -> None:
    """Summarize a completed run. Updates summary_status through generating→completed/failed.

    Idempotent: if summary_status is 'completed', returns immediately.
    """
    async with session_factory() as db:
        run = (await db.execute(
            select(AgentRun).where(AgentRun.id == run_id)
        )).scalar_one_or_none()
        if run is None or run.status != "completed":
            return
        if run.summary_status == "completed":
            return  # idempotent

        run.summary_status = "generating"
        run.summary_error = None
        await db.commit()

        steps = (await db.execute(
            select(AgentRunStep).where(AgentRunStep.run_id == run_id).order_by(AgentRunStep.step_number)
        )).scalars().all()

        llm_client, resolved_model = await get_summarization_client(db)

    # Build the summarization input
    step_summary = []
    for s in steps:
        if s.type == "tool_call":
            step_summary.append(f"tool: {s.content.get('tool')}({json.dumps(s.content.get('args', {}))[:200]})")
        elif s.type in ("llm_response", "agent_message"):
            content_text = json.dumps(s.content)[:300] if s.content else ""
            step_summary.append(f"llm: {content_text}")

    user_content = json.dumps({
        "input": run.input,
        "output": run.output,
        "tool_calls": step_summary[:20],
    })

    messages = [
        LLMMessage(role="system", content=SUMMARIZE_SYSTEM_PROMPT),
        LLMMessage(role="user", content=user_content),
    ]

    try:
        response = await llm_client.complete(messages=messages, model=resolved_model, max_tokens=400)
        parsed = json.loads(response.content)
    except json.JSONDecodeError as e:
        logger.warning(f"Summarizer returned invalid JSON for run {run_id}")
        async with session_factory() as db:
            run = (await db.execute(select(AgentRun).where(AgentRun.id == run_id))).scalar_one()
            run.summary_status = "failed"
            run.summary_error = f"Invalid JSON from summarization model: {str(e)[:200]}"
            await db.commit()
        return
    except Exception as e:
        logger.exception(f"Summarizer LLM call failed for run {run_id}")
        async with session_factory() as db:
            run = (await db.execute(select(AgentRun).where(AgentRun.id == run_id))).scalar_one()
            run.summary_status = "failed"
            run.summary_error = f"LLM call failed: {str(e)[:200]}"
            await db.commit()
        # Re-raise so RabbitMQ nacks the message and retries with backoff
        raise

    # Persist success
    async with session_factory() as db:
        run = (await db.execute(select(AgentRun).where(AgentRun.id == run_id))).scalar_one()
        run.asked = (parsed.get("asked") or "")[:400]
        run.did = (parsed.get("did") or "")[:400]
        run.confidence = _clamp_confidence(parsed.get("confidence"))
        run.confidence_reason = (parsed.get("confidence_reason") or "")[:500]
        md = parsed.get("metadata") or {}
        if isinstance(md, dict):
            # Merge extracted metadata into any agent-supplied metadata (agent-supplied wins)
            merged = {**{str(k): str(v)[:256] for k, v in md.items() if isinstance(v, (str, int, float))}, **(run.metadata or {})}
            # Cap at 16 keys
            run.metadata = dict(list(merged.items())[:16])
        run.summary_generated_at = datetime.now(timezone.utc)
        run.summary_status = "completed"
        run.summary_error = None

        # Record AI usage — summarization costs land on the same run
        db.add(AIUsage(
            agent_run_id=run.id,
            organization_id=run.org_id,
            provider="anthropic",
            model=response.model or resolved_model,
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
            cost=None,  # computed by pricing service if present; otherwise null
            timestamp=datetime.now(timezone.utc),
            sequence=9999,  # distinguish from execution AI calls
        ))
        await db.commit()
```

- [ ] **Step 4: Enqueue summarization from executor on completion**

In `api/src/services/execution/autonomous_agent_executor.py`, after the run completes and before returning the result dict (search for `return {` near the end of `run(...)`), add:

```python
# Enqueue post-run summarization via worker queue (non-blocking; worker handles retries)
if status == "completed":
    try:
        from src.services.execution.run_summarizer import enqueue_summarize
        await enqueue_summarize(UUID(run_id))
    except Exception:
        logger.exception(f"Failed to enqueue summarizer for run {run_id}")
        # Don't fail the run — summary_status stays 'pending' and the UI can offer regenerate
```

- [ ] **Step 5: Run test, verify pass, commit**

```bash
./test.sh tests/unit/test_run_summarizer.py -v
git add api/src/services/execution/run_summarizer.py \
        api/src/services/execution/autonomous_agent_executor.py \
        api/tests/unit/test_run_summarizer.py
git commit -m "feat(executor): summarize runs post-completion, track cost on run"
```


---

### Task 13: Metadata SDK surface (agent emits metadata during run)

**Files:**
- Create: `api/src/services/execution/run_metadata.py`
- Create: `api/tests/unit/test_run_metadata_sdk.py`
- Modify: `api/src/services/execution/autonomous_agent_executor.py` (pass metadata callback into tool context)

- [ ] **Step 1: Write the failing test**

```python
"""Agents can emit metadata during execution."""
import pytest
from uuid import uuid4

from src.services.execution.run_metadata import set_run_metadata


@pytest.mark.asyncio
async def test_set_metadata_persists(db_session_factory, seed_completed_run):
    await set_run_metadata(
        seed_completed_run.id,
        {"ticket_id": "4821", "severity": "high"},
        session_factory=db_session_factory,
    )
    async with db_session_factory() as db:
        from sqlalchemy import select
        from src.models.orm.agent_runs import AgentRun
        run = (await db.execute(select(AgentRun).where(AgentRun.id == seed_completed_run.id))).scalar_one()
        assert run.metadata == {"ticket_id": "4821", "severity": "high"}


@pytest.mark.asyncio
async def test_set_metadata_cap_at_16_keys(db_session_factory, seed_completed_run):
    from src.services.execution.run_metadata import TooManyMetadataKeys
    with pytest.raises(TooManyMetadataKeys):
        await set_run_metadata(
            seed_completed_run.id,
            {f"k{i}": "v" for i in range(17)},
            session_factory=db_session_factory,
        )


@pytest.mark.asyncio
async def test_set_metadata_value_length_capped(db_session_factory, seed_completed_run):
    await set_run_metadata(
        seed_completed_run.id,
        {"foo": "x" * 1000},
        session_factory=db_session_factory,
    )
    async with db_session_factory() as db:
        from sqlalchemy import select
        from src.models.orm.agent_runs import AgentRun
        run = (await db.execute(select(AgentRun).where(AgentRun.id == seed_completed_run.id))).scalar_one()
        assert len(run.metadata["foo"]) == 256
```

- [ ] **Step 2: Run test, verify fail**

- [ ] **Step 3: Implement**

`api/src/services/execution/run_metadata.py`:

```python
"""Helpers for agent-emitted metadata on runs."""
from typing import Mapping
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession

from src.models.orm.agent_runs import AgentRun


class TooManyMetadataKeys(ValueError):
    pass


MAX_KEYS = 16
MAX_VALUE_LEN = 256


async def set_run_metadata(
    run_id: UUID,
    metadata: Mapping[str, str],
    *,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Replace a run's metadata dict. Validates caps."""
    if len(metadata) > MAX_KEYS:
        raise TooManyMetadataKeys(f"Maximum {MAX_KEYS} metadata keys (got {len(metadata)})")
    cleaned = {
        str(k)[:64]: str(v)[:MAX_VALUE_LEN]
        for k, v in metadata.items()
    }
    async with session_factory() as db:
        run = (await db.execute(select(AgentRun).where(AgentRun.id == run_id))).scalar_one()
        run.metadata = cleaned
        await db.commit()
```

- [ ] **Step 4: Run test, verify pass, commit**

```bash
./test.sh tests/unit/test_run_metadata_sdk.py -v
git add api/src/services/execution/run_metadata.py \
        api/tests/unit/test_run_metadata_sdk.py
git commit -m "feat(agent-runs): add SDK helper for agent-emitted metadata"
```

---

### Task 14: Agent stats endpoint

**Files:**
- Create: `api/src/services/agent_stats.py`
- Create: `api/src/models/contracts/agent_stats.py`
- Modify: `api/src/routers/agents.py`
- Create: `api/tests/unit/test_agent_stats_service.py`

- [ ] **Step 1: Write the failing test**

```python
"""Agent stats service computes fleet + per-agent metrics."""
import pytest

from src.services.agent_stats import get_agent_stats, get_fleet_stats


@pytest.mark.asyncio
async def test_per_agent_stats(db_session, seed_agent, seed_runs_7d_for_agent):
    stats = await get_agent_stats(seed_agent.id, db_session, window_days=7)
    assert stats.runs_7d > 0
    assert 0.0 <= stats.success_rate <= 1.0
    assert stats.avg_duration_ms > 0
    assert stats.total_cost_7d >= 0
    assert stats.last_run_at is not None
    assert len(stats.runs_by_day) == 7


@pytest.mark.asyncio
async def test_fleet_stats(db_session, seed_multiple_agents):
    s = await get_fleet_stats(db_session, org_id=None, window_days=7)
    assert s.total_runs > 0
    assert s.active_agents > 0
    assert 0.0 <= s.avg_success_rate <= 1.0
    assert s.needs_review >= 0
```

- [ ] **Step 2: Run test, verify fail**

- [ ] **Step 3: Implement service**

`api/src/services/agent_stats.py`:

```python
"""Agent stats — per-agent and fleet-level."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.contracts.agent_stats import AgentStatsResponse, FleetStatsResponse
from src.models.orm.agent_runs import AgentRun
from src.models.orm.ai_usage import AIUsage
from src.models.orm.agents import Agent


async def get_agent_stats(agent_id: UUID, db: AsyncSession, *, window_days: int = 7) -> AgentStatsResponse:
    cutoff = datetime.now(timezone.utc) - timedelta(days=window_days)
    base = select(AgentRun).where(
        AgentRun.agent_id == agent_id,
        AgentRun.created_at >= cutoff,
    )
    runs_result = await db.execute(base)
    runs = runs_result.scalars().all()

    runs_count = len(runs)
    completed = [r for r in runs if r.status == "completed"]
    success_rate = len(completed) / max(1, runs_count)
    durations = [r.duration_ms for r in runs if r.duration_ms is not None]
    avg_duration_ms = int(sum(durations) / max(1, len(durations))) if durations else 0

    cost_result = await db.execute(
        select(func.sum(AIUsage.cost)).where(
            AIUsage.agent_run_id.in_([r.id for r in runs] or [UUID(int=0)])
        )
    )
    total_cost = cost_result.scalar() or Decimal("0")

    last_run_at = max((r.created_at for r in runs), default=None)

    # 7-day bucket counts
    buckets = [0] * window_days
    now = datetime.now(timezone.utc)
    for r in runs:
        day_offset = (now - r.created_at).days
        if 0 <= day_offset < window_days:
            buckets[window_days - 1 - day_offset] += 1

    return AgentStatsResponse(
        agent_id=agent_id,
        runs_7d=runs_count,
        success_rate=success_rate,
        avg_duration_ms=avg_duration_ms,
        total_cost_7d=total_cost,
        last_run_at=last_run_at,
        runs_by_day=buckets,
        needs_review=sum(1 for r in runs if r.verdict == "down"),
        unreviewed=sum(1 for r in runs if r.verdict is None and r.status == "completed"),
    )


async def get_fleet_stats(db: AsyncSession, *, org_id: UUID | None, window_days: int = 7) -> FleetStatsResponse:
    cutoff = datetime.now(timezone.utc) - timedelta(days=window_days)
    agent_filter = []
    if org_id is not None:
        agent_filter.append(Agent.organization_id == org_id)
    run_filter = [AgentRun.created_at >= cutoff]
    if org_id is not None:
        run_filter.append(AgentRun.org_id == org_id)

    total_runs = (await db.execute(
        select(func.count(AgentRun.id)).where(*run_filter)
    )).scalar() or 0
    completed = (await db.execute(
        select(func.count(AgentRun.id)).where(*run_filter, AgentRun.status == "completed")
    )).scalar() or 0
    active_agents = (await db.execute(
        select(func.count(Agent.id)).where(*agent_filter, Agent.is_active.is_(True))
    )).scalar() or 0
    needs_review = (await db.execute(
        select(func.count(AgentRun.id)).where(*run_filter, AgentRun.verdict == "down")
    )).scalar() or 0
    # Note: cost query uses explicit join to avoid org_id mismatch between AIUsage and Run
    total_cost_query = select(func.sum(AIUsage.cost)).join(
        AgentRun, AgentRun.id == AIUsage.agent_run_id
    ).where(*run_filter)
    total_cost = (await db.execute(total_cost_query)).scalar() or Decimal("0")

    return FleetStatsResponse(
        total_runs=total_runs,
        avg_success_rate=(completed / max(1, total_runs)),
        total_cost_7d=total_cost,
        active_agents=active_agents,
        needs_review=needs_review,
    )
```

- [ ] **Step 4: Write contracts**

`api/src/models/contracts/agent_stats.py`:

```python
"""Agent stats response models."""
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field


class AgentStatsResponse(BaseModel):
    agent_id: UUID
    runs_7d: int
    success_rate: float
    avg_duration_ms: int
    total_cost_7d: Decimal
    last_run_at: datetime | None
    runs_by_day: list[int]
    needs_review: int
    unreviewed: int


class FleetStatsResponse(BaseModel):
    total_runs: int
    avg_success_rate: float
    total_cost_7d: Decimal
    active_agents: int
    needs_review: int
```

- [ ] **Step 5: Add endpoints**

In `api/src/routers/agents.py`, add:

```python
@router.get("/{agent_id}/stats", response_model=AgentStatsResponse)
async def get_agent_stats_endpoint(
    agent_id: UUID,
    db: DbSession,
    user: CurrentActiveUser,
    window_days: int = Query(7, ge=1, le=90),
) -> AgentStatsResponse:
    from src.services.agent_stats import get_agent_stats
    # TODO: access check via repo (same pattern as get_agent)
    return await get_agent_stats(agent_id, db, window_days=window_days)


@router.get("/stats/fleet", response_model=FleetStatsResponse)
async def get_fleet_stats_endpoint(
    db: DbSession,
    user: CurrentActiveUser,
    window_days: int = Query(7, ge=1, le=90),
) -> FleetStatsResponse:
    from src.services.agent_stats import get_fleet_stats
    org_id = None if user.is_superuser else user.organization_id
    return await get_fleet_stats(db, org_id=org_id, window_days=window_days)
```

Import contracts at top.

- [ ] **Step 6: Run test, verify pass, regenerate types, commit**

```bash
./test.sh tests/unit/test_agent_stats_service.py -v
cd client && npm run generate:types && cd ..
git add api/src/services/agent_stats.py \
        api/src/models/contracts/agent_stats.py \
        api/src/routers/agents.py \
        api/tests/unit/test_agent_stats_service.py \
        client/src/lib/v1.d.ts
git commit -m "feat(agents): add per-agent and fleet stats endpoints"
```

---

### Task 15: Flag-conversation endpoints (GET, POST, assistant response)

**Files:**
- Create: `api/src/services/execution/tuning_service.py`
- Modify: `api/src/routers/agent_runs.py`
- Create: `api/tests/unit/test_flag_conversation_endpoints.py`

Endpoints:
- `GET /api/agent-runs/{run_id}/flag-conversation` — fetch conversation
- `POST /api/agent-runs/{run_id}/flag-conversation/message` — user sends a message; server appends user turn + calls tuning LLM to append assistant turn; returns updated conversation. Charges to run's cost.
- `POST /api/agent-runs/{run_id}/flag-conversation/dry-run` — runs a sandboxed re-execution with the most recent proposed prompt against just this run.

(Tuning LLM call uses the resolved tuning model — `llm_config.tuning_model` override or fall back to the primary model — and records AIUsage on the parent run.)

- [ ] **Step 1: Write the failing test**

```python
"""Flag conversation CRUD + LLM response."""
import pytest
from unittest.mock import AsyncMock, patch
from uuid import uuid4


@pytest.mark.asyncio
async def test_get_empty_conversation_returns_empty(client_as_admin, seed_completed_flagged_run):
    res = await client_as_admin.get(
        f"/api/agent-runs/{seed_completed_flagged_run.id}/flag-conversation"
    )
    assert res.status_code == 200
    assert res.json()["messages"] == []


@pytest.mark.asyncio
async def test_post_message_appends_and_gets_assistant_reply(
    client_as_admin, seed_completed_flagged_run
):
    with patch("src.services.execution.tuning_service.get_tuning_client") as mock_llm:
        mock_client = AsyncMock()
        mock_client.complete.return_value.content = "I see the issue — routing was overeager."
        mock_client.complete.return_value.input_tokens = 500
        mock_client.complete.return_value.output_tokens = 50
        mock_client.complete.return_value.model = "claude-sonnet-4-6"
        mock_llm.return_value = mock_client

        res = await client_as_admin.post(
            f"/api/agent-runs/{seed_completed_flagged_run.id}/flag-conversation/message",
            json={"content": "This was wrong."},
        )
    assert res.status_code == 200
    messages = res.json()["messages"]
    assert messages[0]["kind"] == "user"
    assert messages[0]["content"] == "This was wrong."
    assert messages[1]["kind"] == "assistant"
    assert "routing" in messages[1]["content"]


@pytest.mark.asyncio
async def test_tuning_llm_call_recorded_in_ai_usage(
    client_as_admin, seed_completed_flagged_run, db_session
):
    # ... (similar to above, then query AIUsage by agent_run_id)
    ...
```

- [ ] **Step 2: Run test, verify fail**

- [ ] **Step 3: Implement tuning service**

`api/src/services/execution/tuning_service.py`:

```python
"""Per-flag and consolidated tuning service."""
import json
import logging
from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession

from src.models.orm.agent_runs import AgentRun, AgentRunStep
from src.models.orm.ai_usage import AIUsage
from src.models.orm.agent_run_flag_conversations import AgentRunFlagConversation
from src.services.llm import LLMMessage
from src.services.execution.model_selection import get_tuning_client

logger = logging.getLogger(__name__)


FLAG_DIAGNOSE_SYSTEM = """You help users refine AI agent prompts. Given a flagged agent run (one that produced a wrong result), the user's note about what went wrong, and the conversation so far, respond naturally:
- Ask a clarifying question if the note is ambiguous
- Diagnose the likely cause by pointing to the prompt, tool choice, or missing knowledge
- When you have enough info, propose a specific, minimal prompt change (as a diff — add/keep/remove blocks)
Don't propose changes if the user hasn't confirmed the issue. Always be specific. Never apologize — the user wants action."""


async def get_or_create_conversation(
    run_id: UUID, db: AsyncSession
) -> AgentRunFlagConversation:
    conv = (await db.execute(
        select(AgentRunFlagConversation).where(AgentRunFlagConversation.run_id == run_id)
    )).scalar_one_or_none()
    if conv is None:
        now = datetime.now(timezone.utc)
        conv = AgentRunFlagConversation(
            id=uuid4(),
            run_id=run_id,
            messages=[],
            created_at=now,
            last_updated_at=now,
        )
        db.add(conv)
        await db.flush()
    return conv


async def append_user_message_and_reply(
    run_id: UUID,
    user_content: str,
    db: AsyncSession,
) -> AgentRunFlagConversation:
    run = (await db.execute(select(AgentRun).where(AgentRun.id == run_id))).scalar_one()
    conv = await get_or_create_conversation(run_id, db)

    now = datetime.now(timezone.utc)
    messages = list(conv.messages or [])
    messages.append({
        "kind": "user",
        "content": user_content,
        "at": now.isoformat(),
    })

    # Build the LLM prompt
    steps = (await db.execute(
        select(AgentRunStep).where(AgentRunStep.run_id == run_id).order_by(AgentRunStep.step_number)
    )).scalars().all()
    step_summary = "\n".join(
        f"- {s.type}: {json.dumps(s.content)[:300] if s.content else ''}"
        for s in steps
    )

    llm_messages = [
        LLMMessage(role="system", content=FLAG_DIAGNOSE_SYSTEM),
        LLMMessage(role="user", content=json.dumps({
            "agent_name": run.agent.name if run.agent else None,
            "input": run.input,
            "output": run.output,
            "steps": step_summary,
            "history": messages,
        })),
    ]

    llm_client, resolved_model = await get_tuning_client(db)
    response = await llm_client.complete(messages=llm_messages, model=resolved_model, max_tokens=1500)

    messages.append({
        "kind": "assistant",
        "content": response.content,
        "at": datetime.now(timezone.utc).isoformat(),
    })

    conv.messages = messages
    conv.last_updated_at = datetime.now(timezone.utc)

    # Record cost against the flagged run
    db.add(AIUsage(
        agent_run_id=run_id,
        organization_id=run.org_id,
        provider="anthropic",
        model=response.model or resolved_model,
        input_tokens=response.input_tokens,
        output_tokens=response.output_tokens,
        cost=None,
        timestamp=datetime.now(timezone.utc),
        sequence=9500,  # separate from execution + summarization
    ))
    await db.commit()
    return conv
```

- [ ] **Step 4: Add endpoints**

In `api/src/routers/agent_runs.py`:

```python
from src.models.contracts.agent_run_flag_conversations import (
    FlagConversationResponse, SendFlagMessageRequest,
)
from src.services.execution.tuning_service import (
    get_or_create_conversation, append_user_message_and_reply,
)


@router.get("/{run_id}/flag-conversation", response_model=FlagConversationResponse)
async def get_flag_conversation(run_id: UUID, db: DbSession, user: CurrentActiveUser):
    # access check: user can read the run
    run = (await db.execute(select(AgentRun).where(AgentRun.id == run_id))).scalar_one_or_none()
    if run is None or (not user.is_superuser and user.organization_id != run.org_id):
        raise HTTPException(404, "Run not found")
    conv = await get_or_create_conversation(run_id, db)
    return FlagConversationResponse(
        id=conv.id, run_id=conv.run_id, messages=conv.messages,
        created_at=conv.created_at, last_updated_at=conv.last_updated_at,
    )


@router.post("/{run_id}/flag-conversation/message", response_model=FlagConversationResponse)
async def send_flag_message(
    run_id: UUID,
    request: SendFlagMessageRequest,
    db: DbSession,
    user: CurrentActiveUser,
):
    run = (await db.execute(select(AgentRun).where(AgentRun.id == run_id))).scalar_one_or_none()
    if run is None or (not user.is_superuser and user.organization_id != run.org_id):
        raise HTTPException(404, "Run not found")
    if run.status != "completed":
        raise HTTPException(409, "Flag conversations only available on completed runs")

    conv = await append_user_message_and_reply(run_id, request.content, db)
    return FlagConversationResponse(
        id=conv.id, run_id=conv.run_id, messages=conv.messages,
        created_at=conv.created_at, last_updated_at=conv.last_updated_at,
    )
```

- [ ] **Step 5: Run test, verify pass, regenerate types, commit**

```bash
./test.sh tests/unit/test_flag_conversation_endpoints.py -v
cd client && npm run generate:types && cd ..
git add api/src/services/execution/tuning_service.py \
        api/src/routers/agent_runs.py \
        api/tests/unit/test_flag_conversation_endpoints.py \
        client/src/lib/v1.d.ts
git commit -m "feat(agent-runs): add per-flag tuning conversation endpoints"
```

---

### Task 16: Dry-run: "would you make the same decision with this prompt?"

**Files:**
- Create: `api/src/services/execution/dry_run.py`
- Modify: `api/src/routers/agent_runs.py` (dry-run endpoint)
- Create: `api/tests/unit/test_dry_run.py`

**Design — intentionally simple.** Not a full sandbox. Not replaying tool calls. The dry-run is a single LLM call that gives the model:

- The proposed new system prompt
- The original run's input
- The original run's tool calls and their recorded results
- The original run's final output

...and asks it: **"Given this new prompt, would you still produce this output? If not, what would you do differently?"**

One LLM call, no tool execution, no mocking framework. Output is a natural-language "would still decide the same" or "would do X differently" plus a confidence score the user can eyeball.

Writes one AIUsage row on the original run (`sequence=8000`). Uses the resolved tuning model (override or default) — same selector as tuning chat since the reasoning requirements are similar.

- [ ] **Step 1: Write the failing test**

```python
import pytest
from unittest.mock import AsyncMock, patch

from src.services.execution.dry_run import evaluate_against_prompt


@pytest.mark.asyncio
async def test_dry_run_returns_structured_verdict(db_session_factory, seed_completed_run_with_steps):
    with patch("src.services.execution.dry_run.get_tuning_client") as mock_llm:
        mock_client = AsyncMock()
        mock_client.complete.return_value.content = (
            '{"would_still_decide_same": false, '
            '"reasoning": "The new prompt would require clarification before routing, '
            'so I would have asked rather than closed as duplicate.", '
            '"alternative_action": "Ask if caller is on same VPN gateway as #4821", '
            '"confidence": 0.82}'
        )
        mock_client.complete.return_value.input_tokens = 700
        mock_client.complete.return_value.output_tokens = 120
        mock_client.complete.return_value.model = "claude-sonnet-4-6"
        mock_llm.return_value = mock_client

        result = await evaluate_against_prompt(
            run_id=seed_completed_run_with_steps.id,
            proposed_prompt="New prompt with clarification rule",
            session_factory=db_session_factory,
        )

    assert result.would_still_decide_same is False
    assert "clarification" in result.alternative_action.lower()
    assert 0.0 <= result.confidence <= 1.0


@pytest.mark.asyncio
async def test_dry_run_does_not_mutate_agent(db_session_factory, seed_agent, seed_completed_run_with_steps):
    from sqlalchemy import select
    from src.models.orm.agents import Agent
    original = seed_agent.system_prompt
    with patch("src.services.execution.dry_run.get_tuning_client") as mock_llm:
        mock_client = AsyncMock()
        mock_client.complete.return_value.content = '{"would_still_decide_same": true, "reasoning": "same", "alternative_action": null, "confidence": 0.9}'
        mock_client.complete.return_value.input_tokens = 100
        mock_client.complete.return_value.output_tokens = 20
        mock_client.complete.return_value.model = "claude-sonnet-4-6"
        mock_llm.return_value = mock_client

        await evaluate_against_prompt(
            run_id=seed_completed_run_with_steps.id,
            proposed_prompt="Different prompt",
            session_factory=db_session_factory,
        )
    async with db_session_factory() as db:
        agent = (await db.execute(select(Agent).where(Agent.id == seed_agent.id))).scalar_one()
        assert agent.system_prompt == original


@pytest.mark.asyncio
async def test_dry_run_records_ai_usage_on_original_run(db_session_factory, seed_completed_run_with_steps):
    # After a dry-run, AIUsage has a row with sequence=8000 tagged to the run
    ...
```

- [ ] **Step 2: Run test, verify fail**

- [ ] **Step 3: Implement**

`api/src/services/execution/dry_run.py`:

```python
"""Dry-run a proposed prompt against a past run's transcript.

Intentionally simple: one LLM call. The model reads the full transcript (input, tool calls,
tool results, final output) plus the proposed new system prompt, and answers:
"Would you have made the same decision with this prompt? If not, what would you have done?"

No tool execution, no sandbox. Fast, cheap, probabilistic.
"""
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession

from src.models.orm.agent_runs import AgentRun, AgentRunStep
from src.models.orm.ai_usage import AIUsage
from src.services.llm import LLMMessage
from src.services.execution.model_selection import get_tuning_client

logger = logging.getLogger(__name__)


DRY_RUN_SYSTEM_PROMPT = """You evaluate whether a proposed system prompt change would alter an agent's past decision.

Given: (1) a proposed new system prompt, (2) the original user input, (3) the tool calls the agent made and their recorded results, and (4) the final output the agent produced.

Answer: with this new prompt, would you have made the same decision?

Return ONLY a JSON object:
{
  "would_still_decide_same": bool,
  "reasoning": "<one or two sentences explaining your conclusion>",
  "alternative_action": "<null if same decision; otherwise what you would do instead, one sentence>",
  "confidence": <float 0.0-1.0>
}
Be honest. If the new prompt has no relevant guidance, say would_still_decide_same=true."""


@dataclass
class DryRunResult:
    would_still_decide_same: bool
    reasoning: str
    alternative_action: str | None
    confidence: float


async def evaluate_against_prompt(
    *,
    run_id: UUID,
    proposed_prompt: str,
    session_factory: async_sessionmaker[AsyncSession],
) -> DryRunResult:
    """Ask the tuning model whether the proposed prompt would change this run's decision."""
    async with session_factory() as db:
        run = (await db.execute(select(AgentRun).where(AgentRun.id == run_id))).scalar_one()
        steps = (await db.execute(
            select(AgentRunStep).where(AgentRunStep.run_id == run_id).order_by(AgentRunStep.step_number)
        )).scalars().all()
        llm_client, resolved_model = await get_tuning_client(db)

    # Build a compact transcript
    transcript = []
    for s in steps:
        if s.type == "tool_call":
            transcript.append({
                "role": "tool_call",
                "tool": s.content.get("tool"),
                "args": s.content.get("args", {}),
                "result": s.content.get("result"),
            })
        elif s.type in ("llm_response", "agent_message"):
            transcript.append({"role": "agent_reasoning", "content": s.content})

    payload = {
        "proposed_prompt": proposed_prompt,
        "original_input": run.input,
        "transcript": transcript[:40],  # cap for token budget
        "original_output": run.output,
    }

    messages = [
        LLMMessage(role="system", content=DRY_RUN_SYSTEM_PROMPT),
        LLMMessage(role="user", content=json.dumps(payload)),
    ]

    response = await llm_client.complete(messages=messages, model=resolved_model, max_tokens=600)

    try:
        parsed = json.loads(response.content)
    except json.JSONDecodeError:
        logger.warning(f"Dry-run returned invalid JSON for run {run_id}")
        # Fail open — treat as "same decision"
        parsed = {
            "would_still_decide_same": True,
            "reasoning": "Unable to evaluate (model returned invalid JSON)",
            "alternative_action": None,
            "confidence": 0.0,
        }

    # Record cost against the original run
    async with session_factory() as db:
        db.add(AIUsage(
            agent_run_id=run_id,
            organization_id=run.org_id,
            provider="anthropic",
            model=response.model or resolved_model,
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
            cost=None,
            timestamp=datetime.now(timezone.utc),
            sequence=8000,  # dry-run marker
        ))
        await db.commit()

    conf = parsed.get("confidence")
    try:
        conf_f = max(0.0, min(1.0, float(conf))) if conf is not None else 0.0
    except (TypeError, ValueError):
        conf_f = 0.0

    return DryRunResult(
        would_still_decide_same=bool(parsed.get("would_still_decide_same", True)),
        reasoning=str(parsed.get("reasoning") or "")[:500],
        alternative_action=(str(parsed["alternative_action"])[:500] if parsed.get("alternative_action") else None),
        confidence=conf_f,
    )
```

- [ ] **Step 4: Add endpoint**

In `api/src/routers/agent_runs.py`:

```python
from src.services.execution.dry_run import evaluate_against_prompt


class DryRunRequest(BaseModel):
    proposed_prompt: str = Field(min_length=1, max_length=20000)


class DryRunResponse(BaseModel):
    would_still_decide_same: bool
    reasoning: str
    alternative_action: str | None
    confidence: float


@router.post("/{run_id}/dry-run", response_model=DryRunResponse)
async def dry_run(
    run_id: UUID,
    request: DryRunRequest,
    db: DbSession,
    user: CurrentActiveUser,
):
    run = (await db.execute(select(AgentRun).where(AgentRun.id == run_id))).scalar_one_or_none()
    if run is None or (not user.is_superuser and user.organization_id != run.org_id):
        raise HTTPException(404, "Run not found")
    from src.core.database import get_session_factory
    result = await evaluate_against_prompt(
        run_id=run_id,
        proposed_prompt=request.proposed_prompt,
        session_factory=get_session_factory(),
    )
    return DryRunResponse(
        would_still_decide_same=result.would_still_decide_same,
        reasoning=result.reasoning,
        alternative_action=result.alternative_action,
        confidence=result.confidence,
    )
```

- [ ] **Step 5: Run test, verify pass, commit**

```bash
./test.sh tests/unit/test_dry_run.py -v
cd client && npm run generate:types && cd ..
git add api/src/services/execution/dry_run.py \
        api/src/routers/agent_runs.py \
        api/tests/unit/test_dry_run.py \
        client/src/lib/v1.d.ts
git commit -m "feat(agent-runs): add dry-run evaluation endpoint"
```

---

### Task 17: Consolidated tuning session endpoints

**Files:**
- Create: `api/src/models/contracts/agent_tuning.py`
- Create: `api/src/routers/agent_tuning.py`
- Extend: `api/src/services/execution/tuning_service.py`
- Create: `api/tests/unit/test_consolidated_tuning.py`

Endpoints:
- `POST /api/agents/{id}/tuning-session` — analyze all flagged runs + their flag conversations; return a consolidated proposal
- `POST /api/agents/{id}/tuning-session/dry-run` — sandbox-run every flagged run with the proposed prompt; return before/after per run
- `POST /api/agents/{id}/tuning-session/apply` — update agent.system_prompt, write prompt-history row, set affected flagged runs' verdict back to null (so they get re-evaluated)

- [ ] **Step 1: Write the failing test**

(See the shape in `/tmp/agent-mockup/src/data.ts` — `tuneSeed` and `tuneDryRun`. Tests should cover: returns a proposal when 1+ flagged runs exist; applies updates `agent.system_prompt` and creates a history row; errors gracefully if no flagged runs.)

- [ ] **Step 2: Implement**
- [ ] **Step 3: Add router to app** (register in `api/src/main.py` — follow existing pattern for `agents_router`)
- [ ] **Step 4: Run test, verify pass**
- [ ] **Step 5: Regenerate types, commit**

```bash
git add api/src/models/contracts/agent_tuning.py \
        api/src/routers/agent_tuning.py \
        api/src/services/execution/tuning_service.py \
        api/src/main.py \
        api/tests/unit/test_consolidated_tuning.py \
        client/src/lib/v1.d.ts
git commit -m "feat(agents): add consolidated tuning session endpoints"
```

---

### Task 18: Regenerate summary endpoint

**Files:**
- Modify: `api/src/routers/agent_runs.py`
- Create: `api/tests/unit/test_regenerate_summary.py`

**Endpoint:** `POST /api/agent-runs/{run_id}/regenerate-summary`

**Behavior:**
- Accepts only from platform admins (expensive operation; avoid abuse)
- Resets `summary_status` to `pending`, clears `summary_error`
- Enqueues a new summarization message to the worker
- Returns `{status: "enqueued", run_id}`

Also used implicitly: if `summary_status == "failed"`, the UI shows a "Regenerate" button on the run detail that hits this endpoint.

- [ ] **Step 1: Write the failing test**

```python
import pytest


@pytest.mark.asyncio
async def test_regenerate_requires_admin(client_as_regular_user, seed_completed_run):
    res = await client_as_regular_user.post(
        f"/api/agent-runs/{seed_completed_run.id}/regenerate-summary"
    )
    assert res.status_code == 403


@pytest.mark.asyncio
async def test_regenerate_resets_status_and_enqueues(client_as_admin, seed_failed_summary_run, db_session):
    from unittest.mock import patch
    with patch("src.services.execution.run_summarizer.enqueue_summarize") as mock_enqueue:
        res = await client_as_admin.post(
            f"/api/agent-runs/{seed_failed_summary_run.id}/regenerate-summary"
        )
    assert res.status_code == 200
    assert res.json()["status"] == "enqueued"
    mock_enqueue.assert_called_once()

    from sqlalchemy import select
    from src.models.orm.agent_runs import AgentRun
    run = (await db_session.execute(select(AgentRun).where(AgentRun.id == seed_failed_summary_run.id))).scalar_one()
    assert run.summary_status == "pending"
    assert run.summary_error is None
```

- [ ] **Step 2: Run test, verify fail**

- [ ] **Step 3: Implement endpoint**

In `api/src/routers/agent_runs.py`:

```python
from src.services.execution.run_summarizer import enqueue_summarize


@router.post("/{run_id}/regenerate-summary")
async def regenerate_summary(
    run_id: UUID,
    db: DbSession,
    user: CurrentActiveUser,
) -> dict:
    """Admin-only: reset a run's summary state and re-enqueue summarization."""
    is_admin = user.is_superuser or any(
        role in ["Platform Admin", "Platform Owner"] for role in user.roles
    )
    if not is_admin:
        raise HTTPException(403, "Only platform administrators can regenerate summaries")

    run = (await db.execute(select(AgentRun).where(AgentRun.id == run_id))).scalar_one_or_none()
    if run is None:
        raise HTTPException(404, "Run not found")
    if run.status != "completed":
        raise HTTPException(409, "Summaries only apply to completed runs")

    run.summary_status = "pending"
    run.summary_error = None
    await db.commit()

    await enqueue_summarize(run_id)

    return {"status": "enqueued", "run_id": str(run_id)}
```

- [ ] **Step 4: Run test, verify pass, commit**

```bash
./test.sh tests/unit/test_regenerate_summary.py -v
cd client && npm run generate:types && cd ..
git add api/src/routers/agent_runs.py \
        api/tests/unit/test_regenerate_summary.py \
        client/src/lib/v1.d.ts
git commit -m "feat(agent-runs): add admin regenerate-summary endpoint"
```

---

### Task 19: Budget field visibility gating

**Files:**
- Modify: `api/src/routers/agents.py` (enforce admin-only budget writes)
- Create: `api/tests/unit/test_budget_visibility_permissions.py`

Non-admins who attempt to set `max_iterations`, `max_token_budget`, or `llm_max_tokens` in `AgentUpdate` get `403` (or their write is silently dropped — test both options and decide based on existing patterns in the codebase).

- [ ] **Step 1: Write the failing test**

```python
@pytest.mark.asyncio
async def test_non_admin_cannot_set_max_iterations(client_as_regular_user, seed_private_agent_owned_by_user):
    res = await client_as_regular_user.put(
        f"/api/agents/{seed_private_agent_owned_by_user.id}",
        json={"max_iterations": 100},
    )
    assert res.status_code == 403
    assert "budget" in res.json()["detail"].lower()


@pytest.mark.asyncio
async def test_admin_can_set_max_iterations(client_as_admin, seed_any_agent):
    res = await client_as_admin.put(
        f"/api/agents/{seed_any_agent.id}",
        json={"max_iterations": 100},
    )
    assert res.status_code == 200
```

- [ ] **Step 2: Implement in `update_agent` in `agents.py`**

Near the "if not is_admin:" block, add:

```python
    if any([
        agent_data.max_iterations is not None,
        agent_data.max_token_budget is not None,
        agent_data.llm_max_tokens is not None,
    ]):
        raise HTTPException(403, "Budget fields (max_iterations, max_token_budget, llm_max_tokens) can only be set by platform administrators")
```

- [ ] **Step 3: Run test, verify pass, commit**

```bash
git add api/src/routers/agents.py api/tests/unit/test_budget_visibility_permissions.py
git commit -m "feat(agents): gate budget fields behind platform admin"
```

---

### Task 20: Backend E2E pass

**Files:**
- Create: `api/tests/e2e/test_agent_management_m1.py`

Write one happy-path test exercising: create agent → enqueue run → summarizer populates fields → set verdict → append flag conversation message → dry-run → consolidated tuning → apply tuning → verify prompt changed.

- [ ] **Step 1: Write and run the test. Iterate until green.**

- [ ] **Step 2: Commit**

```bash
./test.sh e2e tests/e2e/test_agent_management_m1.py -v
git add api/tests/e2e/test_agent_management_m1.py
git commit -m "test(e2e): full agent management lifecycle"
```

---

## Phase 3 — Frontend primitives

### Task 21: `ChatComposer` component

**Files:**
- Create: `client/src/components/ui/chat-composer.tsx`
- Create: `client/src/components/ui/chat-composer.test.tsx`

See mockup `/tmp/agent-mockup/src/components/FlagConversation.tsx` (composer section) and `/tmp/agent-mockup/src/styles.css` (`.chat-composer`, `.chat-composer-send`).

- [ ] **Step 1: Write the failing test**

```typescript
import { describe, it, expect, vi } from "vitest";
import { render, fireEvent } from "@testing-library/react";
import { ChatComposer } from "./chat-composer";

describe("ChatComposer", () => {
  it("calls onSend on Enter, not on Shift+Enter", () => {
    const onSend = vi.fn();
    const { getByPlaceholderText } = render(
      <ChatComposer placeholder="say something" onSend={onSend} />
    );
    const ta = getByPlaceholderText("say something");
    fireEvent.change(ta, { target: { value: "hi" } });
    fireEvent.keyDown(ta, { key: "Enter", shiftKey: true });
    expect(onSend).not.toHaveBeenCalled();
    fireEvent.keyDown(ta, { key: "Enter" });
    expect(onSend).toHaveBeenCalledWith("hi");
  });

  it("disables send when empty or while pending", () => {
    const { getByRole } = render(<ChatComposer onSend={() => {}} pending />);
    expect(getByRole("button")).toBeDisabled();
  });
});
```

- [ ] **Step 2: Run test, verify fail**

- [ ] **Step 3: Implement**

```tsx
// client/src/components/ui/chat-composer.tsx
import { Send } from "lucide-react";
import { useState } from "react";
import { cn } from "@/lib/utils";

export interface ChatComposerProps {
  placeholder?: string;
  onSend: (text: string) => void;
  pending?: boolean;
  className?: string;
  autoFocus?: boolean;
}

export function ChatComposer({
  placeholder = "Type a message...",
  onSend,
  pending = false,
  className,
  autoFocus,
}: ChatComposerProps) {
  const [value, setValue] = useState("");

  function submit() {
    if (!value.trim() || pending) return;
    onSend(value.trim());
    setValue("");
  }

  return (
    <div className={cn(
      "flex items-end gap-2 rounded-[20px] border bg-background px-4 py-2.5 transition-all",
      "focus-within:border-primary focus-within:ring-2 focus-within:ring-primary/20",
      className,
    )}>
      <textarea
        autoFocus={autoFocus}
        placeholder={placeholder}
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            submit();
          }
        }}
        className="flex-1 resize-none border-none bg-transparent text-sm outline-none placeholder:text-muted-foreground min-h-[22px] max-h-[180px] py-0.5"
        rows={1}
      />
      <button
        onClick={submit}
        disabled={!value.trim() || pending}
        aria-label="Send"
        className={cn(
          "w-[30px] h-[30px] rounded-full grid place-items-center transition-colors shrink-0",
          "bg-primary text-primary-foreground hover:bg-primary/90",
          "disabled:bg-muted disabled:text-muted-foreground disabled:cursor-not-allowed",
        )}
      >
        <Send size={13} />
      </button>
    </div>
  );
}
```

- [ ] **Step 4: Run test, verify pass, commit**

```bash
cd client && ./test.sh client unit src/components/ui/chat-composer.test.tsx
git add client/src/components/ui/chat-composer.tsx client/src/components/ui/chat-composer.test.tsx
git commit -m "feat(ui): add shared ChatComposer with rounded pill + embedded send"
```

---

### Task 22: `VerdictToggle` component

**Files:**
- Create: `client/src/components/ui/verdict-toggle.tsx`
- Create: `client/src/components/ui/verdict-toggle.test.tsx`

Animated 👍/👎 as seen in the mockup. Emits `onChange(verdict)` with `"up" | "down" | null`. Pop animation on activation.

- [ ] **Steps 1–4:** Test → implement → verify → commit.

---

### Task 23: Run review primitives (`RunReviewPanel`, `RunCard`)

**Files:**
- Create: `client/src/components/agents/RunReviewPanel.tsx`
- Create: `client/src/components/agents/RunCard.tsx`
- Create: corresponding `.test.tsx`

Port directly from `/tmp/agent-mockup/src/components/RunReviewPanel.tsx` and the `RunCard` function in `AgentDetailPage.tsx`. Replace raw CSS with Tailwind + existing shadcn primitives.

- [ ] Steps 1–4.

---

### Task 24: `Sheet` variant — RunReviewSheet

**Files:**
- Create: `client/src/components/agents/RunReviewSheet.tsx`
- Test: `.test.tsx`

Wraps shadcn's `Sheet` (`client/src/components/ui/sheet.tsx`) with sticky header, tabs (Review / Tune), body, and sticky footer. Consumes `RunReviewPanel` in the body.

- [ ] Steps 1–4.

---

### Task 25: `FlagConversation` component

**Files:**
- Create: `client/src/components/agents/FlagConversation.tsx`
- Test: `.test.tsx`

Port from mockup. Uses `ChatComposer` for input. Fetches via `GET /api/agent-runs/{id}/flag-conversation`, posts via `POST .../message`.

- [ ] Steps 1–4.

---

### Task 26: `QueueBanner`, `NeedsReviewCard`, stat cards

**Files:**
- Create: `client/src/components/agents/QueueBanner.tsx`
- Create: `client/src/components/agents/NeedsReviewCard.tsx`
- Create: `client/src/components/agents/FleetStats.tsx`
- Tests for each.

- [ ] Steps 1–4.

---

### Task 27: Agent service wrappers

**Files:**
- Modify: `client/src/services/agents.ts`
- Modify: `client/src/services/agentRuns.ts`
- Create: `client/src/services/agentTuning.ts`

Add typed wrappers for:
- `useAgentStats(agentId)`, `useFleetStats()`
- `useSetVerdict()`, `useClearVerdict()` mutations
- `useFlagConversation(runId)` + `useSendFlagMessage()` + `useDryRunAgent()`
- `useTuningSession(agentId)` + apply/dry-run mutations

Follow the existing `useAgentRuns` pattern in `client/src/services/agentRuns.ts`.

- [ ] **Step 1: Tests (component-level tests in subsequent tasks will exercise these; add direct tests only for non-trivial client-side logic).**
- [ ] **Step 2: Implement**
- [ ] **Step 3: Commit**

---

## Phase 4 — Frontend pages

### Task 28: `FleetPage`

**Files:**
- Create: `client/src/pages/agents/FleetPage.tsx`
- Create: `.test.tsx`

Port from `/tmp/agent-mockup/src/pages/FleetPage.tsx`. Uses `useFleetStats()`, `useAgents()` with stats, `AgentCard`, `FleetStats`.

- [ ] Steps 1–4.

---

### Task 29: `AgentDetailPage` with tabs + creation flow

**Files:**
- Create: `client/src/pages/agents/AgentDetailPage.tsx`
- Create: sub-components as needed (`AgentOverviewTab`, `AgentRunsTab`, `AgentSettingsTab`)
- Create: `.test.tsx`

Port from `/tmp/agent-mockup/src/pages/AgentDetailPage.tsx`. Runs tab embeds the card list + slide-over sheet.

**Creation path — `/agents/new`:**

`AgentDetailPage` handles both edit and create based on URL:
- `/agents/:id` → edit mode (all three tabs active, Overview + Runs tabs load data)
- `/agents/new` → create mode (Overview + Runs tabs disabled with tooltip "Available after first run"; Settings tab is the only active one; "Save" creates the agent, then `navigate(/agents/:id)`)

Tests to write for this task:
- Renders with `:id` in URL → all tabs active
- Renders with `new` in URL → Overview + Runs are disabled
- Saves in create mode → POSTs to `/api/agents` → navigates to `/agents/:newId`
- Saves in edit mode → PUTs to `/api/agents/:id` → stays on page

- [ ] Steps 1–4 (test → implement → verify → commit).

---

### Task 30: `AgentRunDetailPage`

**Files:**
- Create: `client/src/pages/agents/AgentRunDetailPage.tsx`
- `.test.tsx`

Uses `RunReviewPanel` for the main column; timeline + raw steps in advanced section. Sidebar with metadata + AI usage. Port from `/tmp/agent-mockup/src/pages/RunDetailPage.tsx`.

- [ ] Steps 1–4.

---

### Task 31: `AgentReviewPage` (flipbook)

**Files:**
- Create: `client/src/pages/agents/AgentReviewPage.tsx`
- `.test.tsx`

Port from `/tmp/agent-mockup/src/pages/ReviewFlipbookPage.tsx`. Keyboard nav, progress dots, `RunReviewPanel`.

- [ ] Steps 1–4.

---

### Task 32: `AgentTunePage`

**Files:**
- Create: `client/src/pages/agents/AgentTunePage.tsx`
- `.test.tsx`

Port from `/tmp/agent-mockup/src/pages/TuneChatPage.tsx`. Connects to `POST /api/agents/{id}/tuning-session`. Shows flagged runs list in sidebar.

- [ ] Steps 1–4.

---

### Task 33: Routes + navigation

**Files:**
- Modify: `client/src/App.tsx`

Add routes:
- `/agents` → `FleetPage` (replacing existing `<Agents />`)
- `/agents/new` → `AgentDetailPage` in create mode (Overview + Runs tabs disabled)
- `/agents/:id` → `AgentDetailPage` in edit mode
- `/agents/:id/review` → `AgentReviewPage`
- `/agents/:id/tune` → `AgentTunePage`
- `/agents/:agentId/runs/:runId` → `AgentRunDetailPage`

Remove old routes: `/agent-runs/:runId`, update `/history` not to redirect runs.

Delete old page files:
- `client/src/pages/Agents.tsx`
- `client/src/pages/AgentRunDetail.tsx`
- `client/src/components/agents/AgentDialog.tsx` + test
- `client/src/components/agents/AgentRunsTable.tsx`

- [ ] **Step 1: Wire routes, delete old files**

- [ ] **Step 2: Run type-check and lint, fix any reference errors**

```bash
cd client && npm run tsc && npm run lint
```

- [ ] **Step 3: Commit**

```bash
git add client/src/App.tsx
git rm client/src/pages/Agents.tsx client/src/pages/AgentRunDetail.tsx \
       client/src/components/agents/AgentDialog.tsx \
       client/src/components/agents/AgentDialog.test.tsx \
       client/src/components/agents/AgentRunsTable.tsx
git commit -m "feat(agents): wire new agent routes, remove legacy pages"
```

---

### Tasks 34–36: Polish

- **Task 34:** Accessibility — keyboard nav on cards, ARIA labels on sheet, focus management on modal open.
- **Task 35:** Loading/empty/error states — ensure every fetch site renders skeleton, empty, and error. Include the "summary_status=failed → show Regenerate button" UI.
- **Task 36:** Mobile responsive breakpoints — at minimum tablet (768px+) works; sheet becomes full-width below that.

Each: test → implement → commit.

---

## Phase 5 — E2E and polish

### Task 37: Playwright: fleet page happy path

**File:** `client/e2e/agents-fleet.admin.spec.ts`

```typescript
import { test, expect } from "@playwright/test";
// adjust imports to match existing helpers (auth, etc.)

test("fleet page shows stats + agent cards", async ({ page }) => {
  // authenticate as platform admin — follow existing e2e spec pattern
  await page.goto("/agents");
  await expect(page.getByRole("heading", { name: /agents/i })).toBeVisible();
  await expect(page.getByText(/runs \(7d\)/i)).toBeVisible();
  await expect(page.getByText(/success rate/i)).toBeVisible();
  await page.screenshot({ path: "screenshots/fleet-page.png", fullPage: true });
});
```

- [ ] Write, run, fix, commit.

---

### Task 38: Playwright: agent detail + runs card list + inline verdict

`client/e2e/agents-detail-runs.admin.spec.ts` — clicks into agent, Runs tab, sees card list, flags a run inline, sees toast + queue banner appear.

### Task 39: Playwright: review sheet + per-flag chat

`client/e2e/agents-review-verdict.admin.spec.ts` — opens sheet on a run, flips verdict to 👎, Tune tab appears, sends message, sees assistant reply.

### Task 40: Playwright: consolidated tuning + dry-run + apply

`client/e2e/agents-tuning.admin.spec.ts` — full tuning flow.

### Task 41: Playwright: non-admin owner cannot see budget fields

`client/e2e/agents-owner-budget-hidden.user.spec.ts`

### Task 42: Visual regression sweep

Capture screenshots at each step and review:
- `./test.sh client e2e --screenshots`
- Compare against `/tmp/agent-mockup` rendering for critical screens (fleet, detail-overview, detail-runs, sheet, review, tune)
- Address visual drift

### Task 43: Final lint + type-check + test sweep

Run in sequence:
```bash
cd api && pyright && ruff check .
cd ../client && npm run tsc && npm run lint
cd ..
./test.sh stack up
./test.sh all
./test.sh client unit
./test.sh client e2e
```

All must pass with zero errors. Fix any failures before proceeding.

### Task 44: Pause semantics smoke + UAT handoff

- Manual: pause an agent in the UI. Confirm webhook returns 503. Confirm chat UI disables. Confirm an in-flight run completes normally.
- Generate a summary note on the branch — what was built, what's deferred for Plan 2 (judge agent, confidence-based auto-flagging, streaming tuning responses, agent-scoped chat UI).
- Push branch.
- Hand back to user for UAT.

---

## Self-review checklist

- [ ] Every new Pydantic model lives in `api/src/models/contracts/`
- [ ] Every new ORM model lives in `api/src/models/orm/` and is registered in `__init__.py`
- [ ] Every `datetime.now(...)` call passes `timezone.utc`
- [ ] Every new endpoint has a response_model annotation
- [ ] Every new response_model is covered by at least one unit test
- [ ] `client/src/lib/v1.d.ts` is regenerated in any commit touching Pydantic response models
- [ ] No commits use `--no-verify`
- [ ] Each Playwright spec captures at least one screenshot for review

---

## Phase 6 — Plan 2 stubs (DO NOT IMPLEMENT IN THIS PLAN)

**⚠️ STOP HERE.** The tasks below are deliberately left unchecked and without implementation bodies. They represent work that is part of the overall Agent Management vision but **explicitly deferred to Plan 2**.

**Reading rules for any LLM executing this plan:**

1. These tasks are **not done** and are **not part of Plan 1**.
2. Do **NOT** implement them here. Do **NOT** mark the plan "complete" while these checkboxes exist.
3. When Plan 1 (T1–T43) finishes, hand back to the user for UAT. Plan 2 is a separate planning and execution cycle.
4. Their presence is a persistent visual reminder that the product vision is larger than what Plan 1 delivers.

### Task 45: Judge agent [DEFERRED — Plan 2]

- [ ] Auto-flag suspect runs based on confidence + output pattern + known-bad heuristics. Uses the accumulated verdict history as training signal.

### Task 46: Streaming tuning responses [DEFERRED — Plan 2]

- [ ] Replace synchronous LLM calls in flag-conversation with SSE streaming so the tuning assistant's reply appears word-by-word.

### Task 47: Agent-scoped chat UI [DEFERRED — Plan 2]

- [ ] Build agent-initiated chat view (a chat rendering of runs grouped by `conversation_id`). Replaces the standalone chat product with "chat with *this* agent" framing from the mockup.

### Task 48: Prompt versioning UI [DEFERRED — Plan 2]

- [ ] Viewer + diff + revert UI on top of the `agent_prompt_history` table already created in T5. Side-panel, compare any two versions, revert with confirmation.

### Task 49: Cross-agent flagged runs view [DEFERRED — Plan 2]

- [ ] Top-level route `/flagged` that lists flagged runs across all agents, groupable by agent, sortable by confidence/age. Useful for reviewing backlog across the fleet.

### Task 50: Confidence-based review queue [DEFERRED — Plan 2]

- [ ] Show a queue of low-confidence runs (configurable threshold, default 0.5) awaiting human review. Separate from the "flagged runs" queue — this is "might be wrong" vs "known wrong."

### Task 51: Metadata schema discovery [DEFERRED — Plan 2]

- [ ] Per-agent view of which metadata keys the agent has emitted historically, with cardinality and sample values. Powers auto-complete on the runs search bar.

### Task 52: Chat-as-runs consolidation [DEFERRED — Plan 2]

- [ ] Every chat turn is an `AgentRun`. Multi-turn chats group by `conversation_id`. The dedicated chat UI becomes a rendering of runs-in-a-conversation rather than a separate data model.

### Task 53: Cost caps and rate limits on tuning [DEFERRED — Plan 2]

- [ ] Tuning conversations can run away if the user keeps chatting. Add per-agent weekly tuning cost cap (configurable by admin) and a soft rate limit on `POST /flag-conversation/message` to prevent runaway spend.

---

**End of Phase 6.** If an LLM executing this plan reaches this line without having left these tasks unchecked, it has incorrectly implemented scope. Return to the user.

---

## Phase 7 — UX rebuild (landed)

> Phase 1–6 executed mechanically and produced a functionally-complete but visually-weak implementation. The user rejected the initial UX on 2026-04-22 as "an incredibly poor copy" of the approved mockup. Phase 7 is the page-by-page visual rebuild, using a capture-and-compare loop against `/tmp/agent-mockup/` rendered at `localhost:5555`.

### What landed

- [x] **T61 — Shared primitives** (`client/src/components/agents/`): `Sparkline`, `StatCard` (with `alert` variant), `PillTabs` (with count badges). Commit `3665cb58`.
- [x] **T62 — FleetPage rebuild**: stat row with deltas, Grid/Table toggle, agent cards with mini-stat trio + sparkline + footer. `useAgents(undefined, { includeInactive: true })` so paused agents stay visible. Commit `3665cb58`.
- [x] **T63 — AgentDetailPage rebuild**: breadcrumb, Bot + name + Active pill, PillTabs with run-count badge, Overview tab with stats + sparkline + recent activity + Needs-attention + Configuration/Budgets sidebars. Commit `3665cb58`.
- [x] **T64 — AgentRunDetailPage rebuild**: breadcrumb, Completed pill + meta line (time · duration · iter · tokens), What was asked / What the agent answered sections, Captured data chips, Verdict bar, Run metadata KV sidebar, Summary regenerate card, Agent sidebar card, raw step timeline disclosure, Tuning conversation block when present.
- [x] **T65 — AgentReviewPage (flipbook) rebuild**: `Review runs` heading + counter, keyboard hints, `Tune with N flagged` CTA, main card with asked/did/captured data + Verdict bar, Prev/Next + pagination dots.
- [x] **T66 — AgentTunePage rebuild**: two-column layout (chat + sidebar with Flagged runs list + Current prompt). Proposal and dry-run render **inline inside the assistant's ChatBubble** (Phase 7b T71 landed this).
- [x] **T67 — Settings tab parity** — restored Organization selector, Access level with Assigned roles, Tools (system + workflow grouped with orphan/deactivated states), Delegated agents, Knowledge sources (auto-enables search_knowledge), LLM model picker, admin-only Max iterations / Max token budget / Max tokens/response. Commit `a6c437eb`.

### The loop (for every T64–T67)

**Do not dispatch subagents for UX work.** The Phase 3–4 subagents produced the "passable but generic" result that triggered this rebuild. Work in the main loop, one page at a time:

1. **Read the mockup source** at `/tmp/agent-mockup/src/pages/<Page>.tsx` in full. Note structure, what's in each column, what CSS classes are used.
2. **Peek the mockup's styles** at `/tmp/agent-mockup/src/styles.css` for any class referenced. Don't port the CSS — port the visual intent using Tailwind + shared primitives.
3. **Rewrite the page** in `client/src/pages/agents/<Page>.tsx`. Prefer new shared primitives (`StatCard`, `PillTabs`, `Sparkline`) over shadcn where the mockup's density/hierarchy needs it. Don't be afraid to drop shadcn and write custom markup.
4. **`npm run tsc && npm run lint`** — fix errors.
5. **Capture** using the loop below. Seed data via the capture script, don't test against empty state alone.
6. **Read both screenshots** (mockup reference + ours) and compare visually. Write down what's off. Iterate steps 3–6 until the visual intent lands.
7. **Commit** with a focused message per page.

### Capture loop

Mockup is already running on `localhost:5555` (Vite dev server on host).

Our pages require running Playwright inside the worktree's Docker network because the test-stack client container (`bifrost-test-86cbedfe-client-1`) has no host port mapping. Script lives at `/tmp/ux-compare/grab-ours-v3.mjs` (seeds 5 agents, one paused, captures fleet + new-agent + agent detail / runs tab / review / tune). Run with:

```bash
docker run --rm \
  --network bifrost-test-86cbedfe_default \
  -v /tmp/ux-compare/grab-ours-v3.mjs:/work/grab.mjs \
  -v /tmp/ux-out:/tmp/ux-out \
  -w /work \
  -e CLIENT_URL=http://client -e API_URL=http://api:8000 \
  mcr.microsoft.com/playwright:v1.59.1-jammy \
  sh -c 'npm init -y >/dev/null && npm i --silent playwright jsonwebtoken 2>&1 | tail -1 && node grab.mjs'
```

Mockup reference captures land at `/tmp/ux-out/mockup-*.png` (run `/tmp/ux-compare/grab-mockup.mjs` via the Playwright image with `--network host` if they're missing).

Our captures land at `/tmp/ux-out/ours-*.png`. Read each pair with the `Read` tool (it displays PNGs) and compare.

**User can also view** at `~/Sync/Screenshots/agent-ux-compare/` — both `mockup-*.png` and `ours-*.png` are copied there after each capture cycle. Refresh that folder with `cp /tmp/ux-out/*.png ~/Sync/Screenshots/agent-ux-compare/` after each iteration.

### Critical gotchas for Phase 7

- **Token storage key** for the capture script is `bifrost_access_token` in `localStorage` (not `access_token`). See `client/src/lib/auth-token.ts`.
- **Worktree client container** binds Vite on port `80`, not `3000`. The script uses `CLIENT_URL=http://client`.
- **Soft deletes**: `DELETE /api/agents/{id}` only flips `is_active=false`. The server never hard-deletes. Use `?active_only=false` query to see them. Don't mass-DELETE against the DB directly — sandbox correctly blocks that.
- **Fleet view** requires `includeInactive: true` on `useAgents()` or paused agents disappear.
- **`AgentUpdate` requires `clear_roles`** — when calling `useUpdateAgent.mutate` for a pause toggle, include `clear_roles: false` in the body or you'll hit a type error at compile time.
- **`run.output` is `dict | string | null`** on the response — cast via an `asText(v)` helper before rendering as `ReactNode`.
- **JUnit XML** for this worktree is `/tmp/bifrost-bifrost-test-86cbedfe/test-results.xml`, NOT `/tmp/bifrost/test-results.xml`.
- **Playwright purity lint** forbids `Math.random()` at render time — use `useId()` for stable SVG gradient ids.

### Definition of done for Phase 7

Pages T64–T67 each:

1. Visual parity with mockup reference — a diff reader would say "same design, different content" not "similar layout"
2. `tsc` + `lint` clean
3. Sibling `*.test.tsx` updated for any renamed components/changed selectors
4. `./test.sh client unit src/components/agents src/pages/agents` green
5. Committed with a focused message

After T67, recapture all 5 ours-*.png and stage side-by-side with mockup-*.png for user sign-off before re-running the Playwright e2e specs (those assertions may need selector updates after the rebuild).

---

### Phase 7b — Design system + realistic fixtures (landed)

User feedback after the first Phase 7 captures made it obvious that:

- Empty-state screenshots can't be judged. Fleet names truncate, agent cards have no sparklines, activity cards say "No activity yet," tune page has nothing to propose against. Without realistic data the visuals can't carry their own weight.
- The "Propose change" card in the tune page was misframed — it should be inline on the assistant's turn (a `ProposalTurn` block embedded in the chat bubble), not a floating card.
- shadcn wasn't the blocker. The mockup is already a custom component system (`.stat-card`, `.tabs`, `.activity-item`, `.kv`, etc.). We were losing to a half-built design system, not the library.

#### What landed

- [x] **T68 — Design tokens** (`client/src/components/agents/design-tokens.ts`). Composable Tailwind class-list constants: `TYPE_PAGE_TITLE`, `TYPE_CARD_TITLE`, `TYPE_LABEL_UPPERCASE`, `TYPE_STAT_VALUE`, `TYPE_MUTED`, `GAP_CARD`, `CARD_SURFACE`, `CARD_HEADER`, `CARD_BODY`, `PILL_ACTIVE`, `CHIP_OUTLINE`, `successRateTone(rate)`. Every primitive and page composition pulls from here; Fleet / AgentDetail / AgentOverviewTab / StatCard / PillTabs / Sparkline all swept. Commit `e14ec4d5`.

- [x] **T69 — Missing primitives** (`client/src/components/agents/`):
  - `MetaLine.tsx` — muted inline strip `"1h ago · 3.4s · 2 iter · 1,852 tok"`; filters nulls.
  - `KVList.tsx` — 2-column definition list with optional mono values.
  - `Chip.tsx` — labeled metadata pill (`ticket_id 4822`) with tone variants (muted/primary/emerald/rose/yellow).
  - `ChatBubble.tsx` + `ChatBubbleSlot.tsx` — message bubble with `kind=user|assistant|system`; assistant variant accepts `slots` (nested ProposalTurn / DryRunTurn blocks rendered *inside* the bubble). 15 new unit tests, all green.
  Commit `e14ec4d5`.

- [x] **T70 — Realistic seed fixtures.** `docs/ux/seed-realistic.mjs` + `docs/ux/grab-ours.mjs`. Hard-clears `agents` + related tables via SQL, POSTs 5 seed agents, SQL-inserts 45+ runs across the last 7 days with mixed status, ~2–3 flagged per agent, populated asked/did/confidence/run_metadata. One `AgentRunFlagConversation` with user → assistant → proposal (with add/keep/remove diff) → dryrun turns. One `AgentPromptHistory` row. Idempotent. Commit `333456a0`.

- [x] **T71 — Inline proposal/dry-run in tune chat.** `ProposalBubble` + `DryRunBubble` render as assistant ChatBubbles with their content in a `ChatBubbleSlot`. Actions (Dry-run, Try this) sit inline inside the slot. No more floating sibling card. Commit `e68f4122`.

#### Additional UX polish (post-Phase-7b, pre-UAT)

Feedback surfaced during token/primitive captures — all landed on `worktree-agent-management-m1`:

- [x] **Settings tab visual rewrite** — dropped the card-per-section layout and the orphan right-column that held just an activation toggle. Single-card form surface with `.form-section` treatment (uppercase section labels + thin dividers), activation row inline in Identity. Commit `5c2c505a`.
- [x] **Organization selector restored** — regressed when AgentDialog was deleted at `d1eaef49`; platform-admin-only `OrganizationSelect` with `showGlobal`, defaults: admin → null (Global), org user → their org. Commit `0cf367cf`.
- [x] **Full AgentDialog field parity** — tools (system + workflow, orphan/deactivated states), delegated agents, knowledge sources (auto-enables search_knowledge), LLM model combobox, admin-only budgets. Commit `a6c437eb`.

### Open follow-ups before UAT

Small, ordered. Listed roughly by user-visible impact:

- [ ] **Rename tune actions** — "Try this" → "Accept" (saves the new prompt live); "Dry-run" stays (simulate without saving). User feedback `2026-04-22`. Touch: `client/src/pages/agents/AgentTunePage.tsx::ProposalBubble` + its test.
- [ ] **Collapse the Model section by default in create mode** — old AgentDialog had this behind a ChevronsUpDown disclosure so model + budgets don't dominate the form on first-touch. Currently everything is expanded. Low priority; user said the design is "in a much better place" without it.
- [ ] **Empty-state reconcile for the AgentOverviewTab** — stats card still rendered even when the agent has zero runs. Acceptable but could fall back to a single "No runs yet — waiting for traffic" strip for tighter signal.

### Definition of done for UX rebuild

Pages each:

1. ✅ Visual parity with mockup reference — confirmed against `/tmp/agent-mockup/src/pages/*.tsx`.
2. ✅ `tsc` + `lint` clean on the full client tree.
3. ✅ Sibling `*.test.tsx` updated for renamed components.
4. ✅ `./test.sh client unit src/components/agents src/pages/agents` — 20 files / 156 tests green as of `a6c437eb`.
5. ✅ Committed with focused messages.

After the three follow-ups land, re-run the Playwright e2e specs — their selector assertions may need updates after the Phase 7 rewrites.

---

### Pre-UAT checklist — "what do I need before I swap `./debug.sh` over?"

Before moving development off the test stack and back to `./debug.sh`:

1. **Run all three open follow-ups above** (tune action rename + optional Model disclosure + empty-state polish). Only the rename is genuinely user-visible.
2. **Regenerate client types against the dev stack.** The test stack has `/api/openapi.json` cached per-worktree; `./debug.sh` runs the main repo's API which may differ. After starting `./debug.sh`:
   ```bash
   cd client && npm run generate:types
   ```
3. **Re-run client e2e specs** against `./debug.sh`. Many Phase 5 Playwright specs were written against the original (pre-rewrite) page markup. The ones most at risk of selector drift:
   - `client/e2e/agents-fleet.spec.ts`
   - `client/e2e/agent-detail.spec.ts`
   - `client/e2e/agent-review-flipbook.spec.ts`
   - `client/e2e/agent-tuning.spec.ts`
   - `client/e2e/agent-budgets.spec.ts`
   Run: `./test.sh client e2e e2e/agents-*.spec.ts` (inside the test stack) — or click through manually in the dev stack to decide which specs need updating.
4. **Seed realistic data into the dev stack** so the UX is judged against real content, not empty state. The seed script at `docs/ux/seed-realistic.mjs` targets the test-stack postgres; for `./debug.sh` either (a) adapt the script's `PG_HOST`/`PG_PASS` to the dev-stack container names, or (b) drive seeding through the CLI/MCP tools.
5. **Verify Organization scoping** as a non-platform-admin user. The form hides the org selector and should auto-apply the user's own org — click through both create and edit flows with a normal user to confirm.
6. **Run the backend test sweep** one last time on `main`-branch HEAD:
   ```bash
   ./test.sh stack up && ./test.sh all && ./test.sh client unit
   ```
7. **Decide on the test-stack worktree** — this branch has committed state ahead of `main` (roughly 15 commits, mostly visual rewrites + seed scripts). Merge or rebase back to `main` before `./debug.sh` starts generating migrations in a parallel direction.

Non-blocking for UAT but worth landing soon:

- **`ai_usage` seed** — the fleet cards show `$0.00` spend because the seed script doesn't insert `AIUsage` rows. Not broken, just visually underwhelming.
- **Real diff on ProposalBubble** — `ConsolidatedProposalResponse` only carries `proposed_prompt`, not a structured diff. The Before column currently renders `"(current prompt — see sidebar)"`. Plan 2 item.
- **Fleet N+1 on `useAgentStats`** — per-card stat fetch, flagged in code with `TODO(plan-2)`. Plan 2 item.

### Fixture + capture scripts live at

- `docs/ux/seed-realistic.mjs` — realistic seed against the test stack.
- `docs/ux/grab-ours.mjs` — captures all agent surfaces into `/tmp/ux-out/ours-*.png`.
- `docs/ux/README.md` — how to run both inside a Playwright container on the worktree's docker network.

Keep copying `/tmp/ux-out/*.png` to `~/Sync/Screenshots/agent-ux-compare/` after each capture so the user can review without swapping dev stacks.

---

## Phase 8 — Summary hygiene (overflow fix, "(summary pending)" UX, backfill + realtime)

### Context

Uncovered during UX pass 2026-04-23:

1. **Horizontal page scroll** on agent detail Overview. Root cause: `AgentOverviewTab.tsx:74` uses `grid lg:grid-cols-[1fr_320px]` — grid items default to `min-width: auto`, so overlong children in the main column expand the track and push the whole page sideways. The `truncate` on `ActivityRow` (line 338) can't rescue it because the grid track has already grown.
2. **Raw HTML/JSON dumped as "What was asked"** when `run.asked` / `run.did` are null. Fallbacks at `AgentOverviewTab.tsx:339` (`run.did ?? asText(run.output) ?? "—"`) and `RunReviewPanel.tsx:118,178` (`run.asked || inputText`) surface unsummarized raw input. For event-triggered runs the input is often an HTML email body. Confirmed: `asked/did` are populated by a post-run LLM summarizer (`api/src/services/execution/run_summarizer.py`), and any run that predates the summarizer or had `summary_status='failed'` still has them null.
3. **Regenerate button is isolated.** Only exists on `AgentRunDetailPage.tsx:373`, gated by `isPlatformAdmin || summaryFailed`. Not visible from the Review sheet or from the Overview / Runs rows where the "(summary pending)" placeholder will appear.
4. **No bulk backfill.** Post-migration, every old run has `summary_status='pending'` with no worker ever having picked them up, and there's no UI or endpoint to kick them off.
5. **Summarizer doesn't broadcast.** The websocket infra exists (`api/src/core/pubsub.py:276 publish_agent_run_update`, `agent-run:{id}` and `agent-runs` channels, client handlers at `client/src/services/websocket.ts:1655 onAgentRunUpdate`), and `agent_run.py` already publishes on status transitions — but `run_summarizer.py` never publishes when it flips `summary_status`. Also the existing `AgentRunUpdate` payload doesn't carry `summary_status` / `asked` / `did` / `confidence`, so even a naive broadcast wouldn't let the client react.

### Goals

- No horizontal page scroll regardless of payload shape.
- "(summary pending)" placeholder replaces raw-HTML fallback, with an admin regenerate affordance co-located.
- Admin-triggered **background backfill job** with progress, concurrency control, and cost-aware confirmation, reachable both platform-wide and per-agent.
- **Realtime updates** when any run's `summary_status` flips (so both the current page and the backfill progress UI update without polling).
- Cost handling: every regeneration writes an `AIUsage` row as today; `total_cost_7d` on the agent stats card reflects it automatically on the next refetch (no separate bookkeeping needed, but we need to make that cost visible at confirmation time so admins don't accidentally spend $$).

### Non-goals

- Rewriting RunReviewPanel's layout. Keep "What was asked / What it did / What the agent answered" sections; only change the empty-summary path.
- Adding a new dashboard/settings page. The platform-wide backfill entry point is a button in Platform Admin → Agents (or, if no such tab exists, a subtle entry in the Agents list header behind a `is_superuser` guard).
- Streaming token-by-token summaries. The broadcast is just the completed `summary_status` / `asked` / `did` payload; no incremental delta protocol.

---

### Task breakdown

#### T100 — Fix horizontal scroll on AgentOverviewTab (1-line CSS)

**File:** `client/src/components/agents/AgentOverviewTab.tsx:74`

```diff
- <div className={cn("grid lg:grid-cols-[1fr_320px]", GAP_CARD)}>
+ <div className={cn("grid lg:grid-cols-[minmax(0,1fr)_320px]", GAP_CARD)}>
```

`minmax(0, 1fr)` forces the track to be shrinkable past content width, letting `truncate` on descendant rows actually truncate. Mirrors the "min-h-0 flex pattern" feedback memory, applied to grid + `min-width`.

**Verification:** seed a run with a huge `run.output` payload (or inject via DB), visit `/agents/:id`, confirm no horizontal page scrollbar. Playwright check in T110.

#### T101 — "(Summary pending)" placeholder instead of raw-payload fallback

**Files:**
- `client/src/components/agents/AgentOverviewTab.tsx:339` — `ActivityRow` line-1 text.
- `client/src/components/agents/RunCard.tsx:127, 150` — both `asked` and `did` lines.
- `client/src/components/agents/RunReviewPanel.tsx:118, 178` — "What was asked" / "What the agent answered" bodies.

**Rule:** when the corresponding summary field (`asked` / `did`) is null or empty, render a muted placeholder based on `summary_status`:
- `"pending"` or `"generating"` → `"Summary pending…"`
- `"failed"` → `"Summary failed — regenerate"` (link/button, see T102)
- `"completed"` with null (shouldn't happen, but be defensive) → `"—"`

Never fall back to `asText(run.output)` or `renderPayload(run.input)` in the summary-text slots. In `RunReviewPanel`, the raw input/output remains viewable in a new collapsible **"Raw input" / "Raw output"** disclosure (`<details>` or shadcn `Collapsible`), rendered with `whitespace-pre-wrap break-words` and `max-h-[240px] overflow-auto`. This preserves debugability without dumping HTML inline.

**Contract impact:** `AgentRunResponse` already exposes `summary_status` via the ORM column; confirm it's in the response model. It currently isn't (see `api/src/models/contracts/agent_runs.py:24`) — add it.

```diff
# api/src/models/contracts/agent_runs.py (AgentRunResponse)
  confidence: float | None = None
  confidence_reason: str | None = None
+ summary_status: str = "pending"
+ summary_error: str | None = None
```

Regenerate types (`cd client && npm run generate:types`) and consume in the three components above.

**Tests:**
- Unit: `AgentOverviewTab.test.tsx`, `RunCard.test.tsx`, `RunReviewPanel.test.tsx` — snapshot each of the three `summary_status` branches.
- Backend unit: `test_agent_run_response_includes_new_fields.py` already exists; extend to assert `summary_status` / `summary_error` round-trip.

#### T102 — Regenerate button in RunReviewPanel + row-level "failed" shortcut

**File:** `client/src/components/agents/RunReviewPanel.tsx`

Add an inline regenerate control next to the section header when `run.summary_status !== "completed"`:
- If `summary_status === "failed"`: show the affordance to **all users** (read-only users can trigger a retry on their own review) — match existing DetailPage behavior. But keep the per-run cost implication in mind: the endpoint itself remains admin-gated at `api/src/routers/agent_runs.py:669`, so non-admins clicking it will get a 403. Surface that as a tooltip for non-admins: `"Only platform admins can regenerate summaries."` and disable the button.
- Reuse the existing `useRegenerateSummary()` hook from `client/src/services/agentRuns.ts:400`.
- Invalidate `["get", "/api/agent-runs/{run_id}", ...]` and the `"agent-runs"` list cache on success (already realtime via T105 but invalidation is belt-and-suspenders).

In `AgentOverviewTab.ActivityRow` and `RunCard`, when `summary_status === "failed"`, show a small `RefreshCw` icon button inline (admin-only — hidden otherwise), `e.stopPropagation()` so it doesn't trigger row navigation.

**Tests:** vitest — renders & calls mutation; disabled-with-tooltip for non-admin.

#### T103 — Bulk backfill endpoint

**New endpoint:** `POST /api/agent-runs/backfill-summaries`

**Request model** (in `api/src/models/contracts/agent_runs.py`):

```python
class BackfillSummariesRequest(BaseModel):
    agent_id: UUID | None = None  # None = platform-wide
    statuses: list[Literal["pending", "failed"]] = ["pending", "failed"]
    limit: int = Field(default=500, ge=1, le=5000)
    dry_run: bool = False  # if True, return count without enqueuing
```

**Response model:**

```python
class BackfillSummariesResponse(BaseModel):
    job_id: UUID           # the orchestration record (T104)
    queued: int            # number of runs enqueued (0 if dry_run)
    eligible: int          # total matched by the filter
    estimated_cost_usd: Decimal  # best-effort prediction, see below
```

**Behavior:**
- Admin-only (mirror `regenerate_summary` guard at `agent_runs.py:676`).
- Select `AgentRun` rows where `status='completed'` AND `summary_status IN :statuses` AND (optional) `agent_id=:agent_id`, ORDER BY `created_at DESC`, LIMIT :limit.
- `estimated_cost_usd`: average cost-per-summary on the last 100 completed summaries (`AIUsage` rows where `agent_run_id IN (runs WHERE summary_status='completed')` tagged with the summarizer model). Multiply by `eligible`. If no history exists, fall back to a flat $0.002 × eligible with a `"fallback"` flag in the response. Under-estimates are acceptable; the point is to prevent $$-surprise.
- Create a `SummaryBackfillJob` orchestration row (T104), then for each run publish a `SUMMARIZE_QUEUE` message with an added `{"backfill_job_id": "…"}` field.
- Return immediately — work runs async on the existing `summarize_worker`.

**Rate-limit / concurrency:** none at the endpoint. The RabbitMQ `agent-summarization` queue already has `prefetch_count=settings.max_concurrency` and `summarize_run` is idempotent on `summary_status='completed'`. No need to invent throttling.

**Tests:**
- E2E `test_backfill_summaries.py` (new): seed 20 runs (mix of `pending`/`failed`/`completed`), call endpoint, assert `queued==20`, assert messages land on the queue (`aio_pika` test double already used elsewhere — see `api/tests/e2e/api/test_regenerate_summary.py` for pattern).
- Unit: `dry_run=True` returns eligible count without enqueuing, non-admin is 403.

#### T104 — SummaryBackfillJob orchestration row + progress tracking

**New ORM model** `SummaryBackfillJob` (new file `api/src/models/orm/summary_backfill_job.py`):

```python
class SummaryBackfillJob(Base):
    __tablename__ = "summary_backfill_jobs"
    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    agent_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True, index=True)
    requested_by: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="running")  # running | complete | failed
    total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    succeeded: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    estimated_cost_usd: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False, default=Decimal("0"))
    actual_cost_usd: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False, default=Decimal("0"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
```

Alembic migration required.

**Summarizer hook:** in `run_summarizer.summarize_run`, when the incoming message carries a `backfill_job_id`, increment `succeeded` (or `failed`) on the job row atomically at the end of the handler. When `succeeded + failed == total`, set `status='complete'` and `completed_at`. Also accumulate `actual_cost_usd` from the `AIUsage` row this call wrote.

**Endpoints (new on `agent_runs.py`):**
- `GET /api/agent-runs/backfill-jobs/{job_id}` → returns current progress (admin-only).
- `GET /api/agent-runs/backfill-jobs?active=true` → list running jobs (admin-only). Used to short-circuit a second backfill if one is already running (UI: "A backfill is already running — %s of %s done").

**Tests:** unit test for the increment + completion-detection logic; E2E for GET endpoints.

#### T105 — Realtime: publish on summary state changes

**File:** `api/src/services/execution/run_summarizer.py`

At every transition (`'pending' → 'generating'`, `'generating' → 'completed'`, `'generating' → 'failed'`), after the `await db.commit()`:

```python
from src.core.pubsub import publish_agent_run_update
await publish_agent_run_update(run, agent_name_cached)
```

**But first extend `publish_agent_run_update`** (`api/src/core/pubsub.py:276`) to include the summary fields in its payload:

```python
message = {
    "type": "agent_run_update",
    ...
    "summary_status": run.summary_status,
    "asked": run.asked,
    "did": run.did,
    "confidence": float(run.confidence) if run.confidence is not None else None,
    "summary_error": run.summary_error,
    ...
}
```

And extend the TS type in `client/src/services/websocket.ts:198 AgentRunUpdate` to match.

**Backfill job progress channel:** new topic `summary-backfill:{job_id}` (admin-only; add to the whitelist in `api/src/routers/websocket.py` near line 274 with a `user.is_superuser` check). Publish on every increment. Also publish on `complete`/`failed` terminal transition with full stats.

**Client consumption:** new hook `useSummaryBackfillProgress(jobId)` that connects to the channel, returns `{ total, succeeded, failed, status, actual_cost_usd }`. Seeds initial value from `GET /backfill-jobs/{job_id}`; updates via WS.

Also wire the existing `AgentRunUpdate` handler (or add a new one) in the Overview/Runs tabs so that when a broadcast arrives with `run_id` matching a rendered row, the row invalidates / updates its `asked`/`did`/`summary_status` inline. Simplest path: on any `agent_run_update` event for this agent, call `queryClient.invalidateQueries({ queryKey: ["agent-runs"] })` — React Query re-fetches the small page and rows update. More targeted: a custom mutation on the query cache to patch the affected item only.

**Tests:**
- Unit: mock `publish_agent_run_update`, run `summarize_run`, assert it's called once with `summary_status='completed'` and the summary fields populated.
- E2E: vitest + mocked WS client asserts `useAgentRuns` invalidates on an `agent_run_update` with changed `summary_status`.

#### T106 — Backfill UI: cost-aware confirmation + live progress

**Two entry points:**

1. **Platform-wide** — at `client/src/pages/agents/FleetPage.tsx` (or wherever the platform-admin agents list lives), add a header menu "Backfill pending summaries" guarded by `user.is_superuser`.
2. **Per-agent** — in the `AgentDetailPage` header kebab (the new menu added next to Start Chat button), "Regenerate pending summaries for this agent" — admin-only.

**Flow:**
1. Click → calls `POST /backfill-summaries` with `dry_run=true` to fetch `{eligible, estimated_cost_usd}`.
2. Show confirmation dialog: "This will regenerate summaries for **%d runs** (%s pending, %s failed) using the summarization model. Estimated cost: **$X.XX**. Continue?"
3. On confirm, re-POST with `dry_run=false`. Returns `{ job_id, queued }`.
4. Open inline progress card (or toast-like sticky) subscribed to `summary-backfill:{job_id}` via `useSummaryBackfillProgress`. Shows `{succeeded + failed} / {total}` with a progress bar and running `actual_cost_usd`. Stays until job `status==='complete'`, then toast "Regenerated N summaries — $X.XX" and dismisses.
5. While a job is running (detected via `GET /backfill-jobs?active=true` on page mount), show the progress card re-attached to that existing job instead of offering a new backfill.

**Affected files:**
- New `client/src/components/agents/SummaryBackfillDialog.tsx` (confirmation + dry-run fetch).
- New `client/src/components/agents/SummaryBackfillProgress.tsx` (live progress card).
- New hooks in `client/src/services/agentRuns.ts`: `useBackfillSummaries`, `useSummaryBackfillJob(jobId)`, `useActiveSummaryBackfillJobs`, `useSummaryBackfillProgress(jobId)` (WS).
- Header menu changes in `FleetPage.tsx` and `AgentDetailPage.tsx`.

**Tests:**
- Vitest for each new component (dialog, progress).
- Playwright `agents-backfill.admin.spec.ts`: seed 5 pending runs, trigger backfill, wait for progress WS to reach 5/5, assert toast + rows updated on Overview tab.

#### T107 — Cost visibility note

Confirm `total_cost_7d` on `AgentStatsResponse` already includes summarizer costs (it sums `AIUsage.cost` where `agent_run_id IN run-set` — and the summarizer writes `AIUsage` rows per-run, tagged with the summarizer model). After a backfill the Spend (7d) card will reflect it on the next refetch.

No code change — just an assertion in `test_agent_stats.py`: "Summarizer-generated AIUsage rows are included in `total_cost_7d`." Add the fixture setup and a single assertion. If it's not currently included (the test is the source of truth), file a follow-up before shipping the backfill UI — admins will be confused if they run a backfill and the Spend widget doesn't move.

#### T108 — Documentation + runbook

Update `CLAUDE.md` (root) "Project-Specific Rules" with one line: **"Summarizer cost is part of `AgentStats.total_cost_7d` — a backfill of N runs will increase 7-day spend by ~N × (avg summarizer cost)."**

Optional: `docs/runbooks/agent-summary-backfill.md` describing when to run a backfill (post-migration, after changing the summarizer system prompt, after a summarization-model config change), and the kill switch (`UPDATE summary_backfill_jobs SET status='failed' WHERE id=...` — the existing queue will continue draining but the UI stops showing progress).

#### T109 — MCP tool surface (optional, only if we want Claude to trigger backfills)

Thin wrapper tool `backfill_agent_summaries` in `api/src/services/mcp_server/tools/agents.py` calling `POST /api/agent-runs/backfill-summaries`. Admin auth propagates via the HTTP bridge. Skip for M1 unless the user explicitly asks — most backfills are human-triggered at migration time.

#### T110 — E2E screenshot pass

Run `docs/ux/grab-ours.mjs` after the above lands. Expected visual changes:
- No horizontal page scroll on Agent Detail with large payloads (T100).
- Activity rows show `"Summary pending…"` for unsummarized runs (T101).
- Run detail sheet has a collapsible "Raw input" / "Raw output" section (T101).
- Regenerate button in Review sheet header (T102).
- Backfill button on FleetPage (admin view) + AgentDetailPage kebab (T106).

Drop the captures into `~/Sync/Screenshots/agent-ux-compare/` as usual.

---

### Execution order

1. T100 (unblocks UX) + T101 (backend contract + UI placeholders) — can go in one PR.
2. T105 without the backfill pieces (just wire realtime for per-run summarizer transitions) — small, high-value.
3. T102 (regenerate surfacing) — depends on T101.
4. T103 + T104 + T106 together — the backfill slice. Requires a migration so coordinate with other branches.
5. T107 + T108 (verification + docs).
6. T109 optional.
7. T110 screenshots before PR.

### Risks & open questions

- **Queue flooding.** A 5,000-run backfill dumps 5,000 messages. Existing `agent-summarization` consumer has `prefetch_count=max_concurrency` (single-digit in prod), so real concurrency is bounded — but the queue depth metric will spike. Acceptable; mention in runbook.
- **Cost estimate accuracy.** First backfill on a fresh system has no summarizer history — fallback flat rate. Make the dialog show `"Estimate based on %d recent summaries"` or `"No history — using flat $0.002/run estimate"` so admins aren't surprised by either direction.
- **WS reconnection.** If a long-running backfill's progress channel disconnects, the client must reconcile via `GET /backfill-jobs/{job_id}` on reconnect (already how other realtime flows handle it — see `useWorkerWebSocket.ts`).
- **Existing `status='generating'` runs at deploy time.** If a backfill is started while another is mid-summarize, the idempotent guard (`summary_status='completed'` short-circuit in `summarize_run:81`) handles the double-enqueue. No additional locking needed.

### Decision needed from user before execution

- **Platform-wide entry point location**: FleetPage header menu, or a new Platform Admin settings entry? Answered in chat before execution — default FleetPage header.
- **Max `limit`**: 5000 is the proposed cap. Higher means larger single-backfill cost blasts; lower means post-migration you might need multiple runs. 5000 matches the expected pre-migration run count for a well-used org.
