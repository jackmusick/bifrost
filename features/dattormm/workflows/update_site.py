"""
Datto RMM site update workflows.
"""

from __future__ import annotations

from bifrost import workflow
from modules.dattormm import DattoRMMClient


@workflow(
    name="Datto RMM: Update Site",
    description="Update a Datto RMM site by explicit site UID or the current org mapping.",
    category="Datto RMM",
    tags=["dattormm", "site", "update"],
)
async def update_dattormm_site(
    site_uid: str | None = None,
    name: str | None = None,
    extra_fields: dict | None = None,
) -> dict:
    from modules.dattormm import get_client

    if name in (None, "") and not extra_fields:
        raise RuntimeError("Provide name or extra_fields to update the Datto RMM site.")

    client = await get_client()
    try:
        site = await client.update_site(
            site_uid=site_uid,
            name=name,
            extra_fields=extra_fields,
        )
    finally:
        await client.close()

    return {
        "site": DattoRMMClient.normalize_site(site),
        "raw": site,
    }
