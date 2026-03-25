"""
Consent CSP Tenant

Single workflow for both initial consent and refresh/reconsent.

Flow:
1. Partner Center consent for CSP app (delegated permissions) - installs app
2. If 409 (exists), get GDAP token and update scopes via Graph API
3. Get GDAP token and create Microsoft app service principal
4. Grant application permissions to Microsoft app

Architecture:
- "Bifrost CSP" app: Partner Center consent + GDAP access (delegated permissions)
- "Bifrost Microsoft" app: Installed in tenant for client credentials (application permissions)
"""

import asyncio
import logging
from datetime import datetime, timezone

import httpx

from bifrost import workflow, tables, context, integrations, UserError

logger = logging.getLogger(__name__)

STATUS_TABLE = "csp_tenant_status"
PERMISSIONS_TABLE = "microsoft_selected_permissions"

# Well-known Microsoft API enterprise application IDs
MICROSOFT_APIS = {
    "00000003-0000-0000-c000-000000000000": "Microsoft Graph",
    "00000002-0000-0ff1-ce00-000000000000": "Exchange Online",
    "00000003-0000-0ff1-ce00-000000000000": "SharePoint",
    "fc780465-2017-40d4-a0c5-307022471b92": "Windows Defender ATP",
}

# Required bootstrap permissions - always included for delegated consent
# These are needed to grant application permissions via Graph API
REQUIRED_DELEGATED_PERMISSIONS = [
    {"api_id": "00000003-0000-0000-c000-000000000000", "name": "Directory.ReadWrite.All"},
    {"api_id": "00000003-0000-0000-c000-000000000000", "name": "AppRoleAssignment.ReadWrite.All"},
]


async def _update_delegated_scopes(
    client: httpx.AsyncClient,
    headers: dict,
    csp_app_id: str,
    resource_app_id: str,
    scopes: list[str],
) -> None:
    """
    Update delegated permission scopes via Graph API.
    
    Called when Partner Center consent already exists (409) to update the
    OAuth2PermissionGrant with new/updated scopes.
    """
    # Find the CSP app's service principal
    sp_response = await client.get(
        f"https://graph.microsoft.com/v1.0/servicePrincipals(appId='{csp_app_id}')",
        headers=headers,
        timeout=30.0,
    )
    if sp_response.status_code == 404:
        logger.warning(f"CSP app service principal not found: {csp_app_id}")
        return
    sp_response.raise_for_status()
    csp_sp = sp_response.json()
    csp_sp_id = csp_sp["id"]
    
    # Find the resource service principal
    resource_response = await client.get(
        f"https://graph.microsoft.com/v1.0/servicePrincipals(appId='{resource_app_id}')",
        headers=headers,
        timeout=30.0,
    )
    if resource_response.status_code == 404:
        logger.warning(f"Resource service principal not found: {resource_app_id}")
        return
    resource_response.raise_for_status()
    resource_sp = resource_response.json()
    resource_sp_id = resource_sp["id"]
    
    # Find existing OAuth2PermissionGrant
    grants_response = await client.get(
        f"https://graph.microsoft.com/v1.0/servicePrincipals/{csp_sp_id}/oauth2PermissionGrants",
        headers=headers,
        timeout=30.0,
    )
    grants_response.raise_for_status()
    grants = grants_response.json().get("value", [])
    
    # Find grant for this resource
    existing_grant = next(
        (g for g in grants if g.get("resourceId") == resource_sp_id),
        None
    )
    
    if existing_grant:
        # Compare scopes
        existing_scopes = set(existing_grant.get("scope", "").split())
        new_scopes = set(scopes)
        
        if existing_scopes != new_scopes:
            # Update with new scopes (space-delimited)
            new_scope_string = " ".join(scopes)
            await client.patch(
                f"https://graph.microsoft.com/v1.0/oauth2PermissionGrants/{existing_grant['id']}",
                headers={**headers, "Content-Type": "application/json"},
                json={"scope": new_scope_string},
                timeout=30.0,
            )
            logger.info(f"Updated OAuth2PermissionGrant scopes: {new_scope_string}")
        else:
            logger.info("Scopes already match, no update needed")
    else:
        logger.warning(f"No existing OAuth2PermissionGrant found for resource {resource_app_id}")


