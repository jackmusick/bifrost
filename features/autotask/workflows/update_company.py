"""
Autotask company update workflows.
"""

from __future__ import annotations

from bifrost import workflow
from modules.autotask import AutotaskClient


@workflow(
    name="Autotask: Update Company",
    description="Update an AutoTask company by explicit company ID or the current org mapping.",
    category="Autotask",
    tags=["autotask", "company", "update"],
)
async def update_autotask_company(
    company_id: str | None = None,
    company_name: str | None = None,
    extra_fields: dict | None = None,
) -> dict:
    from modules.autotask import get_client

    if company_name in (None, "") and not extra_fields:
        raise RuntimeError("Provide company_name or extra_fields to update the company.")

    client = await get_client()
    try:
        company = await client.update_company(
            company_id=company_id,
            company_name=company_name,
            extra_fields=extra_fields,
        )
    finally:
        await client.close()

    return {
        "company": AutotaskClient.normalize_company(company),
        "raw": company,
    }
