"""Unit tests for data provider Redis cache."""

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest

from src.core.cache.data_provider_cache import (
    TTL_DATA_PROVIDER,
    acquire_compute_lock,
    cache_result,
    compute_param_hash,
    data_provider_cache_key,
    data_provider_lock_key,
    get_cached_result,
    invalidate_data_provider,
    release_compute_lock,
)


class TestKeyGeneration:
    """Tests for cache key generation functions."""

    def test_data_provider_cache_key_with_org(self):
        """Key includes org scope when org_id provided."""
        key = data_provider_cache_key("org-123", "get_users", "abc123")
        assert key == "bifrost:org:org-123:dp:get_users:abc123"

    def test_data_provider_cache_key_global(self):
        """Key uses global scope when org_id is None."""
        key = data_provider_cache_key(None, "get_users", "abc123")
        assert key == "bifrost:global:dp:get_users:abc123"

    def test_data_provider_cache_key_global_string(self):
        """Key uses global scope when org_id is 'GLOBAL'."""
        key = data_provider_cache_key("GLOBAL", "get_users", "abc123")
        assert key == "bifrost:global:dp:get_users:abc123"

    def test_data_provider_lock_key_with_org(self):
        """Lock key includes org scope."""
        key = data_provider_lock_key("org-123", "get_users", "abc123")
        assert key == "bifrost:org:org-123:dp:get_users:abc123:lock"

    def test_data_provider_lock_key_global(self):
        """Lock key uses global scope when org_id is None."""
        key = data_provider_lock_key(None, "get_users", "abc123")
        assert key == "bifrost:global:dp:get_users:abc123:lock"


class TestComputeParamHash:
    """Tests for parameter hashing."""

    def test_empty_params_returns_empty(self):
        """Empty or None params return 'empty' hash."""
        assert compute_param_hash(None) == "empty"
        assert compute_param_hash({}) == "empty"

    def test_deterministic_hash(self):
        """Same params produce same hash."""
        params = {"user_id": "123", "limit": 10}
        hash1 = compute_param_hash(params)
        hash2 = compute_param_hash(params)
        assert hash1 == hash2

    def test_order_independent(self):
        """Parameter order doesn't affect hash."""
        params1 = {"a": 1, "b": 2}
        params2 = {"b": 2, "a": 1}
        assert compute_param_hash(params1) == compute_param_hash(params2)

    def test_different_params_different_hash(self):
        """Different params produce different hashes."""
        hash1 = compute_param_hash({"a": 1})
        hash2 = compute_param_hash({"a": 2})
        assert hash1 != hash2

    def test_hash_length(self):
        """Hash is 16 characters."""
        hash_val = compute_param_hash({"key": "value"})
        assert len(hash_val) == 16


class TestGetCachedResult:
    """Tests for cache retrieval."""

    @pytest.mark.asyncio
    async def test_cache_miss_returns_none(self):
        """Returns None when key not in cache."""
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)

        with patch("src.core.cache.data_provider_cache.get_redis") as mock_get_redis:
            mock_get_redis.return_value.__aenter__ = AsyncMock(return_value=mock_redis)
            mock_get_redis.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await get_cached_result("org-123", "get_users", {"id": 1})
            assert result is None

    @pytest.mark.asyncio
    async def test_cache_hit_returns_entry(self):
        """Returns cached entry when found and not expired."""
        expires_at = (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()
        cached_data = {
            "data": {"users": [1, 2, 3]},
            "expires_at": expires_at
        }

        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=json.dumps(cached_data))

        with patch("src.core.cache.data_provider_cache.get_redis") as mock_get_redis:
            mock_get_redis.return_value.__aenter__ = AsyncMock(return_value=mock_redis)
            mock_get_redis.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await get_cached_result("org-123", "get_users", {"id": 1})
            assert result is not None
            assert result["data"] == {"users": [1, 2, 3]}

    @pytest.mark.asyncio
    async def test_expired_cache_returns_none(self):
        """Returns None and deletes expired entries."""
        expires_at = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
        cached_data = {
            "data": {"users": [1, 2, 3]},
            "expires_at": expires_at
        }

        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=json.dumps(cached_data))
        mock_redis.delete = AsyncMock()

        with patch("src.core.cache.data_provider_cache.get_redis") as mock_get_redis:
            mock_get_redis.return_value.__aenter__ = AsyncMock(return_value=mock_redis)
            mock_get_redis.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await get_cached_result("org-123", "get_users", {"id": 1})
            assert result is None
            mock_redis.delete.assert_called_once()


