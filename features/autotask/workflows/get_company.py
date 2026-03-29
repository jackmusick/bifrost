"""
Autotask company lookup workflows.
"""

from __future__ import annotations

from bifrost import workflow
from modules.autotask import AutotaskClient


@workflow(
    name="Autotask: Get Company",
    description="Get an AutoTask company by explicit company ID or the current org mapping.",
    category="Autotask",
    tags=["autotask", "company"],
)
async def get_autotask_company(
    company_id: str | None = None,
) -> dict:
    from modules.autotask import get_client

    client = await get_client()
    try:
        company = await client.get_company(company_id)
    finally:
        await client.close()

    return {
        "company": AutotaskClient.normalize_company(company),
        "raw": company,
    }
