"""Dynamic model resolution for summarization + tuning.

Reads overrides from ``LLMConfigService``; falls back to the default model.
Provider is always the default provider — overrides change the model name
only, not the provider or API key.
"""
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.llm import BaseLLMClient, get_llm_client
from src.services.llm_config_service import LLMConfigService


async def get_summarization_client(db: AsyncSession) -> tuple[BaseLLMClient, str]:
    """Return ``(llm_client, resolved_model_name)`` for summarization calls."""
    service = LLMConfigService(db)
    config = await service.get_config()
    if config is None:
        raise RuntimeError("No LLM config configured; cannot summarize")
    model = config.summarization_model or config.model
    client = await get_llm_client(db)
    return client, model


async def get_tuning_client(db: AsyncSession) -> tuple[BaseLLMClient, str]:
    """Return ``(llm_client, resolved_model_name)`` for tuning + dry-run calls."""
    service = LLMConfigService(db)
    config = await service.get_config()
    if config is None:
        raise RuntimeError("No LLM config configured; cannot tune")
    model = config.tuning_model or config.model
    client = await get_llm_client(db)
    return client, model
