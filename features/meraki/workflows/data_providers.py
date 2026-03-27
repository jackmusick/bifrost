"""
Meraki data providers for org mapping UI.
"""

from bifrost import data_provider
from modules.meraki import MerakiClient


@data_provider(
    name="Meraki: List Organizations",
    description="Returns Meraki organizations for org mapping picker.",
    category="Meraki",
    tags=["meraki", "data-provider"],
)
async def list_meraki_organizations() -> list[dict]:
    """Return Meraki organizations as {value, label} options for org mapping."""
    from modules.meraki import get_client

    client = await get_client(scope="global")
    try:
        organizations = await client.list_organizations()
    finally:
        await client.close()

    options = []
    for organization in organizations:
        normalized = MerakiClient.normalize_organization(organization)
        if normalized["id"] and normalized["name"]:
            options.append(
                {
                    "value": normalized["id"],
                    "label": normalized["name"],
                }
            )

    return sorted(options, key=lambda item: item["label"].lower())


@data_provider(
    name="Meraki: List Organization Names",
    description="Returns Meraki organization names for admin governance pickers.",
    category="Meraki",
    tags=["meraki", "data-provider", "governance"],
)
async def list_meraki_organization_names() -> list[dict]:
    """Return Meraki organization names as {value, label} options."""
    options = await list_meraki_organizations()
    return [
        {
            "value": item["label"],
            "label": item["label"],
        }
        for item in options
    ]


@data_provider(
    name="Meraki: List Baseline Admin Options",
    description="Returns baseline Meraki admins as picker options for governance policy.",
    category="Meraki",
    tags=["meraki", "data-provider", "governance"],
)
async def list_meraki_baseline_admin_options(
    baseline_org_name: str = "Midtown Technology Group",
) -> list[dict]:
    """Return baseline org admins as {value, label} options."""
    from modules.meraki import get_client

    client = await get_client(scope="global")
    try:
        organizations = await client.list_organizations()
        baseline_org_id = None
        for organization in organizations:
            normalized = MerakiClient.normalize_organization(organization)
            if normalized["name"] == baseline_org_name:
                baseline_org_id = normalized["id"]
                break
        if not baseline_org_id:
            raise RuntimeError(
                f"Baseline organization '{baseline_org_name}' was not found in Meraki."
            )

        admins = await client.list_organization_admins(baseline_org_id)
    finally:
        await client.close()

    options = []
    for admin in admins:
        normalized = MerakiClient.normalize_admin(admin)
        if normalized["email"]:
            label = normalized["email"]
            if normalized["name"] and normalized["name"] != normalized["email"]:
                label = f"{normalized['name']} ({normalized['email']})"
            options.append(
                {
                    "value": normalized["email"],
                    "label": label,
                }
            )

    return sorted(options, key=lambda item: item["label"].lower())
