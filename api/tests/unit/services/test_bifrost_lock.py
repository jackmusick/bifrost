"""Test that .bifrost/ files cannot be written via file_ops."""

import pytest
from fastapi import HTTPException


@pytest.mark.asyncio
async def test_write_file_rejects_bifrost_paths():
    """write_file() should reject writes to .bifrost/ paths."""
    from src.services.file_storage.file_ops import FileOperationsService

    # Create minimal mock instance
    service = FileOperationsService.__new__(FileOperationsService)

    with pytest.raises(HTTPException) as exc_info:
        await service.write_file(".bifrost/workflows.yaml", b"content")

    assert exc_info.value.status_code == 403
    assert ".bifrost" in str(exc_info.value.detail).lower()


@pytest.mark.asyncio
async def test_write_file_rejects_nested_bifrost_paths():
    """write_file() should reject writes to nested .bifrost/ paths."""
    from src.services.file_storage.file_ops import FileOperationsService

    service = FileOperationsService.__new__(FileOperationsService)

    with pytest.raises(HTTPException) as exc_info:
        await service.write_file(".bifrost/forms.yaml", b"content")

    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_delete_file_rejects_bifrost_paths():
    """delete_file() should reject deletes of .bifrost/ paths."""
    from src.services.file_storage.file_ops import FileOperationsService

    service = FileOperationsService.__new__(FileOperationsService)

    with pytest.raises(HTTPException) as exc_info:
        await service.delete_file(".bifrost/workflows.yaml")

    assert exc_info.value.status_code == 403
