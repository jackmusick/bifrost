"""
VIPRE: Sync Sites

Syncs VIPRE child sites inferred from device inventory to Bifrost organizations
and creates IntegrationMappings so org-scoped workflows can resolve the mapped
VIPRE site UUID.

Entity model:
  entity_id   = VIPRE siteUuid
  entity_name = VIPRE siteName
"""

from bifrost import workflow
from bifrost import integrations, organizations
from modules.vipre import VipreClient


@workflow(
    name="VIPRE: Sync Sites",
    description="Sync inferred VIPRE sites to Bifrost organizations.",
    category="VIPRE",
    tags=["vipre", "sync"],
)
async def sync_vipre_sites() -> dict:
    from modules.vipre import get_client

    client = await get_client(scope="global")
    try:
        sites = await client.infer_sites_from_devices()
    finally:
        await client.close()

    existing_mappings = {
        mapping.entity_id: mapping
        for mapping in (await integrations.list_mappings("VIPRE") or [])
    }

    all_orgs = await organizations.list()
    orgs_by_name = {org.name.lower(): org for org in all_orgs}

    created_orgs = 0
    mapped = 0
    already_mapped = 0
    errors: list[str] = []

    for site in sites:
        site_id = site.get("id", "")
        site_name = site.get("name") or site_id

        if not site_id:
            errors.append(f"Skipped inferred site with no ID: {site}")
            continue

        if site_id in existing_mappings:
            already_mapped += 1
            continue

        try:
            org = orgs_by_name.get(site_name.lower())
            if org is None:
                org = await organizations.create(site_name)
                orgs_by_name[site_name.lower()] = org
                created_orgs += 1

            await integrations.upsert_mapping(
                "VIPRE",
                scope=org.id,
                entity_id=site_id,
                entity_name=site_name,
            )
            mapped += 1
        except Exception as exc:
            errors.append(f"{site_name} ({site_id}): {exc}")

    return {
        "total": len(sites),
        "mapped": mapped,
        "already_mapped": already_mapped,
        "created_orgs": created_orgs,
        "errors": errors,
    }

