"""
Google Workspace Reseller: Sync Customers

Syncs reseller-managed Google Workspace customers into Bifrost organizations.

Entity model:
  entity_id   = Google customerId
  entity_name = primary customer domain

Note: the Reseller API does not expose customers.list. Customer discovery is
derived from subscriptions.list and then enriched with customers.get.
"""

from bifrost import workflow
from bifrost import integrations, organizations
from modules import googleworkspace


@workflow(
    name="Google Workspace Reseller: Sync Customers",
    description="Sync reseller-managed Google Workspace customers into Bifrost organizations.",
    category="Google Workspace Reseller",
    tags=["google", "workspace", "reseller"],
)
async def sync_google_workspace_reseller_customers() -> dict:
    client = await googleworkspace.get_reseller_client(scope="global")
    try:
        customers = await client.list_customers()
    finally:
        await client.close()

    existing_mappings = {
        mapping.entity_id: mapping
        for mapping in (await integrations.list_mappings("Google Workspace Reseller") or [])
    }

    all_orgs = await organizations.list()
    orgs_by_name = {org.name.lower(): org for org in all_orgs}

    created_orgs = 0
    mapped = 0
    already_mapped = 0
    errors: list[str] = []

    for customer in customers:
        normalized = googleworkspace.GoogleWorkspaceResellerClient.normalize_customer(customer)
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
                "Google Workspace Reseller",
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
