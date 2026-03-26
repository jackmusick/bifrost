"""
Datto RMM: Sync Sites

Syncs Datto RMM sites to Bifrost organizations and creates IntegrationMappings
so org-scoped workflows can resolve the mapped site UID.

Entity model:
  entity_id   = Datto RMM site UID
  entity_name = site name
"""

from bifrost import workflow
from bifrost import integrations, organizations
from modules import dattormm


@workflow(
    name="Datto RMM: Sync Sites",
    description="Sync Datto RMM sites into Bifrost organizations.",
    category="Datto RMM",
    tags=["datto", "rmm"],
)
async def sync_dattormm_sites() -> dict:
    client = await dattormm.get_client(scope="global")
    try:
        sites = await client.list_sites()
    finally:
        await client.close()

    existing_mappings = {
        mapping.entity_id: mapping
        for mapping in (await integrations.list_mappings("Datto RMM") or [])
    }

    all_orgs = await organizations.list()
    orgs_by_name = {org.name.lower(): org for org in all_orgs}

    created_orgs = 0
    mapped = 0
    already_mapped = 0
    errors: list[str] = []

    for site in sites:
        normalized = dattormm.DattoRMMClient.normalize_site(site)
        site_uid = normalized["id"]
        site_name = normalized["name"] or site_uid

        if not site_uid:
            errors.append(f"Skipped site with no ID: {site}")
            continue

        if site_uid in existing_mappings:
            already_mapped += 1
            continue

        try:
            org = orgs_by_name.get(site_name.lower())
            if org is None:
                org = await organizations.create(site_name)
                orgs_by_name[site_name.lower()] = org
                created_orgs += 1

            await integrations.upsert_mapping(
                "Datto RMM",
                scope=org.id,
                entity_id=site_uid,
                entity_name=site_name,
            )
            mapped += 1
        except Exception as exc:
            errors.append(f"{site_name} ({site_uid}): {exc}")

    return {
        "total": len(sites),
        "mapped": mapped,
        "already_mapped": already_mapped,
        "created_orgs": created_orgs,
        "errors": errors,
    }
