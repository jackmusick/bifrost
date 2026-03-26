"""
List Available Microsoft Permissions

Fetches available delegated and application permissions from Microsoft
service principals for Graph, Exchange, SharePoint, and Defender APIs.
"""

import logging

from bifrost import workflow

logger = logging.getLogger(__name__)

# Well-known Microsoft API enterprise application IDs
MICROSOFT_APIS = {
    "Microsoft Graph": "00000003-0000-0000-c000-000000000000",
    "Exchange Online": "00000002-0000-0ff1-ce00-000000000000",
    "SharePoint": "00000003-0000-0ff1-ce00-000000000000",
    "Windows Defender ATP": "fc780465-2017-40d4-a0c5-307022471b92",
}


@workflow(
    category="Microsoft CSP",
    tags=["microsoft", "csp", "permissions"],
)
async def list_available_permissions() -> dict:
    """
    Fetch available permissions from Microsoft APIs.

    Queries the service principal for each API to get:
    - oauth2PermissionScopes (delegated permissions)
    - appRoles (application permissions)

    Returns:
        dict with permissions grouped by API
    """
    import httpx

    from modules.microsoft.auth import get_graph_token

    # Get a Graph token for the partner tenant to query service principals
    # The token URL in the integration should be configured with the partner tenant ID
    access_token = await get_graph_token(tenant_id="common")

    apis = []

    async with httpx.AsyncClient() as client:
        for api_name, app_id in MICROSOFT_APIS.items():
            logger.info(f"Fetching permissions for {api_name}")

            try:
                response = await client.get(
                    f"https://graph.microsoft.com/v1.0/servicePrincipals(appId='{app_id}')",
                    params={"$select": "id,appId,displayName,appRoles,oauth2PermissionScopes"},
                    headers={"Authorization": f"Bearer {access_token}"},
                    timeout=30.0,
                )

                if response.status_code == 404:
                    logger.warning(f"Service principal not found for {api_name}")
                    continue

                response.raise_for_status()
                data = response.json()

                # Parse delegated permissions
                delegated = []
                for scope in data.get("oauth2PermissionScopes", []):
                    if scope.get("isEnabled", True):
                        delegated.append({
                            "id": scope.get("id"),
                            "name": scope.get("value"),
                            "description": scope.get("adminConsentDescription") or scope.get("userConsentDescription", ""),
                            "admin_consent_required": scope.get("type") == "Admin",
                        })

                # Parse application permissions
                application = []
                for role in data.get("appRoles", []):
                    if role.get("isEnabled", True):
                        application.append({
                            "id": role.get("id"),
                            "name": role.get("value"),
                            "description": role.get("description", ""),
                        })

                # Sort by name
                delegated.sort(key=lambda x: x["name"])
                application.sort(key=lambda x: x["name"])

                apis.append({
                    "api_id": app_id,
                    "api_name": api_name,
                    "display_name": data.get("displayName", api_name),
                    "delegated_permissions": delegated,
                    "application_permissions": application,
                })

            except Exception as e:
                logger.error(f"Failed to fetch permissions for {api_name}: {e}")
                continue

    return {
        "apis": apis,
        "api_count": len(apis),
    }
