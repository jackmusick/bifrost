"""
Events Router

CRUD operations for event sources, subscriptions, and event history.
Supports webhooks as event sources with adapter-based configuration.
"""

import logging
from datetime import datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import joinedload

from src.core.auth import Context, CurrentSuperuser
from src.core.database import DbSession
from src.models.contracts.events import (
    CreateDeliveryRequest,
    DynamicValuesRequest,
    DynamicValuesResponse,
    EventDeliveryListResponse,
    EventDeliveryResponse,
    EventListResponse,
    EventResponse,
    EventSourceCreate,
    EventSourceListResponse,
    EventSourceResponse,
    EventSourceUpdate,
    EventSubscriptionCreate,
    EventSubscriptionListResponse,
    EventSubscriptionResponse,
    EventSubscriptionUpdate,
    RetryDeliveryRequest,
    RetryDeliveryResponse,
    WebhookAdapterInfo,
    WebhookAdapterListResponse,
    WebhookSourceResponse,
)
from src.models.enums import EventDeliveryStatus, EventSourceType
from src.models.orm.events import (
    Event,
    EventDelivery,
    EventSource,
    EventSubscription,
    WebhookSource,
)
from src.repositories.events import (
    EventDeliveryRepository,
    EventRepository,
    EventSourceRepository,
    EventSubscriptionRepository,
)
from src.services.webhooks.registry import get_adapter_registry

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/events", tags=["Events"])


def _build_callback_url(source_id: UUID) -> str:
    """Build callback URL path from event source ID."""
    return f"/api/hooks/{source_id}"


async def _build_event_source_response(
    source: EventSource,
    db: DbSession,
) -> EventSourceResponse:
    """Build EventSourceResponse from ORM model with computed fields."""
    # Get subscription count
    sub_repo = EventSubscriptionRepository(db)
    subscription_count = await sub_repo.count_by_source(source.id, active_only=True)

    # Get event count in last 24 hours
    event_repo = EventRepository(db)
    event_count_24h = await event_repo.count_by_source(
        source.id,
        since=datetime.utcnow() - timedelta(hours=24),
    )

    # Build webhook response if applicable
    webhook_response = None
    if source.source_type == EventSourceType.WEBHOOK and source.webhook_source:
        ws = source.webhook_source
        webhook_response = WebhookSourceResponse(
            adapter_name=ws.adapter_name,
            integration_id=ws.integration_id,
            integration_name=ws.integration.name if ws.integration else None,
            config=ws.config or {},
            callback_url=_build_callback_url(source.id),
            external_id=ws.external_id,
            expires_at=ws.expires_at,
        )

    return EventSourceResponse(
        id=source.id,
        name=source.name,
        source_type=source.source_type,
        organization_id=source.organization_id,
        organization_name=source.organization.name if source.organization else None,
        is_active=source.is_active,
        error_message=source.error_message,
        subscription_count=subscription_count,
        event_count_24h=event_count_24h,
        created_by=source.created_by,
        created_at=source.created_at,
        updated_at=source.updated_at,
        webhook=webhook_response,
    )


async def _build_event_subscription_response(
    subscription: EventSubscription,
    db: DbSession,
) -> EventSubscriptionResponse:
    """Build EventSubscriptionResponse from ORM model with computed fields."""
    # Get delivery counts
    delivery_repo = EventDeliveryRepository(db)
    total_count = await delivery_repo.count_by_subscription(subscription.id)
    success_count = await delivery_repo.count_by_subscription(
        subscription.id, status=EventDeliveryStatus.SUCCESS
    )
    failed_count = await delivery_repo.count_by_subscription(
        subscription.id, status=EventDeliveryStatus.FAILED
    )

    return EventSubscriptionResponse(
        id=subscription.id,
        event_source_id=subscription.event_source_id,
        workflow_id=subscription.workflow_id,
        workflow_name=subscription.workflow.name if subscription.workflow else None,
        event_type=subscription.event_type,
        filter_expression=subscription.filter_expression,
        is_active=subscription.is_active,
        delivery_count=total_count,
        success_count=success_count,
        failed_count=failed_count,
        created_by=subscription.created_by,
        created_at=subscription.created_at,
        updated_at=subscription.updated_at,
    )


# =============================================================================
# Webhook Adapters
# =============================================================================