@workflow(
    category="Microsoft CSP",
    tags=["microsoft", "csp", "consent"],
)
async def consent_csp_tenant(
    tenant_id: str,
) -> dict:
    """
    Grant or refresh consent for a customer tenant.
    
    This workflow handles both initial consent and reconsent (refresh).
    
    Flow:
    1. Partner Center consent for CSP app (installs app + grants delegated permissions)
    2. If consent exists (409), update scopes via Graph API using GDAP token
    3. Get GDAP token, create Microsoft app service principal if needed
    4. Grant application permissions to Microsoft app

    Args:
        tenant_id: Customer's Entra tenant ID

    Returns:
        Consent result with details of what was granted
    """
    from modules.microsoft import create_csp_client
    from modules.microsoft.auth import get_graph_token, get_microsoft_app_credentials, get_gdap_credentials

    if not tenant_id:
        raise UserError("tenant_id is required")

    provider_org_id = context.org_id

    logger.info("Starting consent process", extra={"tenant_id": tenant_id})

    # Get app credentials
    gdap_creds = await get_gdap_credentials()
    csp_app_id = gdap_creds.client_id
    
    microsoft_app = await get_microsoft_app_credentials()
    microsoft_app_id = microsoft_app.client_id

    # Get selected permissions from table
    try:
        result = await tables.query(PERMISSIONS_TABLE, scope=provider_org_id, limit=1000)
        all_permissions = [doc.data for doc in result.documents]
    except Exception as e:
        logger.warning(f"Could not read permissions table: {e}")
        all_permissions = []

    # Separate delegated and application permissions
    delegated_permissions = [p for p in all_permissions if p.get("permission_type") == "delegated"]
    app_permissions = [p for p in all_permissions if p.get("permission_type") == "application"]

    # Build delegated scopes grouped by API
    delegated_by_api: dict[str, list[str]] = {}
    
    # Add required bootstrap permissions
    for req in REQUIRED_DELEGATED_PERMISSIONS:
        api_id = req["api_id"]
        if api_id not in delegated_by_api:
            delegated_by_api[api_id] = []
        if req["name"] not in delegated_by_api[api_id]:
            delegated_by_api[api_id].append(req["name"])
    
    # Add user-selected delegated permissions
    for perm in delegated_permissions:
        api_id = perm.get("api_id")
        perm_name = perm.get("permission_name")
        if api_id and perm_name:
            if api_id not in delegated_by_api:
                delegated_by_api[api_id] = []
            if perm_name not in delegated_by_api[api_id]:
                delegated_by_api[api_id].append(perm_name)

    # Get existing status
    try:
        existing = await tables.get(STATUS_TABLE, tenant_id, scope=provider_org_id)
        existing_data = existing.data if existing else {}
    except Exception:
        existing_data = {}

    now = datetime.now(timezone.utc).isoformat()
    consent_status = "granted"
    error_message = None
    delegated_granted = []
    app_permissions_granted = []
    app_permissions_errors = []

    try:
        csp = await create_csp_client()

        # =====================================================================
        # Step 1: Partner Center consent for CSP app (delegated permissions)
        # This installs the CSP app in the customer tenant
        # No GDAP token needed - uses Partner Center token
        # =====================================================================
        logger.info("Step 1: Partner Center consent for CSP app")
        
        for api_id, scopes in delegated_by_api.items():
            api_name = MICROSOFT_APIS.get(api_id, api_id)
            scope_string = ",".join(scopes)
            
            try:
                csp.grant_consent(
                    tenant_id=tenant_id,
                    application_id=csp_app_id,
                    grants=[{
                        "enterpriseApplicationId": api_id,
                        "scope": scope_string,
                    }],
                )
                
                logger.info(f"Partner Center consent granted for {api_name}: {scope_string}")
                delegated_granted.extend(scopes)
                
            except Exception as e:
                error_str = str(e)
                
                # 409 means consent already exists - need to update via Graph
                if "409" in error_str or "already exists" in error_str.lower():
                    logger.info(f"Consent exists for {api_name}, updating scopes via Graph API")
                    
                    # NOW we get GDAP token (after Partner Center has installed the app)
                    access_token = await get_graph_token(tenant_id=tenant_id)
                    
                    async with httpx.AsyncClient() as client:
                        headers = {"Authorization": f"Bearer {access_token}"}
                        await _update_delegated_scopes(
                            client=client,
                            headers=headers,
                            csp_app_id=csp_app_id,
                            resource_app_id=api_id,
                            scopes=scopes,
                        )
                    
                    delegated_granted.extend(scopes)
                else:
                    logger.error(f"Partner Center consent failed for {api_name}: {e}")
                    raise

        # =====================================================================
        # Step 2: Create Microsoft app service principal and grant app permissions
        # Now we can safely get GDAP token since CSP app is installed
        # =====================================================================
        if app_permissions:
            # Brief delay to allow Azure to propagate permissions
            if delegated_granted:
                logger.info("Waiting for permission propagation...")
                await asyncio.sleep(2)
            
            logger.info(f"Step 2: Installing Microsoft app and granting {len(app_permissions)} application permissions")
            
            # Get GDAP token for customer tenant
            access_token = await get_graph_token(tenant_id=tenant_id)
            
            async with httpx.AsyncClient() as client:
                headers = {"Authorization": f"Bearer {access_token}"}
                
                # Check if Microsoft app's service principal exists
                sp_response = await client.get(
                    f"https://graph.microsoft.com/v1.0/servicePrincipals(appId='{microsoft_app_id}')",
                    headers=headers,
                    timeout=30.0,
                )
                
                if sp_response.status_code == 404:
                    # Create the service principal for Microsoft app
                    logger.info(f"Creating service principal for Microsoft app {microsoft_app_id}")
                    create_sp_response = await client.post(
                        "https://graph.microsoft.com/v1.0/servicePrincipals",
                        headers={**headers, "Content-Type": "application/json"},
                        json={"appId": microsoft_app_id},
                        timeout=30.0,
                    )
                    
                    if create_sp_response.status_code not in [200, 201]:
                        error_text = create_sp_response.text
                        raise UserError(f"Failed to create Microsoft app service principal: {error_text}")
                    
                    microsoft_sp = create_sp_response.json()
                    logger.info(f"Created Microsoft app service principal: {microsoft_sp['id']}")
                else:
                    sp_response.raise_for_status()
                    microsoft_sp = sp_response.json()
                    logger.info(f"Microsoft app service principal already exists: {microsoft_sp['id']}")
                
                microsoft_sp_id = microsoft_sp["id"]
                
                # Group app permissions by API
                app_by_api: dict[str, list[dict]] = {}
                for perm in app_permissions:
                    api_id = perm.get("api_id")
                    if api_id not in app_by_api:
                        app_by_api[api_id] = []
                    app_by_api[api_id].append(perm)
                
                # Grant each permission
                for api_id, perms in app_by_api.items():
                    api_name = MICROSOFT_APIS.get(api_id, api_id)
                    
                    # Get resource service principal
                    resource_response = await client.get(
                        f"https://graph.microsoft.com/v1.0/servicePrincipals(appId='{api_id}')",
                        headers=headers,
                        timeout=30.0,
                    )
                    
                    if resource_response.status_code == 404:
                        logger.warning(f"Resource SP not found: {api_name}")
                        app_permissions_errors.append({
                            "api": api_name,
                            "error": "Service principal not found",
                        })
                        continue
                    
                    resource_response.raise_for_status()
                    resource_sp = resource_response.json()
                    resource_sp_id = resource_sp["id"]
                    app_roles = {role["value"]: role["id"] for role in resource_sp.get("appRoles", [])}
                    
                    for perm in perms:
                        perm_name = perm.get("permission_name")
                        app_role_id = app_roles.get(perm_name)
                        
                        if not app_role_id:
                            logger.warning(f"App role not found: {perm_name}")
                            app_permissions_errors.append({
                                "permission": perm_name,
                                "api": api_name,
                                "error": "App role not found",
                            })
                            continue
                        
                        # Grant the app role
                        grant_response = await client.post(
                            f"https://graph.microsoft.com/v1.0/servicePrincipals/{resource_sp_id}/appRoleAssignedTo",
                            headers={**headers, "Content-Type": "application/json"},
                            json={
                                "principalId": microsoft_sp_id,
                                "resourceId": resource_sp_id,
                                "appRoleId": app_role_id,
                            },
                            timeout=30.0,
                        )
                        
                        if grant_response.status_code in [200, 201]:
                            logger.info(f"Granted app permission: {perm_name}")
                            app_permissions_granted.append({"permission": perm_name, "api": api_name})
                        else:
                            error_text = grant_response.text
                            if "already exists" in error_text.lower():
                                logger.info(f"App permission already granted: {perm_name}")
                                app_permissions_granted.append({
                                    "permission": perm_name,
                                    "api": api_name,
                                    "status": "already_granted",
                                })
                            else:
                                logger.error(f"Failed to grant {perm_name}: {error_text}")
                                app_permissions_errors.append({
                                    "permission": perm_name,
                                    "api": api_name,
                                    "error": error_text,
                                })

        # Determine final status
        if app_permissions_errors:
            consent_status = "partial"
            error_message = f"Failed to grant {len(app_permissions_errors)} app permission(s)"

    except UserError:
        raise
    except Exception as e:
        error_message = str(e)
        consent_status = "failed"
        logger.error(f"Consent failed: {e}", extra={"tenant_id": tenant_id})

    # Update status table
    status_data = {
        "tenant_id": tenant_id,
        "tenant_name": existing_data.get("tenant_name", ""),
        "domain": existing_data.get("domain", ""),
        "customer_id": existing_data.get("customer_id", ""),
        "bifrost_org_id": existing_data.get("bifrost_org_id"),
        "bifrost_org_name": existing_data.get("bifrost_org_name"),
        "consent_status": consent_status,
        "consent_error": error_message,
        "consent_execution_id": context.execution_id,
        "consented_at": now if consent_status in ["granted", "partial"] else existing_data.get("consented_at"),
        "updated_at": now,
    }

    await tables.upsert(STATUS_TABLE, id=tenant_id, data=status_data, scope=provider_org_id)

    # Create IntegrationMapping for Microsoft integration if consent succeeded
    if consent_status in ["granted", "partial"] and existing_data.get("bifrost_org_id"):
        try:
            await integrations.upsert_mapping(
                "Microsoft",
                scope=existing_data["bifrost_org_id"],
                entity_id=tenant_id,
                entity_name=existing_data.get("tenant_name") or existing_data.get("domain", tenant_id),
            )
            logger.info(
                "Created IntegrationMapping for Microsoft",
                extra={"org_id": existing_data["bifrost_org_id"], "tenant_id": tenant_id}
            )
        except Exception as e:
            logger.warning(f"Failed to create IntegrationMapping: {e}")

    # Auto-enrich after successful consent
    org_id = existing_data.get("bifrost_org_id")
    if consent_status == "granted" and org_id:
        try:
            from features.customer_onboarding.workflows.enrich_client_preferences import (
                enrich_client_preferences,
            )
            await enrich_client_preferences(org_id=org_id, tenant_id=tenant_id)
            logger.info(f"Auto-enrichment completed for {tenant_id}")
        except Exception as e:
            logger.warning(f"Auto-enrichment failed for {tenant_id}: {e}")

    return {
        "success": consent_status in ["granted", "partial"],
        "tenant_id": tenant_id,
        "consent_status": consent_status,
        "consent_error": error_message,
        "consented_at": status_data["consented_at"],
        "delegated_granted": delegated_granted,
        "app_permissions_granted": app_permissions_granted,
        "app_permissions_errors": app_permissions_errors,
    }
