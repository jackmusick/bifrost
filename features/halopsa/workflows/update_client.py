"""
HaloPSA client update workflows.
"""

from __future__ import annotations

from bifrost import integrations, workflow
from modules import halopsa


def _normalize_client(area) -> dict:
    if hasattr(area, "to_dict"):
        area = area.to_dict()
    if not isinstance(area, dict):
        area = {}
    client_id = area.get("id")
    return {
        "id": str(client_id) if client_id is not None else "",
        "name": area.get("name") or "",
        "inactive": area.get("inactive"),
    }


@workflow(
    name="HaloPSA: Update Client",
    description="Update a HaloPSA client by explicit client ID or the current org mapping.",
    category="HaloPSA",
    tags=["halopsa", "client", "update"],
)
async def update_halopsa_client(
    client_id: str | None = None,
    name: str | None = None,
    extra_fields: dict | None = None,
) -> dict:
    if name in (None, "") and not extra_fields:
        raise RuntimeError("Provide name or extra_fields to update the HaloPSA client.")

    target_client_id = client_id
    if target_client_id is None:
        mapping = await integrations.get_mapping("HaloPSA")
        if not mapping or not mapping.entity_id:
            raise RuntimeError(
                "HaloPSA client ID is not available. Configure an org mapping first."
            )
        target_client_id = str(mapping.entity_id)

    payload = dict(extra_fields or {})
    payload["id"] = int(str(target_client_id))
    if name not in (None, ""):
        payload["name"] = name

    # HaloPSA uses POST /Client with an array of Area objects for client writes.
    await halopsa.create_client([payload])
    client = await halopsa.get_client(str(target_client_id))

    return {
        "client": _normalize_client(client),
        "raw": client,
    }
