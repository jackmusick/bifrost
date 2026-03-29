"""
DNSFilter: Sync Organizations

Syncs DNSFilter organizations to Bifrost organizations and creates
IntegrationMappings so org-scoped workflows can resolve the mapped DNSFilter
organization ID.

Entity model:
  entity_id   = DNSFilter organization ID
  entity_name = organization name
"""

from bifrost import workflow
from bifrost import integrations, organizations
from modules.dnsfilter import DNSFilterClient


@workflow(
    name="DNSFilter: Sync Organizations",
    description="Sync DNSFilter organizations to Bifrost organizations.",
    category="DNSFilter",
    tags=["dnsfilter", "sync"],
)
async def sync_dnsfilter_networks() -> dict:
    from modules.dnsfilter import get_client

    client = await get_client(scope="global")
    try:
        vendor_organizations = await client.list_organizations()
    finally:
        await client.close()

    existing_mappings = {
        mapping.entity_id: mapping
        for mapping in (await integrations.list_mappings("DNSFilter") or [])
    }

    all_orgs = await organizations.list()
    orgs_by_name = {org.name.lower(): org for org in all_orgs}

    created_orgs = 0
    mapped = 0
    already_mapped = 0
    errors: list[str] = []

    for vendor_organization in vendor_organizations:
        normalized = DNSFilterClient.normalize_organization(vendor_organization)
        organization_id = normalized["id"]
        organization_name = normalized["name"] or organization_id
        mapping_config = None
        if normalized.get("network_ids"):
            mapping_config = {"network_ids": normalized["network_ids"]}

        if not organization_id:
            errors.append(f"Skipped organization with no ID: {vendor_organization}")
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
                "DNSFilter",
                scope=org.id,
                entity_id=organization_id,
                entity_name=organization_name,
                config=mapping_config,
            )
            mapped += 1
        except Exception as exc:
            errors.append(f"{organization_name} ({organization_id}): {exc}")

    return {
        "total": len(vendor_organizations),
        "mapped": mapped,
        "already_mapped": already_mapped,
        "created_orgs": created_orgs,
        "errors": errors,
    }
