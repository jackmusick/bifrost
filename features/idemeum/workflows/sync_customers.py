"""
Idemeum: Sync Customers

Syncs Idemeum customers to Bifrost organizations and creates
IntegrationMappings so org-scoped workflows can resolve the mapped customer ID.

Entity model:
  entity_id   = Idemeum customer id
  entity_name = customer display name
"""

from bifrost import integrations, organizations, workflow
from modules.idemeum import IdemeumClient


@workflow(
    name="Idemeum: Sync Customers",
    description="Sync Idemeum customers to Bifrost organizations.",
    category="Idemeum",
    tags=["idemeum", "sync"],
)
async def sync_idemeum_customers() -> dict:
    from modules.idemeum import get_client

    client = await get_client(scope="global")
    try:
        customers = await client.list_customers()
    finally:
        await client.close()

    existing_mappings = {
        mapping.entity_id: mapping
        for mapping in (await integrations.list_mappings("Idemeum") or [])
    }

    all_orgs = await organizations.list()
    orgs_by_name = {org.name.lower(): org for org in all_orgs}

    created_orgs = 0
    mapped = 0
    already_mapped = 0
    errors: list[str] = []

    for customer in customers:
        normalized = IdemeumClient.normalize_customer(customer)
        customer_id = normalized["id"]
        customer_name = normalized["name"] or customer_id

        if not customer_id:
            errors.append(f"Skipped customer with no ID: {customer}")
            continue

        if customer_id in existing_mappings:
            already_mapped += 1
            continue

        try:
            org = orgs_by_name.get(customer_name.lower())
            if org is None:
                org = await organizations.create(customer_name)
                orgs_by_name[customer_name.lower()] = org
                created_orgs += 1

            await integrations.upsert_mapping(
                "Idemeum",
                scope=org.id,
                entity_id=customer_id,
                entity_name=customer_name,
            )
            mapped += 1
        except Exception as exc:
            errors.append(f"{customer_name} ({customer_id}): {exc}")

    return {
        "total": len(customers),
        "mapped": mapped,
        "already_mapped": already_mapped,
        "created_orgs": created_orgs,
        "errors": errors,
    }