class TestCacheResult:
    """Tests for caching results."""

    @pytest.mark.asyncio
    async def test_cache_result_stores_with_ttl(self):
        """Stores result with correct TTL."""
        mock_redis = AsyncMock()
        mock_redis.setex = AsyncMock()

        with patch("src.core.cache.data_provider_cache.get_redis") as mock_get_redis:
            mock_get_redis.return_value.__aenter__ = AsyncMock(return_value=mock_redis)
            mock_get_redis.return_value.__aexit__ = AsyncMock(return_value=None)

            result = {"users": [1, 2, 3]}
            expires_at = await cache_result("org-123", "get_users", {"id": 1}, result, 300)

            mock_redis.setex.assert_called_once()
            call_args = mock_redis.setex.call_args
            assert call_args[0][1] == 300  # TTL

            # Verify expiration is in the future
            assert expires_at > datetime.now(timezone.utc)

    @pytest.mark.asyncio
    async def test_cache_result_uses_default_ttl(self):
        """Uses default TTL when not specified."""
        mock_redis = AsyncMock()
        mock_redis.setex = AsyncMock()

        with patch("src.core.cache.data_provider_cache.get_redis") as mock_get_redis:
            mock_get_redis.return_value.__aenter__ = AsyncMock(return_value=mock_redis)
            mock_get_redis.return_value.__aexit__ = AsyncMock(return_value=None)

            await cache_result("org-123", "get_users", None, {"data": 1})

            call_args = mock_redis.setex.call_args
            assert call_args[0][1] == TTL_DATA_PROVIDER


class TestInvalidateDataProvider:
    """Tests for cache invalidation."""

    @pytest.mark.asyncio
    async def test_invalidate_specific_params(self):
        """Invalidates specific parameter combination."""
        mock_redis = AsyncMock()
        mock_redis.delete = AsyncMock(return_value=1)

        with patch("src.core.cache.data_provider_cache.get_redis") as mock_get_redis:
            mock_get_redis.return_value.__aenter__ = AsyncMock(return_value=mock_redis)
            mock_get_redis.return_value.__aexit__ = AsyncMock(return_value=None)

            await invalidate_data_provider("org-123", "get_users", {"id": 1})
            mock_redis.delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_invalidate_all_for_provider(self):
        """Invalidates all cached results for a data provider."""
        mock_redis = AsyncMock()
        mock_redis.scan = AsyncMock(return_value=(0, [
            "bifrost:org:org-123:dp:get_users:abc123",
            "bifrost:org:org-123:dp:get_users:def456",
        ]))
        mock_redis.delete = AsyncMock(return_value=2)

        with patch("src.core.cache.data_provider_cache.get_redis") as mock_get_redis:
            mock_get_redis.return_value.__aenter__ = AsyncMock(return_value=mock_redis)
            mock_get_redis.return_value.__aexit__ = AsyncMock(return_value=None)

            await invalidate_data_provider("org-123", "get_users", None)
            mock_redis.scan.assert_called()
            mock_redis.delete.assert_called()


class TestStampedeProtection:
    """Tests for cache stampede protection."""

    @pytest.mark.asyncio
    async def test_acquire_lock_success(self):
        """Successfully acquires lock when not held."""
        mock_redis = AsyncMock()
        mock_redis.set = AsyncMock(return_value=True)

        with patch("src.core.cache.data_provider_cache.get_redis") as mock_get_redis:
            mock_get_redis.return_value.__aenter__ = AsyncMock(return_value=mock_redis)
            mock_get_redis.return_value.__aexit__ = AsyncMock(return_value=None)

            acquired = await acquire_compute_lock("org-123", "get_users", {"id": 1})
            assert acquired is True
            mock_redis.set.assert_called_once()
            # Verify nx=True (only set if not exists)
            call_kwargs = mock_redis.set.call_args[1]
            assert call_kwargs["nx"] is True

    @pytest.mark.asyncio
    async def test_acquire_lock_already_held(self):
        """Returns False when lock already held."""
        mock_redis = AsyncMock()
        mock_redis.set = AsyncMock(return_value=False)

        with patch("src.core.cache.data_provider_cache.get_redis") as mock_get_redis:
            mock_get_redis.return_value.__aenter__ = AsyncMock(return_value=mock_redis)
            mock_get_redis.return_value.__aexit__ = AsyncMock(return_value=None)

            acquired = await acquire_compute_lock("org-123", "get_users", {"id": 1})
            assert acquired is False

    @pytest.mark.asyncio
    async def test_release_lock(self):
        """Releases lock by deleting key."""
        mock_redis = AsyncMock()
        mock_redis.delete = AsyncMock()

        with patch("src.core.cache.data_provider_cache.get_redis") as mock_get_redis:
            mock_get_redis.return_value.__aenter__ = AsyncMock(return_value=mock_redis)
            mock_get_redis.return_value.__aexit__ = AsyncMock(return_value=None)

            await release_compute_lock("org-123", "get_users", {"id": 1})
            mock_redis.delete.assert_called_once()
