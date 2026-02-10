"""Tests for file_index reconciler."""
import pytest
from unittest.mock import AsyncMock, MagicMock


@pytest.fixture
def mock_db():
    return AsyncMock()


@pytest.fixture
def mock_repo_storage():
    storage = AsyncMock()
    return storage


@pytest.mark.asyncio
async def test_reconciler_adds_missing_files(mock_db, mock_repo_storage):
    """Files in S3 but not in file_index should be added."""
    from src.services.file_index_reconciler import reconcile_file_index

    # S3 has two files
    mock_repo_storage.list.return_value = ["workflows/a.py", "workflows/b.py"]
    mock_repo_storage.read.return_value = b"print('hello')"

    # DB has only one
    db_result = MagicMock()
    db_result.all.return_value = [("workflows/a.py",)]
    mock_db.execute = AsyncMock(return_value=db_result)

    stats = await reconcile_file_index(mock_db, mock_repo_storage)

    assert stats["added"] >= 1


@pytest.mark.asyncio
async def test_reconciler_removes_orphaned_entries(mock_db, mock_repo_storage):
    """file_index entries with no corresponding S3 file should be removed."""
    from src.services.file_index_reconciler import reconcile_file_index

    # S3 has one file
    mock_repo_storage.list.return_value = ["workflows/a.py"]
    mock_repo_storage.read.return_value = b"print('hello')"

    # DB has two (one is orphaned)
    db_result = MagicMock()
    db_result.all.return_value = [("workflows/a.py",), ("workflows/deleted.py",)]
    mock_db.execute = AsyncMock(return_value=db_result)

    stats = await reconcile_file_index(mock_db, mock_repo_storage)

    assert stats["removed"] >= 1


@pytest.mark.asyncio
async def test_reconciler_handles_empty_s3(mock_db, mock_repo_storage):
    """Empty S3 should remove all DB entries."""
    from src.services.file_index_reconciler import reconcile_file_index

    mock_repo_storage.list.return_value = []

    db_result = MagicMock()
    db_result.all.return_value = [("workflows/old.py",)]
    mock_db.execute = AsyncMock(return_value=db_result)

    stats = await reconcile_file_index(mock_db, mock_repo_storage)

    assert stats["removed"] >= 1
    assert stats["added"] == 0
