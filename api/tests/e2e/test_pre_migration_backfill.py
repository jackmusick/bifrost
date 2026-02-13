"""
Integration tests for pre-migration data backfill.

Tests that the backfill script correctly reads from old tables
(workspace_files, workflows.code) and writes to file_index + S3.
"""

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.orm.agents import Agent
from src.models.orm.file_index import FileIndex
from src.models.orm.forms import Form, FormField


def _make_mock_repo():
    """Create a properly configured mock RepoStorage."""
    mock_repo = AsyncMock()
    mock_repo.write = AsyncMock(return_value="fakehash123")
    mock_repo.read = AsyncMock(return_value=b"")
    mock_repo.delete = AsyncMock()
    mock_repo.list = AsyncMock(return_value=[])
    mock_repo.exists = AsyncMock(return_value=False)
    return mock_repo


def _patch_repo_storage(mock_repo):
    """Patch RepoStorage in all modules that import it."""
    return [
        patch("src.services.repo_storage.RepoStorage", return_value=mock_repo),
        patch("src.services.repo_sync_writer.RepoStorage", return_value=mock_repo),
        patch("src.services.file_index_service.RepoStorage", return_value=mock_repo),
    ]


@pytest.mark.asyncio
async def test_backfill_noop_when_old_tables_gone(db_session: AsyncSession):
    """Backfill should be a safe no-op when old tables don't exist."""
    from scripts.pre_migration_backfill import backfill_workspace_data

    mock_repo = _make_mock_repo()
    patches = _patch_repo_storage(mock_repo)
    for p in patches:
        p.start()
    try:
        stats = await backfill_workspace_data(db_session)
    finally:
        for p in patches:
            p.stop()

    # No old tables => nothing to migrate (workspace_files and workflow code = 0)
    assert stats["workspace_files"] == 0
    assert stats["workflow_code"] == 0


@pytest.mark.asyncio
async def test_backfill_migrates_workspace_files(db_session: AsyncSession):
    """Backfill should migrate workspace_files content to file_index."""
    from scripts.pre_migration_backfill import backfill_workspace_data

    # Create the workspace_files table (simulating pre-migration state)
    await db_session.execute(text("""
        CREATE TABLE IF NOT EXISTS workspace_files (
            id UUID PRIMARY KEY,
            path VARCHAR(1000) NOT NULL UNIQUE,
            entity_type VARCHAR(50),
            entity_id UUID,
            content TEXT,
            content_hash VARCHAR(64),
            is_deleted BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW()
        )
    """))

    # Insert test data
    wf_id = uuid4()
    await db_session.execute(
        text("""
            INSERT INTO workspace_files (id, path, content, is_deleted)
            VALUES (:id, :path, :content, false)
        """),
        {"id": wf_id, "path": "workflows/my_workflow.py", "content": "def hello():\n    return 'world'"},
    )
    await db_session.flush()

    mock_repo = _make_mock_repo()
    patches = _patch_repo_storage(mock_repo)
    for p in patches:
        p.start()
    try:
        stats = await backfill_workspace_data(db_session)
    finally:
        for p in patches:
            p.stop()

    assert stats["workspace_files"] == 1

    # Verify file_index was populated
    result = await db_session.execute(
        select(FileIndex.content).where(FileIndex.path == "workflows/my_workflow.py")
    )
    content = result.scalar_one_or_none()
    assert content == "def hello():\n    return 'world'"

    # Cleanup
    await db_session.execute(text("DROP TABLE IF EXISTS workspace_files"))


@pytest.mark.skip(reason="ALTER TABLE workflows grabs ACCESS EXCLUSIVE lock, hangs when API has open connections during E2E")
@pytest.mark.asyncio
async def test_backfill_migrates_workflow_code(db_session: AsyncSession):
    """Backfill should migrate workflows.code to file_index."""
    from scripts.pre_migration_backfill import backfill_workspace_data

    # Add the 'code' column to workflows (simulating pre-migration state)
    has_code = await db_session.execute(
        text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name = 'workflows' AND column_name = 'code'"
        )
    )
    if has_code.scalar_one_or_none() is None:
        await db_session.execute(text("ALTER TABLE workflows ADD COLUMN code TEXT"))
        await db_session.flush()

    # Create a workflow with code
    wf_id = uuid4()
    await db_session.execute(
        text("""
            INSERT INTO workflows (id, name, function_name, path, code, is_active, type)
            VALUES (:id, :name, :fn, :path, :code, true, 'workflow')
        """),
        {
            "id": wf_id,
            "name": "test_wf_code",
            "fn": "test_wf_code",
            "path": "workflows/test_wf_code.py",
            "code": "def test_wf_code():\n    pass",
        },
    )
    await db_session.flush()

    mock_repo = _make_mock_repo()
    patches = _patch_repo_storage(mock_repo)
    for p in patches:
        p.start()
    try:
        stats = await backfill_workspace_data(db_session)
    finally:
        for p in patches:
            p.stop()

    assert stats["workflow_code"] == 1

    # Verify file_index was populated
    result = await db_session.execute(
        select(FileIndex.content).where(FileIndex.path == "workflows/test_wf_code.py")
    )
    content = result.scalar_one_or_none()
    assert content == "def test_wf_code():\n    pass"

    # Cleanup: remove the code column we added
    await db_session.execute(text("ALTER TABLE workflows DROP COLUMN IF EXISTS code"))
    await db_session.execute(text("DELETE FROM workflows WHERE id = :id"), {"id": wf_id})
    await db_session.execute(text("DELETE FROM file_index WHERE path = 'workflows/test_wf_code.py'"))


