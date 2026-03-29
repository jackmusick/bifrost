"""
Autotask ticket closing workflows.
"""

from __future__ import annotations

from typing import Any

from bifrost import integrations, workflow
from modules.autotask import AutotaskClient


def _resolve_close_status(explicit: str | None, config: dict[str, Any]) -> str:
    if explicit not in (None, ""):
        return explicit
    for key in (
        "default_close_ticket_status",
        "close_ticket_status",
        "default_ticket_complete_status",
        "ticket_complete_status",
    ):
        value = config.get(key)
        if value not in (None, ""):
            return str(value)
    return "5"


@workflow(
    name="Autotask: Close Ticket",
    description="Close an AutoTask ticket by setting its status to a completed value.",
    category="Autotask",
    tags=["autotask", "ticketing"],
)
async def close_autotask_ticket(
    ticket_id: str,
    resolution: str = "",
    close_status: str | None = None,
    extra_fields: dict[str, Any] | None = None,
) -> dict:
    integration = await integrations.get("Autotask")
    if not integration:
        raise RuntimeError("Integration 'Autotask' not configured")

    integration_config = integration.config or {}
    resolved_close_status = _resolve_close_status(close_status, integration_config)

    from modules.autotask import get_client

    client = await get_client()
    try:
        ticket = await client.update_ticket(
            ticket_id,
            status=resolved_close_status,
            resolution=resolution,
            extra_fields=extra_fields,
        )
    finally:
        await client.close()

    return {
        "ticket": AutotaskClient.normalize_ticket(ticket),
        "raw": ticket,
    }
