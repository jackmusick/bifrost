"""
Microsoft GDAP Relationship Management

Helpers for managing Granular Delegated Admin Privileges (GDAP) relationships
via the Microsoft Graph API.

All functions take a GraphClient instance configured for the partner tenant.
Use get_graph_token("common") or partner tenant ID for the token.

Docs: https://learn.microsoft.com/en-us/graph/api/resources/delegatedadminrelationships-api-overview
"""

import logging
import uuid
from typing import Any

from modules.microsoft.graph import GraphClient

logger = logging.getLogger(__name__)

GDAP_BASE = "/tenantRelationships/delegatedAdminRelationships"

# Consumer domains that cannot have GDAP relationships
CONSUMER_DOMAINS = {
    "outlook.com", "hotmail.com", "live.com", "msn.com",
    "gmail.com", "yahoo.com", "aol.com", "icloud.com",
    "me.com", "mac.com", "mail.com", "protonmail.com",
    "zoho.com", "yandex.com",
}

APPROVAL_URL_TEMPLATE = (
    "https://admin.microsoft.com/AdminPortal/Home"
    "#/partners/invitation/granularAdminRelationships/{relationship_id}"
)

# The GDAP relationship used as the role/group template — excluded from updates
TEMPLATE_RELATIONSHIP_ID = "c6da307c-f1be-48eb-8b01-6e20a09df0ed-fc8fef79-d325-497b-ab24-0f878ee59520"


def is_consumer_domain(domain: str) -> bool:
    """Check if a domain is a consumer email domain (cannot have GDAP)."""
    domain = domain.lower().strip()
    # Check the domain itself and the root (e.g., "sub.outlook.com" -> "outlook.com")
    parts = domain.split(".")
    if len(parts) >= 2:
        root = ".".join(parts[-2:])
        return root in CONSUMER_DOMAINS
    return domain in CONSUMER_DOMAINS


def get_approval_url(relationship_id: str) -> str:
    """Construct the deterministic admin portal approval URL."""
    return APPROVAL_URL_TEMPLATE.format(relationship_id=relationship_id)


def list_relationships(
    graph: GraphClient,
    tenant_id: str | None = None,
) -> list[dict[str, Any]]:
    """
    List GDAP relationships, optionally filtered by customer tenant ID.

    Args:
        graph: GraphClient configured for partner tenant
        tenant_id: Optional customer tenant ID to filter by

    Returns:
        List of relationship objects
    """
    params = {}
    if tenant_id:
        params["$filter"] = f"customer/tenantId eq '{tenant_id}'"

    return graph.paginate(GDAP_BASE, params=params if params else None)


def get_relationship(graph: GraphClient, relationship_id: str) -> dict[str, Any]:
    """Get a single GDAP relationship by ID."""
    return graph.get(f"{GDAP_BASE}/{relationship_id}")


