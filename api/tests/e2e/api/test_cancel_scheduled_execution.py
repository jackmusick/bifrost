"""E2E: cancel a scheduled execution.

Covers the happy path + two status-guarded error paths for
``POST /api/workflows/executions/{execution_id}/cancel``. Same-org /
submitter-or-admin authorization is covered in Task 9; this file sticks to
the three cases above.
"""
from __future__ import annotations

from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.enums import ExecutionStatus
from src.models.orm.executions import Execution
from tests.e2e.conftest import write_and_register


pytestmark = pytest.mark.e2e


@pytest.fixture(scope="module")
def scheduled_workflow(e2e_client, platform_admin):
    """Register a trivial workflow that will be scheduled but never runs."""
    workflow_content = '''"""E2E Cancel Scheduled Execution Workflow"""
from bifrost import workflow

@workflow(
    name="e2e_cancel_scheduled_workflow",
    description="Workflow used by cancel-scheduled-execution E2E tests",
)
async def e2e_cancel_scheduled_workflow(foo: str = "bar") -> dict:
    return {"ok": True, "foo": foo}
'''
    result = write_and_register(
        e2e_client,
        platform_admin.headers,
        "e2e_cancel_scheduled_workflow.py",
        workflow_content,
        "e2e_cancel_scheduled_workflow",
    )
    yield {"id": result["id"], "name": result.get("name", "e2e_cancel_scheduled_workflow")}

    e2e_client.delete(
        "/api/files/editor?path=e2e_cancel_scheduled_workflow.py",
        headers=platform_admin.headers,
    )


@pytest_asyncio.fixture
async def cleanup_scheduled_rows(db_session: AsyncSession):  # type: ignore[misc]
    """Remove Execution rows created by each test."""
    created_ids: list[UUID] = []
    yield created_ids
    if created_ids:
        await db_session.execute(
            delete(Execution).where(Execution.id.in_(created_ids))
        )
        await db_session.commit()


def _schedule_execution(e2e_client, platform_admin, scheduled_workflow) -> UUID:
    """Helper: schedule the module workflow 5 minutes out, return the exec_id."""
    resp = e2e_client.post(
        "/api/workflows/execute",
        headers=platform_admin.headers,
        json={
            "workflow_id": scheduled_workflow["id"],
            "input_data": {},
            "delay_seconds": 300,
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "Scheduled", body
    return UUID(body["execution_id"])


@pytest.mark.asyncio
async def test_cancel_scheduled_flips_to_cancelled(
    e2e_client,
    platform_admin,
    scheduled_workflow,
    db_session: AsyncSession,
    cleanup_scheduled_rows: list[UUID],
):
    exec_id = _schedule_execution(e2e_client, platform_admin, scheduled_workflow)
    cleanup_scheduled_rows.append(exec_id)

    cancel = e2e_client.post(
        f"/api/workflows/executions/{exec_id}/cancel",
        headers=platform_admin.headers,
    )
    assert cancel.status_code == 200, cancel.text
    body = cancel.json()
    assert body["execution_id"] == str(exec_id)
    assert body["status"] == "Cancelled"

    # Verify DB row state.
    await db_session.rollback()  # drop any stale snapshot
    row = (
        await db_session.execute(
            select(Execution).where(Execution.id == exec_id)
        )
    ).scalar_one()
    assert row.status == ExecutionStatus.CANCELLED
    assert row.completed_at is not None


@pytest.mark.asyncio
async def test_cancel_already_cancelled_returns_409(
    e2e_client,
    platform_admin,
    scheduled_workflow,
    cleanup_scheduled_rows: list[UUID],
):
    exec_id = _schedule_execution(e2e_client, platform_admin, scheduled_workflow)
    cleanup_scheduled_rows.append(exec_id)

    first = e2e_client.post(
        f"/api/workflows/executions/{exec_id}/cancel",
        headers=platform_admin.headers,
    )
    assert first.status_code == 200, first.text

    second = e2e_client.post(
        f"/api/workflows/executions/{exec_id}/cancel",
        headers=platform_admin.headers,
    )
    assert second.status_code == 409, second.text
    assert "Cancelled" in second.json()["detail"]


def test_cancel_not_found_returns_404(e2e_client, platform_admin):
    resp = e2e_client.post(
        f"/api/workflows/executions/{uuid4()}/cancel",
        headers=platform_admin.headers,
    )
    assert resp.status_code == 404, resp.text
