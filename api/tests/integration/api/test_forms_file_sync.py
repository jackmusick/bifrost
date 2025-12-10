"""
Test forms file system synchronization.

Verifies that forms are persisted to *.form.json files and that
the discovery watcher syncs file changes to the database.

NOTE: These tests require the full API stack running (http_client connects to api:8000).
Run with `./test.sh --e2e` to include these tests.
"""

import json
import os
import time
from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from src.models import Form as FormORM
from tests.helpers.mock_auth import create_platform_admin_headers


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_form_create_writes_to_file_system(http_client: AsyncClient, integration_db_session):
    """Test that creating a form via API writes to file system."""
    workspace = Path(os.environ["BIFROST_WORKSPACE_LOCATION"])

    # Create form via API
    form_data = {
        "name": "Test Form File Sync",
        "description": "Testing file system sync",
        "linked_workflow": "test_workflow",
        "form_schema": {
            "fields": [
                {"name": "test_field", "type": "text", "label": "Test Field", "required": True}
            ]
        },
        "access_level": "authenticated"
    }

    response = await http_client.post(
        "/api/forms",
        json=form_data,
        headers=create_platform_admin_headers()
    )
    assert response.status_code == 201
    form = response.json()
    form_id = form["id"]

    # Verify form exists in database
    result = await integration_db_session.execute(
        select(FormORM).where(FormORM.id == form_id)
    )
    db_form = result.scalar_one_or_none()
    assert db_form is not None
    assert db_form.name == "Test Form File Sync"
    assert db_form.file_path is not None

    # Verify form file was written to file system
    form_file = workspace / db_form.file_path
    assert form_file.exists(), f"Form file not found: {form_file}"

    # Verify file content
    file_content = json.loads(form_file.read_text())
    assert file_content["id"] == form_id
    assert file_content["name"] == "Test Form File Sync"
    assert file_content["linked_workflow"] == "test_workflow"
    assert file_content["is_active"] is True
    assert "form_schema" in file_content
    assert len(file_content["form_schema"]["fields"]) == 1

    # Cleanup
    form_file.unlink()


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_form_update_syncs_to_file_system(http_client: AsyncClient, integration_db_session):
    """Test that updating a form syncs changes to file system."""
    workspace = Path(os.environ["BIFROST_WORKSPACE_LOCATION"])

    # Create form
    form_data = {
        "name": "Original Name",
        "description": "Original description",
        "linked_workflow": "test_workflow",
        "form_schema": {
            "fields": [
                {"name": "field1", "type": "text", "label": "Field 1", "required": True}
            ]
        },
        "access_level": "authenticated"
    }

    response = await http_client.post(
        "/api/forms",
        json=form_data,
        headers=create_platform_admin_headers()
    )
    assert response.status_code == 201
    form = response.json()
    form_id = form["id"]

    # Get original file path
    result = await integration_db_session.execute(
        select(FormORM).where(FormORM.id == form_id)
    )
    db_form = result.scalar_one_or_none()
    original_file = workspace / db_form.file_path
    assert original_file.exists()

    # Update form
    update_data = {
        "name": "Updated Name",
        "description": "Updated description"
    }

    response = await http_client.patch(
        f"/api/forms/{form_id}",
        json=update_data,
        headers=create_platform_admin_headers()
    )
    assert response.status_code == 200

    # Verify database was updated
    await integration_db_session.refresh(db_form)
    assert db_form.name == "Updated Name"
    assert db_form.description == "Updated description"

    # Verify file was updated (may have new name due to rename)
    updated_file = workspace / db_form.file_path
    assert updated_file.exists()

    # Verify file content
    file_content = json.loads(updated_file.read_text())
    assert file_content["id"] == form_id
    assert file_content["name"] == "Updated Name"
    assert file_content["description"] == "Updated description"

    # Cleanup old file if it's different
    if original_file != updated_file and original_file.exists():
        original_file.unlink()
    updated_file.unlink()


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_form_delete_deactivates_in_file_system(http_client: AsyncClient, integration_db_session):
    """Test that deleting a form sets isActive=false in file system."""
    workspace = Path(os.environ["BIFROST_WORKSPACE_LOCATION"])

    # Create form
    form_data = {
        "name": "Form To Delete",
        "description": "Will be deleted",
        "linked_workflow": "test_workflow",
        "form_schema": {
            "fields": [
                {"name": "field1", "type": "text", "label": "Field 1", "required": True}
            ]
        },
        "access_level": "authenticated"
    }

    response = await http_client.post(
        "/api/forms",
        json=form_data,
        headers=create_platform_admin_headers()
    )
    assert response.status_code == 201
    form = response.json()
    form_id = form["id"]

    # Get file path
    result = await integration_db_session.execute(
        select(FormORM).where(FormORM.id == form_id)
    )
    db_form = result.scalar_one_or_none()
    form_file = workspace / db_form.file_path
    assert form_file.exists()

    # Verify form is active
    file_content = json.loads(form_file.read_text())
    assert file_content["is_active"] is True

    # Delete form
    response = await http_client.delete(
        f"/api/forms/{form_id}",
        headers=create_platform_admin_headers()
    )
    assert response.status_code == 204

    # Verify database shows inactive
    await integration_db_session.refresh(db_form)
    assert db_form.is_active is False

    # Verify file shows inactive
    file_content = json.loads(form_file.read_text())
    assert file_content["is_active"] is False

    # Cleanup
    form_file.unlink()


@pytest.mark.e2e
@pytest.mark.skip(reason="Requires discovery watcher container running - test in E2E mode")
@pytest.mark.asyncio
async def test_manual_form_file_synced_to_database(http_client: AsyncClient, integration_db_session):
    """
    Test that manually created *.form.json files are synced to database.

    NOTE: This test requires the discovery watcher container to be running.
    Run with `./test.sh --e2e` to include this test.
    """
    workspace = Path(os.environ["BIFROST_WORKSPACE_LOCATION"])

    # Create a manual form file
    form_id = "manual-test-form-12345"
    form_file = workspace / "manual-test-form.form.json"

    form_data = {
        "id": form_id,
        "name": "Manual Form",
        "description": "Created manually in file system",
        "linked_workflow": "test_workflow",
        "form_schema": {
            "fields": [
                {"name": "manual_field", "type": "text", "label": "Manual Field", "required": True}
            ]
        },
        "is_active": True,
        "is_global": True,
        "org_id": "GLOBAL",
        "access_level": "authenticated",
        "created_by": "manual",
        "created_at": "2024-01-01T00:00:00Z",
        "updated_at": "2024-01-01T00:00:00Z"
    }

    form_file.write_text(json.dumps(form_data, indent=2))

    # Wait for discovery watcher to pick it up (max 5 seconds)
    # The discovery watcher runs every 1 second
    max_wait = 5
    db_form = None
    for _ in range(max_wait * 10):  # Check every 100ms
        result = await integration_db_session.execute(
            select(FormORM).where(FormORM.name == "Manual Form")
        )
        db_form = result.scalar_one_or_none()
        if db_form:
            break
        await integration_db_session.rollback()  # Rollback to see new data
        time.sleep(0.1)

    # Verify form was synced to database
    assert db_form is not None, "Discovery watcher did not sync manual form file"
    assert db_form.name == "Manual Form"
    assert db_form.description == "Created manually in file system"
    assert db_form.linked_workflow == "test_workflow"
    assert db_form.is_active is True
    assert db_form.file_path is not None

    # Cleanup
    form_file.unlink()
