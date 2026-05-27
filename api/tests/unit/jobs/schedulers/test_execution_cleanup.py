from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

from src.jobs.schedulers.execution_cleanup import _is_restart_orphan


def test_is_restart_orphan_when_execution_predates_current_workers():
    now = datetime.now(timezone.utc)
    execution = SimpleNamespace(
        id=uuid4(),
        started_at=now - timedelta(minutes=15),
    )
    heartbeat_state = {
        "active_execution_ids": set(),
        "oldest_worker_started_at": now - timedelta(minutes=5),
        "heartbeat_count": 3,
    }

    assert _is_restart_orphan(execution, now=now, heartbeat_state=heartbeat_state)


def test_is_restart_orphan_keeps_execution_claimed_by_heartbeat():
    now = datetime.now(timezone.utc)
    execution_id = uuid4()
    execution = SimpleNamespace(
        id=execution_id,
        started_at=now - timedelta(minutes=15),
    )
    heartbeat_state = {
        "active_execution_ids": {str(execution_id)},
        "oldest_worker_started_at": now - timedelta(minutes=5),
        "heartbeat_count": 3,
    }

    assert not _is_restart_orphan(execution, now=now, heartbeat_state=heartbeat_state)


def test_is_restart_orphan_waits_for_worker_grace_period():
    now = datetime.now(timezone.utc)
    execution = SimpleNamespace(
        id=uuid4(),
        started_at=now - timedelta(minutes=15),
    )
    heartbeat_state = {
        "active_execution_ids": set(),
        "oldest_worker_started_at": now - timedelta(seconds=30),
        "heartbeat_count": 3,
    }

    assert not _is_restart_orphan(execution, now=now, heartbeat_state=heartbeat_state)