@router.get(
    "/adapters",
    response_model=WebhookAdapterListResponse,
    summary="List available webhook adapters",
    description="List all available webhook adapters and their configuration schemas (Platform admin only).",
)
async def list_adapters(
    ctx: Context,
    user: CurrentSuperuser,
) -> WebhookAdapterListResponse:
    """List all available webhook adapters."""
    registry = get_adapter_registry()
    adapters_info = registry.list_adapters()

    return WebhookAdapterListResponse(
        adapters=[WebhookAdapterInfo(**info) for info in adapters_info]
    )


@router.post(
    "/adapters/{adapter_name}/dynamic-values",
    response_model=DynamicValuesResponse,
    summary="Get dynamic values for adapter config",
    description="Fetch dynamic options for a config field with x-dynamic-values (Platform admin only).",
)
async def get_dynamic_values(
    adapter_name: str,
    request: DynamicValuesRequest,
    ctx: Context,
    user: CurrentSuperuser,
    db: DbSession,
) -> DynamicValuesResponse:
    """
    Fetch dynamic values for adapter configuration fields.

    This endpoint is called by the UI to populate dropdowns for config fields
    that have x-dynamic-values defined in their config_schema. Similar to
    Power Automate's x-ms-dynamic-values pattern.

    The adapter's get_dynamic_values method is called with:
    - operation: The operation name from x-dynamic-values.operation
    - integration: OAuth integration (if integration_id provided)
    - current_config: Values selected so far (for dependent fields)

    Returns a list of option objects that the UI uses to populate dropdowns.
    """
    from src.models.orm.integrations import Integration

    # Get adapter
    registry = get_adapter_registry()
    adapter = registry.get(adapter_name)

    if not adapter:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown adapter: {adapter_name}",
        )

    # Load integration if provided
    integration = None
    if request.integration_id:
        result = await db.execute(
            select(Integration).where(Integration.id == request.integration_id)
        )
        integration = result.scalar_one_or_none()

        if not integration:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Integration not found",
            )

    # Call adapter's get_dynamic_values
    try:
        items = await adapter.get_dynamic_values(
            operation=request.operation,
            integration=integration,
            current_config=request.current_config,
        )
        return DynamicValuesResponse(items=items)

    except NotImplementedError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error(
            f"Failed to get dynamic values for {adapter_name}/{request.operation}: {e}",
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch dynamic values: {e}",
        )


# =============================================================================
# Event Sources
# =============================================================================


@router.get(
    "/sources",
    response_model=EventSourceListResponse,
    summary="List event sources",
    description="List all event sources (Platform admin only).",
)
async def list_sources(
    ctx: Context,
    user: CurrentSuperuser,
    db: DbSession,
    source_type: EventSourceType | None = Query(
        None, description="Filter by source type"
    ),
    organization_id: UUID | None = Query(
        None, description="Filter by organization"
    ),
    limit: int = Query(100, ge=1, le=1000, description="Max results"),
    offset: int = Query(0, ge=0, description="Skip results"),
) -> EventSourceListResponse:
    """
    List event sources (Platform admin only).
    """
    repo = EventSourceRepository(db)

    # Determine org filter (admins can filter by org or see all)
    org_filter = organization_id
    include_global = organization_id is None

    sources = await repo.get_by_organization(
        organization_id=org_filter,
        source_type=source_type,
        include_global=include_global,
        limit=limit,
        offset=offset,
    )

    total = await repo.count_by_organization(
        organization_id=org_filter,
        source_type=source_type,
        include_global=include_global,
    )

    items = [await _build_event_source_response(s, db) for s in sources]

    return EventSourceListResponse(items=items, total=total)


