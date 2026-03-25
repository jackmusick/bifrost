"""
IT Glue: Sync Organizations

Syncs IT Glue organizations to Bifrost organizations and creates
IntegrationMappings so org-scoped workflows can resolve the mapped IT Glue
organization ID.

Entity model:
  entity_id   = IT Glue organization ID
  entity_name = organization name
"""

from bifrost import integrations, organizations
from modules import itglue


async def sync_itglue_organizations() -> dict:
    client = await itglue.get_client(scope="global")
    itglue_organizations = client.list_organizations()

    existing_mappings = {
        mapping.entity_id: mapping
        for mapping in (await integrations.list_mappings("IT Glue") or [])
    }

    all_orgs = await organizations.list()
    orgs_by_name = {org.name.lower(): org for org in all_orgs}

    created_orgs = 0
    mapped = 0
    already_mapped = 0
    errors: list[str] = []

    for organization in itglue_organizations:
        normalized = itglue.ITGlueClient.normalize_organization(organization)
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
                "IT Glue",
                scope=org.id,
                entity_id=organization_id,
                entity_name=organization_name,
            )
            mapped += 1
        except Exception as exc:
            errors.append(f"{organization_name} ({organization_id}): {exc}")

    return {
        "total": len(itglue_organizations),
        "mapped": mapped,
        "already_mapped": already_mapped,
        "created_orgs": created_orgs,
        "errors": errors,
    }
