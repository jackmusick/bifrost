"""
Get My Permissions

Returns the calling user's Bifrost role memberships and derived access flags.
Intended to be called from apps to gate UI elements without hard-coding
role logic in each page.

Any workflow enforcing access should also call require_role() server-side —
this workflow is for UI hints only, not a security boundary on its own.
"""

import logging

from bifrost import workflow, context
from modules.extensions.permissions import (
    get_user_roles,
    is_provider,
    HR_ADMIN,
    SALES,
)

logger = logging.getLogger(__name__)


@workflow(
    name="Get My Permissions",
    description=(
        "Returns the calling user's role memberships and derived access flags "
        "for UI-level gating in apps. Provider users always receive full access."
    ),
    category="Platform",
    tags=["permissions", "roles", "platform"],
)
async def get_my_permissions() -> dict:
    """
    Returns:
        {
            "is_provider": bool,
            "roles": ["HR Admin", ...],
            "can_onboard": bool,
            "can_offboard": bool,
            "can_edit_users": bool,
        }
    """
    user_id = context.user_id
    provider = await is_provider(user_id)

    if provider:
        return {
            "is_provider": True,
            "roles": [],
            "can_onboard": True,
            "can_offboard": True,
            "can_reactivate": True,
            "can_edit_users": True,
            "can_create_opportunity": True,
        }

    user_roles = await get_user_roles(user_id) if user_id else []
    has_hr_admin = HR_ADMIN in user_roles
    has_sales = SALES in user_roles

    logger.info(f"User {user_id} roles: {user_roles}")

    return {
        "is_provider": False,
        "roles": user_roles,
        "can_onboard": has_hr_admin,
        "can_offboard": has_hr_admin,
        "can_reactivate": has_hr_admin,
        "can_edit_users": has_hr_admin,
        "can_create_opportunity": has_sales,
    }
