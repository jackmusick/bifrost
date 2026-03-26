"""
Meraki: Sync Organizations

Syncs Meraki organizations visible to the API key to Bifrost organizations and
creates IntegrationMappings so org-scoped workflows can resolve the mapped
Meraki organization ID.

Entity model:
  entity_id   = Meraki organization ID
  entity_name = organization name
"""

from bifrost import workflow
from bifrost import integrations, organizations
from modules.meraki import MerakiClient


@workflow(
    name="Meraki: Sync Organizations",
    description="Sync Meraki organizations to Bifrost organizations.",
    category="Meraki",
    tags=["meraki", "sync"],
)
async def sync_meraki_organizations() -> dict:
    from modules.meraki import get_client

    client = await get_client(scope="global")
    try:
        meraki_organizations = await client.list_organizations()
    finally:
        await client.close()

    existing_mappings = {
        mapping.entity_id: mapping
        for mapping in (await integrations.list_mappings("Meraki") or [])
    }

    all_orgs = await organizations.list()
    orgs_by_name = {org.name.lower(): org for org in all_orgs}

    created_orgs = 0
    mapped = 0
    already_mapped = 0
    errors: list[str] = []

    for organization in meraki_organizations:
        normalized = MerakiClient.normalize_organization(organization)
        organization_id = normalized["id"]
        organization_name = normalized["name"] or organization_id

        if not organization_id:
            errors.append(f"Skipped organization with no ID: {organization}")
            continue

        if organization_id in existing_mappings:
            already_mapped += 1
            continue

        try:
            org = orgs_by_name.get(organization_name.lower())
            if org is None:
                org = await organizations.create(organization_name)
                orgs_by_name[organization_name.lower()] = org
                created_orgs += 1

            await integrations.upsert_mapping(
                "Meraki",
                scope=org.id,
                entity_id=organization_id,
                entity_name=organization_name,
            )
            mapped += 1
        except Exception as exc:
            errors.append(f"{organization_name} ({organization_id}): {exc}")

    return {
        "total": len(meraki_organizations),
        "mapped": mapped,
        "already_mapped": already_mapped,
        "created_orgs": created_orgs,
        "errors": errors,
    }

