"""Tests for repo storage service."""
import pytest
from unittest.mock import AsyncMock, MagicMock


@pytest.fixture
def mock_s3_client():
    client = AsyncMock()
    client.put_object = AsyncMock()
    client.get_object = AsyncMock()
    client.delete_object = AsyncMock()
    client.list_objects_v2 = AsyncMock()
    return client


@pytest.mark.asyncio
async def test_write_prepends_repo_prefix(mock_s3_client):
    """Writing to 'workflows/test.py' should write to '_repo/workflows/test.py' in S3."""
    from src.services.repo_storage import RepoStorage

    storage = RepoStorage.__new__(RepoStorage)
    storage._bucket = "test-bucket"

    mock_s3_client.put_object = AsyncMock()

    await storage._write_to_s3(mock_s3_client, "workflows/test.py", b"print('hello')")

    mock_s3_client.put_object.assert_called_once()
    call_kwargs = mock_s3_client.put_object.call_args[1]
    assert call_kwargs["Key"] == "_repo/workflows/test.py"


@pytest.mark.asyncio
async def test_read_prepends_repo_prefix(mock_s3_client):
    """Reading 'workflows/test.py' should read from '_repo/workflows/test.py' in S3."""
    from src.services.repo_storage import RepoStorage

    storage = RepoStorage.__new__(RepoStorage)
    storage._bucket = "test-bucket"

    body_mock = AsyncMock()
    body_mock.read = AsyncMock(return_value=b"print('hello')")
    mock_s3_client.get_object = AsyncMock(return_value={"Body": body_mock})

    content = await storage._read_from_s3(mock_s3_client, "workflows/test.py")

    mock_s3_client.get_object.assert_called_once()
    call_kwargs = mock_s3_client.get_object.call_args[1]
    assert call_kwargs["Key"] == "_repo/workflows/test.py"
    assert content == b"print('hello')"


@pytest.mark.asyncio
async def test_list_prepends_and_strips_prefix(mock_s3_client):
    """Listing should use _repo/ prefix and strip it from results."""
    from src.services.repo_storage import RepoStorage

    storage = RepoStorage.__new__(RepoStorage)
    storage._bucket = "test-bucket"

    mock_s3_client.list_objects_v2 = AsyncMock(return_value={
        "Contents": [
            {"Key": "_repo/workflows/a.py"},
            {"Key": "_repo/workflows/b.py"},
        ],
        "IsTruncated": False,
    })

    paths = await storage._list_from_s3(mock_s3_client, prefix="workflows/")

    assert paths == ["workflows/a.py", "workflows/b.py"]
    # Verify the prefix was sent to S3 with _repo/ prepended
    call_kwargs = mock_s3_client.list_objects_v2.call_args[1]
    assert call_kwargs["Prefix"] == "_repo/workflows/"


def test_compute_hash():
    """Compute SHA-256 hash of content."""
    from src.services.repo_storage import RepoStorage
    h = RepoStorage.compute_hash(b"hello world")
    assert len(h) == 64  # SHA-256 hex
