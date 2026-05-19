"""
Event processing services for the Bifrost event system.
"""

from uuid import UUID

from src.services.events.processor import (
    EventProcessor,
    resolve_webhook_source,
    update_delivery_from_execution,
)


async def emit_internal_event(
    event_type: str,
    data: dict,
    *,
    organization_id: UUID | None = None,
    triggered_by: str | None = None,
) -> UUID:
    """Emit an internal platform event and return its event_id.

    Opens its own DB session and commits, so callers don't need to manage
    transactions. Safe to call from within a request handler that has its
    own open session.
    """
    from src.core.database import get_session_factory

    session_factory = get_session_factory()
    async with session_factory() as db:
        processor = EventProcessor(db)
        event_id = await processor.emit_internal(
            event_type=event_type,
            data=data,
            organization_id=organization_id,
            triggered_by=triggered_by,
        )
        await db.commit()
        await processor.queue_event_deliveries(event_id)
        return event_id


__all__ = [
    "EventProcessor",
    "emit_internal_event",
    "resolve_webhook_source",
    "update_delivery_from_execution",
]
