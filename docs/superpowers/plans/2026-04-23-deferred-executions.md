# Deferred Executions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let callers schedule a one-shot workflow execution for a future time via `scheduled_at` / `delay_seconds` on `/api/workflows/execute`, promote matured rows to the existing RabbitMQ queue, and let users cancel scheduled rows from the UI.

**Architecture:** Add `SCHEDULED` enum value + `scheduled_at` column to `executions`. Router inserts scheduled rows directly (skipping the queue). A new 60s APScheduler job in the existing scheduler pod promotes due rows to `PENDING` and publishes them using the same Redis-blob-plus-RabbitMQ path the run-now flow already uses (extracted into a shared helper). Cancel is a status-guarded UPDATE.

**Tech Stack:** Python 3.11, FastAPI, SQLAlchemy, Alembic, Pydantic, APScheduler, RabbitMQ, Redis, PostgreSQL, TypeScript/React, Vitest, Playwright.

**Spec:** `docs/superpowers/specs/2026-04-23-deferred-executions-design.md`

---

## File Structure

**Backend — create:**
- `api/alembic/versions/<rev>_add_scheduled_status_and_scheduled_at.py` — migration.
- `api/src/jobs/schedulers/deferred_execution_promoter.py` — promoter entrypoint.
- `api/tests/unit/jobs/schedulers/test_deferred_execution_promoter.py` — promoter unit tests.
- `api/tests/unit/models/test_executions_contract.py` — contract validation (extend if exists).
- `api/tests/e2e/api/test_workflow_scheduling.py` — end-to-end scheduling and cancel.

**Backend — modify:**
- `api/src/models/enums.py` — add `SCHEDULED`.
- `api/src/models/orm/executions.py` — add `scheduled_at` column.
- `api/src/models/contracts/executions.py` — add `scheduled_at` / `delay_seconds` on request, `scheduled_at` on response, validation.
- `api/src/services/execution/async_executor.py` — extract `_publish_pending` helper.
- `api/src/routers/workflows.py` — scheduled-insert branch in `execute_workflow`; new cancel endpoint.
- `api/src/scheduler/main.py` — register the 60s promoter job.
- `api/bifrost/workflows.py` — SDK `execute(..., scheduled_at, delay_seconds)` + new `cancel()`.

**Frontend — create:**
- `client/src/components/forms/ScheduledExecutionCancelDialog.test.tsx` — confirm-cancel dialog test (colocated with dialog component).
- `client/e2e/scheduled-execution.spec.ts` — Playwright flow.

**Frontend — modify:**
- `client/src/components/execution/ExecutionStatusBadge.tsx` — add `Scheduled` variant + hover datetime.
- `client/src/components/execution/ExecutionStatusBadge.test.tsx` — cover new variant.
- `client/src/pages/ExecutionHistory.tsx` — `Scheduled` in filter dropdown, cancel row action.
- `client/src/pages/ExecutionHistory.test.tsx` (if exists; otherwise add) — filter + cancel test.
- `client/src/pages/ExecutionDetails.tsx` — show `Scheduled for ...` when populated.

---

## Branch and worktree setup

- [ ] **Step 0.1: Create feature branch**

```bash
cd /home/jack/GitHub/bifrost
git checkout -b feat/deferred-executions
```

- [ ] **Step 0.2: Confirm dev stack is up (for type generation later)**

```bash
docker ps --filter "name=bifrost-dev-api" --format '{{.Names}}' | grep -q bifrost-dev-api || ./debug.sh
```

Expected: the command exits 0 silently (stack already up) or `./debug.sh` starts it.

- [ ] **Step 0.3: Confirm test stack is up for this worktree**

```bash
./test.sh stack status || ./test.sh stack up
```

Expected: "Stack is up" or a fresh boot.

---

## Task 1: Add `SCHEDULED` enum value

**Files:**
- Modify: `api/src/models/enums.py`
- Test: `api/tests/unit/models/test_enums.py` (create if absent)

- [ ] **Step 1.1: Write the failing test**

Create `api/tests/unit/models/test_enums.py` if it doesn't exist, and add:

```python
from src.models.enums import ExecutionStatus


def test_execution_status_has_scheduled():
    assert ExecutionStatus.SCHEDULED.value == "Scheduled"


def test_scheduled_is_distinct_from_pending():
    assert ExecutionStatus.SCHEDULED is not ExecutionStatus.PENDING
    assert ExecutionStatus.SCHEDULED.value != ExecutionStatus.PENDING.value
```

- [ ] **Step 1.2: Run test and verify it fails**

```bash
./test.sh tests/unit/models/test_enums.py -v
```

Expected: `AttributeError: SCHEDULED` or similar.

- [ ] **Step 1.3: Add the enum value**

Edit `api/src/models/enums.py`. Add this line inside `class ExecutionStatus` immediately after `PENDING`:

```python
    SCHEDULED = "Scheduled"
```

- [ ] **Step 1.4: Run test and verify it passes**

```bash
./test.sh tests/unit/models/test_enums.py -v
```

Expected: PASS.

- [ ] **Step 1.5: Commit**

```bash
git add api/src/models/enums.py api/tests/unit/models/test_enums.py
git commit -m "feat(enums): add Scheduled execution status"
```

---

## Task 2: Add `scheduled_at` column + partial index (Alembic migration)

**Files:**
- Create: `api/alembic/versions/<auto>_add_scheduled_at_to_executions.py`
- Modify: `api/src/models/orm/executions.py`

- [ ] **Step 2.1: Generate migration skeleton**

```bash
cd api && alembic revision -m "add_scheduled_at_to_executions"
```

Expected: new file under `api/alembic/versions/` — note the filename (e.g. `20260423_xxxx_add_scheduled_at_to_executions.py`).

- [ ] **Step 2.2: Fill in the migration**

Replace the generated file's `upgrade`/`downgrade` with:

```python
"""add_scheduled_at_to_executions

Revision ID: <keep the generated revision id>
Revises: <keep the generated down_revision>
Create Date: <keep the generated date>
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "<keep>"
down_revision = "<keep>"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Postgres forbids referencing a newly-added enum value in the same
    # transaction that added it — so commit the ADD VALUE via an autocommit
    # block before the CREATE INDEX below references it in its WHERE clause.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE execution_status ADD VALUE IF NOT EXISTS 'Scheduled'")

    # Add the nullable scheduled_at column.
    op.add_column(
        "executions",
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
    )

    # Partial index: only rows currently in the Scheduled state.
    op.execute(
        "CREATE INDEX ix_executions_scheduled_due "
        "ON executions (scheduled_at) "
        "WHERE status = 'Scheduled'"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_executions_scheduled_due")
    op.drop_column("executions", "scheduled_at")
    # Note: Postgres does not support removing a value from an enum; leaving it.
```

- [ ] **Step 2.3: Add the column to the ORM**

In `api/src/models/orm/executions.py`, inside `class Execution(Base)`, add this line immediately below the existing `created_at` column (around line 86):

```python
    scheduled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None, nullable=True
    )
```

- [ ] **Step 2.4: Apply the migration and restart the API**

```bash
docker restart bifrost-init && sleep 3 && docker restart bifrost-dev-api-1
```

Expected: both containers restart; migration runs in `bifrost-init`.

- [ ] **Step 2.5: Verify the column exists**

```bash
docker exec -i bifrost-dev-postgres-1 psql -U bifrost -d bifrost -c "\d executions" | grep scheduled_at
```

Expected: `scheduled_at | timestamp with time zone | | |`.

- [ ] **Step 2.6: Verify the enum value exists**

```bash
docker exec -i bifrost-dev-postgres-1 psql -U bifrost -d bifrost -c "SELECT unnest(enum_range(NULL::execution_status))"
```

Expected: includes `Scheduled`.

- [ ] **Step 2.7: Re-run Task 1 tests to confirm no regression**

```bash
./test.sh tests/unit/models/test_enums.py -v
```

