"""
Quoter: Sync Organizations

Syncs Quoter organizations inferred from contact records to Bifrost
organizations and creates IntegrationMappings so org-scoped workflows can
resolve the mapped Quoter organization name.

Entity model:
  entity_id   = Quoter contact.organization
  entity_name = Quoter contact.organization
"""

from bifrost import workflow
from bifrost import integrations, organizations


@workflow(
    name="Quoter: Sync Organizations",
    description="Sync Quoter organizations inferred from contacts to Bifrost organizations.",
    category="Quoter",
    tags=["quoter", "sync"],
)
async def sync_quoter_organizations() -> dict:
    from modules.quoter import get_client

    client = await get_client(scope="global")
    try:
        quoter_organizations = await client.infer_organizations_from_contacts()
    finally:
        await client.close()

    existing_mappings = {
        mapping.entity_id: mapping
        for mapping in (await integrations.list_mappings("Quoter") or [])
    }

    all_orgs = await organizations.list()
    orgs_by_name = {org.name.lower(): org for org in all_orgs}

    created_orgs = 0
    mapped = 0
    already_mapped = 0
    errors: list[str] = []

    for organization in quoter_organizations:
        organization_id = organization.get("id", "")
        organization_name = organization.get("name") or organization_id

        if not organization_id:
            errors.append(f"Skipped inferred organization with no ID: {organization}")
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
                "Quoter",
                scope=org.id,
                entity_id=organization_id,
                entity_name=organization_name,
            )
            mapped += 1
        except Exception as exc:
            errors.append(f"{organization_name} ({organization_id}): {exc}")

    return {
        "total": len(quoter_organizations),
        "mapped": mapped,
        "already_mapped": already_mapped,
        "created_orgs": created_orgs,
        "errors": errors,
    }

