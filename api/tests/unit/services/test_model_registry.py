"""
Unit tests for Model Registry Service.

Tests display name lookup, caching, and provider API fetching.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.model_registry import (
    MODEL_REGISTRY_KEY_PREFIX,
    MODEL_REGISTRY_TTL,
    cache_model_mapping,
    get_display_name,
    invalidate_model_registry,
    normalize_model_name,
    refresh_model_registry,
)


class TestNormalizeModelName:
    """Tests for fallback normalize_model_name function."""

    def test_normalizes_anthropic_dated_model(self):
        """Test normalization of Anthropic dated model ID."""
        result = normalize_model_name("claude-opus-4-5-20251101")
        assert result == "claude-opus-4-5"

    def test_normalizes_anthropic_sonnet(self):
        """Test normalization of Anthropic Sonnet model ID."""
        result = normalize_model_name("claude-sonnet-4-20250514")
        assert result == "claude-sonnet-4"

    def test_normalizes_anthropic_haiku(self):
        """Test normalization of Anthropic Haiku model ID."""
        result = normalize_model_name("claude-3-5-haiku-20241022")
        assert result == "claude-3-5-haiku"

    def test_normalizes_openai_dated_model(self):
        """Test normalization of OpenAI dated model ID."""
        result = normalize_model_name("gpt-4o-2024-11-20")
        assert result == "gpt-4o"

    def test_normalizes_openai_mini(self):
        """Test normalization of OpenAI mini model ID."""
        result = normalize_model_name("gpt-4o-mini-2024-07-18")
        assert result == "gpt-4o-mini"

    def test_passes_through_already_normalized(self):
        """Test already normalized names pass through unchanged."""
        assert normalize_model_name("gpt-4o") == "gpt-4o"
        assert normalize_model_name("gpt-4o-mini") == "gpt-4o-mini"
        assert normalize_model_name("claude-sonnet-4") == "claude-sonnet-4"

    def test_handles_edge_cases(self):
        """Test edge cases that shouldn't be normalized."""
        # Shouldn't normalize regular hyphens or numbers
        assert normalize_model_name("my-custom-model") == "my-custom-model"
        assert normalize_model_name("model-v2") == "model-v2"


