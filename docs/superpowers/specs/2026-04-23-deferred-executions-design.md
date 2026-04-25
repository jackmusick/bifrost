# Deferred Executions Design

**Status:** Draft
**Date:** 2026-04-23
**Author:** Jack Musick (with Claude)

## Summary

Let callers schedule a one-shot workflow execution for a future time. The request returns immediately with an `execution_id`; the row sits in a new `Scheduled` state until a scheduler job promotes it to `Pending` and publishes it to the existing `workflow-executions` RabbitMQ queue. From that point on, the run is indistinguishable from a "run now" execution. Scheduled runs can be cancelled until they're promoted.

This is a fire-and-forget feature. Recurring schedules remain the cron scheduler's job; this design intentionally does not touch that path.

## Goals

- Callers (SDK, REST, form trigger) can defer a workflow run by passing an absolute time or a relative delay.
- Scheduled runs are visible in the executions history with status `Scheduled` and can be cancelled.
- Late-on-recovery is the correct behavior: if the scheduler is down when a run matures, it runs as soon as the scheduler is back, up to a 1-year cap.
- No new infrastructure — reuse the existing scheduler pod (APScheduler, single replica) and RabbitMQ queue.

## Non-goals

- Recurrence / cron-like schedules (use the existing cron scheduler).
- Sync execution with a delay (`sync=True` + schedule is rejected).
- Delayed inline code execution (`code=...` + schedule is rejected; inline runs stay admin-only and immediate).
- Rescheduling an existing row (cancel and re-submit instead).
- A separate "Scheduled" tab or sidebar entry.
- Per-workflow `max_staleness` policies.

## User-facing contract

### REST

`POST /api/workflows/execute` gains two mutually-exclusive optional fields on `WorkflowExecutionRequest`:

```python
scheduled_at: datetime | None = Field(
    default=None,
    description="Run at this tz-aware timestamp (ISO-8601). Must be strictly in the future and ≤ 1 year from now. Mutually exclusive with delay_seconds.",
)
delay_seconds: int | None = Field(
    default=None, ge=1, le=31_536_000,
    description="Run this many seconds from now (≤ 1 year). Mutually exclusive with scheduled_at.",
)
```

Validation (extends the existing `@model_validator`):

