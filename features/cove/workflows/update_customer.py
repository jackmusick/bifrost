"""
Cove customer update workflows.
"""

from __future__ import annotations

from bifrost import workflow
from modules.cove import CoveClient


@workflow(
    name="Cove: Update Customer",
    description="Update a Cove customer partner by explicit partner ID or the current org mapping.",
    category="Cove",
    tags=["cove", "customer", "update"],
)
async def update_cove_customer(
    partner_id: str | None = None,
    name: str | None = None,
    extra_fields: dict | None = None,
) -> dict:
    from modules.cove import get_client

    if name in (None, "") and not extra_fields:
        raise RuntimeError("Provide name or extra_fields to update the Cove customer.")

    client = await get_client()
    try:
        customer = await client.update_customer(
            partner_id=int(partner_id) if partner_id not in (None, "") else None,
            name=name,
            extra_fields=extra_fields,
        )
    finally:
        await client.close()

    return {
        "customer": CoveClient.normalize_partner(customer),
        "raw": customer,
    }
