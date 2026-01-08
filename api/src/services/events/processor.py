"""
Event Processor Service

Handles the core event processing logic:
1. Receive webhook requests
2. Route to appropriate adapter
3. Create Event records
4. Find matching subscriptions
5. Create EventDelivery records
6. Queue workflow executions

Events are always processed asynchronously and return 202 immediately.
"""

import logging
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.models.enums import EventDeliveryStatus, EventStatus
from src.models.orm.events import (
    Event,
    EventDelivery,
    EventSource,
    WebhookSource,
)
from src.repositories.events import (
    EventDeliveryRepository,
    EventRepository,
    EventSubscriptionRepository,
    WebhookSourceRepository,
)
from src.services.webhooks.protocol import (
    Deliver,
    HandleResult,
    Rejected,
    ValidationResponse,
    WebhookRequest,
)
from src.services.webhooks.registry import get_adapter

logger = logging.getLogger(__name__)


class EventProcessor:
    """
    Core event processor for webhook events.

    Handles the lifecycle of incoming webhook requests:
    - Adapter routing and request handling
    - Event logging
    - Subscription matching
    - Delivery tracking
    - Workflow execution queueing
    """

    def __init__(self, session: AsyncSession):
        self.session = session
        self._webhook_repo = WebhookSourceRepository(session)
        self._subscription_repo = EventSubscriptionRepository(session)
        self._event_repo = EventRepository(session)
        self._delivery_repo = EventDeliveryRepository(session)

    async def process_webhook(
        self,
        source_id: str,
        request: WebhookRequest,
    ) -> HandleResult:
        """
        Process an incoming webhook request.

        Args:
            source_id: The event source UUID (from URL path)
            request: The incoming webhook request data

        Returns:
            HandleResult indicating how to respond:
            - ValidationResponse: Return specific response (for handshakes)
            - Deliver: Event was accepted and will be processed
            - Rejected: Request was rejected (invalid signature, etc.)
        """
        # Validate and parse source_id as UUID
        try:
            from uuid import UUID as PyUUID
            source_uuid = PyUUID(source_id)
        except (ValueError, TypeError):
            logger.warning(f"Invalid source_id: {source_id}")
            return Rejected(
                message="Invalid webhook URL",
                status_code=404,
            )

        # Look up webhook source by event_source_id
        webhook_source = await self._webhook_repo.get_by_event_source_id(source_uuid)

        if not webhook_source:
            logger.warning(f"Webhook not found for source_id: {source_id}")
            return Rejected(
                message="Webhook not found",
                status_code=404,
            )

        event_source = webhook_source.event_source
        if not event_source or not event_source.is_active:
            logger.warning(f"Event source inactive for webhook: {source_id}")
            return Rejected(
                message="Webhook is inactive",
                status_code=404,
            )

        # Get the adapter for this webhook
        adapter = get_adapter(webhook_source.adapter_name)
        if not adapter:
            logger.error(f"Adapter not found: {webhook_source.adapter_name}")
            return Rejected(
                message="Webhook adapter not configured",
                status_code=500,
            )

        # Let adapter handle the request
        config = webhook_source.config or {}
        state = webhook_source.state or {}

        try:
            result = await adapter.handle_request(request, config, state)
        except Exception as e:
            logger.error(f"Adapter error handling webhook: {e}", exc_info=True)
            return Rejected(
                message="Error processing webhook",
                status_code=500,
            )

        # Handle adapter result
        if isinstance(result, ValidationResponse):
            # Validation/handshake response - return directly without logging event
            logger.debug(f"Webhook validation response: {source_id}")
            return result

        if isinstance(result, Rejected):
            # Request rejected by adapter (invalid signature, etc.)
            logger.warning(f"Webhook rejected: {source_id} - {result.message}")
            return result

        if isinstance(result, Deliver):
            # Process the event
            return await self._process_delivery(
                webhook_source=webhook_source,
                event_source=event_source,
                deliver=result,
                request=request,
            )

        # Unknown result type
        logger.error(f"Unknown adapter result type: {type(result)}")
        return Rejected(
            message="Internal error",
            status_code=500,
        )

    async def _process_delivery(
        self,
        webhook_source: WebhookSource,
        event_source: EventSource,
        deliver: Deliver,
        request: WebhookRequest,
    ) -> HandleResult:
        """
        Process a delivery request from an adapter.

        Creates event record, finds subscriptions, creates deliveries,
        and queues workflow executions.
        """
        # Create event record
        event = Event(
            id=uuid.uuid4(),
            event_source_id=event_source.id,
            event_type=deliver.event_type,
            received_at=datetime.utcnow(),
            headers=deliver.raw_headers,
            data=deliver.data,
            source_ip=request.client_ip,
            status=EventStatus.RECEIVED,
        )
        self.session.add(event)
        await self.session.flush()

        logger.info(
            f"Event received: {event.id}",
            extra={
                "event_id": str(event.id),
                "event_source_id": str(event_source.id),
                "event_type": deliver.event_type,
            },
        )

        # Broadcast event_created to WebSocket subscribers
        await self._broadcast_event_update(
            event_source_id=event_source.id,
            event=event,
            update_type="event_created",
        )

        # Find active subscriptions that match this event
        subscriptions = await self._subscription_repo.get_active_for_event(
            source_id=event_source.id,
            event_type=deliver.event_type,
        )

        if not subscriptions:
            # No subscriptions - mark event as completed (nothing to deliver)
            event.status = EventStatus.COMPLETED
            await self.session.flush()
            logger.info(f"No subscriptions for event: {event.id}")
            return Deliver(
                data=deliver.data,
                event_type=deliver.event_type,
            )

        # Create deliveries and queue executions
        event.status = EventStatus.PROCESSING
        await self.session.flush()

        deliveries_created = 0
        for subscription in subscriptions:
            if not subscription.workflow_id or not subscription.workflow:
                logger.warning(
                    f"Subscription {subscription.id} has no workflow, skipping"
                )
                continue

            # Create delivery record
            delivery = EventDelivery(
                id=uuid.uuid4(),
                event_id=event.id,
                event_subscription_id=subscription.id,
                workflow_id=subscription.workflow_id,
                status=EventDeliveryStatus.PENDING,
            )
            self.session.add(delivery)
            deliveries_created += 1

        await self.session.flush()

        logger.info(
            f"Created {deliveries_created} deliveries for event: {event.id}",
            extra={
                "event_id": str(event.id),
                "delivery_count": deliveries_created,
            },
        )

        # Return success - actual execution happens after commit
        return Deliver(
            data=deliver.data,
            event_type=deliver.event_type,
        )

    async def _broadcast_event_update(
        self,
        event_source_id: uuid.UUID,
        event: Event,
        update_type: str,
        success_count: int = 0,
        failed_count: int = 0,
        queued_count: int = 0,
        pending_count: int = 0,
    ) -> None:
        """
        Broadcast event update to WebSocket subscribers.

        Args:
            event_source_id: The event source UUID
            event: The Event model
            update_type: Type of update (event_created, event_updated, deliveries_queued)
            success_count: Number of successful deliveries
            failed_count: Number of failed deliveries
            queued_count: Number of queued deliveries
            pending_count: Number of pending deliveries
        """
        from src.core.pubsub import manager

        channel = f"event_source:{event_source_id}"

        # Build event payload
        message = {
            "type": update_type,
            "event": {
                "id": str(event.id),
                "event_source_id": str(event.event_source_id),
                "event_type": event.event_type,
                "status": getattr(event.status, "value", event.status),
                "received_at": event.received_at.isoformat() if event.received_at else None,
                "source_ip": event.source_ip,
                "success_count": success_count,
                "failed_count": failed_count,
                "queued_count": queued_count,
                "pending_count": pending_count,
                "delivery_count": success_count + failed_count + queued_count + pending_count,
            },
        }

        try:
            await manager.broadcast(channel, message)
            logger.debug(f"Broadcast {update_type} to channel {channel}")
        except Exception as e:
            # Don't fail event processing if broadcast fails
            logger.warning(f"Failed to broadcast event update: {e}")

    async def queue_event_deliveries(self, event_id: uuid.UUID) -> int:
        """
        Queue workflow executions for all pending deliveries of an event.

        This should be called after the transaction commits to ensure
        delivery records exist before queueing.

        Args:
            event_id: Event UUID

        Returns:
            Number of deliveries queued
        """
        # Get all pending deliveries for this event
        deliveries = await self._delivery_repo.get_by_event(event_id)

        queued = 0
        for delivery in deliveries:
            if delivery.status != EventDeliveryStatus.PENDING:
                continue

            # Get the event data
            event = await self._event_repo.get_by_id(event_id)
            if not event:
                logger.error(f"Event not found when queueing delivery: {event_id}")
                continue

            try:
                await self._queue_workflow_execution(delivery, event)
                delivery.status = EventDeliveryStatus.QUEUED
                queued += 1
            except Exception as e:
                logger.error(
                    f"Failed to queue delivery {delivery.id}: {e}",
                    exc_info=True,
                )
                delivery.status = EventDeliveryStatus.FAILED
                delivery.error_message = str(e)

        await self.session.flush()

        # Broadcast update after queueing
        if event:
            # Count current delivery statuses
            all_deliveries = await self._delivery_repo.get_by_event(event_id)
            success_count = sum(
                1 for d in all_deliveries if d.status == EventDeliveryStatus.SUCCESS
            )
            failed_count = sum(
                1 for d in all_deliveries if d.status == EventDeliveryStatus.FAILED
            )
            queued_count = sum(
                1 for d in all_deliveries if d.status == EventDeliveryStatus.QUEUED
            )
            pending_count = sum(
                1 for d in all_deliveries if d.status == EventDeliveryStatus.PENDING
            )

            await self._broadcast_event_update(
                event_source_id=event.event_source_id,
                event=event,
                update_type="deliveries_queued",
                success_count=success_count,
                failed_count=failed_count,
                queued_count=queued_count,
                pending_count=pending_count,
            )

        return queued

    async def _queue_workflow_execution(
        self,
        delivery: EventDelivery,
        event: Event,
    ) -> None:
        """
        Queue a workflow execution for an event delivery.

        Uses the same execution infrastructure as the rest of the platform.
        """
        from src.services.execution.async_executor import enqueue_system_workflow_execution

        # Get workflow details
        workflow = delivery.workflow
        if not workflow:
            raise ValueError(f"Delivery {delivery.id} has no workflow")

        # Build parameters for workflow (matches endpoint behavior)
        # Extract body fields as flat params so they match function signatures
        parameters: dict[str, Any] = {}
        if isinstance(event.data, dict):
            parameters.update(event.data)

        # Always include full event context under reserved key
        # This includes the COMPLETE raw body for complex/non-dict payloads
        parameters["_event"] = {
            "id": str(event.id),
            "type": event.event_type,
            "body": event.data,  # Full raw body (dict, list, string, whatever)
            "headers": event.headers,
            "received_at": event.received_at.isoformat() if event.received_at else None,
            "source_ip": event.source_ip,
        }

        # Use the centralized system execution helper
        # Use workflow's org_id so org-scoped workflows only access their org's data
        execution_id = await enqueue_system_workflow_execution(
            workflow_id=str(workflow.id),
            parameters=parameters,
            source="Event System",
            org_id=str(workflow.organization_id) if workflow.organization_id else None,
        )

        # Store the execution ID on the delivery for tracking
        delivery.execution_id = uuid.UUID(execution_id)

        logger.info(
            "Queued workflow execution for event delivery",
            extra={
                "execution_id": execution_id,
                "delivery_id": str(delivery.id),
                "workflow_id": str(workflow.id),
                "event_id": str(event.id),
            },
        )


