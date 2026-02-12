"""
LLM Configuration Admin Router

Admin endpoints for managing LLM provider configuration.
Requires platform admin access.
"""

import logging

from fastapi import APIRouter, HTTPException, status

from src.core.auth import CurrentActiveUser, RequirePlatformAdmin
from src.core.database import DbSession
from src.models.contracts.llm import (
    EmbeddingConfigRequest,
    EmbeddingConfigResponse,
    EmbeddingTestResponse,
    LLMConfigRequest,
    LLMConfigResponse,
    LLMModelInfo,
    LLMModelsResponse,
    LLMTestRequest,
    LLMTestResponse,
)
from src.services.embeddings.factory import (
    EMBEDDING_CONFIG_CATEGORY,
    EMBEDDING_CONFIG_KEY,
    get_embedding_config,
)
from src.services.llm_config_service import LLMConfigService

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/admin/llm",
    tags=["LLM Configuration"],
    dependencies=[RequirePlatformAdmin],  # All endpoints require platform admin
)


@router.get("/config")
async def get_llm_config(
    db: DbSession,
    user: CurrentActiveUser,
) -> LLMConfigResponse | None:
    """
    Get current LLM provider configuration.

    Returns the configuration without the API key (only indicates if it's set).
    Requires platform admin access.
    """
    service = LLMConfigService(db)
    config = await service.get_config()

    if not config:
        return None

    return LLMConfigResponse(
        provider=config.provider,
        model=config.model,
        endpoint=config.endpoint,
        max_tokens=config.max_tokens,
        temperature=config.temperature,
        default_system_prompt=config.default_system_prompt,
        is_configured=config.is_configured,
        api_key_set=config.api_key_set,
    )


@router.post("/config", status_code=status.HTTP_200_OK)
async def set_llm_config(
    request: LLMConfigRequest,
    db: DbSession,
    user: CurrentActiveUser,
) -> LLMConfigResponse:
    """
    Set LLM provider configuration.

    The API key will be encrypted before storage.
    Requires platform admin access.
    """
    service = LLMConfigService(db)

    await service.save_config(
        provider=request.provider,
        model=request.model,
        api_key=request.api_key,
        endpoint=request.endpoint,
        max_tokens=request.max_tokens,
        temperature=request.temperature,
        default_system_prompt=request.default_system_prompt,
        updated_by=user.email,
    )

    await db.commit()

    logger.info(f"LLM config updated by {user.email}: provider={request.provider}, model={request.model}")

    return LLMConfigResponse(
        provider=request.provider,
        model=request.model,
        endpoint=request.endpoint,
        max_tokens=request.max_tokens,
        temperature=request.temperature,
        default_system_prompt=request.default_system_prompt,
        is_configured=True,
        api_key_set=True,
    )


@router.delete("/config", status_code=status.HTTP_204_NO_CONTENT)
async def delete_llm_config(
    db: DbSession,
    user: CurrentActiveUser,
) -> None:
    """
    Delete LLM provider configuration.

    Requires platform admin access.
    """
    service = LLMConfigService(db)
    deleted = await service.delete_config()

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="LLM configuration not found",
        )

    await db.commit()
    logger.info(f"LLM config deleted by {user.email}")


@router.post("/test")
async def test_llm_connection(
    request: LLMTestRequest,
    db: DbSession,
    user: CurrentActiveUser,
) -> LLMTestResponse:
    """
    Test LLM connection with provided credentials.

    Tests the connection without saving the configuration.
    Useful for validating API keys before committing.
    Also caches the model ID -> display name mapping for AI usage tracking.
    Requires platform admin access.
    """
    service = LLMConfigService(db)

    # Temporarily save the config to test
    # We'll roll back the transaction so it's not persisted
    await service.save_config(
        provider=request.provider,
        model=request.model,
        api_key=request.api_key,
        endpoint=request.endpoint,
        updated_by=user.email,
    )

    result = await service.test_connection()

    # Rollback to not persist the test config
    await db.rollback()

    # Cache model mapping for AI usage tracking (even if test-only)
    if result.success and result.models:
        await _cache_model_mapping_from_result(request.provider, result.models)

    return LLMTestResponse(
        success=result.success,
        message=result.message,
        models=[LLMModelInfo(id=m.id, display_name=m.display_name) for m in result.models] if result.models else None,
    )