def find_best_relationship(
    relationships: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """
    Find the best relationship from a list (prefer active > approvalPending > created).

    Excludes the template relationship (TEMPLATE_RELATIONSHIP_ID).
    Returns None if no valid relationship found.
    """
    priority = {"active": 0, "approved": 1, "approvalPending": 2, "created": 3}
    valid = [
        r for r in relationships
        if r.get("status") in priority and r.get("id") != TEMPLATE_RELATIONSHIP_ID
    ]
    if not valid:
        return None
    valid.sort(key=lambda r: priority.get(r.get("status", ""), 99))
    return valid[0]


def create_relationship(
    graph: GraphClient,
    tenant_id: str,
    unified_roles: list[dict[str, str]],
    duration: str = "P730D",
    auto_extend: str = "P180D",
) -> dict[str, Any]:
    """
    Create a new GDAP relationship and lock it for approval.

    Args:
        graph: GraphClient configured for partner tenant
        tenant_id: Customer tenant ID
        unified_roles: List of {"roleDefinitionId": "..."} role objects
        duration: Relationship duration (default 2 years)
        auto_extend: Auto-extend duration (default 180 days)

    Returns:
        Created relationship object with id, status, approval_url
    """
    display_name = f"GDAP-{uuid.uuid4()}"

    body = {
        "displayName": display_name,
        "customer": {"tenantId": tenant_id},
        "accessDetails": {"unifiedRoles": unified_roles},
        "duration": duration,
        "autoExtendDuration": auto_extend,
    }

    logger.info(f"Creating GDAP relationship for tenant {tenant_id}")
    relationship = graph.post(GDAP_BASE, body)
    relationship_id = relationship.get("id", "")

    # Lock for approval
    if relationship.get("status") == "created":
        logger.info(f"Locking relationship {relationship_id} for approval")
        graph.post(
            f"{GDAP_BASE}/{relationship_id}/requests",
            {"action": "lockForApproval"},
        )
        relationship["status"] = "approvalPending"

    relationship["approval_url"] = get_approval_url(relationship_id)
    return relationship


def list_assignments(
    graph: GraphClient,
    relationship_id: str,
) -> list[dict[str, Any]]:
    """
    List access assignments for a GDAP relationship.

    Returns only active assignments with accessContainer + accessDetails.
    """
    assignments = graph.paginate(
        f"{GDAP_BASE}/{relationship_id}/accessAssignments"
    )
    return [a for a in assignments if a.get("status") == "active"]


def sync_assignments(
    graph: GraphClient,
    relationship_id: str,
    template_assignments: list[dict[str, Any]],
) -> dict[str, int]:
    """
    Sync access assignments on a relationship to match the template.

    Compares by accessContainerId (security group ID):
    - Creates assignments for groups in template but not in current
    - Updates assignments for groups in both (always-push, overwrites roles)
    - Removes assignments for groups in current but not in template

    Args:
        graph: GraphClient configured for partner tenant
        relationship_id: GDAP relationship ID
        template_assignments: List of template assignments, each with:
            - accessContainer: {"accessContainerId": "group-uuid"}
            - accessDetails: {"unifiedRoles": [{"roleDefinitionId": "..."}]}

    Returns:
        Dict with counts: {"created": N, "updated": N, "removed": N}
    """
    base_path = f"{GDAP_BASE}/{relationship_id}/accessAssignments"
    current = list_assignments(graph, relationship_id)

    # Index by security group ID
    current_by_group = {
        a["accessContainer"]["accessContainerId"]: a for a in current
    }
    template_by_group = {
        a["accessContainer"]["accessContainerId"]: a for a in template_assignments
    }

    counts = {"created": 0, "updated": 0, "removed": 0}

    # Create missing assignments
    for group_id, template in template_by_group.items():
        if group_id not in current_by_group:
            logger.info(f"Creating assignment for group {group_id}")
            graph.post(base_path, {
                "accessContainer": template["accessContainer"],
                "accessDetails": template["accessDetails"],
            })
            counts["created"] += 1

    # Update existing assignments (always-push strategy)
    for group_id, current_assignment in current_by_group.items():
        if group_id in template_by_group:
            template = template_by_group[group_id]
            assignment_id = current_assignment["id"]
            etag = current_assignment.get("@odata.etag", "")
            headers = {"If-Match": etag} if etag else None

            logger.info(f"Updating assignment {assignment_id} for group {group_id}")
            graph.patch(
                f"{base_path}/{assignment_id}",
                {"accessDetails": template["accessDetails"]},
                headers=headers,
            )
            counts["updated"] += 1

    # Remove stale assignments
    for group_id, current_assignment in current_by_group.items():
        if group_id not in template_by_group:
            assignment_id = current_assignment["id"]
            etag = current_assignment.get("@odata.etag", "")
            headers = {"If-Match": etag} if etag else None

            logger.info(f"Removing assignment {assignment_id} for group {group_id}")
            graph.delete(f"{base_path}/{assignment_id}", headers=headers)
            counts["removed"] += 1

    return counts