@pytest.mark.skip(reason="ALTER TABLE workflows grabs ACCESS EXCLUSIVE lock, hangs when API has open connections during E2E")
@pytest.mark.asyncio
async def test_backfill_workspace_files_takes_precedence(db_session: AsyncSession):
    """workspace_files content should take precedence over workflows.code."""
    from scripts.pre_migration_backfill import backfill_workspace_data

    path = "workflows/precedence_test.py"
    ws_content = "# from workspace_files"
    wf_content = "# from workflows.code"

    # Create workspace_files table and add entry
    await db_session.execute(text("""
        CREATE TABLE IF NOT EXISTS workspace_files (
            id UUID PRIMARY KEY,
            path VARCHAR(1000) NOT NULL UNIQUE,
            entity_type VARCHAR(50),
            entity_id UUID,
            content TEXT,
            content_hash VARCHAR(64),
            is_deleted BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW()
        )
    """))
    await db_session.execute(
        text("INSERT INTO workspace_files (id, path, content, is_deleted) VALUES (:id, :path, :content, false)"),
        {"id": uuid4(), "path": path, "content": ws_content},
    )

    # Add code column and workflow
    has_code = await db_session.execute(
        text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name = 'workflows' AND column_name = 'code'"
        )
    )
    if has_code.scalar_one_or_none() is None:
        await db_session.execute(text("ALTER TABLE workflows ADD COLUMN code TEXT"))

    wf_id = uuid4()
    await db_session.execute(
        text("""
            INSERT INTO workflows (id, name, function_name, path, code, is_active, type)
            VALUES (:id, :name, :fn, :path, :code, true, 'workflow')
        """),
        {"id": wf_id, "name": "prec_test", "fn": "prec_test", "path": path, "code": wf_content},
    )
    await db_session.flush()

    mock_repo = _make_mock_repo()
    patches = _patch_repo_storage(mock_repo)
    for p in patches:
        p.start()
    try:
        stats = await backfill_workspace_data(db_session)
    finally:
        for p in patches:
            p.stop()

    # workspace_files was migrated, workflow code was skipped (path already exists)
    assert stats["workspace_files"] == 1
    assert stats["workflow_code"] == 0

    # file_index should have workspace_files content
    result = await db_session.execute(
        select(FileIndex.content).where(FileIndex.path == path)
    )
    content = result.scalar_one_or_none()
    assert content == ws_content

    # Cleanup
    await db_session.execute(text("DROP TABLE IF EXISTS workspace_files"))
    await db_session.execute(text("ALTER TABLE workflows DROP COLUMN IF EXISTS code"))
    await db_session.execute(text("DELETE FROM workflows WHERE id = :id"), {"id": wf_id})
    await db_session.execute(text("DELETE FROM file_index WHERE path = :path"), {"path": path})


@pytest.mark.asyncio
async def test_backfill_generates_form_yaml(db_session: AsyncSession):
    """Backfill should generate YAML for active forms without existing files."""
    from scripts.pre_migration_backfill import backfill_workspace_data

    # Create a form with a field
    form_id = uuid4()
    form = Form(
        id=form_id,
        name="Test Backfill Form",
        description="A test form",
        created_by="test",
        is_active=True,
    )
    db_session.add(form)
    await db_session.flush()

    field = FormField(
        form_id=form_id,
        name="test_field",
        label="Test Field",
        type="text",
        required=True,
        position=0,
    )
    db_session.add(field)
    await db_session.flush()

    mock_repo = _make_mock_repo()
    patches = _patch_repo_storage(mock_repo)
    for p in patches:
        p.start()
    try:
        stats = await backfill_workspace_data(db_session)
    finally:
        for p in patches:
            p.stop()

    assert stats["forms"] >= 1

    # Verify YAML was written to file_index
    form_path = f"forms/{form_id}.form.yaml"
    result = await db_session.execute(
        select(FileIndex.content).where(FileIndex.path == form_path)
    )
    content = result.scalar_one_or_none()
    assert content is not None
    assert "Test Backfill Form" in content
    assert "test_field" in content


