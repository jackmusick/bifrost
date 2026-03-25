"""
Shared HaloPSA Agreement Tools

Look up what service agreements a client has (Unified IT, Managed IT, etc.).
"""

from bifrost import tool
from modules import halopsa
from modules.extensions.halopsa import paginate

# Lookup 76 = agreement subtypes. These are the effective agreement levels.
AGREEMENT_TYPES = {
    1: "Unified IT",
    2: "Managed IT",
    3: "Security Essentials",
    4: "Cloud Management",
    5: "Network Management",
}


@tool(
    description=(
        "Get the active service agreements for a HaloPSA client. "
        "Returns agreement types like Unified IT, Managed IT, Security Essentials. "
        "Use this to determine what services are in scope for a customer."
    )
)
async def get_customer_agreements(client_id: int) -> dict:
    """Look up active contracts for a client and return their agreement types.

    Args:
        client_id: The HaloPSA client ID.
    """
    contracts = await paginate(
        halopsa.list_client_contracts,
        client_id=client_id,
        includeinactive=False,
    )

    agreements = []
    for c in contracts:
        c = c if isinstance(c, dict) else dict(c)

        # Skip expired or inactive
        if c.get("expired") or not c.get("active"):
            continue

        subtype = c.get("subtype") or 0
        agreement_name = AGREEMENT_TYPES.get(subtype, f"Other (subtype {subtype})")

        agreements.append({
            "contract_id": c.get("id"),
            "ref": c.get("ref"),
            "agreement_type": agreement_name,
            "subtype_id": subtype,
            "status": c.get("contract_status"),
            "start_date": c.get("start_date"),
            "end_date": c.get("end_date"),
        })

    # Derive a simple summary
    agreement_names = [a["agreement_type"] for a in agreements]
    has_unified = "Unified IT" in agreement_names

    return {
        "client_id": client_id,
        "agreements": agreements,
        "agreement_types": agreement_names,
        "has_unified_it": has_unified,
        "includes_config_hardening": has_unified,
    }
