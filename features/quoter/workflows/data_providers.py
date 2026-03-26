"""
Quoter data providers for org mapping UI.
"""


from bifrost import data_provider
@data_provider(
    name="Quoter: List Organizations",
    description="Returns Quoter organizations inferred from contacts for org mapping picker.",
    category="Quoter",
    tags=["quoter", "data-provider"],
)
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