@pytest.mark.asyncio
async def test_backfill_generates_agent_yaml(db_session: AsyncSession):
    """Backfill should generate YAML for active non-system agents."""
    from scripts.pre_migration_backfill import backfill_workspace_data

    agent_id = uuid4()
    agent = Agent(
        id=agent_id,
        name="Test Backfill Agent",
        system_prompt="You are a test agent.",
        is_active=True,
        is_system=False,
        created_by="test",
    )
    db_session.add(agent)
    await db_session.flush()

    mock_repo = _make_mock_repo()
    patches = _patch_repo_storage(mock_repo)
    for p in patches:
        p.start()
    try:
        stats = await backfill_workspace_data(db_session)
    finally:
        for p in patches:
            p.stop()

    assert stats["agents"] >= 1

    # Verify YAML was written to file_index
    agent_path = f"agents/{agent_id}.agent.yaml"
    result = await db_session.execute(
        select(FileIndex.content).where(FileIndex.path == agent_path)
    )
    content = result.scalar_one_or_none()
    assert content is not None
    assert "Test Backfill Agent" in content
    assert "You are a test agent." in content


@pytest.mark.asyncio
async def test_backfill_generates_manifest(db_session: AsyncSession):
    """Backfill should generate .bifrost/ manifest files."""
    from scripts.pre_migration_backfill import backfill_workspace_data

    mock_repo = _make_mock_repo()
    patches = _patch_repo_storage(mock_repo)
    for p in patches:
        p.start()
    try:
        stats = await backfill_workspace_data(db_session)
    finally:
        for p in patches:
            p.stop()

    assert stats["manifest"] == 1


@pytest.mark.asyncio
async def test_backfill_skips_existing_file_index_entries(db_session: AsyncSession):
    """Backfill should not overwrite content already in file_index."""
    from scripts.pre_migration_backfill import backfill_workspace_data

    path = "workflows/already_indexed.py"
    existing_content = "# existing content"

    # Pre-populate file_index
    await db_session.execute(
        text("INSERT INTO file_index (path, content, content_hash) VALUES (:path, :content, :hash)"),
        {"path": path, "content": existing_content, "hash": "abc"},
    )

    # Create workspace_files table with different content
    await db_session.execute(text("""
        CREATE TABLE IF NOT EXISTS workspace_files (
            id UUID PRIMARY KEY,
            path VARCHAR(1000) NOT NULL UNIQUE,
            entity_type VARCHAR(50),
            entity_id UUID,
            content TEXT,
            content_hash VARCHAR(64),
            is_deleted BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW()
        )
    """))
    await db_session.execute(
        text("INSERT INTO workspace_files (id, path, content, is_deleted) VALUES (:id, :path, :content, false)"),
        {"id": uuid4(), "path": path, "content": "# new content from workspace_files"},
    )
    await db_session.flush()

    mock_repo = _make_mock_repo()
    patches = _patch_repo_storage(mock_repo)
    for p in patches:
        p.start()
    try:
        stats = await backfill_workspace_data(db_session)
    finally:
        for p in patches:
            p.stop()

    # Should NOT have overwritten existing entry
    assert stats["workspace_files"] == 0

    # Content should still be the original
    result = await db_session.execute(
        select(FileIndex.content).where(FileIndex.path == path)
    )
    content = result.scalar_one_or_none()
    assert content == existing_content

    # Cleanup
    await db_session.execute(text("DROP TABLE IF EXISTS workspace_files"))
    await db_session.execute(text("DELETE FROM file_index WHERE path = :path"), {"path": path})


@pytest.mark.asyncio
async def test_backfill_skips_deleted_workspace_files(db_session: AsyncSession):
    """Backfill should not migrate workspace_files marked as deleted."""
    from scripts.pre_migration_backfill import backfill_workspace_data

    await db_session.execute(text("""
        CREATE TABLE IF NOT EXISTS workspace_files (
            id UUID PRIMARY KEY,
            path VARCHAR(1000) NOT NULL UNIQUE,
            entity_type VARCHAR(50),
            entity_id UUID,
            content TEXT,
            content_hash VARCHAR(64),
            is_deleted BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW()
        )
    """))
    await db_session.execute(
        text("INSERT INTO workspace_files (id, path, content, is_deleted) VALUES (:id, :path, :content, true)"),
        {"id": uuid4(), "path": "workflows/deleted.py", "content": "# should not migrate"},
    )
    await db_session.flush()

    mock_repo = _make_mock_repo()
    patches = _patch_repo_storage(mock_repo)
    for p in patches:
        p.start()
    try:
        stats = await backfill_workspace_data(db_session)
    finally:
        for p in patches:
            p.stop()

    assert stats["workspace_files"] == 0

    # Cleanup
    await db_session.execute(text("DROP TABLE IF EXISTS workspace_files"))
