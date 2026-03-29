"""
Autotask ticket note workflows.
"""

from __future__ import annotations

from typing import Any

from bifrost import integrations, workflow


def _resolve_note_default(explicit: str | None, config: dict[str, Any], *keys: str) -> str | None:
    if explicit not in (None, ""):
        return explicit
    for key in keys:
        value = config.get(key)
        if value not in (None, ""):
            return str(value)
    return None


@workflow(
    name="Autotask: Create Ticket Note",
    description="Create an AutoTask note on an existing ticket.",
    category="Autotask",
    tags=["autotask", "ticketing"],
)
async def create_autotask_ticket_note(
    ticket_id: str,
    description: str,
    note_type: str | None = None,
    publish: str | None = None,
    title: str = "",
    extra_fields: dict | None = None,
    use_integration_defaults: bool = True,
) -> dict:
    integration = await integrations.get("Autotask")
    if not integration:
        raise RuntimeError("Integration 'Autotask' not configured")

    integration_config = integration.config or {}
    resolved_note_type = note_type
    resolved_publish = publish

    if use_integration_defaults:
        resolved_note_type = _resolve_note_default(
            note_type,
            integration_config,
            "default_ticket_note_type",
            "ticket_note_type",
        ) or "3"
        resolved_publish = _resolve_note_default(
            publish,
            integration_config,
            "default_ticket_note_publish",
            "ticket_note_publish",
        ) or "1"
    resolved_title = title
    if resolved_title in (None, ""):
        resolved_title = _resolve_note_default(
            None,
            integration_config,
            "default_ticket_note_title",
            "ticket_note_title",
        ) or "Bifrost Automation Note"

    from modules.autotask import get_client

    client = await get_client()
    try:
        note = await client.create_ticket_note(
            ticket_id=ticket_id,
            description=description,
            note_type=resolved_note_type,
            publish=resolved_publish,
            title=resolved_title,
            extra_fields=extra_fields,
        )
    finally:
        await client.close()

    return {"note": note}
