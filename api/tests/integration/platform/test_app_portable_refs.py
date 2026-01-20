"""
Integration tests for app file portable workflow reference resolution.

Tests the complete flow:
1. Create workflow in database
2. Import app file with useWorkflow(portable_ref)
3. Verify UUID is resolved in stored source
"""

import json
import logging
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import Application, AppFile, AppVersion, Workflow, WorkspaceFile
from src.services.file_storage.indexers.app import AppIndexer

logger = logging.getLogger(__name__)


@pytest_asyncio.fixture
async def clean_app_test_data(db_session: AsyncSession):
    """Clean up test data before and after tests."""
    async def cleanup():
        # Delete app files first
        apps_to_delete = await db_session.execute(
            select(Application.id).where(
                Application.slug.like("test-portable-ref-%")
            )
        )
        app_ids = [r[0] for r in apps_to_delete.fetchall()]

        if app_ids:
            # Get version IDs
            versions = await db_session.execute(
                select(AppVersion.id).where(AppVersion.application_id.in_(app_ids))
            )
            version_ids = [r[0] for r in versions.fetchall()]

            if version_ids:
                await db_session.execute(
                    delete(AppFile).where(AppFile.app_version_id.in_(version_ids))
                )

            await db_session.execute(
                delete(AppVersion).where(AppVersion.application_id.in_(app_ids))
            )

        await db_session.execute(
            delete(Application).where(Application.slug.like("test-portable-ref-%"))
        )

        await db_session.execute(
            delete(Workflow).where(Workflow.path.like("workflows/test_app_ref_%"))
        )

        await db_session.execute(
            delete(WorkspaceFile).where(WorkspaceFile.path.like("apps/test-portable-ref-%"))
        )

        await db_session.commit()

    await cleanup()
    yield
    await cleanup()


@pytest_asyncio.fixture
async def test_workflow_for_app(db_session: AsyncSession, clean_app_test_data):  # noqa: ARG001
    """Create a workflow for testing app portable ref resolution."""
    workflow_id = uuid4()
    workflow_path = f"workflows/test_app_ref_{workflow_id.hex[:8]}.py"
    workflow_function = f"test_app_ref_{workflow_id.hex[:8]}"

    workflow = Workflow(
        id=workflow_id,
        name=workflow_function,
        function_name=workflow_function,
        path=workflow_path,
        description="Test workflow for app ref resolution",
        type="workflow",
        is_active=True,
        category="test",
    )
    db_session.add(workflow)
    await db_session.commit()

    portable_ref = f"{workflow_path}::{workflow_function}"

    yield {
        "id": workflow_id,
        "path": workflow_path,
        "function_name": workflow_function,
        "portable_ref": portable_ref,
    }


@pytest.mark.integration
class TestAppPortableRefResolution:
    """Test app indexer resolves portable refs to UUIDs."""

    @pytest.mark.asyncio
    async def test_app_file_use_workflow_resolution(
        self,
        db_session: AsyncSession,
        test_workflow_for_app,
    ):
        """
        Test that useWorkflow(portable_ref) is resolved to UUID in app files.
        """
        portable_ref = test_workflow_for_app["portable_ref"]
        workflow_id = test_workflow_for_app["id"]
        app_slug = f"test-portable-ref-{uuid4().hex[:8]}"

        # First, create the app via app.json
        indexer = AppIndexer(db_session)
        app_json = json.dumps({"name": "Test App", "slug": app_slug}).encode()
        await indexer.index_app_json(f"apps/{app_slug}/app.json", app_json)

        # Now import an app file with portable ref
        tsx_source = f"""
import {{ useWorkflow }} from '@bifrost/sdk';

export function MyPage() {{
    const {{ execute }} = useWorkflow('{portable_ref}');
    return <button onClick={{execute}}>Run Workflow</button>;
}}
"""
        await indexer.index_app_file(
            f"apps/{app_slug}/pages/index.tsx",
            tsx_source.encode("utf-8"),
        )
        await db_session.commit()

        # Verify the stored source has UUID, not portable ref
        app = await db_session.execute(
            select(Application).where(Application.slug == app_slug)
        )
        app = app.scalar_one()

        files = await db_session.execute(
            select(AppFile).where(AppFile.app_version_id == app.draft_version_id)
        )
        file = files.scalar_one()

        assert str(workflow_id) in file.source, (
            f"Expected UUID {workflow_id} in source, got: {file.source}"
        )
        assert portable_ref not in file.source, (
            f"Portable ref should be resolved: {file.source}"
        )

    @pytest.mark.asyncio
    async def test_app_file_unresolved_ref_preserved(
        self,
        db_session: AsyncSession,
        clean_app_test_data,  # noqa: ARG002
    ):
        """
        Test that unresolved refs are preserved in source (not corrupted).
        """
        app_slug = f"test-portable-ref-{uuid4().hex[:8]}"
        missing_ref = "workflows/does_not_exist.py::missing_func"

        # Create the app
        indexer = AppIndexer(db_session)
        app_json = json.dumps({"name": "Test App", "slug": app_slug}).encode()
        await indexer.index_app_json(f"apps/{app_slug}/app.json", app_json)

        # Import file with unresolved ref
        tsx_source = f"""
const {{ execute }} = useWorkflow('{missing_ref}');
"""
        await indexer.index_app_file(
            f"apps/{app_slug}/pages/index.tsx",
            tsx_source.encode("utf-8"),
        )
        await db_session.commit()

        # Verify unresolved ref is preserved (not corrupted)
        app = await db_session.execute(
            select(Application).where(Application.slug == app_slug)
        )
        app = app.scalar_one()

        files = await db_session.execute(
            select(AppFile).where(AppFile.app_version_id == app.draft_version_id)
        )
        file = files.scalar_one()

        assert missing_ref in file.source, (
            f"Unresolved ref should be preserved: {file.source}"
        )

    @pytest.mark.asyncio
    async def test_app_file_mixed_refs(
        self,
        db_session: AsyncSession,
        test_workflow_for_app,
    ):
        """
        Test file with both resolvable and unresolvable refs.
        """
        portable_ref = test_workflow_for_app["portable_ref"]
        workflow_id = test_workflow_for_app["id"]
        app_slug = f"test-portable-ref-{uuid4().hex[:8]}"
        missing_ref = "workflows/missing.py::gone"

        # Create the app
        indexer = AppIndexer(db_session)
        app_json = json.dumps({"name": "Test App", "slug": app_slug}).encode()
        await indexer.index_app_json(f"apps/{app_slug}/app.json", app_json)

        # Import file with both refs
        tsx_source = f"""
const w1 = useWorkflow('{portable_ref}');
const w2 = useWorkflow('{missing_ref}');
"""
        await indexer.index_app_file(
            f"apps/{app_slug}/pages/index.tsx",
            tsx_source.encode("utf-8"),
        )
        await db_session.commit()

        # Verify: resolved ref becomes UUID, unresolved stays as-is
        app = await db_session.execute(
            select(Application).where(Application.slug == app_slug)
        )
        app = app.scalar_one()

        files = await db_session.execute(
            select(AppFile).where(AppFile.app_version_id == app.draft_version_id)
        )
        file = files.scalar_one()

        assert str(workflow_id) in file.source
        assert missing_ref in file.source
        assert portable_ref not in file.source
