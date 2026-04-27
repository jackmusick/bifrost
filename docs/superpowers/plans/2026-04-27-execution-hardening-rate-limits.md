# Execution Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Harden the execution pipeline against runaway storms by adding per-source webhook rate limits, schedule overlap protection, and fixing the orphaned-execution bug where cancelled / crashed executions sit in `RUNNING` status for 15+ minutes.

**Architecture:** Three independent components shipped sequentially in order of risk/effort:
1. Stuck-execution fix (no schema, purely additive to `process_pool.py`).
2. Schedule overlap policy (one column on `ScheduleSource`, enforced in `cron_scheduler.py`).
3. Webhook rate limiting (three columns on `WebhookSource`, enforced in `hooks.py`, admin UI).

Each component is independently mergeable. Components 1 and 3 reuse the existing `RateLimiter` in `api/src/core/rate_limit.py` and the existing `_report_*` callback pattern in `process_pool.py`.

**Tech Stack:** Python 3.11 / FastAPI / SQLAlchemy / Alembic / Pydantic / Redis / pytest. Frontend: React / TypeScript / Vite (admin UI for component 3).

**Spec:** `docs/superpowers/specs/2026-04-27-execution-hardening-rate-limits-design.md`

---

## Component 1: Stuck-execution fix

The bug: when `_handle_cancel_request` or `_kill_process` runs, it sets `handle.state = ProcessState.KILLED` *before* the result callback fires (`_report_cancellation` / `_report_timeout`). If anything between those two steps fails (exception, missed pubsub message, race), the handle is in `KILLED` state but the DB sits at `status=RUNNING`/`CANCELLING`. The `_check_process_health` loop *skips* `KILLED` processes (line 1102: `handle.state != ProcessState.KILLED`), so it never recovers.

The fix: track whether a result callback fired for each handle. The cancel/timeout/crash paths set the flag after firing. `_check_process_health` is extended to also sweep `KILLED` processes whose flag is still false — fire a callback for them and remove from the pool.

### Task 1.1: Add `result_reported` flag to `ProcessHandle`

**Files:**
- Modify: `api/src/services/execution/process_pool.py:115-151` (the `ProcessHandle` dataclass)

- [ ] **Step 1: Read current `ProcessHandle` dataclass**

Run: `sed -n '115,151p' /home/jack/GitHub/bifrost/api/src/services/execution/process_pool.py`

- [ ] **Step 2: Add `result_reported` field to the dataclass**

Add a field after the existing `state` and `current_execution` fields in `ProcessHandle`:

```python
@dataclass
class ProcessHandle:
    # ... existing fields ...
    result_reported: bool = False  # True once on_result has fired for current_execution; reset on assignment to a new execution
```

The exact position depends on the existing field order. Place it after the last default-value field to satisfy dataclass ordering (no non-default after default).

- [ ] **Step 3: Reset `result_reported` when a new execution is assigned**

In `route_execution` around line 687 (`idle.state = ProcessState.BUSY`), set `idle.result_reported = False` when `current_execution` is also set.

```python
idle.state = ProcessState.BUSY
idle.current_execution = ExecutionInfo(...)
idle.result_reported = False
```

(Locate the actual current_execution assignment and put it on the same block.)

- [ ] **Step 4: Commit**

```bash
git add api/src/services/execution/process_pool.py
git commit -m "feat(process-pool): add result_reported flag to ProcessHandle"
```

### Task 1.2: Set `result_reported = True` in all existing reporting paths

**Files:**
- Modify: `api/src/services/execution/process_pool.py` — `_report_timeout` (line 838), `_report_cancellation` (line 1072), `_report_crash` (line 1122), and the success path in the result loop (search for `await self.on_result(` and find the success-path call site).

- [ ] **Step 1: Read all `on_result` call sites**

Run: `grep -n "on_result" /home/jack/GitHub/bifrost/api/src/services/execution/process_pool.py`

- [ ] **Step 2: After each successful `await self.on_result(...)` call, set the handle's `result_reported = True`**

For `_report_timeout` (line 847–854), `_report_cancellation` (line 1081–1088), and `_report_crash` (line 1131–1138): the function takes `exec_info: ExecutionInfo`, but the flag lives on the `ProcessHandle`. Refactor signatures to take the handle instead:

```python
async def _report_timeout(self, handle: ProcessHandle) -> None:
    if self.on_result and not handle.result_reported:
        try:
            await self.on_result({
                "type": "result",
                "execution_id": handle.current_execution.execution_id,
                "success": False,
                "error": f"Execution timed out after {handle.current_execution.timeout_seconds}s",
                "error_type": "TimeoutError",
                "duration_ms": int(handle.current_execution.elapsed_seconds * 1000),
            })
            handle.result_reported = True
        except Exception as e:
            logger.exception(f"Error reporting timeout: {e}")
```

