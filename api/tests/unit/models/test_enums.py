from src.models.enums import ExecutionStatus


def test_execution_status_has_scheduled():
    assert ExecutionStatus.SCHEDULED.value == "Scheduled"


def test_scheduled_is_distinct_from_pending():
    assert ExecutionStatus.SCHEDULED is not ExecutionStatus.PENDING
    assert ExecutionStatus.SCHEDULED.value != ExecutionStatus.PENDING.value
