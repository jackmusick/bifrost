"""
Cache warming functions for Bifrost SDK.

Pre-warms Redis cache before workflow execution starts.
Called from the workflow execution consumer before spawning the worker thread.

Pattern:
    1. Consumer receives execution request
    2. Consumer calls prewarm_sdk_cache() (async, in main event loop)
    3. Worker thread spawns and SDK reads from Redis (fast, non-blocking)
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import or_, select

from .keys import (
    TTL_CONFIG,
    TTL_FORMS,
    TTL_OAUTH,
    TTL_ORGS,
    TTL_ROLES,
    config_hash_key,
    forms_hash_key,
    oauth_hash_key,
    org_key,
    role_forms_key,
    role_users_key,
    roles_hash_key,
    user_forms_key,
)
from .redis_client import get_shared_redis

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


async def prewarm_sdk_cache(
    execution_id: str,
    org_id: str | None,
    user_id: str,
    is_admin: bool = False,
) -> None:
    """
    Pre-warm Redis cache with data needed for SDK operations.

    Called from async context BEFORE workflow execution starts.
    Queries Postgres once and populates Redis with all data the SDK might need.

    Args:
        execution_id: Execution UUID for logging
        org_id: Organization ID (or None for global scope)
        user_id: User ID executing the workflow
        is_admin: Whether the user is an admin (affects form visibility)
    """
    from src.core.database import get_session_factory

    session_factory = get_session_factory()

    org_uuid = None
    if org_id and org_id != "GLOBAL":
        try:
            org_uuid = UUID(org_id)
        except ValueError:
            pass

    try:
        async with session_factory() as db:
            r = await get_shared_redis()

            # Pre-warm in parallel for efficiency
            await _prewarm_configs(db, r, org_uuid)
            await _prewarm_oauth(db, r, org_uuid)
            await _prewarm_forms(db, r, org_uuid, user_id, is_admin)
            await _prewarm_roles(db, r, org_uuid)

            if org_uuid:
                await _prewarm_organization(db, r, org_uuid)

        logger.debug(
            f"Pre-warmed SDK cache for execution {execution_id}, org={org_id}"
        )
    except Exception as e:
        # Log but don't fail execution - SDK will fall back to DB queries
        logger.warning(f"Failed to pre-warm SDK cache: {e}")


# =============================================================================
# Pre-warming Functions
# =============================================================================


async def _prewarm_configs(
    db: "AsyncSession",
    r: Any,
    org_uuid: UUID | None,
) -> None:
    """Pre-warm all config values for the organization."""
    from src.core.security import decrypt_secret
    from src.models.orm import Config

    # Query org-specific + global configs
    if org_uuid:
        query = select(Config).where(
            or_(Config.organization_id == org_uuid, Config.organization_id.is_(None))
        )
    else:
        query = select(Config).where(Config.organization_id.is_(None))

    result = await db.execute(query)
    configs = result.scalars().all()

    if not configs:
        return

    # Build hash data
    config_data: dict[str, str] = {}
    for config in configs:
        config_value = config.value or {}
        raw_value = (
            config_value.get("value", config_value)
            if isinstance(config_value, dict)
            else config_value
        )
        config_type = config.config_type.value if config.config_type else "string"

        # Decrypt secrets at pre-warm time
        if config_type == "secret":
            try:
                decrypted = decrypt_secret(raw_value)
                cache_value = {"value": decrypted, "type": "secret"}
            except Exception:
                continue  # Skip if decryption fails
        else:
            cache_value = {"value": raw_value, "type": config_type}

        # Use config key as hash field
        # For org-specific, it overrides global (last write wins)
        config_data[config.key] = json.dumps(cache_value)

    # Write to Redis hash
    org_id = str(org_uuid) if org_uuid else None
    hash_key = config_hash_key(org_id)
    if config_data:
        await r.hset(hash_key, mapping=config_data)
        await r.expire(hash_key, TTL_CONFIG)


async def _prewarm_oauth(
    db: "AsyncSession",
    r: Any,
    org_uuid: UUID | None,
) -> None:
    """Pre-warm OAuth providers and tokens for the organization."""
    from src.core.security import decrypt_secret
    from src.models.orm import OAuthProvider, OAuthToken

    # Query providers (org-specific + global)
    if org_uuid:
        query = select(OAuthProvider).where(
            or_(
                OAuthProvider.organization_id == org_uuid,
                OAuthProvider.organization_id.is_(None),
            )
        )
    else:
        query = select(OAuthProvider).where(OAuthProvider.organization_id.is_(None))

    result = await db.execute(query)
    providers = result.scalars().all()

    if not providers:
        return

    oauth_data: dict[str, str] = {}
    for provider in providers:
        # Get org-level token (user_id is NULL)
        token_query = select(OAuthToken).where(
            OAuthToken.provider_id == provider.id,
            OAuthToken.user_id.is_(None),
        )
        token_result = await db.execute(token_query)
        token = token_result.scalars().first()

        # Decrypt sensitive fields
        try:
            # encrypted_* fields may be bytes or str depending on DB driver
            client_secret_raw = provider.encrypted_client_secret
            client_secret = (
                decrypt_secret(
                    client_secret_raw.decode() if isinstance(client_secret_raw, bytes) else client_secret_raw
                )
                if client_secret_raw
                else None
            )

            access_token_raw = token.encrypted_access_token if token else None
            access_token = (
                decrypt_secret(
                    access_token_raw.decode() if isinstance(access_token_raw, bytes) else access_token_raw
                )
                if access_token_raw
                else None
            )

            refresh_token_raw = token.encrypted_refresh_token if token else None
            refresh_token = (
                decrypt_secret(
                    refresh_token_raw.decode() if isinstance(refresh_token_raw, bytes) else refresh_token_raw
                )
                if refresh_token_raw
                else None
            )
        except Exception:
            continue  # Skip if decryption fails

        cache_value = {
            "provider_id": str(provider.id),
            "provider_name": provider.provider_name,
            "client_id": provider.client_id,
            "client_secret": client_secret,
            "authorization_url": provider.authorization_url,
            "token_url": provider.token_url,
            "scopes": provider.scopes,
            "access_token": access_token,
            "refresh_token": refresh_token,
            "expires_at": token.expires_at.isoformat() if token and token.expires_at else None,
        }

        oauth_data[provider.provider_name] = json.dumps(cache_value)

    # Write to Redis hash
    org_id = str(org_uuid) if org_uuid else None
    hash_key = oauth_hash_key(org_id)
    if oauth_data:
        await r.hset(hash_key, mapping=oauth_data)
        await r.expire(hash_key, TTL_OAUTH)


async def _prewarm_forms(
    db: "AsyncSession",
    r: Any,
    org_uuid: UUID | None,
    user_id: str,
    is_admin: bool,
) -> None:
    """Pre-warm forms accessible by the user."""
    from src.models.orm import Form, FormRole, UserRole

    user_uuid = UUID(user_id)

    # Admins see all active forms
    if is_admin:
        if org_uuid:
            query = select(Form).where(
                Form.is_active.is_(True),
                or_(Form.organization_id == org_uuid, Form.organization_id.is_(None)),
            )
        else:
            query = select(Form).where(
                Form.is_active.is_(True),
                Form.organization_id.is_(None),
            )
    else:
        # Non-admins see forms assigned to their roles
        query = (
            select(Form)
            .join(FormRole, Form.id == FormRole.form_id)
            .join(UserRole, FormRole.role_id == UserRole.role_id)
            .where(
                Form.is_active.is_(True),
                UserRole.user_id == user_uuid,
            )
        )
        if org_uuid:
            query = query.where(
                or_(Form.organization_id == org_uuid, Form.organization_id.is_(None))
            )

    result = await db.execute(query)
    forms = result.scalars().all()

    if not forms:
        return

    # Build hash data
    forms_data: dict[str, str] = {}
    form_ids: list[str] = []
    for form in forms:
        cache_value = {
            "id": str(form.id),
            "name": form.name,
            "description": form.description,
            "linked_workflow": form.linked_workflow,
            "is_active": form.is_active,
            "organization_id": str(form.organization_id) if form.organization_id else None,
        }
        forms_data[str(form.id)] = json.dumps(cache_value)
        form_ids.append(str(form.id))

    # Write to Redis hash
    org_id = str(org_uuid) if org_uuid else None
    hash_key = forms_hash_key(org_id)
    if forms_data:
        await r.hset(hash_key, mapping=forms_data)
        await r.expire(hash_key, TTL_FORMS)

    # Also cache user's accessible form IDs
    user_forms_redis_key = user_forms_key(org_id, user_id)
    if form_ids:
        await r.delete(user_forms_redis_key)  # Clear existing
        await r.sadd(user_forms_redis_key, *form_ids)
        await r.expire(user_forms_redis_key, TTL_FORMS)


async def _prewarm_roles(
    db: "AsyncSession",
    r: Any,
    org_uuid: UUID | None,
) -> None:
    """Pre-warm roles for the organization."""
    from src.models.orm import FormRole, Role, UserRole

    # Query roles
    if org_uuid:
        query = select(Role).where(
            Role.is_active.is_(True),
            or_(Role.organization_id == org_uuid, Role.organization_id.is_(None)),
        )
    else:
        query = select(Role).where(
            Role.is_active.is_(True),
            Role.organization_id.is_(None),
        )

    result = await db.execute(query)
    roles = result.scalars().all()

    if not roles:
        return

    roles_data: dict[str, str] = {}
    org_id = str(org_uuid) if org_uuid else None

    for role in roles:
        cache_value = {
            "id": str(role.id),
            "name": role.name,
            "description": role.description,
            "is_active": role.is_active,
            "organization_id": str(role.organization_id) if role.organization_id else None,
        }
        roles_data[str(role.id)] = json.dumps(cache_value)

        # Also cache role's user and form assignments
        # User assignments
        user_query = select(UserRole.user_id).where(UserRole.role_id == role.id)
        user_result = await db.execute(user_query)
        user_ids = [str(uid) for uid in user_result.scalars().all()]
        if user_ids:
            users_key = role_users_key(org_id, str(role.id))
            await r.delete(users_key)
            await r.sadd(users_key, *user_ids)
            await r.expire(users_key, TTL_ROLES)

        # Form assignments
        form_query = select(FormRole.form_id).where(FormRole.role_id == role.id)
        form_result = await db.execute(form_query)
        form_ids = [str(fid) for fid in form_result.scalars().all()]
        if form_ids:
            forms_key = role_forms_key(org_id, str(role.id))
            await r.delete(forms_key)
            await r.sadd(forms_key, *form_ids)
            await r.expire(forms_key, TTL_ROLES)

    # Write to Redis hash
    hash_key = roles_hash_key(org_id)
    if roles_data:
        await r.hset(hash_key, mapping=roles_data)
        await r.expire(hash_key, TTL_ROLES)


async def _prewarm_organization(
    db: "AsyncSession",
    r: Any,
    org_uuid: UUID,
) -> None:
    """Pre-warm organization data."""
    from src.models.orm import Organization

    query = select(Organization).where(Organization.id == org_uuid)
    result = await db.execute(query)
    org = result.scalars().first()

    if not org:
        return

    cache_value = {
        "id": str(org.id),
        "name": org.name,
        "domain": org.domain,
        "is_active": org.is_active,
    }

    redis_key = org_key(str(org_uuid))
    await r.set(redis_key, json.dumps(cache_value), ex=TTL_ORGS)
