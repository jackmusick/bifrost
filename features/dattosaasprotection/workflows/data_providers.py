"""
Datto SaaS Protection data providers for org mapping UI.
"""

from bifrost import data_provider
from modules.dattosaasprotection import DattoSaaSProtectionClient


@data_provider(
    name="Datto SaaS Protection: List Domains",
    description="Returns Datto SaaS Protection domains for org mapping picker.",
    category="Datto SaaS Protection",
    tags=["datto", "saas", "data-provider"],
)
async def list_dattosaas_domains() -> list[dict]:
    """Return Datto SaaS Protection domains as {value, label} options."""
    from modules.dattosaasprotection import get_client

    client = await get_client(scope="global")
    try:
        domains = await client.list_domains()
    finally:
        await client.close()

    options = []
    for domain in domains:
        normalized = DattoSaaSProtectionClient.normalize_domain(domain)
        if normalized["id"] and normalized["label"]:
            options.append(
                {
                    "value": normalized["id"],
                    "label": normalized["label"],
                }
            )

    return sorted(options, key=lambda item: item["label"].lower())