Same shape for `_report_cancellation` and `_report_crash`. Update the call sites in `_check_timeouts` (line 796), `_handle_cancel_request` (line 1059), and `_check_process_health` (line 1110) to pass the handle, not the exec_info.

For the success path (in the result loop where `_handle_result`-shaped messages flow): find the `on_result` call that propagates worker-completed results and set `handle.result_reported = True` after it fires. Use `grep -n "on_result" /home/jack/GitHub/bifrost/api/src/services/execution/process_pool.py` to find the success site if not obvious.

- [ ] **Step 3: Run existing process-pool tests to confirm no regression**

Run from repo root: `./test.sh stack up && ./test.sh tests/unit/execution/test_process_pool.py -v`

Expected: All currently-passing tests still pass. Some may need signature updates (passing handle vs exec_info).

- [ ] **Step 4: Commit**

```bash
git add api/src/services/execution/process_pool.py api/tests/unit/execution/test_process_pool.py
git commit -m "feat(process-pool): track result_reported across all reporting paths"
```

### Task 1.3: Sweep KILLED processes with no reported result

**Files:**
- Modify: `api/src/services/execution/process_pool.py:1092-1116` (`_check_process_health`)
- Test: `api/tests/unit/execution/test_process_pool.py`

- [ ] **Step 1: Write a failing test for the orphan-sweep**

Add to `api/tests/unit/execution/test_process_pool.py`:

```python
import asyncio
from unittest.mock import AsyncMock
import pytest

@pytest.mark.asyncio
async def test_check_process_health_sweeps_orphaned_killed_handles(process_pool_manager):
    """
    A handle whose state is KILLED but result_reported=False should
    have a synthetic callback fired so the DB doesn't sit orphaned.
    """
    pool = process_pool_manager
    callback = AsyncMock()
    pool.on_result = callback

    # Create a handle that looks like a cancelled-but-unreported execution
    handle = _make_handle(state=ProcessState.KILLED, result_reported=False)
    handle.current_execution = ExecutionInfo(
        execution_id="exec-orphan-1",
        timeout_seconds=300,
        started_at=datetime.now(timezone.utc),
    )
    pool.processes["proc-1"] = handle

    await pool._check_process_health()

    callback.assert_awaited_once()
    args = callback.await_args.args[0]
    assert args["execution_id"] == "exec-orphan-1"
    assert args["success"] is False
    assert args["error_type"] == "OrphanedExecution"
    assert "proc-1" not in pool.processes
```

The test uses a `_make_handle` fixture helper (add it near the top of the file or alongside other helpers). Mirror existing helpers used in the file — check `test_process_pool.py` for the pattern.

- [ ] **Step 2: Run the test to verify it fails**

Run: `./test.sh tests/unit/execution/test_process_pool.py::test_check_process_health_sweeps_orphaned_killed_handles -v`

Expected: FAIL — `_check_process_health` currently skips KILLED handles outright (line 1102 condition).

- [ ] **Step 3: Implement the orphan sweep**

Replace `_check_process_health` (lines 1092–1116) with:

```python
async def _check_process_health(self) -> None:
    """
    Check for crashed processes AND orphaned KILLED handles, replacing them.

    Two reporting cases:
    - Process is dead but state is not KILLED: a crash. Fire crash callback.
    - Process is in KILLED state but result_reported=False: cancellation/timeout
      that started but never completed its callback (race or exception).
      Fire orphan callback so the DB doesn't sit at RUNNING/CANCELLING.
    """
    to_remove: list[str] = []

    for process_id, handle in self.processes.items():
        if not handle.is_alive and handle.state != ProcessState.KILLED:
            logger.warning(
                f"Process {process_id} crashed "
                f"(exit_code={handle.process.exitcode})"
            )
            if handle.current_execution and not handle.result_reported:
                await self._report_crash(handle)
            to_remove.append(process_id)
            continue

        if (
            handle.state == ProcessState.KILLED
            and handle.current_execution
            and not handle.result_reported
        ):
            logger.warning(
                f"Process {process_id} is KILLED but execution "
                f"{handle.current_execution.execution_id[:8]} was never reported; "
                f"firing orphan callback"
            )
            await self._report_orphan(handle)
            to_remove.append(process_id)

    for process_id in to_remove:
        del self.processes[process_id]

    while len(self.processes) < self.min_workers:
        self._fork_process()
```

Add the new `_report_orphan` method below `_report_crash`:

```python
async def _report_orphan(self, handle: ProcessHandle) -> None:
    """
    Report an orphaned execution — KILLED state with no prior reporting.

    Used by _check_process_health to recover from races where the cancel/
    timeout path killed a process but never fired the result callback.
    """
    if self.on_result and not handle.result_reported:
        try:
            await self.on_result({
                "type": "result",
                "execution_id": handle.current_execution.execution_id,
                "success": False,
                "error": "Execution orphaned — process was killed but result was never reported",
                "error_type": "OrphanedExecution",
                "duration_ms": int(handle.current_execution.elapsed_seconds * 1000),
            })
            handle.result_reported = True
        except Exception as e:
            logger.exception(f"Error reporting orphan: {e}")
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `./test.sh tests/unit/execution/test_process_pool.py::test_check_process_health_sweeps_orphaned_killed_handles -v`

Expected: PASS.

- [ ] **Step 5: Run the full process-pool test suite**

Run: `./test.sh tests/unit/execution/ -v`

Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add api/src/services/execution/process_pool.py api/tests/unit/execution/test_process_pool.py
git commit -m "fix(process-pool): sweep orphaned KILLED handles in health check"
```

### Task 1.4: Add reaper-fired metric

**Files:**
- Modify: `api/src/jobs/schedulers/execution_cleanup.py`

- [ ] **Step 1: Read the cleanup job**

Run: `cat /home/jack/GitHub/bifrost/api/src/jobs/schedulers/execution_cleanup.py | head -120`

- [ ] **Step 2: Find the existing metric pattern in the codebase**

Run: `grep -rn "Counter\|prom_client\|prometheus" /home/jack/GitHub/bifrost/api/src/ | head -20`

If no existing metrics framework: add a structured WARN log instead — `logger.warning("orphan_execution_swept", extra={"execution_id": ..., "stuck_status": ..., "stuck_for_seconds": ...})` so the existing log aggregation captures it.

- [ ] **Step 3: Add the warn log to the cleanup function**

In the loop where stuck executions are flipped to TIMEOUT/CANCELLED:

```python
logger.warning(
    "orphan_execution_swept",
    extra={
        "execution_id": str(execution.id),
        "stuck_status": execution.status.value,
        "stuck_for_seconds": int((datetime.now(timezone.utc) - execution.updated_at).total_seconds()),
    },
)
```

This lets ops see whether the reaper is still doing real work after Component 1 lands. If counts drop to ~0 over time, the orphan-sweep fix is working.

- [ ] **Step 4: Commit**

```bash
git add api/src/jobs/schedulers/execution_cleanup.py
git commit -m "feat(cleanup): log orphan_execution_swept events"
```

### Task 1.5: E2E test — SIGKILL worker, assert fast recovery

**Files:**
- Test: `api/tests/e2e/api/test_executions_orphan_recovery.py` (new)

- [ ] **Step 1: Write the failing E2E test**

Create `api/tests/e2e/api/test_executions_orphan_recovery.py`:

```python
"""E2E: when a worker process is SIGKILLed mid-execution, the DB status
flips to FAILED within seconds rather than waiting for the 5-min reaper."""
import asyncio
import os
import signal
import time
import pytest


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_killed_worker_flips_status_within_seconds(api_client, db_session, long_running_workflow):
    """
    Start a long-running workflow, find its worker PID via the pool's
    introspection endpoint, send SIGKILL, assert status flips to FAILED
    within 10 seconds (well under the 5-min reaper cycle).
    """
    response = await api_client.post(f"/api/endpoints/{long_running_workflow.id}", json={"sleep_seconds": 60})
    assert response.status_code == 202
    execution_id = response.json()["execution_id"]

    # Poll until execution is RUNNING and we have a worker PID
    pid = None
    for _ in range(20):
        await asyncio.sleep(0.5)
        debug = await api_client.get("/api/admin/process-pool")
        for handle in debug.json()["processes"]:
            if handle.get("current_execution", {}).get("execution_id") == execution_id:
                pid = handle["pid"]
                break
        if pid:
            break
    assert pid, f"Could not find worker PID for execution {execution_id}"

    os.kill(pid, signal.SIGKILL)
    kill_at = time.monotonic()

    # Wait for status flip
    final_status = None
    for _ in range(40):  # up to 20 seconds
        await asyncio.sleep(0.5)
        ex_resp = await api_client.get(f"/api/executions/{execution_id}")
        if ex_resp.json()["status"] in ("FAILED", "TIMEOUT"):
            final_status = ex_resp.json()["status"]
            break
    elapsed = time.monotonic() - kill_at
    assert final_status == "FAILED", f"Expected FAILED, got {final_status} after {elapsed:.1f}s"
    assert elapsed < 10, f"Recovery took {elapsed:.1f}s, expected < 10s (orphan sweep should fire fast)"
```