@router.post(
    "/sources",
    response_model=EventSourceResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create event source",
    description="Create a new event source (Platform admin only).",
)
async def create_source(
    request: EventSourceCreate,
    ctx: Context,
    user: CurrentSuperuser,
    db: DbSession,
) -> EventSourceResponse:
    """
    Create a new event source.

    For webhooks, this will:
    1. Generate a unique callback URL
    2. Call the adapter's subscribe method (if needed)
    3. Store the webhook configuration
    """
    now = datetime.utcnow()

    # Create base event source
    source = EventSource(
        name=request.name,
        source_type=request.source_type,
        organization_id=request.organization_id,
        is_active=True,
        created_by=ctx.user.email,
        created_at=now,
        updated_at=now,
    )
    db.add(source)
    await db.flush()

    # Handle webhook-specific configuration
    if request.source_type == EventSourceType.WEBHOOK:
        if not request.webhook:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Webhook configuration required for webhook source type",
            )

        # Get adapter
        adapter_name = request.webhook.adapter_name
        adapter = get_adapter_registry().get(adapter_name)
        if not adapter:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unknown adapter: {adapter_name}",
            )

        # Validate integration if required
        integration = None
        if adapter.requires_integration:
            if not request.webhook.integration_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Adapter '{adapter_name}' requires integration",
                )
            # TODO: Load integration from database
            # integration = await get_integration(request.webhook.integration_id)

        # Create webhook source record
        webhook_source = WebhookSource(
            event_source_id=source.id,
            adapter_name=adapter_name,
            integration_id=request.webhook.integration_id,
            config=request.webhook.config,
            created_at=now,
            updated_at=now,
        )

        # Call adapter subscribe (for external subscriptions)
        # Note: callback_url is a path - client will combine with origin
        callback_url = _build_callback_url(source.id)
        try:
            result = await adapter.subscribe(
                callback_url=callback_url,
                config=request.webhook.config,
                integration=integration,
            )

            webhook_source.external_id = result.external_id
            webhook_source.state = result.state
            webhook_source.expires_at = result.expires_at

        except Exception as e:
            logger.error(f"Failed to subscribe webhook: {e}", exc_info=True)
            source.error_message = str(e)

        db.add(webhook_source)
        await db.flush()

    # Reload with relationships
    result = await db.execute(
        select(EventSource)
        .options(
            joinedload(EventSource.webhook_source).joinedload(WebhookSource.integration),
            joinedload(EventSource.organization),
        )
        .where(EventSource.id == source.id)
    )
    source = result.unique().scalar_one()

    logger.info(f"Created event source {source.id}: {source.name}")

    return await _build_event_source_response(source, db)


@router.get(
    "/sources/{source_id}",
    response_model=EventSourceResponse,
    summary="Get event source",
    description="Get a specific event source by ID (Platform admin only).",
)
async def get_source(
    source_id: UUID,
    ctx: Context,
    user: CurrentSuperuser,
    db: DbSession,
) -> EventSourceResponse:
    """Get event source by ID (Platform admin only)."""
    repo = EventSourceRepository(db)
    source = await repo.get_by_id_with_details(source_id)

    if not source:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Event source not found",
        )

    return await _build_event_source_response(source, db)


@router.patch(
    "/sources/{source_id}",
    response_model=EventSourceResponse,
    summary="Update event source",
    description="Update an event source (Platform admin only).",
)
async def update_source(
    source_id: UUID,
    request: EventSourceUpdate,
    ctx: Context,
    user: CurrentSuperuser,
    db: DbSession,
) -> EventSourceResponse:
    """Update an event source."""
    repo = EventSourceRepository(db)
    source = await repo.get_by_id_with_details(source_id)

    if not source:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Event source not found",
        )

    # Update basic fields
    if request.name is not None:
        source.name = request.name
    if request.is_active is not None:
        source.is_active = request.is_active
        # Clear error message when reactivating
        if request.is_active:
            source.error_message = None

    source.updated_at = datetime.utcnow()

    # Update webhook-specific fields
    if request.webhook and source.webhook_source:
        ws = source.webhook_source
        if request.webhook.config:
            ws.config = request.webhook.config
        ws.updated_at = datetime.utcnow()

    await db.flush()

    # Reload with relationships
    result = await db.execute(
        select(EventSource)
        .options(
            joinedload(EventSource.webhook_source).joinedload(WebhookSource.integration),
            joinedload(EventSource.organization),
        )
        .where(EventSource.id == source_id)
    )
    source = result.unique().scalar_one()

    logger.info(f"Updated event source {source_id}")

    return await _build_event_source_response(source, db)


