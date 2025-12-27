"""
LLM Configuration Pydantic Models

Request/response models for LLM admin endpoints.
"""

from typing import Literal

from pydantic import BaseModel, Field


class LLMConfigResponse(BaseModel):
    """LLM configuration response (API key is never returned)."""

    provider: Literal["openai", "anthropic", "custom"]
    model: str
    endpoint: str | None = None
    max_tokens: int = 4096
    temperature: float = 0.7
    default_system_prompt: str | None = None
    is_configured: bool = True
    api_key_set: bool = False


class LLMConfigRequest(BaseModel):
    """Request to set LLM configuration."""

    provider: Literal["openai", "anthropic", "custom"] = Field(
        ...,
        description="LLM provider type",
    )
    model: str = Field(
        ...,
        min_length=1,
        description="Model identifier (e.g., 'gpt-4o', 'claude-sonnet-4-20250514')",
    )
    api_key: str = Field(
        ...,
        min_length=1,
        description="API key for the provider",
    )
    endpoint: str | None = Field(
        None,
        description="Custom endpoint URL (for custom OpenAI-compatible providers)",
    )
    max_tokens: int = Field(
        4096,
        ge=1,
        le=128000,
        description="Maximum tokens for completion",
    )
    temperature: float = Field(
        0.7,
        ge=0.0,
        le=2.0,
        description="Temperature for sampling (0.0-2.0)",
    )
    default_system_prompt: str | None = Field(
        None,
        description="Default system prompt for agentless chat",
    )


class LLMTestRequest(BaseModel):
    """Request to test LLM configuration before saving."""

    provider: Literal["openai", "anthropic", "custom"] = Field(
        ...,
        description="LLM provider type",
    )
    model: str = Field(
        ...,
        min_length=1,
        description="Model identifier",
    )
    api_key: str = Field(
        ...,
        min_length=1,
        description="API key to test",
    )
    endpoint: str | None = Field(
        None,
        description="Custom endpoint URL",
    )


class LLMModelInfo(BaseModel):
    """Model information with both ID and display name."""

    id: str
    display_name: str


class LLMTestResponse(BaseModel):
    """Response from testing LLM connection."""

    success: bool
    message: str
    models: list[LLMModelInfo] | None = None


class LLMModelsResponse(BaseModel):
    """Response listing available models."""

    models: list[LLMModelInfo]
    provider: str


# =============================================================================
# Embedding Configuration
# =============================================================================


class EmbeddingConfigResponse(BaseModel):
    """Embedding configuration response (API key is never returned)."""

    model: str = "text-embedding-3-small"
    dimensions: int = 1536
    is_configured: bool = True
    api_key_set: bool = False
    uses_llm_key: bool = False  # True if using LLM config's OpenAI key


class EmbeddingConfigRequest(BaseModel):
    """Request to set dedicated embedding configuration."""

    api_key: str = Field(
        ...,
        min_length=1,
        description="OpenAI API key for embeddings",
    )
    model: str = Field(
        "text-embedding-3-small",
        description="Embedding model (text-embedding-3-small or text-embedding-3-large)",
    )
    dimensions: int = Field(
        1536,
        ge=256,
        le=3072,
        description="Embedding dimensions (1536 for small, up to 3072 for large)",
    )


class EmbeddingTestResponse(BaseModel):
    """Response from testing embedding configuration."""

    success: bool
    message: str
    dimensions: int | None = None


# =============================================================================
# Coding Mode Configuration
# =============================================================================


class CodingConfigResponse(BaseModel):
    """Coding mode configuration response."""

    configured: bool = Field(
        description="True if coding mode has both API key and model configured"
    )
    model: str | None = Field(
        None,
        description="Effective model (override or main LLM)"
    )
    model_override: str | None = Field(
        None,
        description="Explicit model override if set"
    )
    has_key_override: bool = Field(
        False,
        description="True if using a dedicated coding API key instead of main LLM"
    )
    main_llm_is_anthropic: bool = Field(
        False,
        description="True if main LLM config is Anthropic (can be used as fallback)"
    )


class CodingConfigUpdate(BaseModel):
    """Request to update coding mode overrides."""

    model: str | None = Field(
        None,
        description="Model override. Set to override main LLM model."
    )
    api_key: str | None = Field(
        None,
        description="API key override. Set to use a dedicated key instead of main LLM."
    )
    clear_overrides: bool = Field(
        False,
        description="Set true to remove all overrides and use main LLM config"
    )
