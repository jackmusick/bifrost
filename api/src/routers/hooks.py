"""
Hooks Router

Public webhook receiver endpoints for the Bifrost event system.
These endpoints do NOT require authentication - they are called by external services.

Security is handled by:
1. Unique, random callback paths
2. Adapter-specific validation (HMAC signatures, client state, etc.)
"""

import logging

from fastapi import APIRouter, Request, Response, status
from fastapi.responses import PlainTextResponse

from src.core.database import DbSession
from src.services.events.processor import EventProcessor
from src.services.webhooks.protocol import (
    Deliver,
    Rejected,
    ValidationResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/hooks", tags=["Webhooks"])


def _get_client_ip(request: Request) -> str | None:
    """Extract client IP from request, handling proxies."""
    # Check X-Forwarded-For header (set by reverse proxies)
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        # Take the first IP in the chain
        return forwarded.split(",")[0].strip()

    # Fall back to direct client IP
    if request.client:
        return request.client.host

    return None


def _normalize_headers(headers: dict) -> dict[str, str]:
    """Normalize headers to lowercase keys."""
    return {k.lower(): v for k, v in headers.items()}


# Health endpoint MUST be defined before the wildcard /{source_id} route
@router.get(
    "/health",
    summary="Webhook health check",
    description="Health check endpoint for webhook receiver.",
    response_class=PlainTextResponse,
)
async def webhook_health() -> str:
    """Health check for webhook receiver."""
    return "OK"


@router.api_route(
    "/{source_id}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    summary="Webhook receiver",
    description="Public endpoint for receiving webhooks. Returns 202 on acceptance.",
    include_in_schema=False,  # Don't expose in API docs
)
async def receive_webhook(
    source_id: str,
    request: Request,
    db: DbSession,
) -> Response:
    """
    Receive webhook from external service.

    This endpoint is called by external services to deliver events.
    It supports various HTTP methods to accommodate different webhook providers.

    The source_id is the event source UUID, used directly as the webhook path.

    Processing flow:
    1. Look up webhook source by event_source_id
    2. Route to appropriate adapter for validation
    3. Adapter validates request (signature, etc.)
    4. Create event record and queue deliveries
    5. Return 202 Accepted (or adapter-specific response)

    No authentication required - security through:
    - UUID-based paths (unguessable)
    - Adapter-specific validation (HMAC, client state, etc.)
    """
    # Read raw body
    body = await request.body()

    # Extract request details
    headers = _normalize_headers(dict(request.headers))
    query_params = dict(request.query_params)
    method = request.method
    source_ip = _get_client_ip(request)

    logger.debug(
        f"Webhook received: {method} /api/hooks/{source_id}",
        extra={
            "source_id": source_id,
            "method": method,
            "source_ip": source_ip,
            "content_length": len(body),
        },
    )

    # Process through EventProcessor
    processor = EventProcessor(db)

    from src.services.webhooks.protocol import WebhookRequest

    webhook_request = WebhookRequest(
        method=method,
        path=f"/api/hooks/{source_id}",
        headers=headers,
        query_params=query_params,
        body=body,
        client_ip=source_ip,
    )

    try:
        result = await processor.process_webhook(source_id, webhook_request)
    except Exception as e:
        logger.error(f"Error processing webhook: {e}", exc_info=True)
        # Return 500 but don't expose internal error details
        return Response(
            content="Internal server error",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            media_type="text/plain",
        )

    # Handle result types
    if isinstance(result, ValidationResponse):
        # Return adapter-specific validation response
        return Response(
            content=result.body,
            status_code=result.status_code,
            media_type=result.content_type,
            headers=result.headers or {},
        )

    if isinstance(result, Rejected):
        # Request was rejected by adapter
        logger.warning(
            f"Webhook rejected: {source_id}",
            extra={
                "source_id": source_id,
                "status_code": result.status_code,
                "reject_reason": result.message,
            },
        )
        return Response(
            content=result.message,
            status_code=result.status_code,
            media_type="text/plain",
        )

    if isinstance(result, Deliver):
        # Event accepted - commit transaction and queue deliveries
        await db.commit()

        # Queue workflow executions asynchronously
        # This is done after commit to ensure delivery records exist
        try:
            # Get the event ID from the most recent event for this source
            from uuid import UUID as PyUUID
            from sqlalchemy import select
            from src.models.orm.events import Event

            try:
                source_uuid = PyUUID(source_id)
            except ValueError:
                source_uuid = None

            if source_uuid:
                event_result = await db.execute(
                    select(Event)
                    .where(Event.event_source_id == source_uuid)
                    .order_by(Event.created_at.desc())
                    .limit(1)
                )
                event = event_result.scalar_one_or_none()

                if event:
                    queued = await processor.queue_event_deliveries(event.id)
                    await db.commit()

                    logger.info(
                        f"Webhook accepted: {source_id}",
                        extra={
                            "source_id": source_id,
                            "event_id": str(event.id),
                            "deliveries_queued": queued,
                        },
                    )
        except Exception as e:
            logger.error(f"Error queueing deliveries: {e}", exc_info=True)
            # Event was recorded, just couldn't queue - don't fail the webhook

        # Return 202 Accepted
        return Response(
            content="Accepted",
            status_code=status.HTTP_202_ACCEPTED,
            media_type="text/plain",
        )

    # Unknown result type
    logger.error(f"Unknown result type from processor: {type(result)}")
    return Response(
        content="Internal server error",
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        media_type="text/plain",
    )