If the project doesn't already expose `/api/admin/process-pool` for introspection, find an existing fixture or admin endpoint that surfaces handle PIDs. Otherwise add a minimal helper that queries the pool directly. **Do not block on this** — if there is no introspection endpoint, write the test against the in-process `ProcessPoolManager` fixture used in unit tests; convert from E2E to integration test scope.

- [ ] **Step 2: Run to verify it passes** (this is mostly a regression-prevention test; it should pass given Tasks 1.1–1.3)

Run: `./test.sh e2e tests/e2e/api/test_executions_orphan_recovery.py -v`

Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add api/tests/e2e/api/test_executions_orphan_recovery.py
git commit -m "test(e2e): assert orphaned worker recovery within 10s"
```

---

## Component 2: Schedule overlap policy

### Task 2.1: Migration — add `overlap_policy` column to `ScheduleSource`

**Files:**
- Create: `api/alembic/versions/<YYYYMMDD>_<slug>_schedule_overlap_policy.py`
- Modify: `api/src/models/orm/events.py:105-143` (the `ScheduleSource` ORM)

- [ ] **Step 1: Generate the migration**

Run from repo root:
```bash
docker compose exec api alembic revision -m "add overlap_policy to schedule_sources"
```

Or, if you cannot reach the dev API container, hand-create one matching the latest naming pattern (`YYYYMMDD_<slug>.py` — see `api/alembic/versions/20260426_171650_partial_uq_system_configs_null_org.py`).

- [ ] **Step 2: Write the migration**

Edit the new migration file:

```python
"""add overlap_policy to schedule_sources

Revision ID: <auto-generated>
Revises: <previous>
Create Date: 2026-04-27
"""
from typing import Sequence, Union
import sqlalchemy as sa
from alembic import op

revision: str = "<auto-generated>"
down_revision: Union[str, None] = "<previous>"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    overlap_policy_enum = sa.Enum("skip", "queue", "replace", name="schedule_overlap_policy")
    overlap_policy_enum.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "schedule_sources",
        sa.Column(
            "overlap_policy",
            overlap_policy_enum,
            nullable=False,
            server_default="skip",
        ),
    )


def downgrade() -> None:
    op.drop_column("schedule_sources", "overlap_policy")
    sa.Enum(name="schedule_overlap_policy").drop(op.get_bind(), checkfirst=True)
```

- [ ] **Step 3: Update the ORM**

In `api/src/models/orm/events.py` `ScheduleSource` (around line 122–124):

```python
from enum import Enum as PyEnum

class ScheduleOverlapPolicy(str, PyEnum):
    SKIP = "skip"
    QUEUE = "queue"
    REPLACE = "replace"
```

(Place enum near the top of the module alongside other enums.)

Add column to ScheduleSource:

```python
overlap_policy: Mapped[ScheduleOverlapPolicy] = mapped_column(
    sa.Enum(ScheduleOverlapPolicy, name="schedule_overlap_policy"),
    default=ScheduleOverlapPolicy.SKIP,
    nullable=False,
)
```

- [ ] **Step 4: Run migration and verify**

Run from repo root:
```bash
docker compose -f docker-compose.dev.yml restart bifrost-init
docker compose -f docker-compose.dev.yml restart api
```

Then verify:
```bash
docker compose exec postgres psql -U postgres -d bifrost -c "\d schedule_sources" | grep overlap
```

Expected: `overlap_policy | schedule_overlap_policy | not null default 'skip'`

- [ ] **Step 5: Commit**

```bash
git add api/alembic/versions/ api/src/models/orm/events.py
git commit -m "feat(db): add overlap_policy column to schedule_sources"
```

### Task 2.2: Add Pydantic model field for the API

**Files:**
- Modify: `api/shared/models.py` — find the existing `ScheduleSource` Pydantic models (Create / Update / Response)

- [ ] **Step 1: Find the relevant Pydantic models**

Run: `grep -n "ScheduleSource\|ScheduleSourceCreate\|ScheduleSourceUpdate\|ScheduleSourceResponse" /home/jack/GitHub/bifrost/api/shared/models.py`

- [ ] **Step 2: Add `overlap_policy` field to each schedule-source model**

For each (Create, Update, Response or whatever exists):
```python
overlap_policy: ScheduleOverlapPolicy = ScheduleOverlapPolicy.SKIP
```

Re-export `ScheduleOverlapPolicy` from `models.py` if it's defined in `orm/events.py`. The model is already in `orm/events.py` from Task 2.1; import it.

- [ ] **Step 3: Regenerate frontend types**

Run from repo root:
```bash
cd client && npm run generate:types && cd ..
```

Expected: `client/src/lib/v1.d.ts` updated with new field.

- [ ] **Step 4: Commit**

```bash
git add api/shared/models.py client/src/lib/v1.d.ts
git commit -m "feat(api): expose overlap_policy on ScheduleSource models"
```

### Task 2.3: Enforce skip in `cron_scheduler.py`

**Files:**
- Modify: `api/src/jobs/schedulers/cron_scheduler.py:69-196` (`process_schedule_sources`)
- Test: `api/tests/unit/test_cron_scheduler.py` (if exists; otherwise create)

- [ ] **Step 1: Write the failing unit test**

Find or create `api/tests/unit/test_cron_scheduler.py`. Confirm whether one exists:

Run: `find /home/jack/GitHub/bifrost/api/tests -name "test_cron_scheduler*" -o -name "test_schedule*"`

Add the test (adapt fixture style to match existing tests in the file):

```python
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

