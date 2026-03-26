"""
Keeper MSP: Sync Managed Companies

Syncs Keeper MSP managed companies to Bifrost organizations and creates
IntegrationMappings so org-scoped workflows can resolve the mapped Keeper
managed company ID.

Entity model:
  entity_id   = Keeper managed company ID
  entity_name = managed company name
"""

from bifrost import workflow
from bifrost import integrations, organizations
from modules import keeper


@workflow(
    name="Keeper MSP: Sync Managed Companies",
    description="Sync Keeper managed companies into Bifrost organizations.",
    category="Keeper MSP",
    tags=["keeper", "msp"],
)
async def sync_keeper_managed_companies() -> dict:
    client = await keeper.get_client(scope="global")
    try:
        managed_companies = await client.list_managed_companies()
    finally:
        await client.close()

    existing_mappings = {
        mapping.entity_id: mapping
        for mapping in (await integrations.list_mappings("Keeper MSP") or [])
    }

    all_orgs = await organizations.list()
    orgs_by_name = {org.name.lower(): org for org in all_orgs}

    created_orgs = 0
    mapped = 0
    already_mapped = 0
    errors: list[str] = []

    for company in managed_companies:
        normalized = keeper.KeeperMSPClient.normalize_managed_company(company)
        company_id = normalized["id"]
        company_name = normalized["name"] or company_id

        if not company_id:
            errors.append(f"Skipped managed company with no ID: {company}")
            continue

        if company_id in existing_mappings:
            already_mapped += 1
            continue

        try:
            org = orgs_by_name.get((company_name or "").lower())
            if org is None:
                org = await organizations.create(company_name)
                orgs_by_name[company_name.lower()] = org
                created_orgs += 1

            await integrations.upsert_mapping(
                "Keeper MSP",
                scope=org.id,
                entity_id=company_id,
                entity_name=company_name,
            )
            mapped += 1
        except Exception as exc:
            errors.append(f"{company_name} ({company_id}): {exc}")

    return {
        "total": len(managed_companies),
        "mapped": mapped,
        "already_mapped": already_mapped,
        "created_orgs": created_orgs,
        "errors": errors,
    }
