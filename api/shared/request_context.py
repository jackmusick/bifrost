"""
Request Context - Unified context extraction for all endpoints

Provides a single, consistent way to extract:
- User identity (from EasyAuth)
- Organization scope (from header or database)
- Platform admin status
- Execution context for workflows

This replaces the scattered authentication/authorization logic across
auth.py, auth_headers.py, and middleware.py.
"""

import base64
import json
import logging
from dataclasses import dataclass

import azure.functions as func

logger = logging.getLogger(__name__)


@dataclass
class RequestContext:
    """
    Unified request context for all endpoints.

    Contains everything needed to execute workflows and queries:
    - user_id: User identifier (from EasyAuth or "system" for function keys)
    - email: User email (from EasyAuth or "system@local" for function keys)
    - name: User display name
    - org_id: Organization ID (None = GLOBAL scope)
    - is_platform_admin: Whether user is platform admin
    - is_function_key: Whether authenticated via function key (not a user)

    Usage:
        context = get_request_context(req)
        if context.is_platform_admin:
            # Allow admin operations

        # Use org_id for queries
        partition_key = context.org_id or "GLOBAL"
    """
    user_id: str
    email: str
    name: str
    org_id: str | None
    is_platform_admin: bool
    is_function_key: bool

    @property
    def scope(self) -> str:
        """Get partition key for database queries"""
        return self.org_id or "GLOBAL"


async def get_request_context(req: func.HttpRequest) -> RequestContext:
    """
    Extract unified request context from Azure Functions request.

    This is THE canonical function for determining execution context.

    Authentication Priority:
    1. Function key (x-functions-key header or ?code param)
       - Sets is_function_key=True
       - User is "system"
       - org_id from X-Organization-Id header (optional)

    2. Easy Auth (X-MS-CLIENT-PRINCIPAL from SWA)
       - Sets is_function_key=False
       - User from principal
       - org_id derived from user's org in database
       - Platform admins can override org_id via X-Organization-Id header

    Scoping Rules:
    - Platform admins: Can set X-Organization-Id or leave None for GLOBAL
    - Regular users: org_id derived from database, cannot override
    - Function keys: Can set X-Organization-Id or leave None for GLOBAL

    Args:
        req: Azure Functions HTTP request

    Returns:
        RequestContext with user, org, and permissions

    Raises:
        ValueError: If user not found in database or lacks org context
    """
    # Check if function key authentication
    # Azure Functions already validated the key if auth_level=FUNCTION
    # We just need to detect if it was used
    function_key = req.headers.get('x-functions-key') or req.params.get('code')

    if function_key:
        # Function key authentication - system caller
        org_id = req.headers.get('X-Organization-Id')  # Optional

        logger.info(f"Function key authentication: scope={org_id or 'GLOBAL'}")

        return RequestContext(
            user_id="system",
            email="system@local",
            name="System (Function Key)",
            org_id=org_id,
            is_platform_admin=True,  # Function keys have admin privileges
            is_function_key=True
        )

    # Try Easy Auth (X-MS-CLIENT-PRINCIPAL from SWA)
    principal_header = req.headers.get('X-MS-CLIENT-PRINCIPAL')

    if not principal_header:
        # No authentication found - this is an error
        # In production, SWA handles auth and always provides X-MS-CLIENT-PRINCIPAL
        # In local dev with GetRoles enabled, SWA CLI provides the same header
        logger.error("No authentication found - request rejected")
        raise ValueError(
            "Authentication required. "
            "Ensure you're using SWA with GetRoles configured, or provide a function key."
        )

    # Parse Easy Auth principal
    try:
        principal_json = base64.b64decode(principal_header).decode('utf-8')
        principal_data = json.loads(principal_json)

        # SWA production provides userId, but local dev (SWA CLI) does not
        # Fall back to userDetails (email) as user_id for local development
        user_id = principal_data.get('userId')
        email = principal_data.get('userDetails', '')

        if not user_id:
            if email:
                user_id = email  # Use email as user_id for local dev
            else:
                raise ValueError(
                    "X-MS-CLIENT-PRINCIPAL missing both userId and userDetails")

        name = email.split('@')[0] if email else user_id
        user_roles = principal_data.get('userRoles', [])

        logger.info(f"Easy Auth user: {email}, roles: {user_roles}")

    except Exception as e:
        logger.error(f"Failed to parse Easy Auth principal: {e}")
        raise ValueError(f"Invalid authentication: {e}") from e

    # Check if user is platform admin (role set by GetRoles endpoint)
    is_admin = 'PlatformAdmin' in user_roles

    # Get user's organization from database
    # GetRoles endpoint ensures user exists and is properly provisioned
    from shared.user_lookup import get_user_organization

    # Determine org_id based on user role and headers
    provided_org_id = req.headers.get('X-Organization-Id')

    if is_admin:
        # Platform admin can specify org or work in GLOBAL scope
        org_id = provided_org_id  # May be None for GLOBAL

        if org_id:
            logger.info(f"Platform admin {email} in org scope: {org_id}")
        else:
            logger.info(f"Platform admin {email} in GLOBAL scope")

        return RequestContext(
            user_id=user_id,
            email=email,
            name=name,
            org_id=org_id,
            is_platform_admin=True,
            is_function_key=False
        )

    # Regular user - must derive org from database
    if provided_org_id:
        # Non-admin cannot override org context
        logger.warning(
            f"Non-admin user {email} attempted to set X-Organization-Id")
        raise PermissionError(
            "Only platform administrators can override organization context")

    # Look up user's org in database
    # GetRoles endpoint ensures user is provisioned with org assignment
    org_id = await get_user_organization(email)

    if not org_id:
        # User authenticated but has no org assignment
        # This should not happen if GetRoles is working properly
        logger.error(
            f"User {email} authenticated but has no organization assignment")
        raise ValueError(
            f"User {email} has no organization assignment. "
            "Please contact your administrator to assign you to an organization."
        )

    logger.info(f"User {email} in org scope: {org_id}")

    return RequestContext(
        user_id=user_id,
        email=email,
        name=name,
        org_id=org_id,
        is_platform_admin=False,
        is_function_key=False
    )


# Note: User provisioning is handled by GetRoles endpoint (src/routers/roles.py)
# This module only looks up existing users - GetRoles ensures they exist first
