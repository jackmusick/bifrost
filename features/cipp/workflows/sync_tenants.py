"""
CIPP: Sync Tenants

Syncs all non-excluded CIPP-managed customer tenants to Bifrost organizations
and creates IntegrationMappings so per-org workflows can call the CIPP API
scoped to that customer's tenant.

Entity model:
  entity_id   = defaultDomainName (e.g. "contoso.onmicrosoft.com")
  entity_name = displayName

Run this after initial CIPP integration setup, and again whenever new
customer tenants are onboarded in CIPP.
"""

from bifrost import workflow
from bifrost import integrations, organizations


@workflow(
    name="CIPP: Sync Tenants",
    description="Sync CIPP-managed customer tenants to Bifrost organizations.",
    category="CIPP",
    tags=["cipp", "sync"],
)
async def sync_cipp_tenants() -> dict:
    from modules.cipp import get_client

    client = await get_client()
    try:
        tenants = await client.list_tenants()
    finally:
        await client.close()

    existing_mappings = {
        m.entity_id: m
        for m in await integrations.list_mappings("CIPP")
    }

    all_orgs = await organizations.list()
    orgs_by_name = {o.name.lower(): o for o in all_orgs}

    created_orgs = 0
    mapped = 0
    already_mapped = 0
    errors = []

    for tenant in tenants:
        domain = tenant.get("defaultDomainName") or tenant.get("customerId", "")
        display_name = tenant.get("displayName") or domain

        if not domain:
            errors.append(f"Skipped tenant with no domain: {tenant}")
            continue

        if domain in existing_mappings:
            already_mapped += 1
            continue

        try:
            org = orgs_by_name.get(display_name.lower())
            if not org:
                org = await organizations.create(display_name)
                orgs_by_name[display_name.lower()] = org
                created_orgs += 1

            await integrations.upsert_mapping(
                "CIPP",
                scope=org.id,
                entity_id=domain,
                entity_name=display_name,
            )
            mapped += 1
        except Exception as exc:
            errors.append(f"{display_name} ({domain}): {exc}")

    return {
        "total": len(tenants),
        "mapped": mapped,
        "already_mapped": already_mapped,
        "created_orgs": created_orgs,
        "errors": errors,
    }