@router.delete(
    "/sources/{source_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete event source",
    description="Soft delete an event source (Platform admin only).",
)
async def delete_source(
    source_id: UUID,
    ctx: Context,
    user: CurrentSuperuser,
    db: DbSession,
) -> None:
    """
    Soft delete an event source.

    This will:
    1. Deactivate the source
    2. Call adapter unsubscribe (for external subscriptions)
    """
    repo = EventSourceRepository(db)
    source = await repo.get_by_id_with_details(source_id)

    if not source:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Event source not found",
        )

    # Call adapter unsubscribe for webhooks
    if source.source_type == EventSourceType.WEBHOOK and source.webhook_source:
        ws = source.webhook_source
        adapter = get_adapter_registry().get(ws.adapter_name)
        if adapter:
            try:
                await adapter.unsubscribe(
                    external_id=ws.external_id,
                    state=ws.state or {},
                    integration=ws.integration,
                )
            except Exception as e:
                logger.warning(f"Failed to unsubscribe webhook: {e}")
                # Continue with soft delete anyway

    source.is_active = False
    source.updated_at = datetime.utcnow()

    await db.flush()

    logger.info(f"Soft deleted event source {source_id}")


# =============================================================================
# Event Subscriptions
# =============================================================================


@router.get(
    "/sources/{source_id}/subscriptions",
    response_model=EventSubscriptionListResponse,
    summary="List subscriptions",
    description="List subscriptions for an event source (Platform admin only).",
)
async def list_subscriptions(
    source_id: UUID,
    ctx: Context,
    user: CurrentSuperuser,
    db: DbSession,
    limit: int = Query(100, ge=1, le=1000, description="Max results"),
    offset: int = Query(0, ge=0, description="Skip results"),
) -> EventSubscriptionListResponse:
    """List subscriptions for an event source (Platform admin only)."""
    # Verify source exists
    source_repo = EventSourceRepository(db)
    source = await source_repo.get_by_id(source_id)

    if not source:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Event source not found",
        )

    # Get subscriptions
    sub_repo = EventSubscriptionRepository(db)
    subscriptions = await sub_repo.get_by_source(source_id, active_only=False)

    total = await sub_repo.count_by_source(source_id, active_only=False)

    items = [await _build_event_subscription_response(s, db) for s in subscriptions]

    return EventSubscriptionListResponse(items=items, total=total)


@router.post(
    "/sources/{source_id}/subscriptions",
    response_model=EventSubscriptionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create subscription",
    description="Create a subscription to an event source (Platform admin only).",
)
async def create_subscription(
    source_id: UUID,
    request: EventSubscriptionCreate,
    ctx: Context,
    user: CurrentSuperuser,
    db: DbSession,
) -> EventSubscriptionResponse:
    """Create a subscription to an event source."""
    now = datetime.utcnow()

    # Verify source exists
    source_repo = EventSourceRepository(db)
    source = await source_repo.get_by_id(source_id)

    if not source:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Event source not found",
        )

    # TODO: Verify workflow exists
    # workflow = await get_workflow(request.workflow_id)

    subscription = EventSubscription(
        event_source_id=source_id,
        workflow_id=request.workflow_id,
        event_type=request.event_type,
        filter_expression=request.filter_expression,
        is_active=True,
        created_by=ctx.user.email,
        created_at=now,
        updated_at=now,
    )
    db.add(subscription)
    await db.flush()

    # Reload with workflow relationship
    result = await db.execute(
        select(EventSubscription)
        .options(joinedload(EventSubscription.workflow))
        .where(EventSubscription.id == subscription.id)
    )
    subscription = result.unique().scalar_one()

    logger.info(f"Created subscription {subscription.id} for source {source_id}")

    return await _build_event_subscription_response(subscription, db)


@router.patch(
    "/sources/{source_id}/subscriptions/{subscription_id}",
    response_model=EventSubscriptionResponse,
    summary="Update subscription",
    description="Update an event subscription (Platform admin only).",
)
async def update_subscription(
    source_id: UUID,
    subscription_id: UUID,
    request: EventSubscriptionUpdate,
    ctx: Context,
    user: CurrentSuperuser,
    db: DbSession,
) -> EventSubscriptionResponse:
    """Update an event subscription."""
    # Verify source exists
    source_repo = EventSourceRepository(db)
    source = await source_repo.get_by_id(source_id)

    if not source:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Event source not found",
        )

    # Get subscription
    result = await db.execute(
        select(EventSubscription)
        .options(joinedload(EventSubscription.workflow))
        .where(
            EventSubscription.id == subscription_id,
            EventSubscription.event_source_id == source_id,
        )
    )
    subscription = result.unique().scalar_one_or_none()

    if not subscription:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Subscription not found",
        )

    # Update fields - use model_fields_set to distinguish "not provided" from "set to null"
    if "event_type" in request.model_fields_set:
        subscription.event_type = request.event_type
    if "filter_expression" in request.model_fields_set:
        subscription.filter_expression = request.filter_expression
    if "is_active" in request.model_fields_set:
        subscription.is_active = request.is_active

    subscription.updated_at = datetime.utcnow()

    await db.flush()

    logger.info(f"Updated subscription {subscription_id}")

    return await _build_event_subscription_response(subscription, db)


