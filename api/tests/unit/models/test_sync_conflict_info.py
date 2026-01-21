"""Test SyncConflictInfo model with metadata fields."""
import pytest
from src.models.contracts.github import SyncConflictInfo


def test_sync_conflict_info_with_metadata():
    """SyncConflictInfo should accept metadata fields."""
    conflict = SyncConflictInfo(
        path="forms/contact.form.json",
        local_content='{"name": "Contact Form"}',
        remote_content='{"name": "Contact Form v2"}',
        local_sha="abc123",
        remote_sha="def456",
        display_name="Contact Form",
        entity_type="form",
        parent_slug=None,
    )

    assert conflict.path == "forms/contact.form.json"
    assert conflict.display_name == "Contact Form"
    assert conflict.entity_type == "form"
    assert conflict.parent_slug is None


def test_sync_conflict_info_metadata_optional():
    """Metadata fields should be optional for backwards compatibility."""
    conflict = SyncConflictInfo(
        path="workflows/export.py",
        local_content="def export(): pass",
        remote_content="def export(): return True",
        local_sha="abc123",
        remote_sha="def456",
    )

    assert conflict.display_name is None
    assert conflict.entity_type is None
    assert conflict.parent_slug is None


def test_sync_conflict_info_app_file_with_parent():
    """App files should have parent_slug."""
    conflict = SyncConflictInfo(
        path="apps/dashboard/src/index.tsx",
        local_content="export default App;",
        remote_content="export default AppV2;",
        local_sha="abc123",
        remote_sha="def456",
        display_name="src/index.tsx",
        entity_type="app_file",
        parent_slug="dashboard",
    )

    assert conflict.entity_type == "app_file"
    assert conflict.parent_slug == "dashboard"
