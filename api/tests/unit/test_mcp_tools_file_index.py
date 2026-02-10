"""Tests for MCP tools _read_from_cache_or_s3."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.asyncio
async def test_cache_or_s3_returns_content_from_redis():
    """When Redis cache has the content, it should be returned directly."""
    from src.services.mcp_server.tools.code_editor import _read_from_cache_or_s3

    with patch(
        "src.core.module_cache.get_module",
        new_callable=AsyncMock,
        return_value={"content": "def hello(): pass"},
    ):
        result = await _read_from_cache_or_s3("workflows/test.py")

    assert result == "def hello(): pass"


@pytest.mark.asyncio
async def test_cache_or_s3_returns_content_from_s3_fallback():
    """When Redis cache misses, S3 fallback should return decoded content."""
    from src.services.mcp_server.tools.code_editor import _read_from_cache_or_s3

    mock_repo = MagicMock()
    mock_repo.read = AsyncMock(return_value=b"def hello(): pass")

    with (
        patch(
            "src.core.module_cache.get_module",
            new_callable=AsyncMock,
            return_value=None,
        ),
        patch(
            "src.services.repo_storage.RepoStorage",
            return_value=mock_repo,
        ),
    ):
        result = await _read_from_cache_or_s3("workflows/test.py")

    assert result == "def hello(): pass"


@pytest.mark.asyncio
async def test_cache_or_s3_returns_none_when_not_found():
    """When neither Redis nor S3 has the file, None should be returned."""
    from src.services.mcp_server.tools.code_editor import _read_from_cache_or_s3

    mock_repo = MagicMock()
    mock_repo.read = AsyncMock(side_effect=FileNotFoundError("not found"))

    with (
        patch(
            "src.core.module_cache.get_module",
            new_callable=AsyncMock,
            return_value=None,
        ),
        patch(
            "src.services.repo_storage.RepoStorage",
            return_value=mock_repo,
        ),
    ):
        result = await _read_from_cache_or_s3("workflows/nonexistent.py")

    assert result is None
