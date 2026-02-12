"""
LLM Configuration Service

Manages LLM provider configuration in system_configs table.
Follows the same pattern as GitHubConfigService for SystemConfig storage.
"""

import base64
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

from cryptography.fernet import Fernet
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import get_settings
from src.models.orm import SystemConfig

logger = logging.getLogger(__name__)

# SystemConfig keys (same as factory.py)
LLM_CONFIG_CATEGORY = "llm"
LLM_CONFIG_KEY = "provider_config"


@dataclass
class LLMProviderConfig:
    """LLM provider configuration (API key masked for responses)."""

    provider: Literal["openai", "anthropic"]
    model: str
    endpoint: str | None = None  # For custom OpenAI-compatible providers
    max_tokens: int = 4096
    temperature: float = 0.7
    default_system_prompt: str | None = None  # Default system prompt for agentless chat
    is_configured: bool = False
    api_key_set: bool = False  # Indicates if API key is configured (never return actual key)


@dataclass
class LLMModelInfo:
    """Model information with both ID and display name."""

    id: str
    display_name: str


@dataclass
class LLMTestResult:
    """Result of testing LLM connection."""

    success: bool
    message: str
    models: list[LLMModelInfo] | None = None  # Available models if provider supports listing


class LLMConfigService:
    """
    Service for managing LLM provider configuration.

    Stores configuration in system_configs table with:
    - category: "llm"
    - key: "provider_config"
    - value_json: JSON object with provider settings
    - organization_id: NULL (global config)

    API keys are encrypted using Fernet (same as GitHub token encryption).
    """

    def __init__(self, session: AsyncSession):
        """Initialize the service with a database session."""
        self.session = session
        self.settings = get_settings()

    def _get_fernet(self) -> Fernet:
        """Get Fernet instance for encryption/decryption."""
        key_bytes = self.settings.secret_key.encode()[:32].ljust(32, b"0")
        return Fernet(base64.urlsafe_b64encode(key_bytes))

    async def get_config(self) -> LLMProviderConfig | None:
        """
        Get current LLM configuration (API key masked).

        Returns:
            LLMProviderConfig with current settings, or None if not configured
        """
        result = await self.session.execute(
            select(SystemConfig).where(
                SystemConfig.category == LLM_CONFIG_CATEGORY,
                SystemConfig.key == LLM_CONFIG_KEY,
                SystemConfig.organization_id.is_(None),
            )
        )
        config = result.scalars().first()

        if not config or not config.value_json:
            return None

        config_data = config.value_json

        # Map legacy "custom" provider to "openai"
        provider = config_data.get("provider", "openai")
        if provider == "custom":
            provider = "openai"

        return LLMProviderConfig(
            provider=provider,
            model=config_data.get("model", ""),
            endpoint=config_data.get("endpoint"),
            max_tokens=config_data.get("max_tokens", 4096),
            temperature=config_data.get("temperature", 0.7),
            default_system_prompt=config_data.get("default_system_prompt"),
            is_configured=True,
            api_key_set=bool(config_data.get("encrypted_api_key")),
        )

    async def save_config(
        self,
        provider: Literal["openai", "anthropic"],
        model: str,
        api_key: str,
        endpoint: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        default_system_prompt: str | None = None,
        updated_by: str = "system",
    ) -> None:
        """
        Save LLM provider configuration.

        Args:
            provider: LLM provider type
            model: Model identifier
            api_key: API key (will be encrypted)
            endpoint: Custom endpoint URL (for custom providers)
            max_tokens: Maximum tokens for completion
            temperature: Temperature for sampling
            default_system_prompt: Default system prompt for agentless chat
            updated_by: Email/ID of user making the change
        """
        fernet = self._get_fernet()

        # Encrypt the API key
        encrypted_api_key = fernet.encrypt(api_key.encode()).decode()

        # Check if config already exists
        result = await self.session.execute(
            select(SystemConfig).where(
                SystemConfig.category == LLM_CONFIG_CATEGORY,
                SystemConfig.key == LLM_CONFIG_KEY,
                SystemConfig.organization_id.is_(None),
            )
        )
        existing = result.scalars().first()

        config_data = {
            "provider": provider,
            "model": model,
            "encrypted_api_key": encrypted_api_key,
            "endpoint": endpoint,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "default_system_prompt": default_system_prompt,
        }

        if existing:
            # Update existing config
            existing.value_json = config_data
            existing.updated_at = datetime.now(timezone.utc)
            existing.updated_by = updated_by
            logger.info(f"Updated LLM config: provider={provider}, model={model}")
        else:
            # Create new config
            new_config = SystemConfig(
                id=uuid4(),
                category=LLM_CONFIG_CATEGORY,
                key=LLM_CONFIG_KEY,
                value_json=config_data,
                value_bytes=None,
                organization_id=None,
                created_by=updated_by,
                updated_by=updated_by,
            )
            self.session.add(new_config)
            logger.info(f"Created LLM config: provider={provider}, model={model}")

        await self.session.flush()

    async def delete_config(self) -> bool:
        """
        Delete LLM configuration.

        Returns:
            True if config was deleted, False if it didn't exist
        """
        result = await self.session.execute(
            select(SystemConfig).where(
                SystemConfig.category == LLM_CONFIG_CATEGORY,
                SystemConfig.key == LLM_CONFIG_KEY,
                SystemConfig.organization_id.is_(None),
            )
        )
        config = result.scalars().first()

        if config:
            await self.session.delete(config)
            await self.session.flush()
            logger.info("Deleted LLM config")
            return True

        return False

    async def test_connection(self) -> LLMTestResult:
        """
        Test connection to the configured LLM provider.

        Returns:
            LLMTestResult with success status and available models
        """
        from src.services.llm.factory import get_llm_config

        try:
            # Get and validate config
            config = await get_llm_config(self.session)

            # Try to create a minimal completion to test the connection
            if config.provider == "openai":
                return await self._test_openai(config.api_key, config.model, config.endpoint)
            elif config.provider == "anthropic":
                return await self._test_anthropic(config.api_key, config.model, config.endpoint)
            else:
                return LLMTestResult(
                    success=False,
                    message=f"Unknown provider: {config.provider}",
                )

        except ValueError as e:
            return LLMTestResult(success=False, message=str(e))
        except Exception as e:
            logger.error(f"LLM connection test failed: {e}")
            return LLMTestResult(success=False, message=f"Connection test failed: {e}")

    async def _test_openai(self, api_key: str, model: str, endpoint: str | None = None) -> LLMTestResult:
        """Test OpenAI-compatible connection and list models."""
        import re

        try:
            from openai import AsyncOpenAI

            client = AsyncOpenAI(api_key=api_key, base_url=endpoint or None)

            endpoint_label = endpoint or "https://api.openai.com/v1"

            # Try to list models (some custom endpoints may not support this)
            model_infos: list[LLMModelInfo] = []
            model_available = False
            try:
                models_response = await client.models.list()

                # OpenAI date suffix pattern: -YYYY-MM-DD
                date_pattern = re.compile(r"-\d{4}-\d{2}-\d{2}$")
                seen_display_names: set[str] = set()

                for m in sorted(models_response.data, key=lambda x: x.id, reverse=True):
                    # Derive display name by stripping date suffix
                    display_name = date_pattern.sub("", m.id)

                    # Only include the newest version of each model (first seen since sorted desc)
                    if display_name in seen_display_names:
                        continue

                    seen_display_names.add(display_name)
                    model_infos.append(LLMModelInfo(id=m.id, display_name=display_name))

                # Sort by display name for consistent ordering
                model_infos.sort(key=lambda x: x.display_name)

                # Check if the configured model is available
                all_model_ids = [m.id for m in models_response.data]
                model_available = model in all_model_ids
            except Exception as e:
                logger.info(f"Model listing not supported at {endpoint_label}: {e}")

            if model_infos:
                return LLMTestResult(
                    success=True,
                    message=f"Connected to {endpoint_label}. Model '{model}' {'is' if model_available else 'may not be'} available.",
                    models=model_infos[:20],
                )
            else:
                return LLMTestResult(
                    success=True,
                    message=f"Connected to {endpoint_label}. Model listing not available — enter model ID manually.",
                    models=None,
                )

        except Exception as e:
            return LLMTestResult(success=False, message=f"OpenAI connection failed: {e}")

    async def _test_anthropic(self, api_key: str, model: str, endpoint: str | None = None) -> LLMTestResult:
        """Test Anthropic connection and list models."""
        try:
            from anthropic import AsyncAnthropic

            client = AsyncAnthropic(api_key=api_key, base_url=endpoint or None)

            endpoint_label = endpoint or "https://api.anthropic.com"

            # Try to list models (custom endpoints may not support this)
            model_infos: list[LLMModelInfo] = []
            model_available = False
            try:
                models_response = await client.models.list()

                # Anthropic API returns display_name directly
                seen_display_names: set[str] = set()

                # Sort by ID descending to get newest versions first
                for m in sorted(models_response.data, key=lambda x: x.id, reverse=True):
                    display_name = getattr(m, "display_name", m.id)

                    # Only include the newest version of each model
                    if display_name in seen_display_names:
                        continue

                    seen_display_names.add(display_name)
                    model_infos.append(LLMModelInfo(id=m.id, display_name=display_name))

                # Sort by display name for consistent ordering
                model_infos.sort(key=lambda x: x.display_name)

                # Check if the configured model is available
                all_model_ids = [m.id for m in models_response.data]
                model_available = model in all_model_ids
            except Exception as e:
                logger.info(f"Model listing not supported at {endpoint_label}: {e}")

            if model_infos:
                return LLMTestResult(
                    success=True,
                    message=f"Connected to {endpoint_label}. Model '{model}' {'is' if model_available else 'may not be'} available.",
                    models=model_infos,
                )
            else:
                return LLMTestResult(
                    success=True,
                    message=f"Connected to {endpoint_label}. Model listing not available — enter model ID manually.",
                    models=None,
                )

        except Exception as e:
            return LLMTestResult(success=False, message=f"Anthropic connection failed: {e}")

    async def list_models(self) -> list[LLMModelInfo] | None:
        """
        List available models from the configured provider.

        Returns:
            List of model info objects, or None if not available
        """
        result = await self.test_connection()
        return result.models if result.success else None