@pytest.mark.asyncio
async def test_schedule_skipped_when_previous_run_active(db_session, freeze_time_at_cron_match):
    """
    Schedule with overlap_policy=skip and an active previous Execution
    must not create a new Event.
    """
    from src.models.orm.events import (
        EventSource, ScheduleSource, EventSourceType, ScheduleOverlapPolicy,
    )
    from src.models.orm.executions import Execution, ExecutionStatus

    source = EventSource(name="hourly-sync", source_type=EventSourceType.SCHEDULE, is_active=True)
    schedule = ScheduleSource(
        event_source=source,
        cron_expression="0 * * * *",  # top of hour
        timezone="UTC",
        enabled=True,
        overlap_policy=ScheduleOverlapPolicy.SKIP,
    )
    db_session.add_all([source, schedule])
    await db_session.flush()

    active_execution = Execution(
        id="exec-active-1",
        source_event_id=...,  # link to a prior Event from this source
        status=ExecutionStatus.RUNNING,
    )
    db_session.add(active_execution)
    await db_session.commit()

    from src.jobs.schedulers.cron_scheduler import process_schedule_sources
    result = await process_schedule_sources()

    new_events = await db_session.execute(
        sa.select(Event).where(Event.event_source_id == source.id, Event.created_at >= now)
    )
    assert new_events.all() == [], "Expected no new Event when previous run is active"
    assert result["skipped_overlap"] >= 1
```

(The fixture details — `freeze_time_at_cron_match`, `db_session` — should match how the existing scheduler tests are structured. If no scheduler tests exist, mirror an existing job-scheduler test file like `test_execution_cleanup.py`.)

- [ ] **Step 2: Run the test to verify it fails**

Run: `./test.sh tests/unit/test_cron_scheduler.py -v`

Expected: FAIL — no overlap check exists yet.

- [ ] **Step 3: Implement the overlap check**

In `api/src/jobs/schedulers/cron_scheduler.py`, after the cron-match validation (line ~114) and before creating the Event (line ~117), add:

```python
from src.models.orm.events import ScheduleOverlapPolicy

overlap_policy = source.schedule_source.overlap_policy
if overlap_policy in (ScheduleOverlapPolicy.SKIP, ScheduleOverlapPolicy.QUEUE, ScheduleOverlapPolicy.REPLACE):
    # v1: all three behave as SKIP; queue/replace are reserved for future work.
    active_count = await db.scalar(
        sa.select(sa.func.count(Execution.id))
        .join(Event, Event.id == Execution.source_event_id)
        .where(
            Event.event_source_id == source.id,
            Execution.status.in_(["PENDING", "RUNNING", "CANCELLING"]),
        )
    )
    if active_count and active_count > 0:
        if overlap_policy != ScheduleOverlapPolicy.SKIP:
            logger.warning(
                "schedule_overlap_policy_not_implemented",
                extra={
                    "schedule_id": str(source.id),
                    "policy": overlap_policy.value,
                    "behavior": "treated as SKIP for v1",
                },
            )
        logger.info(
            "schedule_skipped_overlap",
            extra={
                "schedule_id": str(source.id),
                "schedule_name": source.name,
                "active_executions": active_count,
            },
        )
        result["skipped_overlap"] = result.get("skipped_overlap", 0) + 1
        continue  # skip to next source
