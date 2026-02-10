"""Unit tests for requirements_cache module."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.requirements_cache import (
    REQUIREMENTS_KEY,
    CachedRequirements,
    get_requirements,
    save_requirements_to_db,
    set_requirements,
    warm_requirements_cache,
)


class TestGetRequirements:
    """Tests for get_requirements function."""

    @pytest.fixture
    def mock_redis_client(self):
        """Create a mock async Redis client."""
        mock_client = AsyncMock()
        mock_client.get = AsyncMock()
        return mock_client

    async def test_returns_cached_data(self, mock_redis_client):
        """Test get_requirements returns cached data."""
        cached = {"content": "flask==2.3.0\n", "hash": "abc123"}
        mock_redis_client.get.return_value = json.dumps(cached)

        with patch("src.core.requirements_cache.get_redis_client", return_value=mock_redis_client):
            result = await get_requirements()

            assert result == cached
            mock_redis_client.get.assert_called_once_with(REQUIREMENTS_KEY)

    async def test_returns_none_when_not_cached(self, mock_redis_client):
        """Test get_requirements returns None when not in cache."""
        mock_redis_client.get.return_value = None

        with patch("src.core.requirements_cache.get_redis_client", return_value=mock_redis_client):
            result = await get_requirements()

            assert result is None
            mock_redis_client.get.assert_called_once_with(REQUIREMENTS_KEY)


class TestSetRequirements:
    """Tests for set_requirements function."""

    @pytest.fixture
    def mock_redis_client(self):
        """Create a mock async Redis client."""
        mock_client = AsyncMock()
        mock_client.setex = AsyncMock()
        return mock_client

    async def test_caches_with_ttl(self, mock_redis_client):
        """Test set_requirements stores with correct TTL."""
        content = "flask==2.3.0\n"
        content_hash = "abc123"

        with patch("src.core.requirements_cache.get_redis_client", return_value=mock_redis_client):
            await set_requirements(content, content_hash)

            mock_redis_client.setex.assert_called_once()
            call_args = mock_redis_client.setex.call_args
            assert call_args[0][0] == REQUIREMENTS_KEY
            assert call_args[0][1] == 86400  # 24 hours

            cached = json.loads(call_args[0][2])
            assert cached["content"] == content
            assert cached["hash"] == content_hash


class TestWarmRequirementsCache:
    """Tests for warm_requirements_cache function."""

    @pytest.fixture
    def mock_redis_client(self):
        """Create a mock async Redis client."""
        mock_client = AsyncMock()
        mock_client.setex = AsyncMock()
        return mock_client

    @pytest.fixture
    def mock_file_index_record(self):
        """Create a mock FileIndex record."""
        mock_file = MagicMock()
        mock_file.content = "flask==2.3.0\nrequests==2.31.0\n"
        mock_file.content_hash = "def456"
        return mock_file

    async def test_caches_from_database(self, mock_redis_client, mock_file_index_record):
        """Test warm_requirements_cache loads from database and caches."""
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_file_index_record
        mock_session.execute.return_value = mock_result

        with patch("src.core.requirements_cache.get_redis_client", return_value=mock_redis_client):
            result = await warm_requirements_cache(session=mock_session)

            assert result is True
            mock_session.execute.assert_called_once()
            mock_redis_client.setex.assert_called_once()

            # Verify cached content
            call_args = mock_redis_client.setex.call_args
            cached = json.loads(call_args[0][2])
            assert cached["content"] == mock_file_index_record.content
            assert cached["hash"] == mock_file_index_record.content_hash

    async def test_returns_false_when_not_found(self, mock_redis_client):
        """Test warm_requirements_cache returns False when requirements.txt not in file_index."""
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        with patch("src.core.requirements_cache.get_redis_client", return_value=mock_redis_client):
            result = await warm_requirements_cache(session=mock_session)

            assert result is False
            mock_redis_client.setex.assert_not_called()

    async def test_returns_false_when_content_is_none(self, mock_redis_client):
        """Test warm_requirements_cache returns False when file exists but content is None."""
        mock_file = MagicMock()
        mock_file.content = None
        mock_file.content_hash = None

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_file
        mock_session.execute.return_value = mock_result

        with patch("src.core.requirements_cache.get_redis_client", return_value=mock_redis_client):
            result = await warm_requirements_cache(session=mock_session)

            assert result is False
            mock_redis_client.setex.assert_not_called()

    async def test_creates_session_when_not_provided(self, mock_redis_client, mock_file_index_record):
        """Test warm_requirements_cache creates its own session when none provided."""
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_file_index_record
        mock_session.execute.return_value = mock_result

        mock_context_manager = AsyncMock()
        mock_context_manager.__aenter__.return_value = mock_session
        mock_context_manager.__aexit__.return_value = None

        with (
            patch("src.core.requirements_cache.get_redis_client", return_value=mock_redis_client),
            patch("src.core.database.get_db_context", return_value=mock_context_manager),
        ):
            result = await warm_requirements_cache()

            assert result is True
            mock_session.execute.assert_called_once()


class TestSaveRequirementsToDb:
    """Tests for save_requirements_to_db function."""

    @pytest.fixture
    def mock_redis_client(self):
        """Create a mock async Redis client."""
        mock_client = AsyncMock()
        mock_client.setex = AsyncMock()
        return mock_client

    async def test_upserts_record(self, mock_redis_client):
        """Test save_requirements_to_db upserts FileIndex record."""
        content = "flask==2.3.0\nrequests==2.31.0\n"

        mock_session = AsyncMock()
        mock_session.execute.return_value = MagicMock()

        with patch("src.core.requirements_cache.get_redis_client", return_value=mock_redis_client):
            await save_requirements_to_db(content, session=mock_session)

            # Verify execute was called (upsert via insert...on_conflict_do_update)
            mock_session.execute.assert_called_once()
            mock_session.commit.assert_called_once()

            # Verify cache was updated
            mock_redis_client.setex.assert_called_once()

    async def test_computes_correct_hash(self, mock_redis_client):
        """Test save_requirements_to_db computes SHA-256 hash correctly."""
        import hashlib

        content = "flask==2.3.0\nrequests==2.31.0\n"
        expected_hash = hashlib.sha256(content.encode()).hexdigest()

        mock_session = AsyncMock()
        mock_session.execute.return_value = MagicMock()

        with patch("src.core.requirements_cache.get_redis_client", return_value=mock_redis_client):
            await save_requirements_to_db(content, session=mock_session)

            # Verify cache received correct hash
            call_args = mock_redis_client.setex.call_args
            cached = json.loads(call_args[0][2])
            assert cached["hash"] == expected_hash

    async def test_creates_session_when_not_provided(self, mock_redis_client):
        """Test save_requirements_to_db creates its own session when none provided."""
        content = "flask==2.3.0\n"

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        mock_context_manager = AsyncMock()
        mock_context_manager.__aenter__.return_value = mock_session
        mock_context_manager.__aexit__.return_value = None

        with (
            patch("src.core.requirements_cache.get_redis_client", return_value=mock_redis_client),
            patch("src.core.database.get_db_context", return_value=mock_context_manager),
        ):
            await save_requirements_to_db(content)

            mock_session.execute.assert_called_once()
            mock_session.commit.assert_called_once()


class TestCachedRequirementsTypedDict:
    """Tests for the CachedRequirements TypedDict."""

    def test_cached_requirements_structure(self):
        """Verify CachedRequirements has expected fields."""
        requirements: CachedRequirements = {
            "content": "flask==2.3.0\nrequests==2.31.0\n",
            "hash": "abc123def456",
        }

        assert requirements["content"] == "flask==2.3.0\nrequests==2.31.0\n"
        assert requirements["hash"] == "abc123def456"


class TestKeyPatterns:
    """Tests for Redis key patterns."""

    def test_requirements_key(self):
        """Verify requirements key is correct."""
        assert REQUIREMENTS_KEY == "bifrost:requirements:content"
