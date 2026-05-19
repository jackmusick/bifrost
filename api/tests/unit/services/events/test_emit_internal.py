"""
Unit tests for EventProcessor.emit_internal.

Tests:
- emit_internal creates an Event row with event_type, source_type=INTERNAL, source_id=None
- given a subscription on event_type "user.invited", delivery is created and workflow enqueued
- no subscribers => event logged, zero deliveries, no error
- payload is round-trippable: workflow receives it under _event.body
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.models.enums import EventDeliveryStatus


def _make_processor(subscriptions=None):
    """Create an EventProcessor with repos mocked out."""
    if subscriptions is None:
        subscriptions = []

    mock_session = AsyncMock()

    with (
        patch("src.services.events.processor.EventDeliveryRepository"),
        patch("src.services.events.processor.EventRepository"),
        patch("src.services.events.processor.EventSubscriptionRepository"),
        patch("src.services.events.processor.WebhookSourceRepository"),
    ):
        from src.services.events.processor import EventProcessor

        processor = EventProcessor(mock_session)

        # Wire up the sub_repo mock to return desired subscriptions
        processor._subscription_repo = AsyncMock()
        processor._subscription_repo.get_active_for_internal_event = AsyncMock(
            return_value=subscriptions
        )

        processor._event_repo = AsyncMock()
        processor._delivery_repo = AsyncMock()

        return processor, mock_session


def _make_workflow_subscription(workflow_id=None, org_id=None):
    sub = MagicMock()
    sub.id = uuid.uuid4()
    sub.target_type = "workflow"
    sub.workflow_id = workflow_id or uuid.uuid4()
    sub.agent_id = None
    sub.input_mapping = None

    workflow = MagicMock()
    workflow.id = sub.workflow_id
    workflow.organization_id = org_id or uuid.uuid4()
    sub.workflow = workflow

    return sub


@pytest.mark.asyncio
async def test_emit_internal_creates_event_row():
    """emit_internal adds an Event row to the session with correct fields."""
    # Provide one subscription so the event doesn't immediately transition to COMPLETED
    org_id = uuid.uuid4()
    sub = _make_workflow_subscription(org_id=org_id)
    processor, session = _make_processor(subscriptions=[sub])

    added_objects = []
    session.add = lambda obj: added_objects.append(obj)
    session.flush = AsyncMock()

    event_id = await processor.emit_internal(
        event_type="user.invited",
        data={"user_id": "abc123", "email": "user@example.com"},
        organization_id=org_id,
    )

    # Should have added an Event row (plus a delivery)
    from src.models.orm.events import Event
    events = [obj for obj in added_objects if isinstance(obj, Event)]
    assert len(events) == 1

    event = events[0]
    assert event.event_type == "user.invited"
    assert event.event_source_id is None
    assert event.data == {"user_id": "abc123", "email": "user@example.com"}
    assert event.id == event_id


@pytest.mark.asyncio
async def test_emit_internal_no_subscribers_logs_and_returns():
    """With no subscriptions, event is logged and zero deliveries created."""
    processor, session = _make_processor(subscriptions=[])

    added_objects = []
    session.add = lambda obj: added_objects.append(obj)
    session.flush = AsyncMock()

    event_id = await processor.emit_internal(
        event_type="user.invited",
        data={"user_id": "abc"},
    )

    assert event_id is not None
    # Only the Event itself, no deliveries
    from src.models.orm.events import Event, EventDelivery
    events = [o for o in added_objects if isinstance(o, Event)]
    deliveries = [o for o in added_objects if isinstance(o, EventDelivery)]
    assert len(events) == 1
    assert len(deliveries) == 0


@pytest.mark.asyncio
async def test_emit_internal_with_subscriber_creates_delivery():
    """A matching subscription produces one delivery record."""
    org_id = uuid.uuid4()
    sub = _make_workflow_subscription(org_id=org_id)
    processor, session = _make_processor(subscriptions=[sub])

    added_objects = []
    session.add = lambda obj: added_objects.append(obj)
    session.flush = AsyncMock()

    event_id = await processor.emit_internal(
        event_type="user.invited",
        data={"email": "new@example.com"},
        organization_id=org_id,
    )

    from src.models.orm.events import EventDelivery
    deliveries = [o for o in added_objects if isinstance(o, EventDelivery)]
    assert len(deliveries) == 1
    assert deliveries[0].event_id == event_id
    assert deliveries[0].event_subscription_id == sub.id
    assert deliveries[0].status == EventDeliveryStatus.PENDING


@pytest.mark.asyncio
async def test_emit_internal_payload_under_event_key():
    """The workflow receives payload under _event.body when queued."""
    org_id = uuid.uuid4()
    sub = _make_workflow_subscription(org_id=org_id)
    processor, session = _make_processor(subscriptions=[sub])

    added_objects = []
    session.add = lambda obj: added_objects.append(obj)
    session.flush = AsyncMock()

    payload = {"user_id": "u1", "email": "u@example.com", "reason": "created"}

    with patch(
        "src.services.execution.async_executor.enqueue_system_workflow_execution",
        new_callable=AsyncMock,
        return_value=str(uuid.uuid4()),
    ) as mock_enqueue:
        # queue_event_deliveries is called separately after commit; test _queue_workflow_execution directly
        event_mock = MagicMock()
        event_mock.id = uuid.uuid4()
        event_mock.event_type = "user.invited"
        event_mock.data = payload
        event_mock.headers = None
        event_mock.received_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
        event_mock.source_ip = None

        delivery_mock = MagicMock()
        delivery_mock.id = uuid.uuid4()
        delivery_mock.workflow = sub.workflow
        delivery_mock.subscription = sub
        delivery_mock.execution_id = None

        await processor._queue_workflow_execution(delivery_mock, event_mock)

        assert mock_enqueue.called
        call_kwargs = mock_enqueue.call_args.kwargs
        params = call_kwargs.get("parameters") or mock_enqueue.call_args.args[1] if mock_enqueue.call_args.args else call_kwargs.get("parameters")
        assert params is not None
        assert "_event" in params
        assert params["_event"]["body"] == payload
        assert params["_event"]["type"] == "user.invited"
