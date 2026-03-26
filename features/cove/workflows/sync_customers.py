"""
Cove Data Protection: Sync Customers

Syncs Cove EndCustomer partners to Bifrost organizations and creates
IntegrationMappings so org-scoped workflows can resolve the mapped partner ID.
"""

from bifrost import workflow
from bifrost import integrations, organizations
from modules.cove import CoveClient


@workflow(
    name="Cove Data Protection: Sync Customers",
    description="Sync Cove EndCustomer partners to Bifrost organizations.",
    category="Cove Data Protection",
    tags=["cove", "sync"],
)
async def sync_cove_customers() -> dict:
    from modules.cove import get_client

    client = await get_client(scope="global")
    try:
        partners = await client.enumerate_partners()
    finally:
        await client.close()

    existing_mappings = {
        str(mapping.entity_id): mapping
        for mapping in (await integrations.list_mappings("Cove Data Protection") or [])
    }

    all_orgs = await organizations.list()
    orgs_by_name = {org.name.lower(): org for org in all_orgs}

    cove_customers = [
        partner
        for partner in partners
        if CoveClient.normalize_partner(partner)["level"] == "EndCustomer"
    ]

    created_orgs = 0
    mapped = 0
    already_mapped = 0
    errors: list[str] = []

    for partner in cove_customers:
        normalized = CoveClient.normalize_partner(partner)
        partner_id = normalized["id"]
        partner_name = normalized["name"] or partner_id

        if not partner_id:
            errors.append(f"Skipped partner with no ID: {partner}")
            continue

        if partner_id in existing_mappings:
            already_mapped += 1
            continue

        try:
            org = orgs_by_name.get(partner_name.lower())
            if org is None:
                org = await organizations.create(partner_name)
                orgs_by_name[partner_name.lower()] = org
                created_orgs += 1

            await integrations.upsert_mapping(
                "Cove Data Protection",
                scope=org.id,
                entity_id=partner_id,
                entity_name=partner_name,
            )
            mapped += 1
        except Exception as exc:
            errors.append(f"{partner_name} ({partner_id}): {exc}")

    return {
        "total": len(cove_customers),
        "mapped": mapped,
        "already_mapped": already_mapped,
        "created_orgs": created_orgs,
        "errors": errors,
    }
