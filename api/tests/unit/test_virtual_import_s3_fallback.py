"""Tests for virtual import S3 fallback."""
import json
from unittest.mock import MagicMock, patch


def test_s3_fallback_on_redis_miss():
    """When Redis returns None, should try S3 and cache result."""
    from src.core.module_cache_sync import get_module_sync

    with patch("src.core.module_cache_sync._get_sync_redis") as mock_redis_factory, \
         patch("src.core.module_cache_sync._get_s3_module") as mock_s3:

        # Redis returns None (cache miss)
        mock_redis = MagicMock()
        mock_redis.get.return_value = None
        mock_redis_factory.return_value = mock_redis

        # S3 returns the module content
        mock_s3.return_value = b"def helper(): return 42"

        result = get_module_sync("shared/utils.py")

        # Should have tried S3
        mock_s3.assert_called_once_with("shared/utils.py")
        # Should have cached to Redis
        assert mock_redis.setex.called
        # Should return the module
        assert result is not None
        assert result["content"] == "def helper(): return 42"


def test_redis_hit_skips_s3():
    """When Redis has the module, should not touch S3."""
    from src.core.module_cache_sync import get_module_sync

    cached = json.dumps({"content": "cached content", "path": "shared/utils.py", "hash": "abc"})

    with patch("src.core.module_cache_sync._get_sync_redis") as mock_redis_factory, \
         patch("src.core.module_cache_sync._get_s3_module") as mock_s3:

        mock_redis = MagicMock()
        mock_redis.get.return_value = cached
        mock_redis_factory.return_value = mock_redis

        result = get_module_sync("shared/utils.py")

        mock_s3.assert_not_called()
        assert result is not None
        assert result["content"] == "cached content"


def test_s3_miss_returns_none():
    """When both Redis and S3 miss, should return None."""
    from src.core.module_cache_sync import get_module_sync

    with patch("src.core.module_cache_sync._get_sync_redis") as mock_redis_factory, \
         patch("src.core.module_cache_sync._get_s3_module") as mock_s3:

        mock_redis = MagicMock()
        mock_redis.get.return_value = None
        mock_redis_factory.return_value = mock_redis
        mock_s3.return_value = None

        result = get_module_sync("shared/nonexistent.py")

        assert result is None
