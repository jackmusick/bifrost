"""
DNSFilter organization update workflows.
"""

from __future__ import annotations

from bifrost import workflow
from modules.dnsfilter import DNSFilterClient


@workflow(
    name="DNSFilter: Update Organization",
    description="Update a DNSFilter organization by explicit organization ID or the current org mapping.",
    category="DNSFilter",
    tags=["dnsfilter", "organization", "update"],
)
async def update_dnsfilter_organization(
    organization_id: str | None = None,
    name: str | None = None,
    extra_fields: dict | None = None,
) -> dict:
    from modules.dnsfilter import get_client

    if name in (None, "") and not extra_fields:
        raise RuntimeError("Provide name or extra_fields to update the DNSFilter organization.")

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
        "organization": DNSFilterClient.normalize_organization(organization),
        "raw": organization,
    }
