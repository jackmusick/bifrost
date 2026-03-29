"""
Autotask: Create Ticket

Reusable workflow for creating AutoTask tickets from Bifrost automations.
"""

from __future__ import annotations

from typing import Any

from bifrost import integrations, workflow
from modules.autotask import AutotaskClient


def _resolve_default(explicit: str | None, config: dict[str, Any], *keys: str) -> str | None:
    if explicit not in (None, ""):
        return explicit
    for key in keys:
        value = config.get(key)
        if value not in (None, ""):
            return str(value)
    return None


@workflow(
    name="Autotask: Create Ticket",
    description="Create an AutoTask ticket for the mapped customer or an explicit company ID.",
    category="Autotask",
    tags=["autotask", "ticketing"],
)
async def create_autotask_ticket(
    title: str,
    description: str = "",
    company_id: str | None = None,
    queue_id: str | None = None,
    issue_type: str | None = None,
    sub_issue_type: str | None = None,
    status: str | None = None,
    priority: str | None = None,
    source: str | None = None,
    due_date: str | None = None,
    extra_fields: dict | None = None,
    use_integration_defaults: bool = True,
) -> dict:
    integration = await integrations.get("Autotask")
    if not integration:
        raise RuntimeError("Integration 'Autotask' not configured")

    integration_config = integration.config or {}

    resolved_queue_id = queue_id
    resolved_issue_type = issue_type
    resolved_sub_issue_type = sub_issue_type
    resolved_status = status
    resolved_priority = priority
    resolved_source = source

    if use_integration_defaults:
        resolved_queue_id = _resolve_default(
            queue_id,
            integration_config,
            "default_ticket_queue_id",
            "ticket_queue_id",
        )
        resolved_issue_type = _resolve_default(
            issue_type,
            integration_config,
            "default_ticket_issue_type",
            "ticket_issue_type",
        )
        resolved_sub_issue_type = _resolve_default(
            sub_issue_type,
            integration_config,
            "default_ticket_sub_issue_type",
            "ticket_sub_issue_type",
        )
        resolved_status = _resolve_default(
            status,
            integration_config,
            "default_ticket_status",
            "ticket_status",
        )
        resolved_priority = _resolve_default(
            priority,
            integration_config,
            "default_ticket_priority",
            "ticket_priority",
        )
        resolved_source = _resolve_default(
            source,
            integration_config,
            "default_ticket_source",
            "ticket_source",
        )

    from modules.autotask import get_client

    client = await get_client()
    try:
        ticket = await client.create_ticket(
            title=title,
            description=description,
            company_id=company_id,
            queue_id=resolved_queue_id,
            issue_type=resolved_issue_type,
            sub_issue_type=resolved_sub_issue_type,
            status=resolved_status,
            priority=resolved_priority,
            source=resolved_source,
            due_date=due_date,
            extra_fields=extra_fields,
        )
    finally:
        await client.close()

    normalized = AutotaskClient.normalize_ticket(ticket)
    return {
        "ticket": normalized,
        "raw": ticket,
    }