@router.delete(
    "/sources/{source_id}/subscriptions/{subscription_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete subscription",
    description="Soft delete an event subscription (Platform admin only).",
)
async def delete_subscription(
    source_id: UUID,
    subscription_id: UUID,
    ctx: Context,
    user: CurrentSuperuser,
    db: DbSession,
) -> None:
    """Soft delete an event subscription."""
    # Verify source exists
    source_repo = EventSourceRepository(db)
    source = await source_repo.get_by_id(source_id)

    if not source:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Event source not found",
        )

    # Get subscription
    result = await db.execute(
        select(EventSubscription).where(
            EventSubscription.id == subscription_id,
            EventSubscription.event_source_id == source_id,
        )
    )
    subscription = result.scalar_one_or_none()

    if not subscription:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Subscription not found",
        )

    subscription.is_active = False
    subscription.updated_at = datetime.utcnow()

    await db.flush()

    logger.info(f"Soft deleted subscription {subscription_id}")


# =============================================================================
# Events
# =============================================================================


@router.get(
    "/sources/{source_id}/events",
    response_model=EventListResponse,
    summary="List events",
    description="List events for an event source with optional filters (Platform admin only).",
)
async def list_events(
    source_id: UUID,
    ctx: Context,
    user: CurrentSuperuser,
    db: DbSession,
    event_status: str | None = Query(None, alias="status", description="Filter by status (received, processing, completed, failed)"),
    event_type: str | None = Query(None, description="Filter by event type"),
    since: datetime | None = Query(None, description="Filter events received after this time"),
    until: datetime | None = Query(None, description="Filter events received before this time"),
    limit: int = Query(100, ge=1, le=1000, description="Max results"),
    offset: int = Query(0, ge=0, description="Skip results"),
) -> EventListResponse:
    """List events for an event source with optional filters (Platform admin only)."""
    from src.models.enums import EventStatus

    # Verify source exists
    source_repo = EventSourceRepository(db)
    source = await source_repo.get_by_id(source_id)

    if not source:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Event source not found",
        )

    # Parse status filter
    status_enum = None
    if event_status:
        try:
            status_enum = EventStatus(event_status)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid status: {event_status}. Valid values: received, processing, completed, failed",
            )

    # Get events with filters
    event_repo = EventRepository(db)
    events = await event_repo.get_by_source(
        source_id,
        status=status_enum,
        event_type=event_type,
        since=since,
        until=until,
        limit=limit,
        offset=offset,
    )
    total = await event_repo.count_by_source(
        source_id,
        status=status_enum,
        event_type=event_type,
        since=since,
        until=until,
    )

    items = []
    for event in events:
        # Get delivery counts
        delivery_repo = EventDeliveryRepository(db)
        deliveries = await delivery_repo.get_by_event(event.id)
        total_deliveries = len(deliveries)
        success_count = sum(1 for d in deliveries if d.status == EventDeliveryStatus.SUCCESS)
        failed_count = sum(1 for d in deliveries if d.status == EventDeliveryStatus.FAILED)

        items.append(
            EventResponse(
                id=event.id,
                event_source_id=event.event_source_id,
                event_source_name=source.name,
                event_type=event.event_type,
                received_at=event.received_at,
                headers=event.headers,
                data=event.data,
                source_ip=event.source_ip,
                status=event.status,
                delivery_count=total_deliveries,
                success_count=success_count,
                failed_count=failed_count,
                created_at=event.created_at,
            )
        )

    return EventListResponse(items=items, total=total)