```

Make sure the surrounding loop structure uses `continue` correctly and that the result dict is the same one the function returns.

- [ ] **Step 4: Run the test to verify it passes**

Run: `./test.sh tests/unit/test_cron_scheduler.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add api/src/jobs/schedulers/cron_scheduler.py api/tests/unit/test_cron_scheduler.py
git commit -m "feat(scheduler): skip schedule when previous run still active"
```

### Task 2.4: Frontend — surface `overlap_policy` on schedule source admin

**Files:**
- Modify: the schedule-source edit form in `client/src/`. Find with: `grep -rn "ScheduleSource\|cron_expression" /home/jack/GitHub/bifrost/client/src/ | head`.

- [ ] **Step 1: Locate the schedule-source admin form**

Run: `grep -rln "cron_expression\|ScheduleSource" /home/jack/GitHub/bifrost/client/src/`

- [ ] **Step 2: Add a select for `overlap_policy` with options skip / queue / replace**

In the form component, add a labeled select bound to `overlap_policy`. Default to `"skip"`. Add a help-text note: "If a previous run is still active when the schedule fires: skip (default) drops the new run, queue and replace are reserved for future use." Use the existing form-input pattern (likely shadcn/ui Select).

- [ ] **Step 3: Run client typecheck**

Run from `client/`: `npm run tsc`

Expected: 0 errors.

- [ ] **Step 4: Commit**

```bash
git add client/src/
git commit -m "feat(client): expose schedule overlap_policy on admin form"
```

---

## Component 3: Per-source webhook rate limiting

### Task 3.1: Migration — add three rate-limit columns to `webhook_sources`

**Files:**
- Create: `api/alembic/versions/<YYYYMMDD>_<slug>_webhook_rate_limit_columns.py`
- Modify: `api/src/models/orm/events.py:146-202` (`WebhookSource`)

- [ ] **Step 1: Create the migration**

Run: `docker compose exec api alembic revision -m "add rate limit columns to webhook_sources"`

- [ ] **Step 2: Write the migration**

```python
"""add rate limit columns to webhook_sources

Revision ID: <auto>
Revises: <previous>
Create Date: 2026-04-27
"""
from typing import Sequence, Union
import sqlalchemy as sa
from alembic import op

