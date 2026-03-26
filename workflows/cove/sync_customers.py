"""
Cove Data Protection → Bifrost customer sync.

Fetches EndCustomer partner records from Cove and ensures each has a
corresponding Bifrost organization with an IntegrationMapping linking back
to the Cove partner ID.

Safe to run repeatedly — idempotent via upsert on both orgs and mappings.

Wire format: JSON-RPC 2.0 over HTTPS.
  - params must be a named dict, not a positional list
  - Login returns a visa that must be passed at the top level of all subsequent calls
  - fields=[64] returns the Name field from EnumeratePartners
  - State is not available via EnumeratePartners; all EndCustomers are synced
"""

import httpx
from bifrost import integrations, organizations, workflow

ACTIVE_LEVELS = {"EndCustomer"}


def _rpc(method: str, params: dict, visa: str | None = None, call_id: str = "1") -> dict:
    """Build a Cove JSON-RPC 2.0 request body."""
    body: dict = {"jsonrpc": "2.0", "method": method, "params": params, "id": call_id}
    if visa:
        body["visa"] = visa
    return body


@workflow(
    name="Cove: Sync Customers",
    description=(
        "Sync Cove EndCustomer partner records to Bifrost organizations. "
        "Creates any missing orgs and keeps IntegrationMappings up to date. "
        "Safe to run repeatedly."
    ),
)
async def sync_cove_customers() -> dict:
    cove = await integrations.get("Cove", scope="global")
    if not cove:
        raise RuntimeError("Cove integration not configured or credentials missing")

    base_url = cove.config["base_url"]
    partner_name = cove.config["partner_name"]
    username = cove.config["username"]
    password = cove.config["password"]

    # ------------------------------------------------------------------ #
    # 1. Fetch all EndCustomer partners from Cove                         #
    # ------------------------------------------------------------------ #
    async with httpx.AsyncClient(verify=False) as client:
        # Login — returns visa required for all subsequent calls
        login_resp = await client.post(
            f"{base_url}?account&Login",
            json=_rpc("Login", {"partner": partner_name, "username": username, "password": password}),
        )
        login_resp.raise_for_status()
        login_data = login_resp.json()
        visa = login_data["visa"]

        # Resolve our own partner ID
        info_resp = await client.post(
            f"{base_url}?account&GetPartnerInfo",
            json=_rpc("GetPartnerInfo", {"name": partner_name}, visa=visa, call_id="2"),
        )
        info_resp.raise_for_status()
        info_data = info_resp.json()
        our_id = info_data["result"]["result"]["Id"]
        visa = info_data.get("visa", visa)

        # Enumerate all child partners recursively.
        # fields=[64] returns the Name field. State not available here;
        # all EndCustomers are synced regardless of state.
        enum_resp = await client.post(
            f"{base_url}?account&EnumeratePartners",
            json=_rpc("EnumeratePartners", {
                "parentPartnerId": our_id,
                "fetchRecursively": True,
                "fields": [64],
            }, visa=visa, call_id="3"),
        )
        enum_resp.raise_for_status()
        all_partners = enum_resp.json()["result"]["result"]

    # Filter to EndCustomers with a non-null Name
    customers = [
        p for p in all_partners
        if p.get("Level") in ACTIVE_LEVELS and p.get("Name")
    ]

    # ------------------------------------------------------------------ #
    # 2. Build lookup maps for what already exists in Bifrost             #
    # ------------------------------------------------------------------ #
    existing_orgs = await organizations.list()
    orgs_by_name: dict[str, object] = {o.name.lower(): o for o in existing_orgs}

    existing_mappings = await integrations.list_mappings("Cove") or []
    mapped_entity_ids: set[str] = {m.entity_id for m in existing_mappings}

    # ------------------------------------------------------------------ #
    # 3. Sync each Cove EndCustomer                                       #
    # ------------------------------------------------------------------ #
    results = {
        "created_orgs": 0,
        "mapped": 0,
        "already_mapped": 0,
        "name_matched_existing_org": [],
        "errors": [],
        "total_cove_customers": len(customers),
    }

    for partner in customers:
        cove_id = str(partner["Id"])
        cove_name: str = partner["Name"]

        if cove_id in mapped_entity_ids:
            results["already_mapped"] += 1
            continue

        try:
            org = orgs_by_name.get(cove_name.lower())
            if org is None:
                org = await organizations.create(cove_name)
                orgs_by_name[cove_name.lower()] = org
                results["created_orgs"] += 1
            else:
                results["name_matched_existing_org"].append(cove_name)

            await integrations.upsert_mapping(
                name="Cove",
                scope=org.id,
                entity_id=cove_id,
                entity_name=cove_name,
            )
            results["mapped"] += 1

        except Exception as exc:
            results["errors"].append({
                "partner": cove_name,
                "cove_id": cove_id,
                "error": str(exc),
            })

    return results
