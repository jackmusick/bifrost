"""
Datto SaaS Protection: Sync Domains

Syncs Datto SaaS Protection domain records to Bifrost organizations and creates
IntegrationMappings so org-scoped workflows can resolve the mapped domain ID.
"""

from bifrost import workflow
from bifrost import integrations, organizations
from modules.dattosaasprotection import DattoSaaSProtectionClient


@workflow(
    name="Datto SaaS Protection: Sync Domains",
    description="Sync Datto SaaS Protection domains to Bifrost organizations.",
    category="Datto SaaS Protection",
    tags=["datto", "saas", "sync"],
)
async def sync_dattosaas_domains() -> dict:
    from modules.dattosaasprotection import get_client

    client = await get_client(scope="global")
    try:
        domains = await client.list_domains()
    finally:
        await client.close()

    existing_mappings = {
        str(mapping.entity_id): mapping
        for mapping in (await integrations.list_mappings("Datto SaaS Protection") or [])
    }

    all_orgs = await organizations.list()
    orgs_by_name = {org.name.lower(): org for org in all_orgs}

    created_orgs = 0
    mapped = 0
    already_mapped = 0
    errors: list[str] = []

    for domain in domains:
        normalized = DattoSaaSProtectionClient.normalize_domain(domain)
        domain_id = normalized["id"]
        organization_name = normalized["name"] or domain_id

        if not domain_id:
            errors.append(f"Skipped domain with no ID: {domain}")
            continue

        if domain_id in existing_mappings:
            already_mapped += 1
            continue

        try:
            org = orgs_by_name.get(organization_name.lower())
            if org is None:
                org = await organizations.create(organization_name)
                orgs_by_name[organization_name.lower()] = org
                created_orgs += 1

            await integrations.upsert_mapping(
                "Datto SaaS Protection",
                scope=org.id,
                entity_id=domain_id,
                entity_name=normalized["label"] or organization_name,
            )
            mapped += 1
        except Exception as exc:
            errors.append(f"{organization_name} ({domain_id}): {exc}")

    return {
        "total": len(domains),
        "mapped": mapped,
        "already_mapped": already_mapped,
        "created_orgs": created_orgs,
        "errors": errors,
    }
