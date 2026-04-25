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
