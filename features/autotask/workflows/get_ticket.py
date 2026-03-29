"""
Autotask ticket lookup workflows.
"""

from __future__ import annotations

from bifrost import workflow
from modules.autotask import AutotaskClient


@workflow(
    name="Autotask: Get Ticket",
    description="Get an AutoTask ticket by ticket ID.",
    category="Autotask",
    tags=["autotask", "ticketing"],
)
async def get_autotask_ticket(
    ticket_id: str,
) -> dict:
    from modules.autotask import get_client

    client = await get_client()
    try:
        ticket = await client.get_ticket(ticket_id)
    finally:
        await client.close()

    return {
        "ticket": AutotaskClient.normalize_ticket(ticket),
        "raw": ticket,
    }
