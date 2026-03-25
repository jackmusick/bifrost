"""
Check Microsoft Setup

Checks if both Microsoft CSP and Microsoft integrations are properly configured.
Returns status for each integration to drive UI state.
"""

import logging

from bifrost import workflow, integrations

logger = logging.getLogger(__name__)


@workflow(
    category="Microsoft CSP",
    tags=["microsoft", "csp", "setup"],
)
async def check_microsoft_setup() -> dict:
    """
    Check if Microsoft integrations are properly configured.

    Returns status for:
    - Microsoft CSP: Delegated OAuth for Partner Center access
    - Microsoft: Client credentials for customer tenant APIs

    Returns:
        dict with integration statuses and overall readiness
    """
    csp_status = {
        "name": "Microsoft CSP",
        "connected": False,
        "description": "Partner Center API access",
        "error": None,
    }

    microsoft_status = {
        "name": "Microsoft",
        "connected": False,
        "description": "Client credentials for customer APIs",
        "error": None,
    }

    # Check Microsoft CSP integration
    try:
        csp_integration = await integrations.get("Microsoft CSP")
        if csp_integration and csp_integration.oauth:
            # For delegated flow, we need a refresh token
            if csp_integration.oauth.refresh_token:
                csp_status["connected"] = True
            else:
                csp_status["error"] = "Not authenticated - OAuth connection required"
        else:
            csp_status["error"] = "Integration not configured"
    except Exception as e:
        csp_status["error"] = str(e)
        logger.warning(f"Failed to check Microsoft CSP integration: {e}")

    # Check Microsoft integration
    try:
        ms_integration = await integrations.get("Microsoft", scope="global")
        if ms_integration and ms_integration.oauth:
            # For client credentials, we need client_id and client_secret
            if ms_integration.oauth.client_id and ms_integration.oauth.client_secret:
                microsoft_status["connected"] = True
            else:
                microsoft_status["error"] = "Missing client credentials"
        else:
            microsoft_status["error"] = "Integration not configured"
    except Exception as e:
        microsoft_status["error"] = str(e)
        logger.warning(f"Failed to check Microsoft integration: {e}")

    # Overall readiness
    ready_for_consent = csp_status["connected"] and microsoft_status["connected"]

    return {
        "csp": csp_status,
        "microsoft": microsoft_status,
        "ready_for_consent": ready_for_consent,
    }
