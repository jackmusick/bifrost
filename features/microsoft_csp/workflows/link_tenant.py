"""
Link CSP Tenant to Bifrost Organization

Links a Microsoft CSP tenant to a Bifrost organization,
enabling Graph API and other Microsoft integrations for that org.
"""

import logging
from datetime import datetime, timezone

from bifrost import workflow, tables, config, context, integrations, UserError

logger = logging.getLogger(__name__)

STATUS_TABLE = "csp_tenant_status"


@workflow(
    category="Microsoft CSP",
    tags=["microsoft", "csp", "link"],
)
async def link_csp_tenant(
    tenant_id: str,
    tenant_name: str,
    domain: str,
    customer_id: str,
    org_id: str | None,
    org_name: str | None,
) -> dict:
    """
    Link a CSP tenant to a Bifrost organization.

    This stores the mapping in the status table and also sets
    the entra_tenant_id config on the organization for Graph API access.

    Args:
        tenant_id: Microsoft Entra tenant ID
        tenant_name: Company name from Partner Center
        domain: Primary domain
        customer_id: Partner Center customer ID
        org_id: Bifrost organization ID to link (None to unlink)
        org_name: Organization name for display

    Returns:
        Updated tenant status
    """
    if not tenant_id:
        raise UserError("tenant_id is required")

    # Get provider org ID from context
    provider_org_id = context.org_id

    logger.info(
        "Linking CSP tenant",
        extra={
            "tenant_id": tenant_id,
            "tenant_name": tenant_name,
            "org_id": org_id,
        }
    )

    # Get existing status to preserve consent info (table may not exist yet)
    try:
        existing = await tables.get(STATUS_TABLE, tenant_id, scope=provider_org_id)
        existing_data = existing.data if existing else {}
    except Exception:
        existing_data = {}

    # Build updated status
    now = datetime.now(timezone.utc).isoformat()
    status_data = {
        "tenant_id": tenant_id,
        "tenant_name": tenant_name,
        "domain": domain,
        "customer_id": customer_id,
        "bifrost_org_id": org_id,
        "bifrost_org_name": org_name,
        # Preserve consent status
        "consent_status": existing_data.get("consent_status", "none"),
        "consent_error": existing_data.get("consent_error"),
        "consented_at": existing_data.get("consented_at"),
        "updated_at": now,
    }

    # Save to status table (scoped to provider org)
    await tables.upsert(STATUS_TABLE, id=tenant_id, data=status_data, scope=provider_org_id)

    # If linking to an org, set up Microsoft integration mapping
    if org_id:
        # Set entra_tenant_id config (legacy, for backwards compatibility)
        await config.set("entra_tenant_id", tenant_id, scope=org_id)

        # Create IntegrationMapping for Microsoft integration
        # This enables integrations.get("Microsoft") to resolve the tenant_id
        # and fetch a fresh token for client credentials access
        try:
            await integrations.upsert_mapping(
                "Microsoft",
                scope=org_id,
                entity_id=tenant_id,
                entity_name=tenant_name or domain or tenant_id,
            )
            logger.info(
                "Created IntegrationMapping for Microsoft",
                extra={"org_id": org_id, "tenant_id": tenant_id}
            )
        except Exception as e:
            # Don't fail the link if mapping fails - consent workflow will also try
            logger.warning(f"Failed to create IntegrationMapping: {e}")

        logger.info(
            "Linked CSP tenant to organization",
            extra={"org_id": org_id, "tenant_id": tenant_id}
        )

    return {
        "success": True,
        "tenant_id": tenant_id,
        "tenant_name": tenant_name,
        "bifrost_org_id": org_id,
        "bifrost_org_name": org_name,
        "consent_status": status_data["consent_status"],
    }