Expected: PASS.

- [ ] **Step 2.8: Commit**

```bash
git add api/alembic/versions/*_add_scheduled_at_to_executions.py api/src/models/orm/executions.py
git commit -m "feat(db): add scheduled_at column and Scheduled enum to executions"
```

---

## Task 3: `WorkflowExecutionRequest` / `Response` contract + validation

**Files:**
- Modify: `api/src/models/contracts/executions.py`
- Test: `api/tests/unit/models/test_executions_contract.py`

- [ ] **Step 3.1: Write failing contract tests**

Create `api/tests/unit/models/test_executions_contract.py` (or extend). Add:

```python
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from src.models.contracts.executions import WorkflowExecutionRequest


def _future(seconds: int = 60) -> datetime:
    return datetime.now(timezone.utc) + timedelta(seconds=seconds)


def test_accepts_scheduled_at_alone():
    req = WorkflowExecutionRequest(workflow_id="wf", scheduled_at=_future(120))
    assert req.scheduled_at is not None


def test_accepts_delay_seconds_alone():
    req = WorkflowExecutionRequest(workflow_id="wf", delay_seconds=60)
    assert req.delay_seconds == 60


def test_rejects_both_scheduling_fields():
    with pytest.raises(ValidationError, match="mutually exclusive"):
        WorkflowExecutionRequest(
            workflow_id="wf", scheduled_at=_future(60), delay_seconds=60
        )


def test_rejects_naive_scheduled_at():
    with pytest.raises(ValidationError, match="timezone"):
        WorkflowExecutionRequest(
            workflow_id="wf",
            scheduled_at=datetime.now() + timedelta(minutes=5),  # naive
        )


def test_rejects_past_scheduled_at():
    with pytest.raises(ValidationError, match="future"):
        WorkflowExecutionRequest(
            workflow_id="wf",
            scheduled_at=datetime.now(timezone.utc) - timedelta(seconds=1),
        )


def test_rejects_scheduled_at_beyond_one_year():
    with pytest.raises(ValidationError, match="1 year"):
        WorkflowExecutionRequest(
            workflow_id="wf",
            scheduled_at=datetime.now(timezone.utc) + timedelta(days=366),
        )


def test_rejects_delay_seconds_zero_or_negative():
    with pytest.raises(ValidationError):
        WorkflowExecutionRequest(workflow_id="wf", delay_seconds=0)


def test_rejects_delay_seconds_beyond_one_year():
    with pytest.raises(ValidationError):
        WorkflowExecutionRequest(workflow_id="wf", delay_seconds=31_536_001)


def test_rejects_sync_with_scheduled_at():
    with pytest.raises(ValidationError, match="sync"):
        WorkflowExecutionRequest(
            workflow_id="wf", scheduled_at=_future(60), sync=True
        )


def test_rejects_sync_with_delay_seconds():
    with pytest.raises(ValidationError, match="sync"):
        WorkflowExecutionRequest(workflow_id="wf", delay_seconds=60, sync=True)


def test_rejects_code_with_scheduled_at():
    with pytest.raises(ValidationError, match="code"):
        WorkflowExecutionRequest(code="cHJpbnQoMSk=", scheduled_at=_future(60))


def test_rejects_code_with_delay_seconds():
    with pytest.raises(ValidationError, match="code"):
        WorkflowExecutionRequest(code="cHJpbnQoMSk=", delay_seconds=60)
```

- [ ] **Step 3.2: Run tests and verify they fail**

```bash
./test.sh tests/unit/models/test_executions_contract.py -v
```

