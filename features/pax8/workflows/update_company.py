"""
Pax8: Update Company
"""

from bifrost import workflow
from modules.pax8 import Pax8Client


@workflow(
    name="Pax8: Update Company",
    description="Update a Pax8 company name.",
    category="Pax8",
    tags=["pax8", "update"],
)
async def update_pax8_company(
    company_id: str,
    name: str,
) -> dict:
    from modules.pax8 import get_client

    client = await get_client(scope="global")
    try:
        current = await client.get_company(company_id)
        update_payload = {"name": name}

        # Pax8 rejects sparse company patches and expects core fields to remain present.
        for field in (
            "phone",
            "website",
            "selfServiceAllowed",
            "billOnBehalfOfEnabled",
            "orderApprovalRequired",
            "externalId",
        ):
            if field in current and current[field] is not None:
                update_payload[field] = current[field]

        address = current.get("address")
        if address:
            update_payload["address"] = address

        company = await client.update_company(company_id, **update_payload)
    finally:
        await client.close()

    normalized = Pax8Client.normalize_company(company)
    return {
        "company": {
            "id": normalized["id"],
            "name": normalized["name"],
        }
    }