class TestGetDisplayName:
    """Tests for get_display_name function."""

    @pytest.fixture
    def mock_redis(self):
        """Create mock Redis client."""
        redis = AsyncMock()
        return redis

    @pytest.mark.asyncio
    async def test_returns_from_cache(self, mock_redis):
        """Test display name lookup from Redis cache."""
        cache_data = {
            "claude-opus-4-5-20251101": "Claude Opus 4.5",
            "claude-sonnet-4-20250514": "Claude Sonnet 4",
        }
        mock_redis.get.return_value = json.dumps(cache_data)

        result = await get_display_name(
            mock_redis, "anthropic", "claude-opus-4-5-20251101"
        )

        assert result == "Claude Opus 4.5"
        mock_redis.get.assert_called_once_with(f"{MODEL_REGISTRY_KEY_PREFIX}anthropic")

    @pytest.mark.asyncio
    async def test_returns_normalized_name_when_not_in_cache_mapping(self, mock_redis):
        """Test returns normalized name when model is not in cached mapping."""
        cache_data = {"other-model": "Other Model"}
        mock_redis.get.return_value = json.dumps(cache_data)

        result = await get_display_name(
            mock_redis, "anthropic", "unknown-model-20251001"
        )

        # Should return normalized name (date stripped) if not found in mapping
        assert result == "unknown-model"

    @pytest.mark.asyncio
    async def test_fetches_from_api_on_cache_miss_with_api_key(self, mock_redis):
        """Test fetches from provider API on cache miss when API key is available."""
        mock_redis.get.return_value = None

        with patch(
            "src.services.model_registry.refresh_model_registry"
        ) as mock_refresh:
            mock_refresh.return_value = {
                "claude-opus-4-5-20251101": "Claude Opus 4.5",
                "claude-sonnet-4-20250514": "Claude Sonnet 4",
            }

            result = await get_display_name(
                mock_redis, "anthropic", "claude-opus-4-5-20251101", api_key="test-key"
            )

            # Should return display name from API fetch
            assert result == "Claude Opus 4.5"
            mock_refresh.assert_called_once_with(mock_redis, "anthropic", "test-key")

    @pytest.mark.asyncio
    async def test_returns_normalized_name_on_cache_miss_without_api_key(self, mock_redis):
        """Test returns normalized name when cache miss and no API key."""
        mock_redis.get.return_value = None

        result = await get_display_name(
            mock_redis, "anthropic", "claude-opus-4-5-20251101"
        )

        # Should return normalized name as fallback (no API key to refresh)
        assert result == "claude-opus-4-5"

    @pytest.mark.asyncio
    async def test_handles_redis_read_error(self, mock_redis):
        """Test graceful handling of Redis read errors."""
        mock_redis.get.side_effect = Exception("Redis connection error")

        result = await get_display_name(
            mock_redis, "anthropic", "claude-opus-4-5-20251101"
        )

        # Should fall back to normalized name on error
        assert result == "claude-opus-4-5"

    @pytest.mark.asyncio
    async def test_handles_api_refresh_error(self, mock_redis):
        """Test graceful handling of API refresh errors."""
        mock_redis.get.return_value = None

        with patch(
            "src.services.model_registry.refresh_model_registry"
        ) as mock_refresh:
            mock_refresh.side_effect = Exception("API error")

            result = await get_display_name(
                mock_redis, "anthropic", "claude-opus-4-5-20251101", api_key="test-key"
            )

            # Should fall back to normalized name when API refresh fails
            assert result == "claude-opus-4-5"
            mock_refresh.assert_called_once()


class TestCacheModelMapping:
    """Tests for cache_model_mapping function."""

    @pytest.fixture
    def mock_redis(self):
        """Create mock Redis client."""
        return AsyncMock()

    @pytest.mark.asyncio
    async def test_caches_mapping(self, mock_redis):
        """Test caches model mapping to Redis."""
        mapping = {
            "claude-opus-4-5-20251101": "Claude Opus 4.5",
            "claude-sonnet-4-20250514": "Claude Sonnet 4",
        }

        await cache_model_mapping(mock_redis, "anthropic", mapping)

        mock_redis.setex.assert_called_once()
        call_args = mock_redis.setex.call_args
        assert call_args[0][0] == f"{MODEL_REGISTRY_KEY_PREFIX}anthropic"
        assert call_args[0][1] == MODEL_REGISTRY_TTL
        cached_data = json.loads(call_args[0][2])
        assert cached_data == mapping

    @pytest.mark.asyncio
    async def test_skips_empty_mapping(self, mock_redis):
        """Test does not cache empty mapping."""
        await cache_model_mapping(mock_redis, "anthropic", {})

        mock_redis.setex.assert_not_called()

    @pytest.mark.asyncio
    async def test_handles_redis_error(self, mock_redis):
        """Test handles Redis errors gracefully."""
        mock_redis.setex.side_effect = Exception("Redis error")

        # Should not raise
        await cache_model_mapping(
            mock_redis,
            "anthropic",
            {"claude-opus-4-5-20251101": "Claude Opus 4.5"},
        )


class TestRefreshModelRegistry:
    """Tests for refresh_model_registry function."""

    @pytest.fixture
    def mock_redis(self):
        """Create mock Redis client."""
        return AsyncMock()

    @pytest.mark.asyncio
    async def test_refreshes_and_caches(self, mock_redis):
        """Test force refresh fetches and caches."""
        with patch(
            "src.services.model_registry._fetch_model_mapping"
        ) as mock_fetch:
            mock_fetch.return_value = {
                "claude-opus-4-5-20251101": "Claude Opus 4.5",
            }

            result = await refresh_model_registry(
                mock_redis, "anthropic", "test-key"
            )

            assert result == {"claude-opus-4-5-20251101": "Claude Opus 4.5"}
            mock_fetch.assert_called_once_with("anthropic", "test-key")
            mock_redis.setex.assert_called_once()

            # Verify cache key and TTL
            call_args = mock_redis.setex.call_args
            assert call_args[0][0] == f"{MODEL_REGISTRY_KEY_PREFIX}anthropic"
            assert call_args[0][1] == MODEL_REGISTRY_TTL


