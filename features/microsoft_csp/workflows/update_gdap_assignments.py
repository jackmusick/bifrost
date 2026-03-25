"""
Update GDAP Assignments

Syncs access assignments on an active GDAP relationship to match the
gdap_template table. Creates missing, updates changed, removes stale.
"""

import logging

from bifrost import workflow, tables, context, UserError

from modules.microsoft.auth import get_graph_token
from modules.microsoft.graph import GraphClient
from modules.microsoft import gdap

logger = logging.getLogger(__name__)

TEMPLATE_TABLE = "gdap_template"


@workflow(
    category="Microsoft CSP",
    tags=["gdap", "update", "assignments"],
)
async def update_gdap_assignments(
    tenant_id: str,
    tenant_name: str | None = None,
) -> dict:
    """
    Sync GDAP assignments to match the template for a single tenant.

    Finds the active GDAP relationship, loads template from table,
    and syncs assignments (create/update/remove).

    Args:
        tenant_id: Customer Entra tenant ID
        tenant_name: Customer name (for display/logging)

    Returns:
        dict with sync results
    """
    provider_org_id = context.org_id
    display = tenant_name or tenant_id

    # 1. Find active relationship
    token = await get_graph_token("common")
    graph = GraphClient(token)

    relationships = gdap.list_relationships(graph, tenant_id=tenant_id)
    best = gdap.find_best_relationship(relationships)

    if not best:
        return {
            "success": False,
            "tenant_id": tenant_id,
            "tenant_name": display,
            "error": "No GDAP relationship found",
            "status": "none",
        }

    status = best.get("status")
    rel_id = best.get("id", "")

    if status != "active":
        return {
            "success": False,
            "tenant_id": tenant_id,
            "tenant_name": display,
            "error": f"Relationship is '{status}', must be 'active' to sync",
            "status": status,
            "relationship_id": rel_id,
        }

    # 2. Load template
    template_result = await tables.query(
        TEMPLATE_TABLE, scope=provider_org_id, limit=1000
    )
    template_groups = [
        doc.data for doc in template_result.documents
        if doc.data.get("enabled", True)
    ]

    if not template_groups:
        raise UserError("No GDAP template configured")

    # 3. Build template assignments format
    template_assignments = []
    for group in template_groups:
        group_id = group.get("security_group_id")
        roles = group.get("unified_roles", [])
        if group_id and roles:
            template_assignments.append({
                "accessContainer": {"accessContainerId": group_id},
                "accessDetails": {
                    "unifiedRoles": [
                        {"roleDefinitionId": r["roleDefinitionId"]}
                        for r in roles
                    ]
                },
            })

    # 4. Sync
    counts = gdap.sync_assignments(graph, rel_id, template_assignments)

    logger.info(
        f"GDAP sync for {display}: "
        f"{counts['created']} created, {counts['updated']} updated, "
        f"{counts['removed']} removed"
    )

    return {
        "success": True,
        "tenant_id": tenant_id,
        "tenant_name": display,
        "relationship_id": rel_id,
        "status": "active",
        **counts,
    }
