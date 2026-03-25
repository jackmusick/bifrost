"""
Create GDAP Relationship

Creates a new GDAP relationship for a customer tenant using the template
roles from the gdap_template table. Locks for approval and returns the
approval URL.
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
    tags=["gdap", "create", "relationship"],
)
async def create_gdap_relationship(
    tenant_id: str,
    tenant_name: str | None = None,
    domain: str | None = None,
    send_email: bool = False,
    admin_email: str | None = None,
) -> dict:
    """
    Create a new GDAP relationship for a customer tenant.

    Uses roles from the gdap_template table. Creates the relationship,
    locks for approval, and optionally emails the customer.

    Args:
        tenant_id: Customer Entra tenant ID
        tenant_name: Customer name (for email/display)
        domain: Customer primary domain (for consumer domain check)
        send_email: Whether to email the approval link
        admin_email: Customer admin email (required if send_email=True)

    Returns:
        dict with relationship_id, status, approval_url
    """
    provider_org_id = context.org_id

    # 1. Consumer domain guard
    if domain and gdap.is_consumer_domain(domain):
        raise UserError(
            f"Cannot create GDAP relationship for consumer domain '{domain}'. "
            "GDAP is only supported for Microsoft 365 business tenants."
        )

    # 2. Load template from table
    template_result = await tables.query(
        TEMPLATE_TABLE, scope=provider_org_id, limit=1000
    )
    template_groups = [
        doc.data for doc in template_result.documents
        if doc.data.get("enabled", True)
    ]

    if not template_groups:
        raise UserError(
            "No GDAP template configured. "
            "Use 'Seed from Dev Tenant' to set up the template first."
        )

    # 3. Build unified roles list (all roles from all enabled groups)
    unified_roles = []
    seen_role_ids = set()
    for group in template_groups:
        for role in group.get("unified_roles", []):
            role_id = role.get("roleDefinitionId")
            if role_id and role_id not in seen_role_ids:
                unified_roles.append({"roleDefinitionId": role_id})
                seen_role_ids.add(role_id)

    if not unified_roles:
        raise UserError("GDAP template has no roles configured")

    # 4. Check for existing relationship
    token = await get_graph_token("common")
    graph = GraphClient(token)

    existing = gdap.list_relationships(graph, tenant_id=tenant_id)
    best = gdap.find_best_relationship(existing)

    if best:
        status = best.get("status")
        rel_id = best.get("id", "")
        if status == "active":
            return {
                "success": False,
                "error": "Active GDAP relationship already exists",
                "relationship_id": rel_id,
                "status": status,
                "approval_url": None,
            }
        if status in ("approvalPending", "created"):
            return {
                "success": True,
                "relationship_id": rel_id,
                "status": status,
                "approval_url": gdap.get_approval_url(rel_id),
                "message": "Existing relationship pending approval",
            }

    # 5. Create relationship
    relationship = gdap.create_relationship(
        graph, tenant_id, unified_roles
    )
    rel_id = relationship.get("id", "")
    approval_url = relationship.get("approval_url", gdap.get_approval_url(rel_id))

    logger.info(f"Created GDAP relationship {rel_id} for tenant {tenant_id}")

    # 6. Optionally email the customer
    if send_email and admin_email:
        try:
            from modules.extensions.sendgrid import send_email as sg_send
            display_name = tenant_name or tenant_id

            html_body = f"""
<div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
  <h2 style="color: #1a1a1a;">GDAP Relationship Request</h2>
  <p>Hello,</p>
  <p>We've submitted a Granular Delegated Admin Privileges (GDAP) request for <strong>{display_name}</strong>.</p>
  <p>GDAP allows us to securely manage your Microsoft 365 environment with the minimum permissions needed. This replaces the older DAP (Delegated Admin Privileges) model with more granular, time-limited access.</p>
  <p>Please click the button below to review and approve the request in the Microsoft Admin Portal:</p>
  <p style="text-align: center; margin: 30px 0;">
    <a href="{approval_url}" style="background-color: #0078D4; color: white; padding: 12px 24px; text-decoration: none; border-radius: 6px; font-weight: 600;">Review &amp; Approve</a>
  </p>
  <p style="color: #666; font-size: 14px;">If the button doesn't work, copy and paste this URL into your browser:</p>
  <p style="color: #666; font-size: 14px; word-break: break-all;">{approval_url}</p>
  <hr style="border: none; border-top: 1px solid #eee; margin: 30px 0;" />
  <p style="color: #999; font-size: 12px;">This is an automated message from your IT service provider.</p>
</div>
"""
            await sg_send(
                recipient=admin_email,
                subject=f"GDAP Approval Request — {display_name}",
                body=f"Please approve the GDAP request for {display_name}: {approval_url}",
                html_body=html_body,
            )
            logger.info(f"Approval email sent to {admin_email}")
        except Exception as e:
            logger.error(f"Failed to send approval email: {e}")

    return {
        "success": True,
        "relationship_id": rel_id,
        "status": relationship.get("status", "approvalPending"),
        "approval_url": approval_url,
        "display_name": relationship.get("displayName", ""),
        "email_sent": send_email and admin_email is not None,
    }
