"""
LLM Configuration Service

Manages LLM provider configuration in system_configs table.
Follows the same pattern as GitHubConfigService for SystemConfig storage.
"""

import base64
import logging
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Literal
from uuid import uuid4

from cryptography.fernet import Fernet
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import get_settings
from src.models.orm import SystemConfig
from src.models.orm.ai_usage import AIModelPricing

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
    max_tokens: int = 16384
    default_system_prompt: str | None = None  # Default system prompt for agentless chat
    summarization_model: str | None = None  # Override for post-run summarization
    tuning_model: str | None = None  # Override for tuning chat + dry-run
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
            max_tokens=config_data.get("max_tokens", 16384),
            default_system_prompt=config_data.get("default_system_prompt"),
            summarization_model=config_data.get("summarization_model"),
            tuning_model=config_data.get("tuning_model"),
            is_configured=True,
            api_key_set=bool(config_data.get("encrypted_api_key")),
        )

    async def save_config(
        self,
        provider: Literal["openai", "anthropic"],
        model: str,
        api_key: str | None = None,
        endpoint: str | None = None,
        max_tokens: int = 16384,
        default_system_prompt: str | None = None,
        summarization_model: str | None = None,
        tuning_model: str | None = None,
        updated_by: str = "system",
    ) -> None:
        """
        Save LLM provider configuration.

        Args:
            provider: LLM provider type
            model: Model identifier
            api_key: API key (will be encrypted). If None, preserves existing key.
            endpoint: Custom endpoint URL (for custom providers)
            max_tokens: Maximum tokens for completion
            default_system_prompt: Default system prompt for agentless chat
            summarization_model: Optional override for summarization calls.
                ``None`` means use the primary model.
            tuning_model: Optional override for tuning chat + dry-run calls.
                ``None`` means use the primary model.
            updated_by: Email/ID of user making the change
        """
        fernet = self._get_fernet()

        # Check if config already exists
        result = await self.session.execute(
            select(SystemConfig).where(
                SystemConfig.category == LLM_CONFIG_CATEGORY,
                SystemConfig.key == LLM_CONFIG_KEY,
                SystemConfig.organization_id.is_(None),
            )
        )
        existing = result.scalars().first()

        # Determine encrypted API key
        if api_key:
            encrypted_api_key = fernet.encrypt(api_key.encode()).decode()
        elif existing and existing.value_json and existing.value_json.get("encrypted_api_key"):
            encrypted_api_key = existing.value_json["encrypted_api_key"]
        else:
            raise ValueError("API key is required for initial configuration")

        config_data = {
            "provider": provider,
            "model": model,
            "encrypted_api_key": encrypted_api_key,
            "endpoint": endpoint,
            "max_tokens": max_tokens,
            "default_system_prompt": default_system_prompt,
            "summarization_model": summarization_model,
            "tuning_model": tuning_model,
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
        """Test OpenAI-compatible connection and verify chat completions work.

        List-models succeeds on many keys that can't actually complete chats
        (e.g. OpenAI project-scoped keys without explicit model permissions,
        which return "User not found" on ``/v1/chat/completions``). We run a
        1-token completion here to catch that before an admin goes and runs
        a backfill against a key that silently fails every real call.
        """
        try:
            from openai import AsyncOpenAI

            client = AsyncOpenAI(api_key=api_key, base_url=endpoint or None)

            endpoint_label = endpoint or "https://api.openai.com/v1"

            # Try to list models (some custom endpoints may not support this)
            model_infos: list[LLMModelInfo] = []
            model_available = False
            try:
                models_response = await client.models.list()

                all_model_ids: list[str] = []
                for m in sorted(models_response.data, key=lambda x: x.id):
                    all_model_ids.append(m.id)
                    model_infos.append(LLMModelInfo(id=m.id, display_name=m.id))

                model_available = model in all_model_ids
            except Exception as e:
                error_str = str(e).lower()
                # Auth errors should fail the connection test, not be silently swallowed
                if "401" in error_str or "403" in error_str or "unauthorized" in error_str or "forbidden" in error_str or "authentication" in error_str or "invalid" in error_str:
                    raise  # Re-raise to outer handler which returns success=False
                logger.info(f"Model listing not supported at {endpoint_label}: {e}")

            # Actually exercise the completions endpoint. A key may list models
            # fine but be rejected on chat completions (scoped keys, missing
            # model permissions). Without this, Test shows green but every
            # summarizer/tuning call dies with "User not found".
            try:
                await client.chat.completions.create(
                    model=model,
                    max_tokens=1,
                    messages=[{"role": "user", "content": "ping"}],
                )
            except Exception as e:
                return LLMTestResult(
                    success=False,
                    message=(
                        f"Connected to {endpoint_label} and listed models, but the "
                        f"configured model '{model}' rejected a test completion: {e}. "
                        "For OpenAI project keys, enable this model under Project Settings → Model Permissions."
                    ),
                    models=model_infos or None,
                )

            if model_infos:
                return LLMTestResult(
                    success=True,
                    message=f"Connected to {endpoint_label}. Model '{model}' {'is' if model_available else 'may not be'} available; test completion succeeded.",
                    models=model_infos,
                )
            else:
                return LLMTestResult(
                    success=True,
                    message=f"Connected to {endpoint_label}. Test completion succeeded — model listing not available.",
                    models=None,
                )

        except Exception as e:
            return LLMTestResult(success=False, message=f"OpenAI connection failed: {e}")

    async def _test_anthropic(self, api_key: str, model: str, endpoint: str | None = None) -> LLMTestResult:
        """Test Anthropic connection and verify message completions work.

        Symmetric with ``_test_openai``: list models, then issue a 1-token
        ``messages.create`` so keys that can enumerate but can't actually
        complete are caught here rather than silently failing every
        summarizer/tuning call downstream.
        """
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
                error_str = str(e).lower()
                # Auth errors should fail the connection test, not be silently swallowed
                if "401" in error_str or "403" in error_str or "unauthorized" in error_str or "forbidden" in error_str or "authentication" in error_str or "invalid" in error_str:
                    raise  # Re-raise to outer handler which returns success=False
                logger.info(f"Model listing not supported at {endpoint_label}: {e}")

            # Actually exercise the messages endpoint — see _test_openai for rationale.
            try:
                await client.messages.create(
                    model=model,
                    max_tokens=1,
                    messages=[{"role": "user", "content": "ping"}],
                )
            except Exception as e:
                return LLMTestResult(
                    success=False,
                    message=(
                        f"Connected to {endpoint_label} and listed models, but the "
                        f"configured model '{model}' rejected a test completion: {e}."
                    ),
                    models=model_infos or None,
                )

            if model_infos:
                return LLMTestResult(
                    success=True,
                    message=f"Connected to {endpoint_label}. Model '{model}' {'is' if model_available else 'may not be'} available; test completion succeeded.",
                    models=model_infos,
                )
            else:
                return LLMTestResult(
                    success=True,
                    message=f"Connected to {endpoint_label}. Test completion succeeded — model listing not available.",
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

    async def sync_provider_pricing(
        self,
        provider: str,
        model: str,
        api_key: str,
        endpoint: str,
    ) -> int:
        """
        Fetch pricing from a provider's /models endpoint and update AIModelPricing
        for the selected model and any existing pricing rows.

        Only creates a new pricing row for the selected model. Updates existing rows
        that match models returned by the provider.

        Returns:
            Number of models with pricing synced.
        """
        import httpx

        models_url = f"{endpoint.rstrip('/')}/models"
        async with httpx.AsyncClient(timeout=30) as http:
            resp = await http.get(
                models_url,
                headers={"Authorization": f"Bearer {api_key}"},
            )
            resp.raise_for_status()
            body = resp.json()

        # Build a lookup of model_id -> (input_per_million, output_per_million)
        provider_pricing: dict[str, tuple[Decimal, Decimal]] = {}
        quantize_to = Decimal("0.0001")
        max_price = Decimal("999999.9999")

        for item in body.get("data", []):
            model_id = item.get("id", "")
            pricing = item.get("pricing")
            if not model_id or not pricing:
                continue

            prompt_price = pricing.get("prompt")
            completion_price = pricing.get("completion")
            if not prompt_price or not completion_price:
                continue

            try:
                input_pm = (Decimal(prompt_price) * 1_000_000).quantize(quantize_to)
                output_pm = (Decimal(completion_price) * 1_000_000).quantize(quantize_to)
            except Exception:
                continue

            if input_pm > max_price or output_pm > max_price:
                continue

            provider_pricing[model_id] = (input_pm, output_pm)

        if not provider_pricing:
            return 0

        synced = 0
        today = date.today()

        # Update existing pricing rows that have a match in the provider data
        existing_result = await self.session.execute(
            select(AIModelPricing).where(AIModelPricing.provider == provider)
        )
        priced_models: set[str] = set()
        for row in existing_result.scalars().all():
            priced_models.add(row.model)
            if row.model in provider_pricing:
                input_pm, output_pm = provider_pricing[row.model]
                row.input_price_per_million = input_pm
                row.output_price_per_million = output_pm
                row.updated_at = datetime.now(timezone.utc)
                synced += 1

        # Find models that have been used but don't have pricing yet
        from src.models.orm.ai_usage import AIUsage

        used_result = await self.session.execute(
            select(AIUsage.model).where(AIUsage.provider == provider).distinct()
        )
        used_models = {row[0] for row in used_result.all()}

        # Create pricing for: selected model + used models without pricing
        models_to_add = ({model} | used_models) - priced_models
        for model_id in models_to_add:
            if model_id in provider_pricing:
                input_pm, output_pm = provider_pricing[model_id]
                self.session.add(
                    AIModelPricing(
                        provider=provider,
                        model=model_id,
                        input_price_per_million=input_pm,
                        output_price_per_million=output_pm,
                        effective_date=today,
                    )
                )
                synced += 1

        await self.session.flush()
        return synced
