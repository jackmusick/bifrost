"""
NinjaOne organization update workflows.
"""

from __future__ import annotations

from bifrost import workflow
from modules.ninjaone import NinjaOnePublicAPI, normalize_organization


@workflow(
    name="NinjaOne: Update Organization",
    description="Update a NinjaOne organization by explicit organization ID or the current org mapping.",
    category="NinjaOne",
    tags=["ninjaone", "organization", "update"],
)
async def update_ninjaone_organization(
    organization_id: str | None = None,
    name: str | None = None,
    extra_fields: dict | None = None,
) -> dict:
    from bifrost import integrations

    if name in (None, "") and not extra_fields:
        raise RuntimeError("Provide name or extra_fields to update the NinjaOne organization.")

    integration = await integrations.get("NinjaOne")
    if not integration:
        raise RuntimeError("Integration 'NinjaOne' not found in Bifrost")

    oauth = getattr(integration, "oauth", None)
    access_token = getattr(oauth, "access_token", None)
    if not access_token:
        raise RuntimeError(
            "NinjaOne integration is missing an access token. Please complete the OAuth setup in Settings."
        )

    target_organization_id = organization_id or getattr(integration, "entity_id", None)
    if not target_organization_id:
        raise RuntimeError(
            "NinjaOne organization ID is not available. Configure an org mapping first."
        )

    config = integration.config or {}
    base_url = config.get("base_url", "https://app.ninjarmm.com")
    client = NinjaOnePublicAPI(base_url=base_url)
    client.session.headers["Authorization"] = f"Bearer {access_token}"

    payload = dict(extra_fields or {})
    if name not in (None, ""):
        payload["name"] = name

    try:
        organization = client.patch_organization(str(target_organization_id), payload)
        if organization is None:
            organization = client.get_organization(str(target_organization_id))
    finally:
        client.session.close()

    return {
        "organization": normalize_organization(organization),
        "raw": organization,
    }
