"""
Datto Networking: Sync Networks

Syncs Datto Networking networks to Bifrost organizations and creates
IntegrationMappings so org-scoped workflows can resolve the mapped network ID.

Entity model:
  entity_id   = Datto Networking network ID
  entity_name = network name
"""

from bifrost import workflow
from bifrost import integrations, organizations
from modules import dattonetworking


@workflow(
    name="Datto Networking: Sync Networks",
    description="Sync Datto Networking networks into Bifrost organizations.",
    category="Datto Networking",
    tags=["datto", "networking"],
)
async def sync_dattonetworking_networks() -> dict:
    client = await dattonetworking.get_client(scope="global")
    try:
        networks = await client.list_networks()
    finally:
        await client.close()

    existing_mappings = {
        mapping.entity_id: mapping
        for mapping in (await integrations.list_mappings("Datto Networking") or [])
    }

    all_orgs = await organizations.list()
    orgs_by_name = {org.name.lower(): org for org in all_orgs}

    created_orgs = 0
    mapped = 0
    already_mapped = 0
    errors: list[str] = []

    for network in networks:
        normalized = dattonetworking.DattoNetworkingClient.normalize_network(network)
        network_id = normalized["id"]
        network_name = normalized["name"] or network_id

        if not network_id:
            errors.append(f"Skipped network with no ID: {network}")
            continue

        if network_id in existing_mappings:
            already_mapped += 1
            continue

        try:
            org = orgs_by_name.get(network_name.lower())
            if org is None:
                org = await organizations.create(network_name)
                orgs_by_name[network_name.lower()] = org
                created_orgs += 1

            await integrations.upsert_mapping(
                "Datto Networking",
                scope=org.id,
                entity_id=network_id,
                entity_name=network_name,
            )
            mapped += 1
        except Exception as exc:
            errors.append(f"{network_name} ({network_id}): {exc}")

    return {
        "total": len(networks),
        "mapped": mapped,
        "already_mapped": already_mapped,
        "created_orgs": created_orgs,
        "errors": errors,
    }