@router.get(
    "/{event_id}",
    response_model=EventResponse,
    summary="Get event",
    description="Get a specific event by ID (Platform admin only).",
)
async def get_event(
    event_id: UUID,
    ctx: Context,
    user: CurrentSuperuser,
    db: DbSession,
) -> EventResponse:
    """Get event by ID (Platform admin only)."""
    # Get event with source
    result = await db.execute(
        select(Event)
        .options(joinedload(Event.event_source))
        .where(Event.id == event_id)
    )
    event = result.unique().scalar_one_or_none()

    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Event not found",
        )

    source = event.event_source

    # Get delivery counts
    delivery_repo = EventDeliveryRepository(db)
    deliveries = await delivery_repo.get_by_event(event_id)
    total_deliveries = len(deliveries)
    success_count = sum(1 for d in deliveries if d.status == EventDeliveryStatus.SUCCESS)
    failed_count = sum(1 for d in deliveries if d.status == EventDeliveryStatus.FAILED)

    return EventResponse(
        id=event.id,
        event_source_id=event.event_source_id,
        event_source_name=source.name if source else None,
        event_type=event.event_type,
        received_at=event.received_at,
        headers=event.headers,
        data=event.data,
        source_ip=event.source_ip,
        status=event.status,
        delivery_count=total_deliveries,
        success_count=success_count,
        failed_count=failed_count,
        created_at=event.created_at,
    )


# =============================================================================
# Event Deliveries
# =============================================================================


@router.get(
    "/{event_id}/deliveries",
    response_model=EventDeliveryListResponse,
    summary="List deliveries",
    description="List deliveries for an event, including undelivered subscriptions (Platform admin only).",
)
async def list_deliveries(
    event_id: UUID,
    ctx: Context,
    user: CurrentSuperuser,
    db: DbSession,
) -> EventDeliveryListResponse:
    """
    List deliveries for an event (Platform admin only).

    Includes both existing deliveries AND subscriptions that were added after
    the event arrived (shown as "not_delivered" status with null id).
    """
    # Get event with event source
    result = await db.execute(
        select(Event)
        .options(joinedload(Event.event_source))
        .where(Event.id == event_id)
    )
    event = result.unique().scalar_one_or_none()

    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Event not found",
        )

    # Get existing deliveries
    delivery_repo = EventDeliveryRepository(db)
    deliveries = await delivery_repo.get_by_event(event_id)

    # Build set of subscription IDs that already have deliveries
    delivered_subscription_ids = {d.event_subscription_id for d in deliveries}

    items = []

    # Add existing deliveries
    for delivery in deliveries:
        items.append(
            EventDeliveryResponse(
                id=delivery.id,
                event_id=delivery.event_id,
                event_subscription_id=delivery.event_subscription_id,
                workflow_id=delivery.workflow_id,
                workflow_name=delivery.workflow.name if delivery.workflow else None,
                execution_id=delivery.execution_id,
                status=delivery.status.value if hasattr(delivery.status, 'value') else delivery.status,
                error_message=delivery.error_message,
                attempt_count=delivery.attempt_count,
                next_retry_at=delivery.next_retry_at,
                completed_at=delivery.completed_at,
                created_at=delivery.created_at,
            )
        )

    # Get all active subscriptions for this event source that match the event type
    subscription_repo = EventSubscriptionRepository(db)
    all_subscriptions = await subscription_repo.get_active_for_event(
        source_id=event.event_source_id,
        event_type=event.event_type,
    )

    # Add "not_delivered" entries for subscriptions without deliveries
    for subscription in all_subscriptions:
        if subscription.id not in delivered_subscription_ids:
            items.append(
                EventDeliveryResponse(
                    id=None,  # No delivery exists
                    event_id=event_id,
                    event_subscription_id=subscription.id,
                    workflow_id=subscription.workflow_id,
                    workflow_name=subscription.workflow.name if subscription.workflow else None,
                    execution_id=None,
                    status="not_delivered",
                    error_message=None,
                    attempt_count=0,
                    next_retry_at=None,
                    completed_at=None,
                    created_at=None,  # No delivery exists
                )
            )

    return EventDeliveryListResponse(items=items, total=len(items))


