"""
Autotask → Bifrost customer sync.

Fetches active customer companies from Autotask and ensures each has a
corresponding Bifrost organization with an IntegrationMapping linking back
to the Autotask company ID.

Safe to run repeatedly — idempotent via upsert on both orgs and mappings.
"""

import httpx
from bifrost import integrations, organizations, workflow


# Autotask companyType picklist values
COMPANY_TYPE_CUSTOMER = 1


@workflow(
    name="Autotask: Sync Customers",
    description=(
        "Sync active Autotask customer companies to Bifrost organizations. "
        "Creates any missing orgs and keeps IntegrationMappings up to date. "
        "Safe to run repeatedly."
    ),
)
async def sync_autotask_customers() -> dict:
    # Pull Autotask credentials from the integration (no org scope needed)
    at = await integrations.get("Autotask", scope="global")
    if not at:
        raise RuntimeError("Autotask integration not configured or credentials missing")

    headers = {
        "ApiIntegrationCode": at.config["api_integration_code"],
        "UserName": at.config["username"],
        "Secret": at.config["secret"],
        "Content-Type": "application/json",
    }
    base_url = at.config["base_url"]

    # ------------------------------------------------------------------ #
    # 1. Fetch all active customers from Autotask                         #
    # ------------------------------------------------------------------ #
    at_companies: list[dict] = []
    next_url: str | None = f"{base_url}/V1.0/Companies/query"
    query = {
        "maxRecords": 500,
        "includeFields": ["id", "companyName", "companyType", "isActive", "phone",
                          "address1", "city", "state", "postalCode", "webAddress"],
        "filter": [
            {
                "op": "and", "field": "", "value": None, "udf": False,
                "items": [
                    {"op": "eq", "field": "companyType", "value": COMPANY_TYPE_CUSTOMER, "udf": False, "items": []},
                    {"op": "eq", "field": "isActive",    "value": True,                  "udf": False, "items": []},
                ],
            }
        ],
    }

    async with httpx.AsyncClient(verify=False) as client:
        while next_url:
            resp = await client.post(next_url, headers=headers, json=query)
            resp.raise_for_status()
            data = resp.json()
            at_companies.extend(data["items"])
            next_url = data["pageDetails"].get("nextPageUrl")

    # ------------------------------------------------------------------ #
    # 2. Build lookup maps for what already exists in Bifrost             #
    # ------------------------------------------------------------------ #

    # Existing orgs keyed by lowercased name for case-insensitive match
    existing_orgs = await organizations.list()
    orgs_by_name: dict[str, object] = {o.name.lower(): o for o in existing_orgs}

    # Existing Autotask mappings keyed by entity_id (Autotask company ID as str)
    existing_mappings = await integrations.list_mappings("Autotask") or []
    mapped_entity_ids: set[str] = {m.entity_id for m in existing_mappings}
    orgs_by_id: dict[str, object] = {o.id: o for o in existing_orgs}

    # ------------------------------------------------------------------ #
    # 3. Sync each Autotask company                                       #
    # ------------------------------------------------------------------ #
    results = {"created_orgs": 0, "mapped": 0, "already_mapped": 0, "errors": []}

    # Always link MTG itself (id=0) to the MTG Bifrost org
    MTG_AT_ID = "0"
    MTG_ORG_NAME = "Midtown Technology Group"

    for company in at_companies:
        at_id = str(company["id"])
        at_name: str = company["companyName"]

        # Skip if mapping already exists
        if at_id in mapped_entity_ids:
            results["already_mapped"] += 1
            continue

        try:
            # Find or create the Bifrost org
            org = orgs_by_name.get(at_name.lower())
            if org is None:
                org = await organizations.create(at_name)
                orgs_by_name[at_name.lower()] = org
                results["created_orgs"] += 1

            # Create the IntegrationMapping
            await integrations.upsert_mapping(
                name="Autotask",
                scope=org.id,
                entity_id=at_id,
                entity_name=at_name,
            )
            results["mapped"] += 1

        except Exception as exc:
            results["errors"].append({"company": at_name, "at_id": at_id, "error": str(exc)})

    results["total_at_companies"] = len(at_companies)
    return results
