"""
Huntress organization update workflows.
"""

from __future__ import annotations

from bifrost import integrations, workflow
from modules import huntress


@workflow(
    name="Huntress: Update Organization",
    description="Update a Huntress organization by explicit organization ID or the current org mapping.",
    category="Huntress",
    tags=["huntress", "organization", "update"],
)
async def update_huntress_organization(
    organization_id: str | None = None,
    name: str | None = None,
    extra_fields: dict | None = None,
) -> dict:
    if name in (None, "") and not extra_fields:
        raise RuntimeError("Provide name or extra_fields to update the Huntress organization.")

    target_organization_id = organization_id
    if target_organization_id is None:
        mapping = await integrations.get_mapping("Huntress")
        if not mapping or not mapping.entity_id:
            raise RuntimeError(
                "Huntress organization ID is not available. Configure an org mapping first."
            )
        target_organization_id = str(mapping.entity_id)

    client = await huntress.get_client()
    try:
        organization = await client.update_organization(
            organization_id=str(target_organization_id),
            name=name,
            extra_fields=extra_fields,
        )
    finally:
        await client.close()

    normalized = huntress.normalize_organization(organization)
    mapping = await integrations.get_mapping("Huntress")
    if (
        mapping
        and mapping.organization_id
        and str(mapping.entity_id or "") == str(target_organization_id)
    ):
        await integrations.upsert_mapping(
            "Huntress",
            scope=mapping.organization_id,
            entity_id=str(target_organization_id),
            entity_name=normalized["name"],
        )

    return {
        "organization": normalized,
        "raw": organization,
    }
