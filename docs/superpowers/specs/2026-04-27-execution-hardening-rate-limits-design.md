# Execution Hardening: Webhook Rate Limits, Schedule Overlap, and Stuck-Execution Fix

**Date:** 2026-04-27
**Status:** Draft — pending user review

## Problem

The execution system is a single shared FIFO pool fed by multiple trigger sources (apps, agents, schedules, webhooks). One noisy source — a service provider sending 100 emails into the ticketing queue, an auto-reply loop — can saturate the pool, starving everything else, including a one-second list query from an app loading data. There are no per-source rate limits on the webhook ingress, and schedules fire blindly without checking whether the previous run is still in flight.

When a runaway happens, the operator's recourse is to manually cancel a long list of executions one at a time. After cancellation, executions that were already mid-route can sit in the database with `status=RUNNING` for 15+ minutes before the cleanup reaper notices, even with the queue otherwise empty.

This spec hardens three things:

1. **Per-source webhook rate limiting** at ingress — stop the storm at the door.
2. **Schedule overlap policy** — schedules that haven't completed don't pile up new copies.
3. **Stuck-execution bug fix** — when a worker process dies silently, the database status reflects it within seconds, not 15+ minutes.

These are independent changes shipped together because they share the same operator-pain story: runaways are survivable, observable, and cleanly recoverable.

## Out of scope

These are deliberately separate concerns and will get their own specs:

- Per-agent concurrency caps.
- `queue` and `replace` schedule overlap policies (column added, behavior is follow-up).
- Cost ceilings, per-org quotas, event dedup keys, circuit breakers.
- Bulk-cancel UI.
- Priority lanes / reserved pool capacity for app-driven workflows. The throttles in this spec prevent the saturation that would make priority lanes necessary.

## Component 1: Per-source webhook rate limiting

### Data model

Add three columns to `WebhookSource` (`api/src/models/orm/events.py:146`):

| Column | Type | Default | Purpose |
|---|---|---|---|
| `rate_limit_per_minute` | `int \| None` | `60` | Max events per window. Null disables. |
| `rate_limit_window_seconds` | `int` | `60` | Window size for the limiter. |
| `rate_limit_enabled` | `bool` | `true` | Per-source kill switch without unsetting the value. |

Migration backfills `(60, 60, true)` for all existing webhook sources. 60/minute is a conservative default that won't break legitimate integrations (most webhook senders operate well under this) but immediately contains an auto-reply storm.

Inline columns are preferred over a sibling `EventSourceLimits` table because these settings only ever apply to webhook sources and the cardinality is 1:1.

### Algorithm

Reuse `RateLimiter` in `api/src/core/rate_limit.py`. The existing implementation is a Redis sliding-window counter (`INCR` + `EXPIRE`), which produces identical user-visible behavior to a token bucket for our use case (reject above rate, return 429). Standardizing on one primitive across auth and webhook ingress avoids carrying two algorithms in the codebase.

The window-based counter does not natively support a "burst" beyond the window's max. Tuning the window down (e.g. 30s instead of 60s) lets us approximate burst-friendly behavior if needed. A future migration to a true token bucket can be made without changing the call sites; the limiter interface is identifier-in / 429-out.

### Enforcement point

In `api/src/routers/hooks.py:receive_webhook` (line 70), after the `WebhookSource` has been resolved by `source_id` but before `EventProcessor.process_webhook` is invoked. The current code resolves the source inside `EventProcessor`; this spec lifts the EventSource/WebhookSource lookup into `receive_webhook` so the rate-limit check happens in the handler, before any side effects. `EventProcessor.process_webhook` is updated to accept the resolved sources rather than re-resolving them.

When the limit fires:

- Return HTTP 429 with `Retry-After: <window_seconds>` header.
- Body: `{"error": "rate_limit_exceeded", "source_id": "<uuid>", "retry_after_seconds": <n>}`.
- Do not create `Event` or `EventDelivery` records. The delivery commit at `hooks.py:166` must be unreachable when the limiter rejects.

### Observability

- WARN-level log on every 429: `webhook rate limit exceeded for source <name> (<id>): <current>/<limit> in <window>s`.
- Counter metric `bifrost_webhook_rate_limited_total{source_id,source_name}` for dashboards.
- The admin webhook source page surfaces a "rate-limited in last 24h" count read from the metric / log aggregation, so admins can spot misconfigured sources.

### UI

The existing webhook source admin page gains three fields: rate per minute, window seconds, enabled toggle. No new pages.

## Component 2: Schedule overlap policy

Overlap policy is a schedule-only concept. Webhooks deliberately do not get an overlap check: every webhook carries unique payload data and silently dropping one is a correctness bug, not a feature. Schedules, by contrast, fire predictably and the same job each time, so skipping a tick when the previous one is still running is almost always the right behavior. This principled split keeps the model honest — the source-level rate limiter handles the webhook story, the overlap policy handles the schedule story, and they don't share code or columns.

### Data model

Add one column to `ScheduleSource` (`api/src/models/orm/events.py:105`):

| Column | Type | Default | Purpose |
|---|---|---|---|
| `overlap_policy` | `enum('skip', 'queue', 'replace')` | `'skip'` | What to do if any subscription target's previous run is still active when this schedule fires. |