async def process_webhook_request(
    session: AsyncSession,
    source_id: str,
    method: str,
    headers: dict[str, str],
    query_params: dict[str, str],
    body: bytes,
    source_ip: str | None = None,
) -> HandleResult:
    """
    Convenience function to process a webhook request.

    Args:
        session: Database session
        source_id: The event source UUID from the URL
        method: HTTP method
        headers: Request headers (lowercase keys)
        query_params: Query parameters
        body: Raw request body
        source_ip: Client IP address

    Returns:
        HandleResult indicating how to respond
    """
    # Build WebhookRequest
    request = WebhookRequest(
        method=method,
        path=f"/api/hooks/{source_id}",
        headers=headers,
        query_params=query_params,
        body=body,
        client_ip=source_ip,
    )

    # Process through EventProcessor
    processor = EventProcessor(session)
    return await processor.process_webhook(source_id, request)


async def update_delivery_from_execution(
    execution_id: str,
    status: str,
    error_message: str | None = None,
) -> None:
    """
    Update EventDelivery status based on workflow execution completion.

    Called by the workflow execution consumer when an execution completes.
    Looks up the EventDelivery by execution_id and updates its status.

    Args:
        execution_id: The workflow execution ID
        status: The execution status (Success, Failed, Timeout, etc.)
        error_message: Error message if failed
    """
    from sqlalchemy import select
    from src.core.database import get_session_factory

    # Map execution status to delivery status
    status_map = {
        "Success": EventDeliveryStatus.SUCCESS,
        "Failed": EventDeliveryStatus.FAILED,
        "Timeout": EventDeliveryStatus.FAILED,
        "Cancelled": EventDeliveryStatus.FAILED,
    }

    delivery_status = status_map.get(status, EventDeliveryStatus.FAILED)

    session_factory = get_session_factory()
    async with session_factory() as session:
        # Find delivery by execution_id
        result = await session.execute(
            select(EventDelivery).where(
                EventDelivery.execution_id == uuid.UUID(execution_id)
            )
        )
        delivery = result.scalar_one_or_none()

        if not delivery:
            # Not an event-triggered execution, nothing to update
            return

        # Update delivery status
        delivery.status = delivery_status
        delivery.completed_at = datetime.utcnow()
        delivery.attempt_count += 1

        if error_message:
            delivery.error_message = error_message

        await session.flush()

        # Update the parent event status
        delivery_repo = EventDeliveryRepository(session)
        await delivery_repo.update_event_status(delivery.event_id)

        await session.commit()

        logger.info(
            "Updated event delivery status",
            extra={
                "delivery_id": str(delivery.id),
                "execution_id": execution_id,
                "status": delivery_status.value,
            },
        )

        # Broadcast event status update to WebSocket subscribers
        event = await EventRepository(session).get_by_id(delivery.event_id)
        if event and event.event_source:
            from src.core.pubsub import manager

            # Get delivery counts for this event
            deliveries = await delivery_repo.get_by_event(delivery.event_id)
            success_count = sum(1 for d in deliveries if d.status == EventDeliveryStatus.SUCCESS)
            failed_count = sum(1 for d in deliveries if d.status == EventDeliveryStatus.FAILED)

            channel = f"event-source:{event.event_source_id}"
            message = {
                "type": "event_updated",
                "event": {
                    "id": str(event.id),
                    "event_source_id": str(event.event_source_id),
                    "event_type": event.event_type,
                    "status": getattr(event.status, "value", event.status),
                    "received_at": event.received_at.isoformat() if event.received_at else None,
                    "source_ip": event.source_ip,
                    "success_count": success_count,
                    "failed_count": failed_count,
                    "delivery_count": len(deliveries),
                },
            }

            try:
                await manager.broadcast(channel, message)
                logger.debug(f"Broadcast event_updated for {event.id}")
            except Exception as e:
                logger.warning(f"Failed to broadcast event update: {e}")
