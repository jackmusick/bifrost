"""
Quoter data providers for org mapping UI.
"""


async def list_quoter_organizations() -> list[dict]:
    """Return inferred Quoter organizations as {value, label} options."""
    from modules.quoter import get_client

    client = await get_client(scope="global")
    try:
        organizations = await client.infer_organizations_from_contacts()
    finally:
        await client.close()

    return [
        {"value": organization["id"], "label": organization["name"]}
        for organization in organizations
        if organization["id"] and organization["name"]
    ]