class TestInvalidateModelRegistry:
    """Tests for invalidate_model_registry function."""

    @pytest.fixture
    def mock_redis(self):
        """Create mock Redis client."""
        return AsyncMock()

    @pytest.mark.asyncio
    async def test_invalidates_specific_provider(self, mock_redis):
        """Test invalidating specific provider cache."""
        await invalidate_model_registry(mock_redis, "anthropic")

        mock_redis.delete.assert_called_once_with(
            f"{MODEL_REGISTRY_KEY_PREFIX}anthropic"
        )

    @pytest.mark.asyncio
    async def test_invalidates_all_providers(self, mock_redis):
        """Test invalidating all provider caches."""
        await invalidate_model_registry(mock_redis)

        assert mock_redis.delete.call_count == 2
        mock_redis.delete.assert_any_call(f"{MODEL_REGISTRY_KEY_PREFIX}openai")
        mock_redis.delete.assert_any_call(f"{MODEL_REGISTRY_KEY_PREFIX}anthropic")

    @pytest.mark.asyncio
    async def test_handles_redis_error(self, mock_redis):
        """Test graceful handling of Redis errors."""
        mock_redis.delete.side_effect = Exception("Redis error")

        # Should not raise
        await invalidate_model_registry(mock_redis, "anthropic")


class TestFetchAnthropicModels:
    """Tests for _fetch_anthropic_models function."""

    @pytest.mark.asyncio
    async def test_fetches_and_maps_models(self):
        """Test fetching and mapping Anthropic models."""
        from src.services.model_registry import _fetch_anthropic_models

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": [
                {
                    "type": "model",
                    "id": "claude-opus-4-5-20251101",
                    "display_name": "Claude Opus 4.5",
                },
                {
                    "type": "model",
                    "id": "claude-sonnet-4-20250514",
                    "display_name": "Claude Sonnet 4",
                },
            ]
        }
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            MockClient.return_value = mock_client

            result = await _fetch_anthropic_models("test-key")

            assert result == {
                "claude-opus-4-5-20251101": "Claude Opus 4.5",
                "claude-sonnet-4-20250514": "Claude Sonnet 4",
            }

            # Verify API call
            mock_client.get.assert_called_once()
            call_args = mock_client.get.call_args
            assert call_args[0][0] == "https://api.anthropic.com/v1/models"
            assert call_args[1]["headers"]["x-api-key"] == "test-key"


class TestFetchOpenAIModels:
    """Tests for _fetch_openai_models function."""

    @pytest.mark.asyncio
    async def test_fetches_and_derives_display_names(self):
        """Test fetching OpenAI models and deriving display names."""
        from src.services.model_registry import _fetch_openai_models

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": [
                {"id": "gpt-4o-2024-11-20", "object": "model"},
                {"id": "gpt-4o-mini-2024-07-18", "object": "model"},
                {"id": "gpt-4o", "object": "model"},
            ]
        }
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            MockClient.return_value = mock_client

            result = await _fetch_openai_models("test-key")

            assert result == {
                "gpt-4o-2024-11-20": "gpt-4o",
                "gpt-4o-mini-2024-07-18": "gpt-4o-mini",
                "gpt-4o": "gpt-4o",
            }

            # Verify API call
            mock_client.get.assert_called_once()
            call_args = mock_client.get.call_args
            assert call_args[0][0] == "https://api.openai.com/v1/models"
            assert "Bearer test-key" in call_args[1]["headers"]["Authorization"]
