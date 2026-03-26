"""
Cove Data Protection entity data providers for Bifrost integration UI.

Wire format: JSON-RPC 2.0 over HTTPS (NOT bare positional arrays).
  - params must be a named dict, not a positional list
  - Login returns a visa that must be passed at the top level of every subsequent call
  - fields=[64] returns the Name field in EnumeratePartners
"""

import httpx
from bifrost import data_provider, integrations

ACTIVE_LEVELS = {"EndCustomer"}


def _rpc(method: str, params: dict, visa: str | None = None, call_id: str = "1") -> dict:
    """Build a Cove JSON-RPC 2.0 request body."""
    body: dict = {"jsonrpc": "2.0", "method": method, "params": params, "id": call_id}
    if visa:
        body["visa"] = visa
    return body


@data_provider(
    name="Cove: List Partners",
    description="Returns active Cove EndCustomer partners for org mapping",
    category="Cove",
)
async def list_cove_partners() -> list[dict]:
    """Returns active Cove EndCustomer partner records as entity picker options."""
    cove = await integrations.get("Cove", scope="global")
    if not cove:
        return []

    base_url = cove.config["base_url"]
    partner_name = cove.config["partner_name"]
    username = cove.config["username"]
    password = cove.config["password"]

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
        # fields=[64] returns the Name field. State is not available via EnumeratePartners;
        # filter on Level=EndCustomer instead.
        enum_resp = await client.post(
            f"{base_url}?account&EnumeratePartners",
            json=_rpc("EnumeratePartners", {
                "parentPartnerId": our_id,
                "fetchRecursively": True,
                "fields": [64],
            }, visa=visa, call_id="3"),
        )
        enum_resp.raise_for_status()
        partners = enum_resp.json()["result"]["result"]

    return sorted(
        [
            {"value": str(p["Id"]), "label": p["Name"]}
            for p in partners
            if p.get("Level") in ACTIVE_LEVELS and p.get("Name")
        ],
        key=lambda x: x["label"],
    )