@router.post("/test-saved")
async def test_saved_llm_connection(
    db: DbSession,
    user: CurrentActiveUser,
) -> LLMTestResponse:
    """
    Test connection using saved LLM configuration.

    Tests the currently saved configuration.
    Also refreshes the model ID -> display name mapping cache.
    Requires platform admin access.
    """
    service = LLMConfigService(db)
    config = await service.get_config()

    if not config or not config.is_configured:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="LLM configuration not found",
        )

    result = await service.test_connection()

    # Cache model mapping for AI usage tracking
    if result.success and result.models:
        await _cache_model_mapping_from_result(config.provider, result.models)

    return LLMTestResponse(
        success=result.success,
        message=result.message,
        models=[LLMModelInfo(id=m.id, display_name=m.display_name) for m in result.models] if result.models else None,
    )


@router.get("/models")
async def list_llm_models(
    db: DbSession,
    user: CurrentActiveUser,
) -> LLMModelsResponse:
    """
    List available models from the configured LLM provider.

    Works with OpenAI and Anthropic (both support model listing).
    Requires platform admin access.
    """
    service = LLMConfigService(db)
    config = await service.get_config()

    if not config or not config.is_configured:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="LLM configuration not found",
        )

    models = await service.list_models()

    if models is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not retrieve models from provider",
        )

    return LLMModelsResponse(
        models=[LLMModelInfo(id=m.id, display_name=m.display_name) for m in models],
        provider=config.provider,
    )


# =============================================================================
# Embedding Configuration Endpoints
# =============================================================================


@router.get("/embedding-config")
async def get_embedding_config_endpoint(
    db: DbSession,
    user: CurrentActiveUser,
) -> EmbeddingConfigResponse:
    """
    Get current embedding configuration.

    Returns the configuration and indicates whether it uses a dedicated key
    or falls back to the LLM provider's OpenAI key.
    Requires platform admin access.
    """
    from sqlalchemy import select
    from src.models.orm import SystemConfig

    # Check for dedicated embedding config
    result = await db.execute(
        select(SystemConfig).where(
            SystemConfig.category == EMBEDDING_CONFIG_CATEGORY,
            SystemConfig.key == EMBEDDING_CONFIG_KEY,
            SystemConfig.organization_id.is_(None),
        )
    )
    embedding_config = result.scalars().first()

    if embedding_config and embedding_config.value_json:
        config_data = embedding_config.value_json
        return EmbeddingConfigResponse(
            model=config_data.get("model", "text-embedding-3-small"),
            dimensions=config_data.get("dimensions", 1536),
            is_configured=True,
            api_key_set=bool(config_data.get("encrypted_api_key")),
            uses_llm_key=False,
        )

    # Check if we can fall back to LLM config
    try:
        await get_embedding_config(db)
        # If we get here, we're using the LLM key
        return EmbeddingConfigResponse(
            model="text-embedding-3-small",
            dimensions=1536,
            is_configured=True,
            api_key_set=True,
            uses_llm_key=True,
        )
    except ValueError:
        # No config available
        return EmbeddingConfigResponse(
            model="text-embedding-3-small",
            dimensions=1536,
            is_configured=False,
            api_key_set=False,
            uses_llm_key=False,
        )


