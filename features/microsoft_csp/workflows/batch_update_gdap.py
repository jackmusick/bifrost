"""
Batch Update GDAP Assignments

Loops through all organizations with M365 tenants and syncs GDAP assignments
for any active relationships to match the template.
"""

import logging

from bifrost import workflow, integrations

logger = logging.getLogger(__name__)


@workflow(
    category="Microsoft CSP",
    tags=["gdap", "batch", "update"],
)
async def batch_update_gdap() -> dict:
    """
    Sync GDAP assignments for all tenants with active relationships.

    Iterates all Microsoft integration mappings to find tenants,
    then calls update_gdap_assignments for each.

    Returns:
        dict with summary counts
    """
    from features.microsoft_csp.workflows.update_gdap_assignments import (
        update_gdap_assignments,
    )

    # Get all Microsoft mappings (tenant_id -> org)
    mappings = await integrations.list_mappings("Microsoft") or []

    results = {
        "total": len(mappings),
        "synced": 0,
        "skipped": 0,
        "no_relationship": 0,
        "errors": [],
    }

    for mapping in mappings:
        tenant_id = str(mapping.entity_id)
        tenant_name = getattr(mapping, "entity_name", tenant_id)

        try:
            result = await update_gdap_assignments(
                tenant_id=tenant_id,
                tenant_name=tenant_name,
            )

            if result.get("success"):
                results["synced"] += 1
            elif result.get("status") == "none":
                results["no_relationship"] += 1
            else:
                results["skipped"] += 1

        except Exception as e:
            logger.error(f"Failed to sync GDAP for {tenant_name}: {e}")
            results["errors"].append({
                "tenant_id": tenant_id,
                "tenant_name": tenant_name,
                "error": str(e),
            })

    logger.info(
        f"Batch GDAP sync: {results['synced']} synced, "
        f"{results['skipped']} skipped, "
        f"{results['no_relationship']} no relationship, "
        f"{len(results['errors'])} errors"
    )

    return {"success": True, **results}