- Reject if both fields are set.
- Reject naive datetimes on `scheduled_at` (matches the project's tz-aware convention).
- Reject `scheduled_at <= now` and `scheduled_at > now + 1 year`.
- Reject `code` combined with either field.
- Reject `sync=True` combined with either field.

The router normalizes `delay_seconds` to `scheduled_at = now + delta` immediately after validation; downstream code only deals with an absolute timestamp.

`WorkflowExecutionResponse` gains `scheduled_at: datetime | None`. For scheduled requests the response has `status=Scheduled` and `scheduled_at` populated; the `result`/`error`/`duration_ms` fields stay null.

### Cancel endpoint

`POST /api/workflows/executions/{execution_id}/cancel`

- For `Scheduled` rows: `UPDATE executions SET status='Cancelled' WHERE id=:id AND status='Scheduled'`. If zero rows match, return 409 with the current status.
- For any other status: return 409 (cancelling an in-flight `Running` execution is a separate existing feature and keeps its current path — we are not merging them).
- Auth: the user must be able to read the execution (own org or platform admin). Cancelling another user's scheduled run within the same org requires platform admin, matching existing cancel semantics.

### SDK

`api/bifrost/workflows.py::workflows.execute`:

```python
async def execute(
    workflow: str,
    input_data: dict[str, Any] | None = None,
    *,
    org_id: str | None = None,
    run_as: str | None = None,
    scheduled_at: datetime | None = None,
    delay_seconds: int | None = None,
) -> str:
    ...
```

Same one-of validation client-side so callers fail fast (`ValueError` before hitting the wire). `scheduled_at` must be tz-aware; the SDK raises on a naive datetime. A new `workflows.cancel(execution_id)` helper wraps the cancel endpoint.

The DTO-parity test (`api/tests/unit/test_dto_flags.py`) catches any drift between `WorkflowExecutionRequest` and the SDK/CLI surfaces. If a CLI flag like `--at` / `--in` is added later, the test will force both to stay in sync.

## Data model

### Enum

Add `SCHEDULED = "Scheduled"` to `ExecutionStatus` in `api/src/models/enums.py`. It is a non-terminal pre-run state distinct from `PENDING` (which implies the message is already on the RabbitMQ queue and the worker will pick it up imminently).

### Column

Add `scheduled_at TIMESTAMPTZ NULL` to the `executions` table. Null for every existing row and every "run now" row going forward.

### Index

Partial index so the promotion query stays cheap regardless of history table size:

```sql
CREATE INDEX ix_executions_scheduled_due
  ON executions (scheduled_at)
  WHERE status = 'Scheduled';
```

### Alembic migration

Single migration: add the column, add the partial index. No data backfill (existing rows stay `scheduled_at = NULL`).

## Router path

`api/src/routers/workflows.py::execute_workflow`:

When a request has `scheduled_at` (after normalization from `delay_seconds`):

1. Run the existing auth/access checks exactly as today.
2. **Skip** `run_workflow()` / `enqueue_workflow_execution()`.
3. Insert an `Execution` row directly with:
   - `status = SCHEDULED`
   - `scheduled_at = <resolved tz-aware UTC>`
   - All context fields the worker currently hydrates from Redis at run time: `workflow_id`, `workflow_name`, `organization_id`, `executed_by`, `parameters`, `form_id`, `api_key_id`, `is_platform_admin`, `started_by` / `name` / `email`, etc.
4. Return `WorkflowExecutionResponse(execution_id=..., status=SCHEDULED, scheduled_at=...)`.

Because the row itself carries the full context, the promoter does not need Redis to already hold a pending-execution blob — it reconstructs one at promotion time (see next section).

## Scheduler promotion job

New module: `api/src/jobs/schedulers/deferred_execution_promoter.py`, one entrypoint `promote_due_executions()`.

Registered in `api/src/scheduler/main.py` alongside the existing processors, with a 60-second trigger and the same misfire options (`misfire_grace_time=600`, `coalesce=True`).

### Tick

Single bounded transaction per tick:

```sql
UPDATE executions
SET status = 'Pending', started_at = NULL
WHERE id IN (
  SELECT id FROM executions
  WHERE status = 'Scheduled' AND scheduled_at <= now()
  ORDER BY scheduled_at ASC
  LIMIT 500
  FOR UPDATE SKIP LOCKED
)
RETURNING id, workflow_id, organization_id, executed_by, parameters, form_id, ...;
```

- `FOR UPDATE SKIP LOCKED` is belt-and-suspenders — the scheduler is single-replica today, but the query stays correct if that ever changes.
- `LIMIT 500` bounds a recovery burst: remaining matured rows roll to the next tick. Matches the B answer (run late on recovery, but don't stampede).

For each row returned, publish to RabbitMQ by reusing a shared helper extracted from `enqueue_workflow_execution`:

1. `redis_client.set_pending_execution(...)` using the RETURNINGed context columns (same shape today's enqueue path writes).
2. `add_to_queue(execution_id)` for queue-position tracking.
3. `publish_message("workflow-executions", {"execution_id", "workflow_id", "sync": False})`.

If the Redis write or RabbitMQ publish fails for a specific row, flip that row back to `Scheduled` (best-effort `UPDATE`), log, and let the next tick retry. The `UPDATE → Pending` commit is the authoritative promotion point; we never silently lose a run.

### Refactor

Extract a private `_publish_pending(execution_id, workflow_id, parameters, org_id, user_id, ...)` helper so the router's run-now path and the promoter share exactly one code path for "stage Redis blob, enqueue, publish." The public signature of `enqueue_workflow_execution` is unchanged.

### Observability

Per tick, log `promoted_count` and `publish_failures` at INFO. No new Prometheus gauge in v1 — the executions list already exposes the SCHEDULED backlog visually. If we later want alerting on "backlog growing faster than we drain it," add a gauge then.

## Cancel race

The cancel endpoint's `UPDATE ... WHERE id=:id AND status='Scheduled'` and the promoter's `UPDATE ... WHERE status='Scheduled' AND scheduled_at<=now()` are both status-guarded. Exactly one wins:

- Cancel wins → row is `Cancelled`, promoter's update sees zero matching rows for that id.
- Promoter wins → row is `Pending`, cancel returns 409 with current status. The caller can follow up with the existing running-execution cancel if they really need to stop it.

No zombie states. No locks needed beyond the row-level UPDATE.

## UI

### Status badge

`client/src/components/execution/ExecutionStatusBadge.tsx` gains a `Scheduled` variant — muted blue with a clock icon, label text `Scheduled`. The badge itself stays the same compact size regardless of status. The `scheduled_at` timestamp is surfaced **only on hover** via the `title` attribute (absolute local datetime, e.g. "Scheduled for Apr 25, 2026, 9:00 AM EDT"). No inline text next to the badge; no new table column.

### History list

`client/src/pages/ExecutionHistory.tsx`:

- Status filter gains `Scheduled` as an option in the existing dropdown.
- Row menu gains a **Cancel** action, visible only for rows with `status=Scheduled`. Confirm dialog: "Cancel scheduled run of `<workflow>` for `<time>`?" On confirm, call `POST /executions/{id}/cancel`. On 200, optimistic status flip to `Cancelled`. On 409, toast the current status and refetch the row.
- The real-time store (`client/src/stores/executionStreamStore.ts`) already handles status transitions via Redis pub/sub. The promoter emits a status-change publish on promotion using the same helper the worker uses for `Pending → Running`, so rows update live.

### Details page

`client/src/pages/ExecutionDetails.tsx`: show `Scheduled for: <datetime>` in the header block whenever `scheduled_at` is populated, regardless of current status. This is where the full timestamp lives; the compact list stays clean.

### Types

`cd client && npm run generate:types` after the contract changes lands the new fields. No manual `v1.d.ts` edits.

## Testing

### Backend unit (`api/tests/unit/`)

- `test_executions_contract.py` (extend or new):
  - Reject both `scheduled_at` and `delay_seconds`.
  - Reject naive `scheduled_at`.
  - Reject past `scheduled_at` and `scheduled_at > now + 1y`.
  - Reject `delay_seconds <= 0` and `delay_seconds > 31_536_000`.
  - Reject `sync=True` with either field.
  - Reject `code=...` with either field.
  - `delay_seconds` normalizes to `scheduled_at = now + delta` (within a small tolerance).
- `test_deferred_execution_promoter.py` (new), with a fake clock + test DB:
  - Due rows flip to `Pending` and result in a publish call.
  - Future rows are untouched.
  - `Cancelled` rows are untouched even when past due.
  - 500-row cap respected; remaining rows picked up next tick.
  - Publish failure reverts that row to `Scheduled`, logs, and does not leak the row as `Pending`.
- `test_dto_flags.py` already exists; running it after the SDK change catches drift.

### Backend e2e (`api/tests/e2e/`)

`test_workflow_scheduling.py` (new), requires the scheduler container (already part of the e2e stack):

- Happy path: schedule a trivial workflow with `delay_seconds=2`; poll and assert `Scheduled → Pending → Success` within ~90s (one promoter tick + execution time).
- Cancel happy path: schedule with `delay_seconds=300`; cancel; assert `Cancelled`; wait past the original time; assert no run happened.
- Cancel race: cancel a row that's on the cusp of promotion; assert we end with either `Cancelled` (and no run) or a 409 that cleanly reports `Pending`, never a zombie state.
- Auth: non-admin schedules a workflow they can already execute. Non-admin cancels their own scheduled run. Non-admin cannot cancel another user's scheduled run (403).
- Validation: past `scheduled_at` → 422. `sync=True` + `delay_seconds` → 422.

### Frontend (`client/`)

- `ExecutionStatusBadge.test.tsx`: renders `Scheduled` variant; `title` attribute contains the absolute local datetime when `scheduled_at` is provided; compact size matches other variants.
- `ExecutionHistory` vitest spec: `Scheduled` appears in the status-filter options; cancel action visible only for `Scheduled` rows; clicking it calls the cancel endpoint and optimistically updates status.
- Playwright `client/e2e/scheduled-execution.spec.ts`: sign in, schedule a short run via API helper, confirm the badge shows `Scheduled` and the hover `title` carries the datetime, confirm live transition to `Success` without a refresh. Cancel path: schedule, cancel via row menu, confirm `Cancelled`.

### Pre-completion gate

Standard CLAUDE.md verification sequence (`pyright`, `ruff check`, `npm run tsc`, `npm run lint`, `./test.sh all`, `./test.sh client unit`, `./test.sh client e2e`). No new steps.

## Rollout

- Migration is additive (nullable column, new enum value, partial index). No backfill. Safe to deploy ahead of the router/scheduler changes.
- Order: migration → router (can write SCHEDULED rows, no promoter yet — rows just sit) → promoter registered in scheduler → SDK → UI.
- If the promoter is disabled or crash-looping, scheduled rows accumulate harmlessly and drain once it's back.

## Open questions / follow-ups

- Do we want `cancelled_by` / `cancelled_at` columns for the details page audit line, or is the existing generic audit enough? Not blocking v1; details page can show just `Scheduled for ...` and status.
- CLI surface (`bifrost run --at`, `--in`): not in v1. DTO-parity test will flag it the moment someone adds CLI flags so we don't drift.