Only `skip` is implemented in this spec. The column is shipped from day one so future work to enable `queue` / `replace` does not require a migration. `queue` and `replace` behave as `skip` for v1, with a one-time WARN log noting the policy is not yet implemented (so users who set it can audit).

The column lives on `ScheduleSource` rather than `Subscription` because overlap is fundamentally a schedule concept: schedules fire predictably and we know what they will do; webhooks don't, and never get overlap-checked. Putting the column on `Subscription` would be misleading — it'd appear on every subscription row including webhook subscriptions where it would silently no-op.

If a future use case emerges where a single schedule fans out to multiple subscriptions with very different durations and only some need skip protection, that's a follow-up to split it per-subscription. Today the simpler model is correct.

### Enforcement

In `api/src/jobs/schedulers/cron_scheduler.py:process_schedule_sources` (line 28), before the per-source firing branch (lines 108–145):

1. Find the subscriptions for this `EventSource`. Each subscription targets a workflow.
2. For each target workflow, query `Execution` for rows where `source_event_id` traces back to this `EventSource` and `status IN ('PENDING', 'RUNNING', 'CANCELLING')`.
3. If any are found and `overlap_policy = 'skip'`: log `schedule <name> skipped: previous run <execution_id> still <status>` at INFO and do not create the `Event`.
4. If none found: fire normally.

The check happens at the schedule-source granularity: if a single schedule fans out to multiple workflows, all are skipped together when any one is still active. This is conservative — see "Data model" above for the rationale.

### Observability

INFO log per skip with the previous execution_id. `bifrost_schedule_skipped_total{schedule_id,schedule_name}` counter so dashboards can show schedules that are skipping unexpectedly often.

## Component 3: Stuck-execution bug fix

### Root cause

In `api/src/services/execution/process_pool.py`, `_check_process_health` (called from `_monitor_loop`) detects when a forked worker dies. When the dead process was `BUSY` (had an execution assigned), the handle gets cleaned up but no result callback fires. The execution row in the database stays at `status=RUNNING` until `execution_cleanup.py` (runs every 5 minutes, requires `timeout_seconds + 5min grace` to elapse) sweeps it.

For a workflow with a 600-second timeout, that's a minimum of 15 minutes between the worker dying and the database reflecting it.

### Fix

In `_check_process_health`, when a `BUSY` process is detected dead:

1. Before removing the handle from the pool, fabricate a failure result: `{"error": "worker process died unexpectedly", "exit_code": <code>}`.
2. Route it through the same `on_result` callback used by normal completion. This triggers the consumer's `_handle_result` → `_process_failure` → `update_execution(status=FAILED)` path within seconds.
3. Add an idempotency flag `cancel_callback_fired: bool` to `ProcessHandle`. The cancel path (`_report_timeout`, cancel listener) sets this flag when it fires the callback. `_check_process_health` reads it and skips if already fired — prevents double-reporting when cancel killed the process and health-check then notices the death.

### The reaper stays

`execution_cleanup.py` remains in place as the safety net for the case where even the health-check signal is missed (e.g. the pool manager itself crashes and restarts). After this fix, we expect it to almost never trigger; that's the point. Add a metric `bifrost_orphan_execution_swept_total` so we can see whether the reaper is still firing in production after the fix lands — if it is, there's another bug.

## Testing

### Webhook rate limit

- **Unit:** `RateLimiter.check` for the new identifier shape (source UUID), assert correct Redis key and 429-on-overflow.
- **Unit:** `hooks.py:receive_webhook` with a mock source at limit → returns 429 with `Retry-After`, no `Event` written.
- **E2E:** Hammer `/api/hooks/{source_id}` past the source's configured limit, assert 429 + `Retry-After` header + counter metric incremented + no `Event`/`EventDelivery` rows created beyond the threshold.

### Schedule overlap

- **Unit:** `process_schedule_sources` with a fixture RUNNING execution traced to a schedule, policy=`skip` → asserts no new `Event` created and a skip log emitted.
- **Unit:** Same fixture with policy=`queue` and `replace` → asserts behaves as `skip` (v1 fallback) with a WARN log.

### Stuck execution

This is the most important test because the bug is non-obvious without it.

- **E2E:** Start a long-running workflow execution. From the test, send SIGKILL to the worker PID. Assert:
  1. Execution status flips to `FAILED` within 5 seconds.
  2. Failure reason includes `worker process died unexpectedly`.
  3. The reaper (`execution_cleanup`) does not need to fire — assert by checking the timestamp of the status flip is within 5s of the SIGKILL, well before the reaper's 5-minute cycle.

- **E2E:** Start an execution, cancel it via `DELETE /api/executions/{id}`. The cancel path kills the process. Assert the result callback fires exactly once (not double-reported by the health check).

## Migration order

1. Ship the stuck-execution fix and reaper metric first. It is purely additive, has no schema change, and improves an existing footgun.
2. Ship schedule overlap (one column, defaults to `skip`, immediate value).
3. Ship webhook rate limiting last. Largest surface area (model, migration, handler refactor, UI).

Each is independently mergeable; the order above just reflects risk and effort.
