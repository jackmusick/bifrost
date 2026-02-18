"""
OAuth Token Refresh Scheduler

Automatically refreshes OAuth tokens that are about to expire.
Runs every 15 minutes to check for tokens expiring before the next run.

Ported from Azure Functions timer trigger: functions/timer/oauth_refresh_timer.py
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from src.core.database import get_db_context
from src.core.security import decrypt_secret, encrypt_secret
from src.models import OAuthToken, OAuthProvider
from src.models.orm import Integration
from src.services.oauth_provider import OAuthProviderClient, resolve_url_template

logger = logging.getLogger(__name__)

# Refresh interval and buffer - tokens expiring within (interval + buffer) will be refreshed
OAUTH_REFRESH_INTERVAL_MINUTES = 15
REFRESH_BUFFER_MINUTES = 5


async def refresh_expiring_tokens() -> dict[str, Any]:
    """
    Refresh OAuth tokens that are about to expire.

    Finds all tokens expiring before the next scheduled run (plus buffer)
    and attempts to refresh them using their associated provider's configuration.

    Returns:
        Summary of refresh results
    """
    threshold = OAUTH_REFRESH_INTERVAL_MINUTES + REFRESH_BUFFER_MINUTES
    return await run_refresh_job(trigger_type="automatic", refresh_threshold_minutes=threshold)


async def run_refresh_job(
    trigger_type: str = "automatic",
    trigger_user: str | None = None,
    refresh_threshold_minutes: int | None = None,
) -> dict[str, Any]:
    """
    Run the OAuth token refresh job.

    This method contains the shared logic for refreshing expiring OAuth tokens.
    Can be called by both the scheduler and HTTP endpoint.

    Args:
        trigger_type: Type of trigger ("automatic" or "manual")
        trigger_user: Email of user who triggered (for manual triggers)
        refresh_threshold_minutes: Threshold in minutes (default: 30 for automatic, None for manual refreshes all)

    Returns:
        Dictionary with job results
    """
    start_time = datetime.now(timezone.utc)
    logger.info(f"▶ OAuth token refresh starting (trigger={trigger_type})")

    results: dict[str, Any] = {
        "total_connections": 0,
        "needs_refresh": 0,
        "refreshed_successfully": 0,
        "refresh_failed": 0,
        "errors": [],
        "trigger_type": trigger_type,
        "trigger_user": trigger_user,
    }

    try:
        async with get_db_context() as db:
            # Get all tokens with refresh tokens, eager-loading provider to avoid N+1
            query = (
                select(OAuthToken)
                .options(selectinload(OAuthToken.provider))
                .where(OAuthToken.encrypted_refresh_token.isnot(None))
            )
            result = await db.execute(query)
            all_tokens = result.scalars().all()

            results["total_connections"] = len(all_tokens)

            # Determine which tokens need refresh
            now = datetime.now(timezone.utc)

            if refresh_threshold_minutes is not None:
                # Automatic: only refresh tokens expiring within threshold
                refresh_threshold = now + timedelta(minutes=refresh_threshold_minutes)
                tokens_to_refresh = [
                    t for t in all_tokens
                    if t.expires_at and t.expires_at <= refresh_threshold
                ]
            else:
                # Manual: refresh all completed connections
                tokens_to_refresh = list(all_tokens)

            results["needs_refresh"] = len(tokens_to_refresh)

            for token in tokens_to_refresh:
                try:
                    # Provider is already loaded via selectinload
                    provider = token.provider

                    if not provider:
                        results["errors"].append({
                            "token_id": str(token.id),
                            "error": "Provider not found",
                        })
                        results["refresh_failed"] += 1
                        continue

                    # Attempt to refresh the token
                    success = await _refresh_single_token(db, token, provider)

                    if success:
                        results["refreshed_successfully"] += 1
                    else:
                        results["refresh_failed"] += 1
                        results["errors"].append({
                            "token_id": str(token.id),
                            "provider": provider.provider_name,
                            "error": "Refresh failed",
                        })

                except Exception as e:
                    results["refresh_failed"] += 1
                    results["errors"].append({
                        "token_id": str(token.id),
                        "error": str(e),
                    })
                    logger.error(f"Error refreshing token {token.id}: {e}", exc_info=True)

            await db.commit()

        # Calculate duration
        end_time = datetime.now(timezone.utc)
        duration_seconds = (end_time - start_time).total_seconds()
        results["duration_seconds"] = duration_seconds
        results["start_time"] = start_time.isoformat()
        results["end_time"] = end_time.isoformat()

        # Log completion with visual marker
        success = results["refreshed_successfully"]
        failed = results["refresh_failed"]
        if failed > 0:
            logger.warning(
                f"⚠ OAuth token refresh completed with errors: "
                f"{success} refreshed, {failed} failed ({duration_seconds:.1f}s)"
            )
        else:
            logger.info(
                f"✓ OAuth token refresh completed: "
                f"{success} refreshed, {failed} failed ({duration_seconds:.1f}s)"
            )

    except Exception as e:
        logger.error(f"✗ OAuth token refresh failed: {e}", exc_info=True)
        results["errors"].append({"error": str(e)})

    return results


async def _refresh_single_token(
    db,
    token: OAuthToken,
    provider: OAuthProvider,
) -> bool:
    """
    Refresh a single OAuth token.

    Args:
        db: Database session
        token: Token to refresh
        provider: OAuth provider configuration

    Returns:
        True if refresh succeeded, False otherwise
    """
    try:
        # Decrypt the refresh token
        if not token.encrypted_refresh_token:
            logger.warning(f"No refresh token for token {token.id}")
            return False

        refresh_token = decrypt_secret(token.encrypted_refresh_token.decode())

        # Get client secret if exists
        client_secret = None
        if provider.encrypted_client_secret:
            client_secret = decrypt_secret(provider.encrypted_client_secret.decode())

        # Build refresh request
        if not provider.token_url:
            logger.warning(f"No token URL configured for provider {provider.provider_name}")
            return False

        # Resolve URL template placeholders (e.g., {entity_id} -> actual tenant ID)
        defaults: dict[str, str] = dict(provider.token_url_defaults) if provider.token_url_defaults else {}
        if provider.integration_id:
            result_int = await db.execute(
                select(Integration).where(Integration.id == provider.integration_id)
            )
            integration = result_int.scalar_one_or_none()
            if integration and integration.default_entity_id:
                defaults["entity_id"] = integration.default_entity_id

        token_url = resolve_url_template(
            url=provider.token_url,
            defaults=defaults,
        )

        # Use the shared OAuth provider client
        oauth_client = OAuthProviderClient()
        success, result = await oauth_client.refresh_access_token(
            token_url=token_url,
            refresh_token=refresh_token,
            client_id=provider.client_id,
            client_secret=client_secret,
            audience=provider.audience,
        )

        if not success:
            error_msg = result.get("error_description", result.get("error", "Refresh failed"))
            logger.error(f"Token refresh failed for {provider.provider_name}: {error_msg}")
            provider.status = "failed"
            provider.status_message = f"Token refresh failed: {error_msg}"
            return False

        # Update token in database
        new_access_token = result.get("access_token")
        new_refresh_token = result.get("refresh_token") or refresh_token  # Keep old if not returned
        expires_at = result.get("expires_at")

        if not new_access_token:
            logger.error(f"No access token in refresh response for {provider.provider_name}")
            return False

        # Encrypt and store new tokens
        token.encrypted_access_token = encrypt_secret(new_access_token).encode()
        token.encrypted_refresh_token = encrypt_secret(new_refresh_token).encode()
        token.expires_at = expires_at

        # Update scopes if returned
        new_scopes = result.get("scope")
        if new_scopes:
            token.scopes = new_scopes.split(" ")

        # Update provider status
        provider.status = "completed"
        provider.last_token_refresh = datetime.now(timezone.utc)
        provider.status_message = None

        return True

    except Exception as e:
        logger.error(f"Error refreshing token: {e}", exc_info=True)
        # Update provider status to indicate error
        provider.status = "failed"
        provider.status_message = f"Token refresh failed: {str(e)[:200]}"
        return False
