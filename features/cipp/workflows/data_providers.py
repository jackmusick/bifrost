"""
CIPP data providers for org mapping UI.
"""


from bifrost import data_provider
@data_provider(
    name="CIPP: List Tenants",
    description="Returns CIPP-managed tenants for org mapping picker.",
    category="CIPP",
    tags=["cipp", "data-provider"],
)
async def list_cipp_tenants() -> list[dict]:
    """
    Returns all non-excluded CIPP tenants as {value, label} pairs
    for use in the integration org-mapping picker.

    value = defaultDomainName
    label = displayName (falls back to domain if missing)
    """
    from modules.cipp import get_client

    client = await get_client()
    try:
        tenants = await client.list_tenants()
    finally:
        await client.close()

    return sorted(
        [
            {
                "value": t.get("defaultDomainName") or t.get("customerId", ""),
                "label": t.get("displayName") or t.get("defaultDomainName", ""),
            }
            for t in tenants
            if t.get("defaultDomainName") or t.get("customerId")
        ],
        key=lambda x: x["label"].lower(),
    )
