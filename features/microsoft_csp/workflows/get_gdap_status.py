"""
Get GDAP Status

Bulk queries all GDAP relationships and returns status per tenant.
Single API call, matched client-side for performance.
"""

import logging

from bifrost import workflow

from modules.microsoft.auth import get_graph_token
from modules.microsoft.graph import GraphClient
from modules.microsoft import gdap

logger = logging.getLogger(__name__)


@workflow(
    category="Microsoft CSP",
    tags=["gdap", "status"],
)
async def get_gdap_status() -> dict:
    """
    Get GDAP relationship status for all tenants.

    Makes a single bulk query to Graph API, then matches relationships
    to tenants by customer.tenantId.

    Returns:
        dict with gdap_by_tenant mapping: tenant_id -> status info
    """
    token = await get_graph_token("common")
    graph = GraphClient(token)

    # Single bulk query — all relationships
    all_relationships = gdap.list_relationships(graph)

    # Group by tenant
    by_tenant: dict[str, list] = {}
    for rel in all_relationships:
        customer = rel.get("customer", {})
        tid = customer.get("tenantId")
        if tid:
            by_tenant.setdefault(tid, []).append(rel)

    # Build per-tenant summary (best relationship) and full relationship list
    gdap_by_tenant = {}
    for tid, rels in by_tenant.items():
        best = gdap.find_best_relationship(rels)
        if best:
            gdap_by_tenant[tid] = {
                "status": best.get("status", "unknown"),
                "relationship_id": best.get("id", ""),
                "display_name": best.get("displayName", ""),
                "approval_url": (
                    gdap.get_approval_url(best["id"])
                    if best.get("status") in ("approvalPending", "created")
                    else None
                ),
                "relationships": [
                    {
                        "id": r.get("id", ""),
                        "display_name": r.get("displayName", ""),
                        "status": r.get("status", "unknown"),
                    }
                    for r in rels
                ],
            }

    return {
        "gdap_by_tenant": gdap_by_tenant,
        "total_relationships": len(all_relationships),
        "tenants_with_gdap": len(gdap_by_tenant),
    }