@router.post("/embedding-config", status_code=status.HTTP_200_OK)
async def set_embedding_config(
    request: EmbeddingConfigRequest,
    db: DbSession,
    user: CurrentActiveUser,
) -> EmbeddingConfigResponse:
    """
    Set dedicated embedding configuration.

    This allows using a separate OpenAI key for embeddings,
    useful when the main LLM provider is Anthropic.
    Requires platform admin access.
    """
    import base64
    from cryptography.fernet import Fernet
    from sqlalchemy import select
    from src.config import get_settings
    from src.models.orm import SystemConfig

    settings = get_settings()

    # Encrypt the API key
    key_bytes = settings.secret_key.encode()[:32].ljust(32, b"0")
    fernet = Fernet(base64.urlsafe_b64encode(key_bytes))
    encrypted_key = fernet.encrypt(request.api_key.encode()).decode()

    config_data = {
        "model": request.model,
        "dimensions": request.dimensions,
        "encrypted_api_key": encrypted_key,
    }

    # Upsert the config
    result = await db.execute(
        select(SystemConfig).where(
            SystemConfig.category == EMBEDDING_CONFIG_CATEGORY,
            SystemConfig.key == EMBEDDING_CONFIG_KEY,
            SystemConfig.organization_id.is_(None),
        )
    )
    existing = result.scalars().first()

    if existing:
        existing.value_json = config_data
        existing.updated_by = user.email
    else:
        new_config = SystemConfig(
            category=EMBEDDING_CONFIG_CATEGORY,
            key=EMBEDDING_CONFIG_KEY,
            value_json=config_data,
            created_by=user.email,
            updated_by=user.email,
        )
        db.add(new_config)

    await db.commit()

    logger.info(f"Embedding config updated by {user.email}: model={request.model}")

    return EmbeddingConfigResponse(
        model=request.model,
        dimensions=request.dimensions,
        is_configured=True,
        api_key_set=True,
        uses_llm_key=False,
    )


@router.delete("/embedding-config", status_code=status.HTTP_204_NO_CONTENT)
async def delete_embedding_config(
    db: DbSession,
    user: CurrentActiveUser,
) -> None:
    """
    Delete dedicated embedding configuration.

    After deletion, embeddings will fall back to using the LLM provider's
    OpenAI key (if available).
    Requires platform admin access.
    """
    from sqlalchemy import select
    from src.models.orm import SystemConfig

    result = await db.execute(
        select(SystemConfig).where(
            SystemConfig.category == EMBEDDING_CONFIG_CATEGORY,
            SystemConfig.key == EMBEDDING_CONFIG_KEY,
            SystemConfig.organization_id.is_(None),
        )
    )
    existing = result.scalars().first()

    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Embedding configuration not found",
        )

    await db.delete(existing)
    await db.commit()

    logger.info(f"Embedding config deleted by {user.email}")


@router.post("/embedding-test")
async def test_embedding_connection(
    request: EmbeddingConfigRequest,
    db: DbSession,
    user: CurrentActiveUser,
) -> EmbeddingTestResponse:
    """
    Test embedding connection with provided credentials.

    Tests the connection without saving the configuration.
    Requires platform admin access.
    """
    from src.services.embeddings.base import EmbeddingConfig
    from src.services.embeddings.openai_client import OpenAIEmbeddingClient

    try:
        config = EmbeddingConfig(
            api_key=request.api_key,
            model=request.model,
            dimensions=request.dimensions,
        )
        client = OpenAIEmbeddingClient(config)

        # Test with a simple embedding
        embedding = await client.embed_single("test connection")

        return EmbeddingTestResponse(
            success=True,
            message="Successfully connected and generated test embedding",
            dimensions=len(embedding),
        )
    except Exception as e:
        logger.warning(f"Embedding test failed: {e}")
        return EmbeddingTestResponse(
            success=False,
            message=f"Connection failed: {str(e)}",
            dimensions=None,
        )


# =============================================================================
# Helper Functions
# =============================================================================


async def _cache_model_mapping_from_result(
    provider: str,
    models: list,
) -> None:
    """
    Cache model ID -> display name mapping from test connection results.

    This populates the model registry cache so that AI usage recording
    can look up display names without making provider API calls.

    Args:
        provider: LLM provider ("openai" or "anthropic")
        models: List of LLMModelInfo dataclasses from test result
    """
    from src.core.cache import get_shared_redis
    from src.services.model_registry import cache_model_mapping

    try:
        redis_client = await get_shared_redis()
        mapping = {m.id: m.display_name for m in models}
        await cache_model_mapping(redis_client, provider, mapping)
    except Exception as e:
        logger.warning(f"Failed to cache model mapping for {provider}: {e}")