revision: str = "<auto>"
down_revision: Union[str, None] = "<previous>"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "webhook_sources",
        sa.Column("rate_limit_per_minute", sa.Integer(), nullable=True, server_default="60"),
    )
    op.add_column(
        "webhook_sources",
        sa.Column("rate_limit_window_seconds", sa.Integer(), nullable=False, server_default="60"),
    )
    op.add_column(
        "webhook_sources",
        sa.Column("rate_limit_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
    )


def downgrade() -> None:
    op.drop_column("webhook_sources", "rate_limit_enabled")
    op.drop_column("webhook_sources", "rate_limit_window_seconds")
    op.drop_column("webhook_sources", "rate_limit_per_minute")
```

- [ ] **Step 3: Update the `WebhookSource` ORM**

In `api/src/models/orm/events.py` after the existing column block (~line 177), add:

```python
rate_limit_per_minute: Mapped[int | None] = mapped_column(Integer, default=60, nullable=True)
rate_limit_window_seconds: Mapped[int] = mapped_column(Integer, default=60, nullable=False)
rate_limit_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
```

- [ ] **Step 4: Apply migration**

```bash
docker compose -f docker-compose.dev.yml restart bifrost-init
docker compose -f docker-compose.dev.yml restart api
```

Verify:
```bash
docker compose exec postgres psql -U postgres -d bifrost -c "\d webhook_sources" | grep rate_limit
```

- [ ] **Step 5: Commit**

```bash
git add api/alembic/versions/ api/src/models/orm/events.py
git commit -m "feat(db): add rate-limit columns to webhook_sources"
```

### Task 3.2: Lift webhook source resolution into `hooks.py`

`EventProcessor.process_webhook` currently resolves the WebhookSource by `source_id`. To rate-limit before any side effects, the resolution moves into the handler and the processor accepts the resolved source.

**Files:**
- Modify: `api/src/routers/hooks.py:70-128`
- Modify: `api/src/services/webhooks/processor.py` (find with: `grep -n "process_webhook" /home/jack/GitHub/bifrost/api/src/services/webhooks/processor.py`)

- [ ] **Step 1: Read the current processor signature**

Run: `grep -n "def process_webhook\|def __init__" /home/jack/GitHub/bifrost/api/src/services/webhooks/processor.py`

- [ ] **Step 2: Add a helper for source resolution**

In the processor (or a new `webhook_resolver.py` if cleanest), expose:

```python
async def resolve_webhook_source(db: AsyncSession, source_id: str) -> tuple[EventSource, WebhookSource] | None:
    """Look up the EventSource + WebhookSource by id. Returns None if missing/inactive."""
    stmt = (
        sa.select(EventSource)
        .options(joinedload(EventSource.webhook_source))
        .where(EventSource.id == source_id, EventSource.is_active == True, EventSource.source_type == EventSourceType.WEBHOOK)
    )
    result = await db.execute(stmt)
    event_source = result.unique().scalar_one_or_none()
    if not event_source or not event_source.webhook_source:
        return None
    return event_source, event_source.webhook_source
```

- [ ] **Step 3: Refactor `process_webhook` to accept resolved sources**

Change the signature from:
```python
async def process_webhook(self, source_id: str, request: WebhookRequest) -> ...
```
to:
```python
async def process_webhook(self, event_source: EventSource, webhook_source: WebhookSource, request: WebhookRequest) -> ...
```

Move the existing internal resolution out (the helper from Step 2 replaces it). Update the docstring.

- [ ] **Step 4: Update the handler to do resolution first**

In `api/src/routers/hooks.py:receive_webhook` (lines 113–128), replace:
```python
processor = EventProcessor(db)
# ...
result = await processor.process_webhook(source_id, webhook_request)
```
with:
```python
resolved = await resolve_webhook_source(db, source_id)
if resolved is None:
    return Response(content="Not Found", status_code=404, media_type="text/plain")
event_source, webhook_source = resolved

processor = EventProcessor(db)
result = await processor.process_webhook(event_source, webhook_source, webhook_request)
```

- [ ] **Step 5: Run the existing webhook tests to confirm no regression**

Run: `./test.sh tests/unit/test_webhooks.py -v` (or wherever webhook tests live — find with `grep -rln "process_webhook" /home/jack/GitHub/bifrost/api/tests/`).

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add api/src/routers/hooks.py api/src/services/webhooks/processor.py
git commit -m "refactor(hooks): resolve webhook source in handler before processing"
```

### Task 3.3: Apply the rate limit in the handler

**Files:**
- Modify: `api/src/routers/hooks.py`
- Test: `api/tests/unit/routers/test_hooks_rate_limit.py` (new)

- [ ] **Step 1: Write the failing test**

```python
"""Webhook ingress rate-limit tests."""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch

from src.main import app


@pytest.fixture
def client():
    return TestClient(app)


@pytest.mark.asyncio
async def test_webhook_returns_429_after_rate_limit_exceeded(client, webhook_source_factory, redis_test_client):
    """A webhook source configured at 5/sec should 429 the 6th request."""
    src = await webhook_source_factory(rate_limit_per_minute=5, rate_limit_window_seconds=60, rate_limit_enabled=True)

    for _ in range(5):
        r = client.post(f"/api/hooks/{src.id}", content=b"{}")
        assert r.status_code in (200, 202)

    r = client.post(f"/api/hooks/{src.id}", content=b"{}")
    assert r.status_code == 429
    assert "Retry-After" in r.headers
    assert int(r.headers["Retry-After"]) > 0


@pytest.mark.asyncio
async def test_webhook_rate_limit_disabled_per_source(client, webhook_source_factory):
    """A source with rate_limit_enabled=False is never throttled."""
    src = await webhook_source_factory(rate_limit_per_minute=1, rate_limit_enabled=False)
    for _ in range(10):
        r = client.post(f"/api/hooks/{src.id}", content=b"{}")
        assert r.status_code != 429
```

(Use the test infra's existing factories. If no `webhook_source_factory` exists, follow the pattern in `api/tests/conftest.py` for other factories.)

**Important:** the existing `RateLimiter.check` short-circuits when `settings.is_testing` is true (line 57–60 of `rate_limit.py`). For these tests to exercise the limiter, they must run with `is_testing=False` for that subset, OR you must instantiate the limiter via a wrapper that respects a per-call testing override. Simplest: in the test, monkeypatch `settings.is_testing` to False just for these tests, OR add a `force=True` parameter to `RateLimiter.check`. Pick the simpler one — monkeypatch is fine here.

- [ ] **Step 2: Run to verify it fails**

Run: `./test.sh tests/unit/routers/test_hooks_rate_limit.py -v`

Expected: FAIL — no rate limit applied.

- [ ] **Step 3: Add the rate-limit check in `receive_webhook`**

In `api/src/routers/hooks.py` after Step 4 of Task 3.2 (resolution) and before constructing the WebhookRequest, add:

```python
if webhook_source.rate_limit_enabled and webhook_source.rate_limit_per_minute is not None:
    limiter = RateLimiter(
        max_requests=webhook_source.rate_limit_per_minute,
        window_seconds=webhook_source.rate_limit_window_seconds,
    )
    try:
        await limiter.check("webhook_ingress", str(event_source.id))
    except HTTPException as exc:
        # Surface the 429 with Retry-After back to the caller.
        return Response(
            content=f'{{"error":"rate_limit_exceeded","source_id":"{event_source.id}"}}',
            status_code=exc.status_code,
            media_type="application/json",
            headers=dict(exc.headers or {}),
        )
```

Add the import at the top:
```python
from fastapi import HTTPException
from src.core.rate_limit import RateLimiter
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `./test.sh tests/unit/routers/test_hooks_rate_limit.py -v`

Expected: PASS.

- [ ] **Step 5: Add a structured WARN log on 429**

The existing `RateLimiter.check` already logs at WARN level (line 75–83). Verify by inspection — no extra log code needed in `hooks.py`. Add a comment in `hooks.py` near the limiter call: `# RateLimiter logs the 429 at WARN with source identifier.`

- [ ] **Step 6: Commit**

```bash
git add api/src/routers/hooks.py api/tests/unit/routers/test_hooks_rate_limit.py
git commit -m "feat(hooks): per-source webhook rate limiting"
```

### Task 3.4: E2E rate-limit test

**Files:**
- Test: `api/tests/e2e/api/test_webhook_rate_limit.py` (new)

- [ ] **Step 1: Write the e2e test**

```python
"""E2E: webhook rate limit prevents Event creation past threshold."""
import pytest
from sqlalchemy import select


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_webhook_rate_limit_prevents_event_creation(api_client, db_session, webhook_source_factory):
    src = await webhook_source_factory(rate_limit_per_minute=3, rate_limit_window_seconds=60, rate_limit_enabled=True)

    accepted = 0
    rejected = 0
    for _ in range(10):
        r = await api_client.post(f"/api/hooks/{src.id}", content=b"{}")
        if r.status_code == 429:
            rejected += 1
        else:
            accepted += 1

    assert accepted == 3
    assert rejected == 7

    from src.models.orm.events import Event
    events = (await db_session.execute(select(Event).where(Event.event_source_id == src.event_source_id))).scalars().all()
    assert len(events) == 3, f"Expected 3 Events created, got {len(events)} — rate limiter let storms through"
```

- [ ] **Step 2: Run**

Run: `./test.sh e2e tests/e2e/api/test_webhook_rate_limit.py -v`

Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add api/tests/e2e/api/test_webhook_rate_limit.py
git commit -m "test(e2e): webhook rate limit caps Event creation"
```

### Task 3.5: Frontend — webhook source admin gains 3 fields

**Files:**
- Modify: webhook source admin form (find with `grep -rn "WebhookSource\|webhook_sources" /home/jack/GitHub/bifrost/client/src/`)
- Modify: `api/shared/models.py` — Pydantic models for WebhookSource

- [ ] **Step 1: Add Pydantic fields**

In `api/shared/models.py` find the `WebhookSourceCreate` / `WebhookSourceUpdate` / `WebhookSourceResponse` (or equivalents) and add:

```python
rate_limit_per_minute: int | None = 60
rate_limit_window_seconds: int = 60
rate_limit_enabled: bool = True
```

- [ ] **Step 2: Regenerate types**

Run: `cd client && npm run generate:types && cd ..`

- [ ] **Step 3: Add UI fields**

In the webhook source edit form, add three inputs:
- "Rate limit (events per window)" — number, allow null/empty (= disabled by null).
- "Window (seconds)" — number, default 60.
- "Enabled" — toggle/checkbox, default true.

Group them in a "Rate limiting" section. Add a help text near the Enabled toggle: "Disable to bypass rate limiting for this source."

- [ ] **Step 4: Run client checks**

```bash
cd client && npm run tsc && npm run lint && cd ..
```

Expected: 0 errors.

- [ ] **Step 5: Commit**

```bash
git add api/shared/models.py client/
git commit -m "feat(client): expose webhook rate-limit fields on admin form"
```

---

## Final integration checks

- [ ] **Step 1: Backend type-check + lint**

```bash
cd api && pyright && ruff check . && cd ..
```

Expected: 0 errors.

- [ ] **Step 2: Frontend type-check + lint**

```bash
cd client && npm run tsc && npm run lint && cd ..
```

- [ ] **Step 3: Full backend test suite**

```bash
./test.sh stack up
./test.sh all
```

Expected: all pass.

- [ ] **Step 4: Manual smoke**

Open the admin UI at http://localhost:3000:
- Webhook source → confirm 3 rate-limit fields render and persist.
- Schedule source → confirm overlap_policy field renders and persists.
- POST a webhook 100x quickly to a test source → confirm 429s.

- [ ] **Step 5: Final commit / PR**

If components are merged separately, open three PRs (one per component, in spec migration order). Otherwise one PR with the three components in separate commits.
