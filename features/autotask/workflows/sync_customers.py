"""
Autotask: Sync Customers

Syncs active Autotask customer companies to Bifrost organizations and creates
IntegrationMappings so org-scoped workflows can resolve the mapped company ID.
"""

from bifrost import integrations, organizations, workflow
from modules.autotask import AutotaskClient


@workflow(
    name="Autotask: Sync Customers",
    description="Sync active Autotask customer companies to Bifrost organizations.",
    category="Autotask",
    tags=["autotask", "sync"],
)
async def sync_autotask_customers() -> dict:
    from modules.autotask import get_client

    client = await get_client(scope="global")
    try:
        companies = await client.list_active_companies()
    finally:
        await client.close()

    existing_mappings = {
        mapping.entity_id: mapping
        for mapping in (await integrations.list_mappings("Autotask") or [])
    }

    all_orgs = await organizations.list()
    orgs_by_name = {org.name.lower(): org for org in all_orgs}

    created_orgs = 0
    mapped = 0
    already_mapped = 0
    errors: list[str] = []

    for company in companies:
        normalized = AutotaskClient.normalize_company(company)
        company_id = normalized["id"]
        company_name = normalized["name"] or company_id

        if not company_id:
            errors.append(f"Skipped company with no ID: {company}")
            continue

        if company_id in existing_mappings:
            already_mapped += 1
            continue

        try:
            org = orgs_by_name.get(company_name.lower())
            if org is None:
                org = await organizations.create(company_name)
                orgs_by_name[company_name.lower()] = org
                created_orgs += 1

            await integrations.upsert_mapping(
                "Autotask",
                scope=org.id,
                entity_id=company_id,
                entity_name=company_name,
            )
            mapped += 1
        except Exception as exc:
            errors.append(f"{company_name} ({company_id}): {exc}")

    return {
        "total": len(companies),
        "mapped": mapped,
        "already_mapped": already_mapped,
        "created_orgs": created_orgs,
        "errors": errors,
    }
