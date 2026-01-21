"""Test sync content endpoint for diff preview."""
import pytest


def test_sync_content_request_model():
    """SyncContentRequest should validate source field."""
    from src.models.contracts.github import SyncContentRequest

    req = SyncContentRequest(path="forms/test.form.json", source="local")
    assert req.source == "local"

    req = SyncContentRequest(path="forms/test.form.json", source="remote")
    assert req.source == "remote"


def test_sync_content_request_invalid_source():
    """SyncContentRequest should reject invalid source values."""
    from typing import Any

    from pydantic import ValidationError
    from src.models.contracts.github import SyncContentRequest

    invalid_source: Any = "invalid"
    with pytest.raises(ValidationError):
        SyncContentRequest(path="forms/test.form.json", source=invalid_source)


def test_sync_content_response_model():
    """SyncContentResponse should allow null content."""
    from src.models.contracts.github import SyncContentResponse

    # File exists
    resp = SyncContentResponse(path="forms/test.form.json", content='{"name": "Test"}')
    assert resp.content == '{"name": "Test"}'

    # File doesn't exist (new file)
    resp = SyncContentResponse(path="forms/new.form.json", content=None)
    assert resp.content is None
