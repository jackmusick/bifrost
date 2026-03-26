"""
Google Workspace: Sync Current Tenant

Discovers the current tenant for an org-scoped direct Google Workspace
integration and stores the customer mapping on that org.
"""

from bifrost import workflow
from bifrost import context, integrations, organizations
from modules import googleworkspace


@workflow(
    name="Google Workspace: Sync Current Tenant",
    description="Discover and bind the current org-scoped Google Workspace tenant.",
    category="Google Workspace",
    tags=["google", "workspace"],
)
async def sync_google_workspace_tenant(org_id: str = "") -> dict:
    effective_org = org_id or context.org_id
    if not effective_org:
        raise RuntimeError(
            "Google Workspace tenant sync requires an org scope or org_id argument"
        )

    if org_id:
        context.set_scope(org_id)

    org = await organizations.get(effective_org)
    client = await googleworkspace.get_workspace_client(scope=effective_org)
    try:
        summary = await client.get_tenant_summary()
    finally:
        await client.close()

    normalized = googleworkspace.GoogleWorkspaceClient.normalize_customer(
        summary["customer"],
        summary["domains"],
    )
    if not normalized["id"]:
        raise RuntimeError(
            "Google Workspace tenant sync could not determine a customer ID"
        )

    await integrations.upsert_mapping(
        "Google Workspace",
        scope=effective_org,
        entity_id=normalized["id"],
        entity_name=normalized["name"],
    )

    return {
        "org_id": effective_org,
        "org_name": org.name,
        "customer_id": normalized["id"],
        "customer_name": normalized["name"],
        "primary_domain": normalized["primary_domain"],
        "domain_count": len(summary["domains"]),
    }
