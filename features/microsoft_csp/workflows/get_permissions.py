"""
Get Selected Microsoft Permissions

Retrieves the currently selected permissions from the table.
Includes the required flag to indicate which permissions are mandatory.
"""

import logging

from bifrost import workflow, tables, context

logger = logging.getLogger(__name__)

PERMISSIONS_TABLE = "microsoft_selected_permissions"

# Required delegated permissions - needed to install app permissions
REQUIRED_PERMISSION_KEYS = {
    "00000003-0000-0000-c000-000000000000:Directory.ReadWrite.All:delegated",
    "00000003-0000-0000-c000-000000000000:AppRoleAssignment.ReadWrite.All:delegated",
}


@workflow(
    category="Microsoft CSP",
    tags=["microsoft", "csp", "permissions"],
)
async def get_selected_permissions() -> dict:
    """
    Get currently selected Microsoft permissions.

    Returns:
        dict with permissions grouped by API and type, including required flags
    """
    org_id = context.org_id

    try:
        result = await tables.query(PERMISSIONS_TABLE, scope=org_id, limit=1000)
        permissions = [doc.data for doc in result.documents]
    except Exception as e:
        logger.debug(f"No permissions table yet: {e}")
        permissions = []

    # Group by API
    by_api = {}
    for perm in permissions:
        api_name = perm.get("api_name", "Unknown")
        if api_name not in by_api:
            by_api[api_name] = {
                "api_id": perm.get("api_id"),
                "api_name": api_name,
                "delegated": [],
                "application": [],
            }

        perm_type = perm.get("permission_type", "delegated")
        perm_key = f"{perm.get('api_id')}:{perm.get('permission_name')}:{perm_type}"
        
        perm_entry = {
            "name": perm.get("permission_name"),
            "required": perm.get("required", perm_key in REQUIRED_PERMISSION_KEYS),
        }
        
        by_api[api_name][perm_type].append(perm_entry)

    # Count totals
    delegated_count = sum(len(api["delegated"]) for api in by_api.values())
    application_count = sum(len(api["application"]) for api in by_api.values())
    required_count = sum(
        1 for api in by_api.values() 
        for perm in api["delegated"] + api["application"] 
        if perm.get("required")
    )

    # Also return flat list for consent workflow
    flat_permissions = []
    for perm in permissions:
        perm_key = f"{perm.get('api_id')}:{perm.get('permission_name')}:{perm.get('permission_type')}"
        flat_permissions.append({
            "api_id": perm.get("api_id"),
            "api_name": perm.get("api_name"),
            "permission_name": perm.get("permission_name"),
            "permission_type": perm.get("permission_type"),
            "required": perm.get("required", perm_key in REQUIRED_PERMISSION_KEYS),
        })

    return {
        "permissions_by_api": list(by_api.values()),
        "permissions": flat_permissions,
        "delegated_count": delegated_count,
        "application_count": application_count,
        "required_count": required_count,
        "total_count": delegated_count + application_count,
    }