@router.post(
    "/{event_id}/deliveries",
    response_model=EventDeliveryResponse,
    summary="Create delivery",
    description="Create a delivery to send an existing event to a subscription (Platform admin only).",
    status_code=status.HTTP_201_CREATED,
)
async def create_delivery(
    event_id: UUID,
    request: CreateDeliveryRequest,
    ctx: Context,
    user: CurrentSuperuser,
    db: DbSession,
) -> EventDeliveryResponse:
    """
    Create a delivery for an existing event and subscription.

    This allows retroactively sending an event to a subscription that was
    added after the event originally arrived.
    """
    import uuid
    from src.services.events.processor import EventProcessor

    # Get event
    result = await db.execute(
        select(Event)
        .options(joinedload(Event.event_source))
        .where(Event.id == event_id)
    )
    event = result.unique().scalar_one_or_none()

    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Event not found",
        )

    # Get subscription and verify it belongs to the same event source
    result = await db.execute(
        select(EventSubscription)
        .options(joinedload(EventSubscription.workflow))
        .where(EventSubscription.id == request.subscription_id)
    )
    subscription = result.unique().scalar_one_or_none()

    if not subscription:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Subscription not found",
        )

    if subscription.event_source_id != event.event_source_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Subscription does not belong to this event's source",
        )

    # Check if delivery already exists
    delivery_repo = EventDeliveryRepository(db)
    existing = await db.execute(
        select(EventDelivery).where(
            EventDelivery.event_id == event_id,
            EventDelivery.event_subscription_id == request.subscription_id,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Delivery already exists for this event and subscription",
        )

    # Create delivery record
    delivery = EventDelivery(
        id=uuid.uuid4(),
        event_id=event_id,
        event_subscription_id=subscription.id,
        workflow_id=subscription.workflow_id,
        status=EventDeliveryStatus.PENDING,
    )
    db.add(delivery)
    await db.flush()

    # Queue the execution
    processor = EventProcessor(db)
    try:
        await processor.queue_event_deliveries(event_id)
    except Exception as e:
        logger.error(f"Failed to queue delivery: {e}", exc_info=True)
        delivery.status = EventDeliveryStatus.FAILED
        delivery.error_message = str(e)
        await db.flush()

    logger.info(f"Created delivery {delivery.id} for event {event_id} subscription {subscription.id}")

    return EventDeliveryResponse(
        id=delivery.id,
        event_id=delivery.event_id,
        event_subscription_id=delivery.event_subscription_id,
        workflow_id=delivery.workflow_id,
        workflow_name=subscription.workflow.name if subscription.workflow else None,
        execution_id=delivery.execution_id,
        status=delivery.status.value if hasattr(delivery.status, 'value') else delivery.status,
        error_message=delivery.error_message,
        attempt_count=delivery.attempt_count,
        next_retry_at=delivery.next_retry_at,
        completed_at=delivery.completed_at,
        created_at=delivery.created_at,
    )


@router.post(
    "/deliveries/{delivery_id}/retry",
    response_model=RetryDeliveryResponse,
    summary="Retry delivery",
    description="Retry a failed delivery (Platform admin only).",
)
async def retry_delivery(
    delivery_id: UUID,
    ctx: Context,
    user: CurrentSuperuser,
    db: DbSession,
    request: RetryDeliveryRequest | None = None,
) -> RetryDeliveryResponse:
    """
    Retry a failed delivery.

    This will create a new workflow execution for the event.
    """
    from src.services.events.processor import EventProcessor

    # Get delivery with event
    result = await db.execute(
        select(EventDelivery)
        .options(
            joinedload(EventDelivery.event).joinedload(Event.event_source),
            joinedload(EventDelivery.workflow),
        )
        .where(EventDelivery.id == delivery_id)
    )
    delivery = result.unique().scalar_one_or_none()

    if not delivery:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Delivery not found",
        )

    # Only retry failed deliveries
    if delivery.status not in (EventDeliveryStatus.FAILED, EventDeliveryStatus.SKIPPED):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot retry delivery with status: {delivery.status}",
        )

    # Reset delivery status to pending
    delivery.status = EventDeliveryStatus.PENDING
    delivery.error_message = None
    delivery.execution_id = None
    await db.flush()

    # Queue the execution
    processor = EventProcessor(db)
    try:
        await processor.queue_event_deliveries(delivery.event_id)
        message = "Delivery queued for retry"
    except Exception as e:
        logger.error(f"Failed to queue retry: {e}", exc_info=True)
        delivery.status = EventDeliveryStatus.FAILED
        delivery.error_message = str(e)
        await db.flush()
        message = f"Failed to queue retry: {e}"

    logger.info(f"Retried delivery {delivery_id}")

    return RetryDeliveryResponse(
        delivery_id=delivery_id,
        status=delivery.status.value,
        message=message,
    )