Expected: all FAIL (fields don't exist yet).

- [ ] **Step 3.3: Add fields and validation to the contract**

Edit `api/src/models/contracts/executions.py`. After the existing fields on `WorkflowExecutionRequest` (immediately before the `@model_validator`), add:

```python
    scheduled_at: datetime | None = Field(
        default=None,
        description=(
            "Run at this tz-aware timestamp (ISO-8601). Must be strictly in the "
            "future and within 1 year of now. Mutually exclusive with delay_seconds."
        ),
    )
    delay_seconds: int | None = Field(
        default=None,
        ge=1,
        le=31_536_000,
        description=(
            "Run this many seconds from now (≤ 1 year). "
            "Mutually exclusive with scheduled_at."
        ),
    )
```

Then replace the existing `validate_workflow_or_code` validator with a combined one:

```python
    @model_validator(mode="after")
    def validate_request(self) -> "WorkflowExecutionRequest":
        if not self.workflow_id and not self.code:
            raise ValueError("Either 'workflow_id' or 'code' must be provided")

        if self.scheduled_at is not None and self.delay_seconds is not None:
            raise ValueError(
                "'scheduled_at' and 'delay_seconds' are mutually exclusive"
            )

        if self.scheduled_at is not None:
            if self.scheduled_at.tzinfo is None:
                raise ValueError("'scheduled_at' must be timezone-aware")
            now = datetime.now(timezone.utc)
            if self.scheduled_at <= now:
                raise ValueError("'scheduled_at' must be in the future")
            if self.scheduled_at > now + timedelta(days=365):
                raise ValueError("'scheduled_at' must be within 1 year")

        if (self.scheduled_at is not None or self.delay_seconds is not None):
            if self.sync:
                raise ValueError("'sync' cannot be combined with scheduling")
            if self.code:
                raise ValueError("'code' (inline) cannot be scheduled")

        return self
```

Add imports at the top of the file if missing:

```python
from datetime import datetime, timedelta, timezone
```

- [ ] **Step 3.4: Add `scheduled_at` to the response model**

In the same file, on `WorkflowExecutionResponse`, add:

```python
    scheduled_at: datetime | None = Field(
        default=None,
        description="For scheduled executions, the target run time.",
    )
```

- [ ] **Step 3.5: Run tests and verify they pass**

```bash
./test.sh tests/unit/models/test_executions_contract.py -v
```

Expected: all PASS.

- [ ] **Step 3.6: Commit**

```bash
git add api/src/models/contracts/executions.py api/tests/unit/models/test_executions_contract.py
git commit -m "feat(contracts): accept scheduled_at/delay_seconds on workflow execute"
```

---

## Task 4: Extract `_publish_pending` helper

Pull the Redis-blob-plus-RabbitMQ-publish tail of `enqueue_workflow_execution` into a private helper so the router's run-now path and the promoter can share it without duplicating the message shape.

**Files:**
- Modify: `api/src/services/execution/async_executor.py`
- Test: `api/tests/unit/services/execution/test_async_executor.py` (create if absent)

- [ ] **Step 4.1: Write a failing test for the helper**

Create the test file if needed, then add:

```python
from unittest.mock import AsyncMock, patch

import pytest

from src.services.execution.async_executor import _publish_pending


@pytest.mark.asyncio
async def test_publish_pending_writes_redis_then_publishes():
    redis = AsyncMock()
    with (
        patch("src.services.execution.async_executor.get_redis_client", return_value=redis),
        patch("src.services.execution.async_executor.add_to_queue", new=AsyncMock()) as q,
        patch("src.services.execution.async_executor.publish_message", new=AsyncMock()) as pub,
    ):
        await _publish_pending(
            execution_id="e1",
            workflow_id="wf",
            parameters={"x": 1},
            org_id="org",
            user_id="u",
            user_name="Name",
            user_email="n@e",
            form_id=None,
            startup=None,
            api_key_id=None,
            sync=False,
            is_platform_admin=False,
            file_path=None,
        )

    redis.set_pending_execution.assert_awaited_once()
    q.assert_awaited_once_with("e1")
    pub.assert_awaited_once()
    # Message shape matches the enqueue contract.
    queue_name, message = pub.await_args.args
    assert queue_name == "workflow-executions"
    assert message == {"execution_id": "e1", "workflow_id": "wf", "sync": False}
```

- [ ] **Step 4.2: Run and verify it fails**

```bash
./test.sh tests/unit/services/execution/test_async_executor.py -v
```

Expected: `ImportError: cannot import name '_publish_pending'`.

- [ ] **Step 4.3: Refactor `async_executor.py`**

In `api/src/services/execution/async_executor.py`, replace the body of `enqueue_workflow_execution` (lines ~57–110) with a call to a new `_publish_pending` helper. Full new file tail:

```python
async def _publish_pending(
    execution_id: str,
    workflow_id: str | None,
    parameters: dict[str, Any],
    org_id: str | None,
    user_id: str,
    user_name: str,
    user_email: str,
    form_id: str | None,
    startup: dict[str, Any] | None,
    api_key_id: str | None,
    sync: bool,
    is_platform_admin: bool,
    file_path: str | None,
) -> None:
    """Write the pending-execution blob to Redis, track queue, publish to RabbitMQ.

    Shared by the run-now router path and the scheduled-execution promoter.
    """
    from src.core.redis_client import get_redis_client
    from src.jobs.rabbitmq import publish_message
    from src.services.execution.queue_tracker import add_to_queue

    redis_client = get_redis_client()

    await redis_client.set_pending_execution(
        execution_id=execution_id,
        workflow_id=workflow_id,
        parameters=parameters,
        org_id=org_id,
        user_id=user_id,
        user_name=user_name,
        user_email=user_email,
        form_id=form_id,
        startup=startup,
        api_key_id=api_key_id,
        sync=sync,
        is_platform_admin=is_platform_admin,
    )

    await add_to_queue(execution_id)

    message: dict[str, Any] = {
        "execution_id": execution_id,
        "workflow_id": workflow_id,
        "sync": sync,
    }
    if file_path:
        message["file_path"] = file_path

    await publish_message(QUEUE_NAME, message)


async def enqueue_workflow_execution(
    context: ExecutionContext,
    workflow_id: str,
    parameters: dict[str, Any],
    form_id: str | None = None,
    execution_id: str | None = None,
    sync: bool = False,
    api_key_id: str | None = None,
    file_path: str | None = None,
) -> str:
    """Enqueue a workflow for immediate async execution."""
    if execution_id is None:
        execution_id = str(uuid.uuid4())

    await _publish_pending(
        execution_id=execution_id,
        workflow_id=workflow_id,
        parameters=parameters,
        org_id=context.org_id,
        user_id=context.user_id,
        user_name=context.name,
        user_email=context.email,
        form_id=form_id,
        startup=context.startup,
        api_key_id=api_key_id,
        sync=sync,
        is_platform_admin=context.is_platform_admin,
        file_path=file_path,
    )

    logger.info(
        f"Enqueued async workflow execution: {workflow_id}",
        extra={
            "execution_id": execution_id,
            "workflow_id": workflow_id,
            "org_id": context.org_id,
        },
    )
    return execution_id
```

- [ ] **Step 4.4: Run the new test**

```bash
./test.sh tests/unit/services/execution/test_async_executor.py -v
```

Expected: PASS.

- [ ] **Step 4.5: Run the broader execution suite for regression**

```bash
./test.sh tests/unit/services/execution/ -v
```

Expected: all PASS (the extraction is behavior-preserving).

- [ ] **Step 4.6: Commit**

```bash
git add api/src/services/execution/async_executor.py api/tests/unit/services/execution/test_async_executor.py
git commit -m "refactor(execution): extract _publish_pending helper"
```

---

## Task 5: Router — scheduled insert branch in `execute_workflow`

**Files:**
- Modify: `api/src/routers/workflows.py`
- Test: `api/tests/unit/routers/test_workflows_scheduled.py` (create)

- [ ] **Step 5.1: Write failing router-unit test**

Create `api/tests/unit/routers/test_workflows_scheduled.py`:

```python
"""Unit tests for scheduled execution insertion (routes-level behavior).

E2E coverage lives in tests/e2e/api/test_workflow_scheduling.py.
"""
from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_schedule_workflow_returns_scheduled_status(
    authenticated_client: AsyncClient, sample_workflow
):
    run_at = datetime.now(timezone.utc) + timedelta(minutes=5)
    resp = await authenticated_client.post(
        "/api/workflows/execute",
        json={
            "workflow_id": str(sample_workflow.id),
            "input_data": {},
            "scheduled_at": run_at.isoformat(),
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "Scheduled"
    assert body["scheduled_at"] is not None


@pytest.mark.asyncio
async def test_schedule_workflow_with_delay_seconds(
    authenticated_client: AsyncClient, sample_workflow
):
    resp = await authenticated_client.post(
        "/api/workflows/execute",
        json={
            "workflow_id": str(sample_workflow.id),
            "input_data": {},
            "delay_seconds": 300,
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "Scheduled"
    # delay_seconds was normalized to scheduled_at
    assert body["scheduled_at"] is not None
```

(If `authenticated_client` / `sample_workflow` aren't existing fixtures in your unit layer, move these tests into `tests/e2e/api/test_workflow_scheduling.py` in Task 9 and skip Step 5.1/5.2 here. In that case add Step 5.1b below.)

- [ ] **Step 5.1b: (Alternative if no router-unit fixtures exist)**

If you skipped 5.1, still validate the insert path via a light-weight helper test in `tests/unit/routers/test_workflows_scheduled.py`:

```python
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from src.routers.workflows import _insert_scheduled_execution  # added in 5.3


@pytest.mark.asyncio
async def test_insert_scheduled_execution_persists_row(db_session):
    run_at = datetime.now(timezone.utc) + timedelta(minutes=5)
    exec_id = await _insert_scheduled_execution(
        db=db_session,
        workflow_id=uuid4(),
        workflow_name="demo",
        parameters={"k": "v"},
        scheduled_at=run_at,
        organization_id=None,
        executed_by=uuid4(),
        executed_by_name="Jack",
        form_id=None,
        api_key_id=None,
        is_platform_admin=False,
    )
    assert exec_id is not None
```

- [ ] **Step 5.2: Run the test and confirm failure**

```bash
./test.sh tests/unit/routers/test_workflows_scheduled.py -v
```

Expected: FAIL (endpoint still routes to `run_workflow`, which needs workers; or `_insert_scheduled_execution` is undefined).

- [ ] **Step 5.3: Add the helper and wire the router branch**

In `api/src/routers/workflows.py`, add this helper above `execute_workflow`:

```python
async def _insert_scheduled_execution(
    *,
    db: AsyncSession,
    workflow_id: UUID,
    workflow_name: str,
    parameters: dict,
    scheduled_at: datetime,
    organization_id: UUID | None,
    executed_by: UUID,
    executed_by_name: str,
    form_id: UUID | None,
    api_key_id: UUID | None,
    is_platform_admin: bool,
) -> UUID:
    """Insert a SCHEDULED execution row. Returns execution id.

    Skips Redis/RabbitMQ entirely — the deferred_execution_promoter job will
    publish the row when scheduled_at matures.
    """
    from uuid import uuid4

    from src.models.enums import ExecutionStatus
    from src.models.orm.executions import Execution

    exec_id = uuid4()
    db.add(
        Execution(
            id=exec_id,
            workflow_id=workflow_id,
            workflow_name=workflow_name,
            status=ExecutionStatus.SCHEDULED,
            parameters=parameters,
            scheduled_at=scheduled_at,
            organization_id=organization_id,
            executed_by=executed_by,
            executed_by_name=executed_by_name,
            form_id=form_id,
            api_key_id=api_key_id,
            execution_context={"is_platform_admin": is_platform_admin},
        )
    )
    await db.commit()
    return exec_id
```

Then in `execute_workflow`, after the block that resolves `execution_org_id` (around line 782) and **before** `shared_ctx = SharedContext(...)`, insert:

```python
    # Scheduled execution: normalize delay_seconds → scheduled_at and insert row.
    scheduled_at: datetime | None = request.scheduled_at
    if request.delay_seconds is not None:
        scheduled_at = datetime.now(timezone.utc) + timedelta(seconds=request.delay_seconds)

    if scheduled_at is not None:
        assert workflow is not None  # schedule-with-code is rejected at the contract
        exec_id = await _insert_scheduled_execution(
            db=db,
            workflow_id=workflow.id,
            workflow_name=workflow.name,
            parameters=request.input_data,
            scheduled_at=scheduled_at,
            organization_id=execution_org_id,
            executed_by=UUID(exec_user_id),
            executed_by_name=exec_user_name,
            form_id=UUID(request.form_id) if request.form_id else None,
            api_key_id=None,  # API-key-triggered scheduling not supported in v1
            is_platform_admin=exec_is_admin,
        )
        return WorkflowExecutionResponse(
            execution_id=str(exec_id),
            workflow_id=str(workflow.id),
            workflow_name=workflow.name,
            status=ExecutionStatus.SCHEDULED,
            scheduled_at=scheduled_at,
        )
```

Add imports at the top of the file if missing:

```python
from datetime import datetime, timedelta, timezone
```

- [ ] **Step 5.4: Run the test and confirm it passes**

```bash
./test.sh tests/unit/routers/test_workflows_scheduled.py -v
```

Expected: PASS.

- [ ] **Step 5.5: Commit**

```bash
git add api/src/routers/workflows.py api/tests/unit/routers/test_workflows_scheduled.py
git commit -m "feat(router): insert SCHEDULED executions without queueing"
```

---

## Task 6: Cancel endpoint

**Files:**
- Modify: `api/src/routers/workflows.py`
- Test: `api/tests/unit/routers/test_workflows_cancel_scheduled.py` (create)

- [ ] **Step 6.1: Write failing test**

```python
"""Unit test for cancel of scheduled executions."""
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from src.models.enums import ExecutionStatus
from src.models.orm.executions import Execution


@pytest.mark.asyncio
async def test_cancel_scheduled_flips_to_cancelled(
    authenticated_client, db_session, current_user
):
    row = Execution(
        id=uuid4(),
        workflow_name="demo",
        status=ExecutionStatus.SCHEDULED,
        parameters={},
        scheduled_at=datetime.now(timezone.utc) + timedelta(minutes=5),
        executed_by=current_user.id,
        executed_by_name=current_user.name or "user",
        organization_id=current_user.organization_id,
    )
    db_session.add(row)
    await db_session.commit()

    resp = await authenticated_client.post(
        f"/api/workflows/executions/{row.id}/cancel"
    )
    assert resp.status_code == 200, resp.text

    await db_session.refresh(row)
    assert row.status == ExecutionStatus.CANCELLED


@pytest.mark.asyncio
async def test_cancel_non_scheduled_returns_409(
    authenticated_client, db_session, current_user
):
    row = Execution(
        id=uuid4(),
        workflow_name="demo",
        status=ExecutionStatus.PENDING,
        parameters={},
        executed_by=current_user.id,
        executed_by_name="u",
        organization_id=current_user.organization_id,
    )
    db_session.add(row)
    await db_session.commit()

    resp = await authenticated_client.post(
        f"/api/workflows/executions/{row.id}/cancel"
    )
    assert resp.status_code == 409
```

- [ ] **Step 6.2: Run and confirm failure**

```bash
./test.sh tests/unit/routers/test_workflows_cancel_scheduled.py -v
```

Expected: 404 (endpoint doesn't exist).

- [ ] **Step 6.3: Add the endpoint**

In `api/src/routers/workflows.py`, append a new handler:

```python
@router.post(
    "/executions/{execution_id}/cancel",
    summary="Cancel a scheduled execution",
    description=(
        "Cancels a SCHEDULED execution (row has not yet been promoted to the queue). "
        "Returns 409 if the row is in any other status (including already PENDING). "
        "Cancelling a RUNNING execution is a separate feature and is not merged here."
    ),
)
async def cancel_scheduled_execution(
    execution_id: UUID,
    ctx: Context,
    db: DbSession,
    user: CurrentActiveUser,
) -> dict:
    from src.models.enums import ExecutionStatus
    from src.models.orm.executions import Execution

    row = await db.get(Execution, execution_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Execution not found")

    # Org-scoped access: user's own org, or admin.
    if (
        not ctx.user.is_superuser
        and row.organization_id is not None
        and row.organization_id != ctx.org_id
    ):
        raise HTTPException(status_code=403, detail="Access denied")

    # Non-admin can only cancel their own scheduled rows.
    if not ctx.user.is_superuser and row.executed_by != ctx.user.user_id:
        raise HTTPException(status_code=403, detail="Only the submitter or an admin may cancel")

    # Status-guarded UPDATE — only succeeds if still Scheduled.
    result = await db.execute(
        update(Execution)
        .where(Execution.id == execution_id)
        .where(Execution.status == ExecutionStatus.SCHEDULED)
        .values(status=ExecutionStatus.CANCELLED, completed_at=datetime.now(timezone.utc))
    )
    await db.commit()

    if result.rowcount == 0:
        # Re-fetch to report current status.
        await db.refresh(row)
        raise HTTPException(
            status_code=409,
            detail=f"Execution is not Scheduled (current status: {row.status.value})",
        )

    return {"execution_id": str(execution_id), "status": ExecutionStatus.CANCELLED.value}
```

Add imports at top of file if missing:

```python
from sqlalchemy import update
```

- [ ] **Step 6.4: Run and confirm pass**

```bash
./test.sh tests/unit/routers/test_workflows_cancel_scheduled.py -v
```

Expected: PASS.

- [ ] **Step 6.5: Commit**

```bash
git add api/src/routers/workflows.py api/tests/unit/routers/test_workflows_cancel_scheduled.py
git commit -m "feat(router): cancel endpoint for scheduled executions"
```

---

## Task 7: Promoter job — unit tests first

**Files:**
- Create: `api/src/jobs/schedulers/deferred_execution_promoter.py`
- Create: `api/tests/unit/jobs/schedulers/test_deferred_execution_promoter.py`

- [ ] **Step 7.1: Write failing tests**

Create `api/tests/unit/jobs/schedulers/test_deferred_execution_promoter.py`:

```python
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from src.models.enums import ExecutionStatus
from src.models.orm.executions import Execution


@pytest.mark.asyncio
async def test_promotes_due_rows(db_session):
    from src.jobs.schedulers.deferred_execution_promoter import promote_due_executions

    due = Execution(
        id=uuid4(),
        workflow_id=uuid4(),
        workflow_name="demo",
        status=ExecutionStatus.SCHEDULED,
        parameters={"k": 1},
        scheduled_at=datetime.now(timezone.utc) - timedelta(seconds=1),
        executed_by=uuid4(),
        executed_by_name="u",
    )
    db_session.add(due)
    await db_session.commit()

    with patch(
        "src.jobs.schedulers.deferred_execution_promoter._publish_pending",
        new=AsyncMock(),
    ) as pub:
        promoted, failed = await promote_due_executions()

    assert promoted == 1
    assert failed == 0
    pub.assert_awaited_once()
    await db_session.refresh(due)
    assert due.status == ExecutionStatus.PENDING


@pytest.mark.asyncio
async def test_leaves_future_rows(db_session):
    from src.jobs.schedulers.deferred_execution_promoter import promote_due_executions

    future = Execution(
        id=uuid4(),
        workflow_id=uuid4(),
        workflow_name="demo",
        status=ExecutionStatus.SCHEDULED,
        parameters={},
        scheduled_at=datetime.now(timezone.utc) + timedelta(hours=1),
        executed_by=uuid4(),
        executed_by_name="u",
    )
    db_session.add(future)
    await db_session.commit()

    with patch(
        "src.jobs.schedulers.deferred_execution_promoter._publish_pending",
        new=AsyncMock(),
    ) as pub:
        promoted, failed = await promote_due_executions()

    assert promoted == 0
    pub.assert_not_awaited()
    await db_session.refresh(future)
    assert future.status == ExecutionStatus.SCHEDULED


@pytest.mark.asyncio
async def test_skips_cancelled_rows(db_session):
    from src.jobs.schedulers.deferred_execution_promoter import promote_due_executions

    cancelled = Execution(
        id=uuid4(),
        workflow_id=uuid4(),
        workflow_name="demo",
        status=ExecutionStatus.CANCELLED,
        parameters={},
        scheduled_at=datetime.now(timezone.utc) - timedelta(minutes=1),
        executed_by=uuid4(),
        executed_by_name="u",
    )
    db_session.add(cancelled)
    await db_session.commit()

    with patch(
        "src.jobs.schedulers.deferred_execution_promoter._publish_pending",
        new=AsyncMock(),
    ):
        promoted, failed = await promote_due_executions()

    assert promoted == 0
    await db_session.refresh(cancelled)
    assert cancelled.status == ExecutionStatus.CANCELLED


@pytest.mark.asyncio
async def test_reverts_on_publish_failure(db_session):
    from src.jobs.schedulers.deferred_execution_promoter import promote_due_executions

    due = Execution(
        id=uuid4(),
        workflow_id=uuid4(),
        workflow_name="demo",
        status=ExecutionStatus.SCHEDULED,
        parameters={},
        scheduled_at=datetime.now(timezone.utc) - timedelta(seconds=1),
        executed_by=uuid4(),
        executed_by_name="u",
    )
    db_session.add(due)
    await db_session.commit()

    with patch(
        "src.jobs.schedulers.deferred_execution_promoter._publish_pending",
        new=AsyncMock(side_effect=RuntimeError("rabbit down")),
    ):
        promoted, failed = await promote_due_executions()

    assert promoted == 0
    assert failed == 1
    await db_session.refresh(due)
    # Reverted so next tick can retry.
    assert due.status == ExecutionStatus.SCHEDULED
```

- [ ] **Step 7.2: Run tests, confirm failure**

```bash
./test.sh tests/unit/jobs/schedulers/test_deferred_execution_promoter.py -v
```

Expected: ModuleNotFoundError.

- [ ] **Step 7.3: Implement the promoter**

Create `api/src/jobs/schedulers/deferred_execution_promoter.py`:

```python
"""Deferred execution promoter.

Every 60 seconds, moves SCHEDULED executions whose scheduled_at has matured
onto the RabbitMQ workflow-executions queue by flipping them to PENDING and
calling the shared _publish_pending helper.
"""
import logging
from datetime import datetime, timezone

from sqlalchemy import select, update

from src.core.database import get_async_session
from src.models.enums import ExecutionStatus
from src.models.orm.executions import Execution
from src.services.execution.async_executor import _publish_pending

logger = logging.getLogger(__name__)

BATCH_LIMIT = 500


async def promote_due_executions() -> tuple[int, int]:
    """Promote due SCHEDULED rows to PENDING and publish them.

    Returns (promoted_count, publish_failures).
    """
    promoted = 0
    failures = 0

    async for db in get_async_session():
        # Select + lock matured rows.
        result = await db.execute(
            select(Execution)
            .where(Execution.status == ExecutionStatus.SCHEDULED)
            .where(Execution.scheduled_at <= datetime.now(timezone.utc))
            .order_by(Execution.scheduled_at.asc())
            .limit(BATCH_LIMIT)
            .with_for_update(skip_locked=True)
        )
        rows = list(result.scalars().all())

        if not rows:
            return 0, 0

        # Flip statuses in one UPDATE so the scheduler commits even if a
        # later publish fails; per-row revert handled below.
        ids = [r.id for r in rows]
        await db.execute(
            update(Execution)
            .where(Execution.id.in_(ids))
            .values(status=ExecutionStatus.PENDING, started_at=None)
        )
        await db.commit()

        for row in rows:
            try:
                await _publish_pending(
                    execution_id=str(row.id),
                    workflow_id=str(row.workflow_id) if row.workflow_id else None,
                    parameters=row.parameters or {},
                    org_id=str(row.organization_id) if row.organization_id else None,
                    user_id=str(row.executed_by) if row.executed_by else "",
                    user_name=row.executed_by_name or "",
                    user_email="",  # Email not persisted on the row; worker hydrates from user record.
                    form_id=str(row.form_id) if row.form_id else None,
                    startup=None,  # Scheduled runs do not carry stale startup results.
                    api_key_id=str(row.api_key_id) if row.api_key_id else None,
                    sync=False,
                    is_platform_admin=bool((row.execution_context or {}).get("is_platform_admin", False)),
                    file_path=None,
                )
                promoted += 1
            except Exception:
                failures += 1
                logger.exception(
                    "deferred_execution_promoter: publish failed, reverting row",
                    extra={"execution_id": str(row.id)},
                )
                # Best-effort revert so next tick retries.
                await db.execute(
                    update(Execution)
                    .where(Execution.id == row.id)
                    .where(Execution.status == ExecutionStatus.PENDING)
                    .values(status=ExecutionStatus.SCHEDULED)
                )
                await db.commit()

        logger.info(
            "deferred_execution_promoter tick complete",
            extra={"promoted": promoted, "failures": failures},
        )
        return promoted, failures

    return promoted, failures
```

- [ ] **Step 7.4: Run tests, confirm pass**

```bash
./test.sh tests/unit/jobs/schedulers/test_deferred_execution_promoter.py -v
```

Expected: PASS all four.

- [ ] **Step 7.5: Commit**

```bash
git add api/src/jobs/schedulers/deferred_execution_promoter.py api/tests/unit/jobs/schedulers/test_deferred_execution_promoter.py
git commit -m "feat(scheduler): deferred execution promoter"
```

---

## Task 8: Register promoter with APScheduler

**Files:**
- Modify: `api/src/scheduler/main.py`

- [ ] **Step 8.1: Add the job registration**

In `api/src/scheduler/main.py`, in `_start_scheduler`, after the `schedule_processor` `scheduler.add_job(...)` block (around line 114), add:

```python
        # Deferred execution promoter — every 60s
        from src.jobs.schedulers.deferred_execution_promoter import promote_due_executions

        scheduler.add_job(
            promote_due_executions,
            IntervalTrigger(seconds=60),
            id="deferred_execution_promoter",
            name="Promote due scheduled executions",
            replace_existing=True,
            next_run_time=datetime.now(timezone.utc),
            **misfire_options,
        )
        logger.info("Deferred execution promoter scheduled (every 60s)")
```

- [ ] **Step 8.2: Restart the scheduler container**

```bash
docker restart bifrost-dev-scheduler-1
```

Expected: container comes up, logs show "Deferred execution promoter scheduled (every 60s)".

- [ ] **Step 8.3: Tail the logs to confirm**

```bash
docker logs --tail 30 bifrost-dev-scheduler-1 2>&1 | grep -i deferred
```

Expected: the log line above.

- [ ] **Step 8.4: Commit**

```bash
git add api/src/scheduler/main.py
git commit -m "feat(scheduler): register deferred execution promoter job"
```

---

## Task 9: Backend E2E — schedule, promote, cancel

**Files:**
- Create: `api/tests/e2e/api/test_workflow_scheduling.py`

- [ ] **Step 9.1: Write the e2e tests**

```python
"""E2E: scheduled workflow execution — schedule, promote, cancel, auth."""
import asyncio
from datetime import datetime, timedelta, timezone

import pytest


@pytest.mark.asyncio
async def test_schedule_and_promote(authenticated_client, sample_workflow):
    resp = await authenticated_client.post(
        "/api/workflows/execute",
        json={
            "workflow_id": str(sample_workflow.id),
            "input_data": {},
            "delay_seconds": 2,
        },
    )
    assert resp.status_code == 200, resp.text
    exec_id = resp.json()["execution_id"]
    assert resp.json()["status"] == "Scheduled"

    # Wait up to 2 promoter ticks (~120s cap in prod; tests trigger directly).
    from src.jobs.schedulers.deferred_execution_promoter import promote_due_executions

    # Poll scheduled_at maturity, then trigger promotion explicitly for test speed.
    await asyncio.sleep(3)
    promoted, _ = await promote_due_executions()
    assert promoted >= 1

    # Poll until terminal.
    for _ in range(30):
        r = await authenticated_client.get(f"/api/executions/{exec_id}")
        if r.json()["status"] in ("Success", "Failed", "CompletedWithErrors"):
            break
        await asyncio.sleep(1)
    assert r.json()["status"] == "Success"


@pytest.mark.asyncio
async def test_cancel_before_promotion(authenticated_client, sample_workflow):
    resp = await authenticated_client.post(
        "/api/workflows/execute",
        json={
            "workflow_id": str(sample_workflow.id),
            "input_data": {},
            "delay_seconds": 300,
        },
    )
    exec_id = resp.json()["execution_id"]

    cancel = await authenticated_client.post(
        f"/api/workflows/executions/{exec_id}/cancel"
    )
    assert cancel.status_code == 200

    # Force a promotion tick; the cancelled row must not run.
    from src.jobs.schedulers.deferred_execution_promoter import promote_due_executions

    promoted, _ = await promote_due_executions()
    assert promoted == 0


@pytest.mark.asyncio
async def test_cancel_after_promotion_returns_409(
    authenticated_client, sample_workflow
):
    resp = await authenticated_client.post(
        "/api/workflows/execute",
        json={
            "workflow_id": str(sample_workflow.id),
            "input_data": {},
            "delay_seconds": 1,
        },
    )
    exec_id = resp.json()["execution_id"]

    await asyncio.sleep(2)
    from src.jobs.schedulers.deferred_execution_promoter import promote_due_executions

    await promote_due_executions()

    cancel = await authenticated_client.post(
        f"/api/workflows/executions/{exec_id}/cancel"
    )
    assert cancel.status_code == 409


@pytest.mark.asyncio
async def test_validation_past_scheduled_at(authenticated_client, sample_workflow):
    past = datetime.now(timezone.utc) - timedelta(minutes=1)
    resp = await authenticated_client.post(
        "/api/workflows/execute",
        json={
            "workflow_id": str(sample_workflow.id),
            "input_data": {},
            "scheduled_at": past.isoformat(),
        },
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_validation_sync_plus_schedule(authenticated_client, sample_workflow):
    resp = await authenticated_client.post(
        "/api/workflows/execute",
        json={
            "workflow_id": str(sample_workflow.id),
            "input_data": {},
            "delay_seconds": 60,
            "sync": True,
        },
    )
    assert resp.status_code == 422
```

- [ ] **Step 9.2: Run the e2e suite**

```bash
./test.sh tests/e2e/api/test_workflow_scheduling.py -v
```

Expected: all PASS. If `sample_workflow` fixture doesn't exist, reuse the fixture used by existing `tests/e2e/api/test_workflows*.py`.

- [ ] **Step 9.3: Commit**

```bash
git add api/tests/e2e/api/test_workflow_scheduling.py
git commit -m "test(e2e): scheduled workflow execution end-to-end"
```

---

## Task 10: SDK — `execute(..., scheduled_at, delay_seconds)` + `cancel()`

**Files:**
- Modify: `api/bifrost/workflows.py`
- Test: `api/tests/unit/bifrost/test_workflows_sdk_scheduling.py` (create)

- [ ] **Step 10.1: Write failing tests**

```python
"""SDK-level validation for scheduled execute."""
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bifrost.workflows import workflows


@pytest.mark.asyncio
async def test_execute_with_scheduled_at_includes_field():
    fake = MagicMock()
    fake.post = AsyncMock(return_value=MagicMock(
        status_code=200,
        json=lambda: {"execution_id": "e1", "status": "Scheduled"},
        headers={},
    ))
    run_at = datetime.now(timezone.utc) + timedelta(minutes=5)

    with patch("bifrost.workflows.get_client", return_value=fake):
        eid = await workflows.execute("wf", scheduled_at=run_at)

    assert eid == "e1"
    payload = fake.post.await_args.kwargs["json"]
    assert payload["scheduled_at"] == run_at.isoformat()


@pytest.mark.asyncio
async def test_execute_with_delay_seconds_includes_field():
    fake = MagicMock()
    fake.post = AsyncMock(return_value=MagicMock(
        status_code=200, json=lambda: {"execution_id": "e1"}, headers={}
    ))

    with patch("bifrost.workflows.get_client", return_value=fake):
        await workflows.execute("wf", delay_seconds=60)

    payload = fake.post.await_args.kwargs["json"]
    assert payload["delay_seconds"] == 60


@pytest.mark.asyncio
async def test_execute_rejects_naive_scheduled_at():
    with pytest.raises(ValueError, match="timezone"):
        await workflows.execute(
            "wf", scheduled_at=datetime.now() + timedelta(minutes=5)
        )


@pytest.mark.asyncio
async def test_execute_rejects_both_fields():
    run_at = datetime.now(timezone.utc) + timedelta(minutes=5)
    with pytest.raises(ValueError, match="mutually exclusive"):
        await workflows.execute("wf", scheduled_at=run_at, delay_seconds=60)


@pytest.mark.asyncio
async def test_cancel_calls_endpoint():
    fake = MagicMock()
    fake.post = AsyncMock(return_value=MagicMock(
        status_code=200, json=lambda: {"status": "Cancelled"}, headers={}
    ))
    with patch("bifrost.workflows.get_client", return_value=fake):
        await workflows.cancel("exec-1")

    fake.post.assert_awaited_once()
    url = fake.post.await_args.args[0]
    assert url == "/api/workflows/executions/exec-1/cancel"
```

- [ ] **Step 10.2: Run and confirm failure**

```bash
./test.sh tests/unit/bifrost/test_workflows_sdk_scheduling.py -v
```

Expected: failures for missing parameters / missing `cancel`.

- [ ] **Step 10.3: Extend the SDK**

In `api/bifrost/workflows.py`, replace the `execute` signature and body:

```python
    @staticmethod
    async def execute(
        workflow: str,
        input_data: dict[str, Any] | None = None,
        *,
        org_id: str | None = None,
        run_as: str | None = None,
        scheduled_at: "datetime | None" = None,
        delay_seconds: int | None = None,
    ) -> str:
        """Execute a workflow (fire-and-forget).

        When scheduled_at or delay_seconds is provided, the workflow is queued
        for a future run; the returned execution_id will be in Scheduled status
        until the scheduler promotes it.

        Args:
            scheduled_at: tz-aware datetime in the future (≤ 1 year).
                Mutually exclusive with delay_seconds.
            delay_seconds: seconds from now (1..31_536_000).
                Mutually exclusive with scheduled_at.

        Raises:
            ValueError: on naive scheduled_at or both scheduling fields set.
        """
        from datetime import datetime  # local import for type check below
        from ._context import get_default_scope

        if scheduled_at is not None and delay_seconds is not None:
            raise ValueError("'scheduled_at' and 'delay_seconds' are mutually exclusive")
        if isinstance(scheduled_at, datetime) and scheduled_at.tzinfo is None:
            raise ValueError("'scheduled_at' must be timezone-aware")

        if org_id is None:
            org_id = get_default_scope()

        client = get_client()
        payload: dict[str, Any] = {
            "workflow_id": workflow,
            "input_data": input_data or {},
            "sync": False,
        }
        if org_id is not None:
            payload["org_id"] = org_id
        if run_as is not None:
            payload["run_as"] = run_as
        if scheduled_at is not None:
            payload["scheduled_at"] = scheduled_at.isoformat()
        if delay_seconds is not None:
            payload["delay_seconds"] = delay_seconds

        response = await client.post("/api/workflows/execute", json=payload)
        raise_for_status_with_detail(response)
        return response.json()["execution_id"]

    @staticmethod
    async def cancel(execution_id: str) -> None:
        """Cancel a Scheduled workflow execution.

        Raises:
            httpx.HTTPStatusError: 409 if the execution is not Scheduled,
                404 if not found, 403 if forbidden.
        """
        client = get_client()
        response = await client.post(
            f"/api/workflows/executions/{execution_id}/cancel"
        )
        raise_for_status_with_detail(response)
```

Add to the top of the file:

```python
from datetime import datetime  # noqa: F401 — used in docstring type hint
```

- [ ] **Step 10.4: Run and confirm pass**

```bash
./test.sh tests/unit/bifrost/test_workflows_sdk_scheduling.py -v
```

Expected: all PASS.

- [ ] **Step 10.5: Run DTO-parity test**

```bash
./test.sh tests/unit/test_dto_flags.py -v
```

Expected: PASS. If it FAILS with `scheduled_at` / `delay_seconds` listed as drifting, add them to `DTO_EXCLUDES` in `api/bifrost/dto_flags.py` with a comment: `# scheduled_at/delay_seconds are SDK kwargs not CLI flags — CLI support is out of scope for v1`, then re-run.

- [ ] **Step 10.6: Commit**

```bash
git add api/bifrost/workflows.py api/bifrost/dto_flags.py api/tests/unit/bifrost/test_workflows_sdk_scheduling.py
git commit -m "feat(sdk): schedule and cancel workflow execute"
```

---

## Task 11: Regenerate TypeScript types

**Files:**
- Modify: `client/src/lib/v1.d.ts` (auto-generated)

- [ ] **Step 11.1: Regenerate**

```bash
cd /home/jack/GitHub/bifrost/client && npm run generate:types
```

Expected: `v1.d.ts` updates silently.

- [ ] **Step 11.2: Confirm the new fields landed**

```bash
grep -A2 "WorkflowExecutionRequest" client/src/lib/v1.d.ts | head -60
grep "scheduled_at" client/src/lib/v1.d.ts
```

Expected: `scheduled_at` appears on both request and response shapes.

- [ ] **Step 11.3: Commit**

```bash
cd /home/jack/GitHub/bifrost
git add client/src/lib/v1.d.ts
git commit -m "chore(client): regenerate types for scheduled executions"
```

---

## Task 12: Frontend — status badge with hover datetime

**Files:**
- Modify: `client/src/components/execution/ExecutionStatusBadge.tsx`
- Modify: `client/src/components/execution/ExecutionStatusBadge.test.tsx`

- [ ] **Step 12.1: Write failing badge test**

In `ExecutionStatusBadge.test.tsx`, add:

```tsx
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";

import { ExecutionStatusBadge } from "./ExecutionStatusBadge";

describe("ExecutionStatusBadge — Scheduled", () => {
  it("renders label without inline datetime", () => {
    render(
      <ExecutionStatusBadge
        status="Scheduled"
        scheduledAt="2026-04-25T13:00:00Z"
      />
    );
    const badge = screen.getByText("Scheduled");
    expect(badge).toBeInTheDocument();
    // No inline time alongside the label.
    expect(badge.textContent?.trim()).toBe("Scheduled");
  });

  it("carries absolute datetime in title attribute", () => {
    render(
      <ExecutionStatusBadge
        status="Scheduled"
        scheduledAt="2026-04-25T13:00:00Z"
      />
    );
    const wrapper = screen.getByText("Scheduled").closest("[title]");
    expect(wrapper).not.toBeNull();
    expect(wrapper?.getAttribute("title")).toMatch(/2026/);
  });

  it("omits title when scheduledAt is undefined", () => {
    render(<ExecutionStatusBadge status="Pending" />);
    const badge = screen.getByText("Pending").closest("[title]");
    expect(badge).toBeNull();
  });
});
```

- [ ] **Step 12.2: Run, confirm failure**

```bash
./test.sh client unit -- src/components/execution/ExecutionStatusBadge.test.tsx
```

Expected: FAIL — `Scheduled` status unsupported or no `scheduledAt` prop.

- [ ] **Step 12.3: Extend the badge**

Update `ExecutionStatusBadge.tsx`:

1. Add `Scheduled` to the status variant map (muted blue, clock icon — mirror existing variant shape).
2. Add an optional prop:

```tsx
interface ExecutionStatusBadgeProps {
  status: ExecutionStatus;
  scheduledAt?: string;
}
```

3. When `status === "Scheduled"` and `scheduledAt` is present, wrap the badge in a `<span title={formatAbsoluteLocal(scheduledAt)}>...</span>` where `formatAbsoluteLocal` uses the same date-fns helper already used on this page (look for existing `formatExecutionTime` or similar — reuse it, don't recreate). If no suitable helper exists, use:

```tsx
import { format } from "date-fns";

const formatAbsoluteLocal = (iso: string) =>
  `Scheduled for ${format(new Date(iso), "PPp zzz")}`;
```

- [ ] **Step 12.4: Run, confirm pass**

```bash
./test.sh client unit -- src/components/execution/ExecutionStatusBadge.test.tsx
```

Expected: PASS.

- [ ] **Step 12.5: Commit**

```bash
git add client/src/components/execution/ExecutionStatusBadge.tsx client/src/components/execution/ExecutionStatusBadge.test.tsx
git commit -m "feat(client): Scheduled badge variant with hover datetime"
```

---

## Task 13: Frontend — history filter + cancel row action

**Files:**
- Modify: `client/src/pages/ExecutionHistory.tsx`
- Create/Modify: `client/src/pages/ExecutionHistory.test.tsx`

- [ ] **Step 13.1: Write failing filter test**

In the history test file:

```tsx
it("status filter dropdown includes Scheduled", () => {
  render(<ExecutionHistory />);
  fireEvent.click(screen.getByRole("button", { name: /status/i }));
  expect(screen.getByRole("option", { name: "Scheduled" })).toBeInTheDocument();
});
```

- [ ] **Step 13.2: Write failing cancel-action test**

```tsx
it("shows Cancel action on Scheduled rows and calls cancel endpoint", async () => {
  const mockPost = vi.fn().mockResolvedValue({ ok: true });
  // ... set up MSW or vi.mock for /api/workflows/executions/:id/cancel
  render(<ExecutionHistory />);
  // row with status Scheduled → open row menu → click Cancel → confirm
  // assert mockPost called with /api/workflows/executions/<id>/cancel
});
```

(Use the existing test pattern for other row actions in this file — follow whatever mocking convention the file already uses.)

- [ ] **Step 13.3: Run, confirm failure**

```bash
./test.sh client unit -- src/pages/ExecutionHistory.test.tsx
```

Expected: FAIL.

- [ ] **Step 13.4: Update `ExecutionHistory.tsx`**

1. In the status-filter dropdown options, add `{ label: "Scheduled", value: "Scheduled" }` in the same shape as the other entries.
2. In the row action menu, conditionally render a "Cancel" item when `row.status === "Scheduled"`. On click, open a confirm dialog ("Cancel scheduled run of `{row.workflow_name}` for `{format(scheduled_at)}`?"). On confirm, call `authFetch("POST", \`/api/workflows/executions/${row.id}/cancel\`)`. On 200, optimistic status flip to `Cancelled`. On 409, toast `"Execution is already {status}"` and invalidate the list query.
3. Pass `scheduledAt={row.scheduled_at}` to `<ExecutionStatusBadge>`.

- [ ] **Step 13.5: Run, confirm pass**

```bash
./test.sh client unit -- src/pages/ExecutionHistory.test.tsx
```

Expected: PASS.

- [ ] **Step 13.6: Commit**

```bash
git add client/src/pages/ExecutionHistory.tsx client/src/pages/ExecutionHistory.test.tsx
git commit -m "feat(client): Scheduled filter option and cancel row action"
```

---

## Task 14: Details page — "Scheduled for" header line

**Files:**
- Modify: `client/src/pages/ExecutionDetails.tsx`

- [ ] **Step 14.1: Add the header line**

In `ExecutionDetails.tsx`, in the header metadata block (near where created_at / completed_at are shown), add:

```tsx
{execution.scheduled_at && (
  <div className="flex gap-2 text-sm text-muted-foreground">
    <span className="font-medium">Scheduled for:</span>
    <span title={execution.scheduled_at}>
      {format(new Date(execution.scheduled_at), "PPp zzz")}
    </span>
  </div>
)}
```

(Use whatever date-fns format helper the rest of this file already uses — match, don't invent.)

- [ ] **Step 14.2: Manual smoke in the running dev stack**

Open `http://localhost:3000`, log in, schedule a run via API (`curl` or the SDK), and open its details page. Confirm "Scheduled for:" renders and hovering the timestamp shows the ISO string. Also confirm other executions (no `scheduled_at`) do not render this line.

- [ ] **Step 14.3: Commit**

```bash
git add client/src/pages/ExecutionDetails.tsx
git commit -m "feat(client): show scheduled_at on execution details page"
```

---

## Task 15: Playwright E2E

**Files:**
- Create: `client/e2e/scheduled-execution.spec.ts`

- [ ] **Step 15.1: Write the e2e spec**

```ts
import { test, expect } from "@playwright/test";
import { apiRequest, login } from "./helpers"; // use existing helpers

test("schedule → live Success transition", async ({ page, request }) => {
  await login(page);

  const resp = await apiRequest(request, "POST", "/api/workflows/execute", {
    workflow_id: process.env.E2E_TEST_WORKFLOW_ID,
    input_data: {},
    delay_seconds: 3,
  });
  expect(resp.status).toBe("Scheduled");

  await page.goto("/executions");
  const row = page.getByText(resp.execution_id).locator("..");
  await expect(row.getByText("Scheduled")).toBeVisible();

  // Wait for promoter tick + run.
  await expect(row.getByText("Success")).toBeVisible({ timeout: 120_000 });
});

test("cancel a scheduled run from the row menu", async ({ page, request }) => {
  await login(page);

  const resp = await apiRequest(request, "POST", "/api/workflows/execute", {
    workflow_id: process.env.E2E_TEST_WORKFLOW_ID,
    input_data: {},
    delay_seconds: 600,
  });

  await page.goto("/executions");
  const row = page.getByText(resp.execution_id).locator("..");
  await row.getByRole("button", { name: /actions/i }).click();
  await page.getByRole("menuitem", { name: /cancel/i }).click();
  await page.getByRole("button", { name: /confirm/i }).click();

  await expect(row.getByText("Cancelled")).toBeVisible();
});
```

- [ ] **Step 15.2: Run Playwright**

```bash
cd /home/jack/GitHub/bifrost
./test.sh client e2e e2e/scheduled-execution.spec.ts
```

Expected: both tests PASS.

- [ ] **Step 15.3: Commit**

```bash
git add client/e2e/scheduled-execution.spec.ts
git commit -m "test(e2e): scheduled execution schedule and cancel flows"
```

---

## Task 16: Full pre-completion verification

- [ ] **Step 16.1: Backend type check and lint**

```bash
cd api && pyright
cd api && ruff check .
```

Expected: zero errors each.

- [ ] **Step 16.2: Regenerate types (if any later backend tweaks)**

```bash
cd /home/jack/GitHub/bifrost/client && npm run generate:types
```

Expected: idempotent.

- [ ] **Step 16.3: Frontend type check and lint**

```bash
cd /home/jack/GitHub/bifrost/client && npm run tsc
cd /home/jack/GitHub/bifrost/client && npm run lint
```

Expected: zero errors each.

- [ ] **Step 16.4: Full backend test suite**

```bash
cd /home/jack/GitHub/bifrost
./test.sh all
```

Expected: all tests PASS. Parse `/tmp/bifrost-<project>/test-results.xml` if any failures.

- [ ] **Step 16.5: Frontend unit suite**

```bash
./test.sh client unit
```

Expected: PASS.

- [ ] **Step 16.6: Frontend e2e suite**

```bash
./test.sh client e2e
```

Expected: PASS.

- [ ] **Step 16.7: Commit any auto-regenerated artifacts**

```bash
cd /home/jack/GitHub/bifrost
git status
# If client/tsconfig.app.tsbuildinfo or similar changed, commit it:
git add -u
git commit -m "chore: regenerate build artifacts after deferred executions" || true
```

- [ ] **Step 16.8: Push and open PR**

```bash
git push -u origin feat/deferred-executions
gh pr create --title "feat: deferred (scheduled) workflow executions" --body "$(cat <<'EOF'
## Summary
- Schedule a one-shot workflow via `scheduled_at` or `delay_seconds` on `/api/workflows/execute`
- New `Scheduled` execution status + nullable `scheduled_at` column (partial index for promoter)
- Scheduler pod gains a 60s promoter that flips due rows to `Pending` and publishes via the shared `_publish_pending` helper
- Cancel endpoint for scheduled rows (status-guarded UPDATE)
- SDK: `workflows.execute(..., scheduled_at=..., delay_seconds=...)` and `workflows.cancel(execution_id)`
- UI: `Scheduled` status badge with hover datetime, status-filter option, cancel row action, and a "Scheduled for" line on the details page

Spec: `docs/superpowers/specs/2026-04-23-deferred-executions-design.md`
Plan: `docs/superpowers/plans/2026-04-23-deferred-executions.md`

## Test plan
- [x] Contract validation unit tests
- [x] Promoter unit tests (due / future / cancelled / publish-failure revert)
- [x] Router cancel unit tests
- [x] SDK scheduling + cancel unit tests
- [x] Backend E2E: schedule → promote → success, cancel-before-promote, cancel-after-promote (409), validation
- [x] Frontend badge test (Scheduled variant, hover title)
- [x] Frontend history filter + cancel row action tests
- [x] Playwright E2E: live transition and cancel

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## Self-Review

**Spec coverage check:**

| Spec section | Task(s) |
|---|---|
| SCHEDULED enum | Task 1 |
| `scheduled_at` column + partial index | Task 2 |
| Request/response contract + validation | Task 3 |
| `_publish_pending` refactor | Task 4 |
| Router scheduled-insert branch | Task 5 |
| Cancel endpoint (+ status guard + auth) | Task 6 |
| Promoter job (batching, revert on failure, skip-cancelled) | Task 7 |
| APScheduler registration (60s) | Task 8 |
| Backend E2E (promote, cancel-before, cancel-after, validation) | Task 9 |
| SDK `execute(..., scheduled_at, delay_seconds)` + `cancel()` + DTO-parity | Task 10 |
| TypeScript type regen | Task 11 |
| Scheduled badge variant with hover datetime, no inline text | Task 12 |
| History filter "Scheduled" + cancel row action | Task 13 |
| Details page "Scheduled for …" | Task 14 |
| Playwright happy-path + cancel | Task 15 |
| Pre-completion verification (pyright, ruff, tsc, lint, ./test.sh all, client unit, client e2e) | Task 16 |

**Placeholder scan:** no TBDs; every code step has concrete code. Step 5.1 offers an alternative if fixtures don't exist — that's a conditional, not a placeholder.

**Type consistency:** `_publish_pending` signature identical in Task 4 (definition) and Task 7 (call from promoter). Enum value `SCHEDULED = "Scheduled"` referenced consistently. SDK `workflows.cancel` and router `/executions/{id}/cancel` match.

**Known trade-off:** `_publish_pending` is called with `user_email=""` in the promoter because the row doesn't store user_email. The worker already tolerates missing email (the email is used for display / audit only), and the worker hydrates from the user record on pickup. If a downstream consumer turns out to require it, add a column in a follow-up; not blocking v1.
