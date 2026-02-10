"""Tests for file index service — dual-write to S3 + DB."""
import pytest
from unittest.mock import AsyncMock, MagicMock


@pytest.fixture
def mock_db():
    db = AsyncMock()
    db.commit = AsyncMock()
    return db


@pytest.fixture
def mock_repo_storage():
    storage = AsyncMock()
    storage.write = AsyncMock(return_value="abc123hash")
    storage.read = AsyncMock(return_value=b"file content")
    storage.delete = AsyncMock()
    storage.list = AsyncMock(return_value=["workflows/a.py", "modules/b.py"])
    return storage


@pytest.mark.asyncio
async def test_write_updates_s3_and_db(mock_db, mock_repo_storage):
    """Write should write to S3 and upsert file_index."""
    from src.services.file_index_service import FileIndexService

    service = FileIndexService(mock_db, mock_repo_storage)
    await service.write("workflows/test.py", b"print('hello')")

    # S3 write happened
    mock_repo_storage.write.assert_called_once_with("workflows/test.py", b"print('hello')")
    # DB upsert happened
    assert mock_db.execute.called


@pytest.mark.asyncio
async def test_write_skips_binary_files(mock_db, mock_repo_storage):
    """Binary files should be written to S3 but not indexed in DB."""
    from src.services.file_index_service import FileIndexService

    service = FileIndexService(mock_db, mock_repo_storage)
    await service.write("images/logo.png", b"\x89PNG binary data")

    # S3 write happened
    mock_repo_storage.write.assert_called_once()
    # DB should NOT be updated for binary files
    assert not mock_db.execute.called


@pytest.mark.asyncio
async def test_delete_removes_from_s3_and_db(mock_db, mock_repo_storage):
    """Delete should remove from both S3 and file_index."""
    from src.services.file_index_service import FileIndexService

    service = FileIndexService(mock_db, mock_repo_storage)
    await service.delete("workflows/test.py")

    mock_repo_storage.delete.assert_called_once_with("workflows/test.py")
    assert mock_db.execute.called


@pytest.mark.asyncio
async def test_search_queries_db(mock_db, mock_repo_storage):
    """Search should query file_index table."""
    from src.services.file_index_service import FileIndexService

    mock_result = MagicMock()
    mock_result.all.return_value = [
        MagicMock(path="workflows/a.py", content="def hello(): pass"),
    ]
    mock_db.execute = AsyncMock(return_value=mock_result)

    service = FileIndexService(mock_db, mock_repo_storage)
    await service.search("hello")

    assert mock_db.execute.called


def test_is_text_file():
    """Text file detection works correctly."""
    from src.services.file_index_service import _is_text_file
    assert _is_text_file("test.py") is True
    assert _is_text_file("test.yaml") is True
    assert _is_text_file("test.png") is False
    assert _is_text_file("test.jpg") is False
    assert _is_text_file("test.md") is True
