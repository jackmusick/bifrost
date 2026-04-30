"""Tests that pubsub helpers emit the right envelopes."""
from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.core import pubsub


@pytest.fixture(autouse=True)
def patch_manager(monkeypatch):
    mgr = AsyncMock()
    monkeypatch.setattr(pubsub, "manager", mgr)
    return mgr


async def test_publish_document_change_envelope(patch_manager):
    table_id = uuid4()
    doc = {"id": "row-1", "data": {"k": "v"}, "created_by": "user-uuid"}
    await pubsub.publish_document_change(table_id, "insert", doc)

    patch_manager.broadcast.assert_called_once()
    channel, message = patch_manager.broadcast.call_args.args
    assert channel == f"table:{table_id}"
    assert message["type"] == "document_change"
    assert message["action"] == "insert"
    assert message["id"] == "row-1"
    assert message["created_by"] == "user-uuid"
    assert message["data"] == {"k": "v"}


async def test_publish_table_access_changed_envelope(patch_manager):
    table_id = uuid4()
    await pubsub.publish_table_access_changed(table_id)
    channel, message = patch_manager.broadcast.call_args.args
    assert channel == f"table:{table_id}"
    assert message["type"] == "table_access_changed"
