"""
Configuration resolver with transparent secret handling.

This module provides unified configuration access that automatically decrypts
secret values stored in the Config table.
"""

import logging
from typing import Any, TYPE_CHECKING

from src.models.models import ConfigType

if TYPE_CHECKING:
    from src.sdk.context import Organization

logger = logging.getLogger(__name__)


class ConfigResolver:
    """
    Resolves configuration values with transparent secret handling.

    Features:
    - Automatic config type detection (secret vs plain values)
    - Transparent decryption for secret type configs
    - Type parsing for int, bool, json types
    """

    def __init__(self):
        """Initialize the configuration resolver."""
        pass

    async def get_config(
        self,
        org_id: str,
        key: str,
        config_data: dict[str, Any],
        default: Any = ...,  # Sentinel value to distinguish None from "not provided"
    ) -> Any:
        """
        Get configuration value with transparent secret decryption.

        Logic:
        1. Check if key exists in config_data
        2. Determine config type (if available)
        3. If type is secret, decrypt the value
        4. Otherwise, return/parse plain value
        5. If key not found, return default or raise KeyError

        Args:
            org_id: Organization identifier
            key: Configuration key
            config_data: Configuration dictionary
                        Expected format: {key: {"value": "...", "type": "secret"}}
                        or {key: "plain_value"}
            default: Default value if key not found. If not provided, raises KeyError.

        Returns:
            Configuration value (with secret decrypted if needed)

        Raises:
            KeyError: If key not found and no default provided
        """
        # Check if key exists
        if key not in config_data:
            if default is ...:  # No default provided
                raise KeyError(f"Configuration key '{key}' not found for org '{org_id}'")
            logger.debug(f"Config key not found: {key}, returning default")
            return default

        config_entry = config_data[key]

        # Handle simple string values (backwards compatibility)
        if isinstance(config_entry, str):
            logger.debug(f"Retrieved plain config value: {key}")
            return config_entry

        # Handle structured config entries
        if isinstance(config_entry, dict):
            config_type = config_entry.get("type")
            config_value = config_entry.get("value")

            if config_value is None:
                raise ValueError(f"Config value is None for key '{key}'")

            # If type is secret, decrypt the value
            if config_type == ConfigType.SECRET.value or config_type == "secret":
                return self._decrypt_secret(key, config_value)

            # Otherwise return parsed plain value
            logger.debug(f"Retrieved plain config value: {key} (type: {config_type})")
            return self._parse_value(config_value, config_type)

        # Fallback: return value as-is
        logger.debug(f"Retrieved config value: {key}")
        return config_entry

    def _decrypt_secret(self, config_key: str, encrypted_value: str) -> str:
        """
        Decrypt a secret value.

        Args:
            config_key: Configuration key (for logging)
            encrypted_value: The encrypted value to decrypt

        Returns:
            Decrypted secret value

        Raises:
            ValueError: If decryption fails
        """
        try:
            from src.core.security import decrypt_secret

            logger.debug(f"Decrypting secret for config '{config_key}'")
            return decrypt_secret(encrypted_value)

        except Exception as e:
            error_msg = f"Failed to decrypt secret for config '{config_key}': {str(e)}"
            logger.error(error_msg, exc_info=True)
            raise ValueError(error_msg) from e

    def _parse_value(self, value: str, config_type: str | None) -> Any:
        """
        Parse configuration value based on type.

        Args:
            value: String value from config
            config_type: Config type (string, int, bool, json, secret)

        Returns:
            Parsed value in appropriate type

        Raises:
            ValueError: If value cannot be parsed for the specified type
        """
        import json

        try:
            if config_type == ConfigType.INT.value or config_type == "int":
                return int(value)
            elif config_type == ConfigType.BOOL.value or config_type == "bool":
                return value.lower() in ("true", "1", "yes")
            elif config_type == ConfigType.JSON.value or config_type == "json":
                return json.loads(value)
            else:
                # STRING or unknown type - return as string
                return value
        except (ValueError, TypeError, json.JSONDecodeError) as e:
            raise ValueError(f"Could not parse value '{value}' as type '{config_type}': {e}") from e

    async def get_organization(self, org_id: str) -> "Organization | None":
        """
        Get organization by ID from PostgreSQL.

        Args:
            org_id: Organization ID (UUID or "ORG:uuid" format)

        Returns:
            Organization object or None if not found
        """
        from uuid import UUID
        from sqlalchemy import select
        from src.core.database import get_session_factory
        from src.models.orm import Organization as OrgModel
        from src.sdk.context import Organization

        # Parse org_id - may be "ORG:uuid" or just "uuid"
        if org_id.startswith("ORG:"):
            org_uuid = org_id[4:]
        else:
            org_uuid = org_id

        try:
            org_uuid_obj = UUID(org_uuid)
        except ValueError:
            logger.warning(f"Invalid organization ID format: {org_id}")
            return None

        session_factory = get_session_factory()

        async with session_factory() as db:
            result = await db.execute(
                select(OrgModel).where(OrgModel.id == org_uuid_obj)
            )
            org_entity = result.scalar_one_or_none()

            if not org_entity:
                logger.debug(f"Organization not found: {org_id}")
                return None

            return Organization(
                id=str(org_entity.id),
                name=org_entity.name,
                is_active=org_entity.is_active,
            )

    async def load_config_for_scope(self, scope: str) -> dict[str, Any]:
        """
        Load all config for a scope (org_id or "GLOBAL") from PostgreSQL.

        Returns config as dict: {key: {"value": v, "type": t}, ...}

        Args:
            scope: "GLOBAL" or organization ID

        Returns:
            Configuration dictionary
        """
        from uuid import UUID
        from sqlalchemy import select
        from src.core.database import get_session_factory
        from src.models.orm import Config

        session_factory = get_session_factory()
        config_dict: dict[str, Any] = {}

        async with session_factory() as db:
            # For GLOBAL, get configs with no organization_id
            # For org scope, get global + org-specific configs (org overrides global)
            if scope == "GLOBAL":
                result = await db.execute(
                    select(Config).where(Config.organization_id.is_(None))
                )
            else:
                # Parse org_id
                if scope.startswith("ORG:"):
                    org_uuid = scope[4:]
                else:
                    org_uuid = scope

                try:
                    org_uuid_obj = UUID(org_uuid)
                except ValueError:
                    logger.warning(f"Invalid scope format: {scope}")
                    return config_dict

                # Get global configs first
                global_result = await db.execute(
                    select(Config).where(Config.organization_id.is_(None))
                )
                for config in global_result.scalars():
                    config_dict[config.key] = {
                        "value": config.value.get("value") if isinstance(config.value, dict) else config.value,
                        "type": config.config_type.value if config.config_type else "string",
                    }

                # Get org-specific configs (these override global)
                result = await db.execute(
                    select(Config).where(Config.organization_id == org_uuid_obj)
                )

            for config in result.scalars():
                config_dict[config.key] = {
                    "value": config.value.get("value") if isinstance(config.value, dict) else config.value,
                    "type": config.config_type.value if config.config_type else "string",
                }

        return config_dict
