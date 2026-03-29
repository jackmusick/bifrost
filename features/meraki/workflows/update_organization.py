"""
Cisco Meraki organization update workflows.
"""

from __future__ import annotations

from bifrost import workflow
from modules.meraki import MerakiClient


@workflow(
    name="Meraki: Update Organization",
    description="Update a Cisco Meraki organization by explicit organization ID or the current org mapping.",
    category="Meraki",
    tags=["meraki", "organization", "update"],
)
async def update_meraki_organization(
    organization_id: str | None = None,
    name: str | None = None,
    extra_fields: dict | None = None,
) -> dict:
    from modules.meraki import get_client

    if name in (None, "") and not extra_fields:
        raise RuntimeError("Provide name or extra_fields to update the Meraki organization.")

    client = await get_client()
    try:
        organization = await client.update_organization(
            organization_id=organization_id,
            name=name,
            extra_fields=extra_fields,
        )
    finally:
        await client.close()

    return {
        "organization": MerakiClient.normalize_organization(organization),
        "raw": organization,
    }
