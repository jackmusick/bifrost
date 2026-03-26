"""
Role Management Workflows

Provider-only workflows for viewing and changing Bifrost role assignments.
These back the role management UI in any portal or app
that needs to surface role membership controls.
"""

import logging

from bifrost import workflow, roles, users, context, UserError
from modules.extensions.permissions import (
    is_provider,
    get_or_create_role,
    HR_ADMIN,
)

logger = logging.getLogger(__name__)

HR_ADMIN_DESCRIPTION = (
    "Access to employee onboarding, offboarding, and user profile management."
)


@workflow(
    name="List Role Members",
    description=(
        "Lists all users in an organization with their HR Admin role membership status. "
        "Provider access required."
    ),
    category="Platform",
    tags=["permissions", "roles", "admin"],
)
async def list_role_members(org_id: str) -> dict:
    """
    List org users with HR Admin membership status.

    Args:
        org_id: The Bifrost organization ID to list users for.

    Returns:
        {
            "role_name": "HR Admin",
            "role_id": "...",
            "users": [
                {"user_id": "...", "name": "...", "email": "...", "is_hr_admin": bool},
                ...
            ]
        }
    """
    caller_id = context.user_id
    if not await is_provider(caller_id):
        raise UserError("Access denied: provider access required.")

    if not org_id:
        raise UserError("org_id is required.")

    role = await get_or_create_role(HR_ADMIN, HR_ADMIN_DESCRIPTION)
    hr_admin_ids = set(await roles.list_users(role.id))

    org_users = await users.list(org_id=org_id)

    members = []
    for u in org_users:
        uid = str(u.id)
        members.append({
            "user_id": uid,
            "name": getattr(u, "name", "") or "",
            "email": getattr(u, "email", "") or "",
            "is_hr_admin": uid in hr_admin_ids,
        })

    members.sort(key=lambda x: (x["name"] or x["email"]).lower())

    return {
        "role_name": HR_ADMIN,
        "role_id": str(role.id),
        "users": members,
    }


@workflow(
    name="Set Role Membership",
    description=(
        "Grant or revoke the HR Admin role for a Bifrost user. "
        "Provider access required."
    ),
    category="Platform",
    tags=["permissions", "roles", "admin"],
)
async def set_role_membership(user_id: str, grant: bool) -> dict:
    """
    Grant or revoke the HR Admin role for a user.

    Uses a read-modify-write on the full member list because the SDK's
    assign_users() replaces the complete membership set.

    Args:
        user_id: The Bifrost user ID to update.
        grant:   True to add the role, False to remove it.

    Returns:
        {"success": True, "action": "granted" | "revoked" | "no_change", ...}
    """
    caller_id = context.user_id
    if not await is_provider(caller_id):
        raise UserError("Access denied: provider access required.")

    if not user_id:
        raise UserError("user_id is required.")

    role = await get_or_create_role(HR_ADMIN, HR_ADMIN_DESCRIPTION)
    current_members = list(await roles.list_users(role.id))

    already_member = user_id in current_members

    if grant:
        if already_member:
            return {"success": True, "action": "no_change", "user_id": user_id, "role": HR_ADMIN}
        new_members = current_members + [user_id]
        action = "granted"
    else:
        if not already_member:
            return {"success": True, "action": "no_change", "user_id": user_id, "role": HR_ADMIN}
        new_members = [m for m in current_members if m != user_id]
        action = "revoked"

    await roles.assign_users(role.id, new_members)
    logger.info(f"Role '{HR_ADMIN}' {action} for user {user_id} by {caller_id}")

    return {"success": True, "action": action, "user_id": user_id, "role": HR_ADMIN}
