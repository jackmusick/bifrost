"""
Webhook Subscription Renewal Scheduler

Automatically renews webhook subscriptions that are about to expire.
Some webhook providers (like Microsoft Graph) require periodic renewal
to keep subscriptions active.

Runs every 6 hours to check for subscriptions expiring within 48 hours.
"""

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import joinedload

from src.core.database import get_db_context
from src.models.orm.events import EventSource, WebhookSource
from src.services.webhooks.registry import get_adapter

logger = logging.getLogger(__name__)

# Check for subscriptions expiring within 48 hours
RENEWAL_THRESHOLD_HOURS = 48


async def renew_expiring_webhooks() -> dict[str, Any]:
    """
    Renew webhook subscriptions that are about to expire.

    Finds all webhook sources with expires_at within the renewal threshold
    and attempts to renew them using their adapter's renewal method.

    Returns:
        Summary of renewal results
    """
    start_time = datetime.now(timezone.utc)
    logger.info("▶ Webhook renewal starting")

    results: dict[str, Any] = {
        "total_webhooks": 0,
        "needs_renewal": 0,
        "renewed_successfully": 0,
        "renewal_failed": 0,
        "no_renewal_support": 0,
        "errors": [],
    }

    try:
        async with get_db_context() as db:
            from src.repositories.events import WebhookSourceRepository

            repo = WebhookSourceRepository(db)

            # Get webhooks expiring within threshold
            webhooks = await repo.get_expiring_soon(within_hours=RENEWAL_THRESHOLD_HOURS)

            results["total_webhooks"] = len(webhooks)
            results["needs_renewal"] = len(webhooks)

            for webhook in webhooks:
                try:
                    # Check if adapter supports renewal
                    adapter = get_adapter(webhook.adapter_name)
                    if not adapter or adapter.renewal_interval is None:
                        results["no_renewal_support"] += 1
                        continue

                    # Get integration if required
                    integration = webhook.integration if webhook.integration_id else None

                    # Attempt renewal
                    renewal_result = await adapter.renew(
                        external_id=webhook.external_id,
                        state=webhook.state or {},
                        integration=integration,
                    )

                    if renewal_result:
                        # Update webhook with new expiration
                        webhook.expires_at = renewal_result.expires_at
                        webhook.updated_at = datetime.utcnow()

                        # Update state if returned
                        if renewal_result.state:
                            webhook.state = {**(webhook.state or {}), **renewal_result.state}

                        results["renewed_successfully"] += 1
                        logger.info(
                            f"Renewed webhook subscription: {webhook.callback_path}",
                            extra={
                                "webhook_id": str(webhook.id),
                                "adapter": webhook.adapter_name,
                                "new_expires_at": renewal_result.expires_at.isoformat() if renewal_result.expires_at else None,
                            },
                        )
                    else:
                        # Renewal returned None - may need to recreate subscription
                        results["renewal_failed"] += 1
                        results["errors"].append({
                            "webhook_id": str(webhook.id),
                            "adapter": webhook.adapter_name,
                            "error": "Renewal returned None - subscription may have expired",
                        })

                        # Mark event source with error
                        if webhook.event_source:
                            webhook.event_source.error_message = "Webhook subscription expired and could not be renewed"

                except Exception as e:
                    results["renewal_failed"] += 1
                    results["errors"].append({
                        "webhook_id": str(webhook.id),
                        "adapter": webhook.adapter_name,
                        "error": str(e),
                    })
                    logger.error(
                        f"Error renewing webhook {webhook.id}: {e}",
                        exc_info=True,
                    )

            await db.commit()

        # Calculate duration
        end_time = datetime.now(timezone.utc)
        duration_seconds = (end_time - start_time).total_seconds()
        results["duration_seconds"] = duration_seconds
        results["start_time"] = start_time.isoformat()
        results["end_time"] = end_time.isoformat()

        # Log completion
        success = results["renewed_successfully"]
        failed = results["renewal_failed"]
        no_support = results["no_renewal_support"]

        if failed > 0:
            logger.warning(
                f"⚠ Webhook renewal completed with errors: "
                f"{success} renewed, {failed} failed, {no_support} no renewal needed "
                f"({duration_seconds:.1f}s)"
            )
        else:
            logger.info(
                f"✓ Webhook renewal completed: "
                f"{success} renewed, {failed} failed, {no_support} no renewal needed "
                f"({duration_seconds:.1f}s)"
            )

    except Exception as e:
        logger.error(f"✗ Webhook renewal failed: {e}", exc_info=True)
        results["errors"].append({"error": str(e)})

    return results
