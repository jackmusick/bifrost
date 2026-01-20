# App Portable Workflow References Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Transform `useWorkflow('{uuid}')` to/from portable refs in App Builder TSX files during git sync.

**Architecture:** Add regex-based source transformation functions to `ref_translation.py`. On export, replace UUIDs with `workflows/path.py::function` refs. On import, resolve refs back to UUIDs. Use existing `DiagnosticsService` pattern for persistent unresolved ref notifications.

**Tech Stack:** Python, regex, SQLAlchemy, existing notification system

---

## Task 1: Add App Source Transformation Functions to ref_translation.py

**Files:**
- Modify: `api/src/services/file_storage/ref_translation.py`
- Test: `api/tests/unit/services/test_ref_translation_app.py`

**Step 1: Write the failing tests**

Create test file `api/tests/unit/services/test_ref_translation_app.py`:

```python
"""
Unit tests for app source workflow reference transformation.

Tests transform_app_source_uuids_to_refs and transform_app_source_refs_to_uuids.
"""

import pytest

from src.services.file_storage.ref_translation import (
    transform_app_source_uuids_to_refs,
    transform_app_source_refs_to_uuids,
)


class TestTransformAppSourceUuidsToRefs:
    """Tests for UUID -> portable ref transformation."""

    def test_transforms_single_use_workflow(self):
        """Single useWorkflow call with matching UUID is transformed."""
        source = """
import { useWorkflow } from '@bifrost/sdk';

export function MyComponent() {
    const { execute } = useWorkflow('550e8400-e29b-41d4-a716-446655440000');
    return <button onClick={execute}>Run</button>;
}
"""
        workflow_map = {
            "550e8400-e29b-41d4-a716-446655440000": "workflows/onboarding.py::provision_user"
        }

        result, transformed = transform_app_source_uuids_to_refs(source, workflow_map)

        assert "useWorkflow('workflows/onboarding.py::provision_user')" in result
        assert "550e8400-e29b-41d4-a716-446655440000" not in result
        assert "550e8400-e29b-41d4-a716-446655440000" in transformed

    def test_transforms_double_quoted_uuid(self):
        """Double-quoted UUID strings are also transformed."""
        source = 'const w = useWorkflow("550e8400-e29b-41d4-a716-446655440000");'
        workflow_map = {
            "550e8400-e29b-41d4-a716-446655440000": "workflows/test.py::my_func"
        }

        result, transformed = transform_app_source_uuids_to_refs(source, workflow_map)

        assert 'useWorkflow("workflows/test.py::my_func")' in result
        assert len(transformed) == 1

    def test_transforms_multiple_use_workflow_calls(self):
        """Multiple useWorkflow calls in same file are all transformed."""
        source = """
const w1 = useWorkflow('uuid-1111-1111-1111-111111111111');
const w2 = useWorkflow('uuid-2222-2222-2222-222222222222');
"""
        workflow_map = {
            "uuid-1111-1111-1111-111111111111": "workflows/a.py::func_a",
            "uuid-2222-2222-2222-222222222222": "workflows/b.py::func_b",
        }

        result, transformed = transform_app_source_uuids_to_refs(source, workflow_map)

        assert "useWorkflow('workflows/a.py::func_a')" in result
        assert "useWorkflow('workflows/b.py::func_b')" in result
        assert len(transformed) == 2

    def test_ignores_uuid_not_in_map(self):
        """UUIDs not in the workflow map are left unchanged."""
        source = "const w = useWorkflow('unknown-uuid-not-in-map-00000');"
        workflow_map = {}

        result, transformed = transform_app_source_uuids_to_refs(source, workflow_map)

        assert result == source
        assert len(transformed) == 0

    def test_preserves_non_use_workflow_content(self):
        """Non-useWorkflow code is preserved unchanged."""
        source = """
const uuid = '550e8400-e29b-41d4-a716-446655440000';
const other = someFunction('550e8400-e29b-41d4-a716-446655440000');
const w = useWorkflow('550e8400-e29b-41d4-a716-446655440000');
"""
        workflow_map = {
            "550e8400-e29b-41d4-a716-446655440000": "workflows/test.py::func"
        }

        result, _ = transform_app_source_uuids_to_refs(source, workflow_map)

        # Only the useWorkflow call should be transformed
        assert "const uuid = '550e8400-e29b-41d4-a716-446655440000'" in result
        assert "someFunction('550e8400-e29b-41d4-a716-446655440000')" in result
        assert "useWorkflow('workflows/test.py::func')" in result

    def test_empty_source(self):
        """Empty source returns empty result."""
        result, transformed = transform_app_source_uuids_to_refs("", {})

        assert result == ""
        assert len(transformed) == 0

    def test_empty_workflow_map(self):
        """Empty workflow map leaves source unchanged."""
        source = "const w = useWorkflow('some-uuid');"

        result, transformed = transform_app_source_uuids_to_refs(source, {})

        assert result == source
        assert len(transformed) == 0


class TestTransformAppSourceRefsToUuids:
    """Tests for portable ref -> UUID transformation."""

    def test_transforms_single_portable_ref(self):
        """Single portable ref is resolved to UUID."""
        source = """
const { execute } = useWorkflow('workflows/onboarding.py::provision_user');
"""
        ref_to_uuid = {
            "workflows/onboarding.py::provision_user": "550e8400-e29b-41d4-a716-446655440000"
        }

        result, unresolved = transform_app_source_refs_to_uuids(source, ref_to_uuid)

        assert "useWorkflow('550e8400-e29b-41d4-a716-446655440000')" in result
        assert "workflows/onboarding.py::provision_user" not in result
        assert len(unresolved) == 0

    def test_transforms_double_quoted_ref(self):
        """Double-quoted portable refs are also transformed."""
        source = 'const w = useWorkflow("workflows/test.py::my_func");'
        ref_to_uuid = {
            "workflows/test.py::my_func": "uuid-1234"
        }

        result, unresolved = transform_app_source_refs_to_uuids(source, ref_to_uuid)

        assert 'useWorkflow("uuid-1234")' in result
        assert len(unresolved) == 0

    def test_collects_unresolved_refs(self):
        """Refs not in the map are collected as unresolved."""
        source = """
const w1 = useWorkflow('workflows/exists.py::func');
const w2 = useWorkflow('workflows/missing.py::not_found');
"""
        ref_to_uuid = {
            "workflows/exists.py::func": "uuid-exists"
        }

        result, unresolved = transform_app_source_refs_to_uuids(source, ref_to_uuid)

        assert "useWorkflow('uuid-exists')" in result
        # Missing ref stays as-is
        assert "useWorkflow('workflows/missing.py::not_found')" in result
        assert len(unresolved) == 1
        assert unresolved[0] == "workflows/missing.py::not_found"

    def test_uuid_strings_pass_through(self):
        """Already-resolved UUIDs pass through unchanged."""
        source = "const w = useWorkflow('550e8400-e29b-41d4-a716-446655440000');"
        ref_to_uuid = {}

        result, unresolved = transform_app_source_refs_to_uuids(source, ref_to_uuid)

        # UUID strings that look like UUIDs should pass through
        assert result == source
        assert len(unresolved) == 0

    def test_multiple_refs_resolved(self):
        """Multiple refs are all resolved."""
        source = """
const w1 = useWorkflow('workflows/a.py::func_a');
const w2 = useWorkflow('workflows/b.py::func_b');
"""
        ref_to_uuid = {
            "workflows/a.py::func_a": "uuid-a",
            "workflows/b.py::func_b": "uuid-b",
        }

        result, unresolved = transform_app_source_refs_to_uuids(source, ref_to_uuid)

        assert "useWorkflow('uuid-a')" in result
        assert "useWorkflow('uuid-b')" in result
        assert len(unresolved) == 0

    def test_empty_source(self):
        """Empty source returns empty result."""
        result, unresolved = transform_app_source_refs_to_uuids("", {})

        assert result == ""
        assert len(unresolved) == 0

    def test_preserves_non_use_workflow_content(self):
        """Non-useWorkflow code is preserved unchanged."""
        source = """
const ref = 'workflows/test.py::func';
const other = someFunction('workflows/test.py::func');
const w = useWorkflow('workflows/test.py::func');
"""
        ref_to_uuid = {
            "workflows/test.py::func": "uuid-1234"
        }

        result, _ = transform_app_source_refs_to_uuids(source, ref_to_uuid)

        # Only the useWorkflow call should be transformed
        assert "const ref = 'workflows/test.py::func'" in result
        assert "someFunction('workflows/test.py::func')" in result
        assert "useWorkflow('uuid-1234')" in result
```

**Step 2: Run tests to verify they fail**

Run: `./test.sh api/tests/unit/services/test_ref_translation_app.py -v`
Expected: FAIL with "cannot import name 'transform_app_source_uuids_to_refs'"

**Step 3: Implement the transformation functions**

Add to `api/src/services/file_storage/ref_translation.py` (after existing imports, around line 23):

```python
import re

# Pattern to match useWorkflow('...') or useWorkflow("...")
# Captures the quote style and the argument
USE_WORKFLOW_PATTERN = re.compile(r"useWorkflow\((['\"])([^'\"]+)\1\)")
```

Add at the end of the file (after `extract_export_metadata`):

```python
# =============================================================================
# App Source Transformation Functions
# =============================================================================


def transform_app_source_uuids_to_refs(
    source: str,
    workflow_map: dict[str, str],
) -> tuple[str, list[str]]:
    """
    Transform useWorkflow('{uuid}') to useWorkflow('{ref}') in TSX source.

    Scans source code for useWorkflow() calls and replaces UUIDs with
    portable workflow references (path::function_name format).

    Args:
        source: TSX/TypeScript source code
        workflow_map: Mapping of UUID string -> "path::function_name"

    Returns:
        Tuple of (transformed_source, list_of_transformed_uuids)
    """
    if not source or not workflow_map:
        return source, []

    transformed_uuids: list[str] = []

    def replace_uuid(match: re.Match[str]) -> str:
        quote = match.group(1)
        arg = match.group(2)

        if arg in workflow_map:
            transformed_uuids.append(arg)
            return f"useWorkflow({quote}{workflow_map[arg]}{quote})"
        return match.group(0)

    result = USE_WORKFLOW_PATTERN.sub(replace_uuid, source)
    return result, transformed_uuids


def transform_app_source_refs_to_uuids(
    source: str,
    ref_to_uuid: dict[str, str],
) -> tuple[str, list[str]]:
    """
    Transform useWorkflow('{ref}') to useWorkflow('{uuid}') in TSX source.

    Scans source code for useWorkflow() calls and resolves portable
    workflow references back to UUIDs.

    Args:
        source: TSX/TypeScript source code
        ref_to_uuid: Mapping of "path::function_name" -> UUID string

    Returns:
        Tuple of (transformed_source, list_of_unresolved_refs)
    """
    if not source:
        return source, []

    unresolved_refs: list[str] = []

    def replace_ref(match: re.Match[str]) -> str:
        quote = match.group(1)
        arg = match.group(2)

        # Check if already a UUID (skip transformation)
        if _looks_like_uuid(arg):
            return match.group(0)

        # Check if it's a portable ref we can resolve
        if arg in ref_to_uuid:
            return f"useWorkflow({quote}{ref_to_uuid[arg]}{quote})"

        # Unresolved ref - keep as-is but track it
        if "::" in arg:  # Looks like a portable ref
            unresolved_refs.append(arg)

        return match.group(0)

    result = USE_WORKFLOW_PATTERN.sub(replace_ref, source)
    return result, unresolved_refs


def _looks_like_uuid(value: str) -> bool:
    """
    Check if a string looks like a UUID.

    Simple heuristic: 36 chars with hyphens in the right places.
    """
    if len(value) != 36:
        return False
    if value[8] != "-" or value[13] != "-" or value[18] != "-" or value[23] != "-":
        return False
    return True
```

**Step 4: Run tests to verify they pass**

Run: `./test.sh api/tests/unit/services/test_ref_translation_app.py -v`
Expected: All tests PASS

**Step 5: Run type checking**

Run: `cd api && pyright src/services/file_storage/ref_translation.py`
Expected: 0 errors

**Step 6: Commit**

```bash
git add api/src/services/file_storage/ref_translation.py api/tests/unit/services/test_ref_translation_app.py
git commit -m "feat(ref-translation): add app source transformation functions

Add transform_app_source_uuids_to_refs and transform_app_source_refs_to_uuids
for transforming useWorkflow() calls in TSX files between UUIDs and portable refs."
```

---

## Task 2: Add Unresolved Ref Notification Helpers to DiagnosticsService

**Files:**
- Modify: `api/src/services/file_storage/diagnostics.py`
- Test: `api/tests/unit/services/test_diagnostics_unresolved_refs.py`

**Step 1: Write the failing tests**

Create test file `api/tests/unit/services/test_diagnostics_unresolved_refs.py`:

```python
"""
Unit tests for unresolved reference notification helpers.

Tests scan_for_unresolved_refs and clear_unresolved_refs_notification.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.services.file_storage.diagnostics import DiagnosticsService


class TestUnresolvedRefNotifications:
    """Tests for unresolved ref notification helpers."""

    @pytest.fixture
    def mock_db(self):
        """Create mock database session."""
        return AsyncMock()

    @pytest.fixture
    def diagnostics_service(self, mock_db):
        """Create diagnostics service with mock db."""
        return DiagnosticsService(mock_db)

    @pytest.mark.asyncio
    async def test_creates_notification_for_unresolved_refs(
        self, diagnostics_service
    ):
        """When unresolved refs exist, creates a notification."""
        unresolved = ["workflows/missing.py::func1", "workflows/gone.py::func2"]

        with patch(
            "src.services.file_storage.diagnostics.get_notification_service"
        ) as mock_get_service:
            mock_service = MagicMock()
            mock_service.find_admin_notification_by_title = AsyncMock(return_value=None)
            mock_service.create_notification = AsyncMock()
            mock_get_service.return_value = mock_service

            await diagnostics_service.scan_for_unresolved_refs(
                path="apps/my-app/pages/index.tsx",
                entity_type="app_file",
                unresolved_refs=unresolved,
            )

            mock_service.create_notification.assert_called_once()
            call_args = mock_service.create_notification.call_args
            assert "Unresolved Workflow Refs" in call_args.kwargs["request"].title
            assert "index.tsx" in call_args.kwargs["request"].title

    @pytest.mark.asyncio
    async def test_clears_notification_when_no_unresolved_refs(
        self, diagnostics_service
    ):
        """When no unresolved refs, clears any existing notification."""
        with patch(
            "src.services.file_storage.diagnostics.get_notification_service"
        ) as mock_get_service:
            mock_service = MagicMock()
            mock_service.find_admin_notification_by_title = AsyncMock(return_value=None)
            mock_get_service.return_value = mock_service

            await diagnostics_service.scan_for_unresolved_refs(
                path="apps/my-app/pages/index.tsx",
                entity_type="app_file",
                unresolved_refs=[],
            )

            # Should not create notification
            mock_service.create_notification.assert_not_called()

    @pytest.mark.asyncio
    async def test_clears_existing_notification(self, diagnostics_service):
        """clear_unresolved_refs_notification dismisses existing notification."""
        with patch(
            "src.services.file_storage.diagnostics.get_notification_service"
        ) as mock_get_service:
            mock_notification = MagicMock()
            mock_notification.id = "notif-123"

            mock_service = MagicMock()
            mock_service.find_admin_notification_by_title = AsyncMock(
                return_value=mock_notification
            )
            mock_service.dismiss_notification = AsyncMock()
            mock_get_service.return_value = mock_service

            await diagnostics_service.clear_unresolved_refs_notification(
                path="apps/my-app/pages/index.tsx"
            )

            mock_service.dismiss_notification.assert_called_once_with(
                "notif-123", user_id="system"
            )

    @pytest.mark.asyncio
    async def test_skips_duplicate_notification(self, diagnostics_service):
        """Does not create duplicate notification if one already exists."""
        unresolved = ["workflows/missing.py::func"]

        with patch(
            "src.services.file_storage.diagnostics.get_notification_service"
        ) as mock_get_service:
            mock_existing = MagicMock()

            mock_service = MagicMock()
            mock_service.find_admin_notification_by_title = AsyncMock(
                return_value=mock_existing
            )
            mock_service.create_notification = AsyncMock()
            mock_get_service.return_value = mock_service

            await diagnostics_service.scan_for_unresolved_refs(
                path="apps/my-app/pages/index.tsx",
                entity_type="app_file",
                unresolved_refs=unresolved,
            )

            # Should not create when existing
            mock_service.create_notification.assert_not_called()
```

**Step 2: Run tests to verify they fail**

Run: `./test.sh api/tests/unit/services/test_diagnostics_unresolved_refs.py -v`
Expected: FAIL with "AttributeError: 'DiagnosticsService' object has no attribute 'scan_for_unresolved_refs'"

**Step 3: Implement the notification helpers**

Add to `api/src/services/file_storage/diagnostics.py` (at end of class, before closing):

```python
    async def scan_for_unresolved_refs(
        self,
        path: str,
        entity_type: str,
        unresolved_refs: list[str],
    ) -> None:
        """
        Create or clear notification for unresolved workflow references.

        Called after file processing to notify about portable refs that
        couldn't be resolved to UUIDs.

        Args:
            path: Relative file path
            entity_type: Type of entity ("app_file", "form", "agent")
            unresolved_refs: List of unresolved portable refs
        """
        if not unresolved_refs:
            # Clear any existing notification since issues are resolved
            await self.clear_unresolved_refs_notification(path)
            return

        service = get_notification_service()

        # Build title from file name
        file_name = Path(path).name
        title = f"Unresolved Workflow Refs: {file_name}"

        # Check for existing notification to avoid duplicates
        existing = await service.find_admin_notification_by_title(
            title=title,
            category=NotificationCategory.SYSTEM,
        )
        if existing:
            logger.debug(f"Unresolved refs notification already exists for {path}")
            return

        # Build description with first few refs
        ref_list = unresolved_refs[:3]
        description = f"{len(unresolved_refs)} unresolved: {', '.join(ref_list)}"
        if len(unresolved_refs) > 3:
            description += "..."

        await service.create_notification(
            user_id="system",
            request=NotificationCreate(
                category=NotificationCategory.SYSTEM,
                title=title,
                description=description,
                metadata={
                    "action": "view_file",
                    "file_path": path,
                    "entity_type": entity_type,
                    "unresolved_refs": unresolved_refs,
                },
            ),
            for_admins=True,
            initial_status=NotificationStatus.AWAITING_ACTION,
        )

        logger.info(f"Created unresolved refs notification for {path}: {len(unresolved_refs)} refs")

    async def clear_unresolved_refs_notification(self, path: str) -> None:
        """
        Clear unresolved refs notification for a file when issues are resolved.

        Called when a file is saved without unresolved refs to remove
        any existing notification that was created for previous issues.

        Args:
            path: Relative file path
        """
        service = get_notification_service()

        # Match the title format used in scan_for_unresolved_refs
        file_name = Path(path).name
        title = f"Unresolved Workflow Refs: {file_name}"

        existing = await service.find_admin_notification_by_title(
            title=title,
            category=NotificationCategory.SYSTEM,
        )
        if existing:
            await service.dismiss_notification(existing.id, user_id="system")
            logger.info(f"Cleared unresolved refs notification for {path}")
```

**Step 4: Run tests to verify they pass**

Run: `./test.sh api/tests/unit/services/test_diagnostics_unresolved_refs.py -v`
Expected: All tests PASS

**Step 5: Run type checking**

Run: `cd api && pyright src/services/file_storage/diagnostics.py`
Expected: 0 errors

**Step 6: Commit**

```bash
git add api/src/services/file_storage/diagnostics.py api/tests/unit/services/test_diagnostics_unresolved_refs.py
git commit -m "feat(diagnostics): add unresolved workflow ref notification helpers

Add scan_for_unresolved_refs and clear_unresolved_refs_notification for
persistent notifications when portable refs can't be resolved during import."
```

---

## Task 3: Update App Indexer for Import (refs → UUIDs)

**Files:**
- Modify: `api/src/services/file_storage/indexers/app.py`
- Test: `api/tests/integration/platform/test_app_portable_refs.py`

**Step 1: Write the failing integration test**

Create test file `api/tests/integration/platform/test_app_portable_refs.py`:

```python
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
from src.models.enums import GitStatus
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
```

**Step 2: Run tests to verify they fail**

Run: `./test.sh api/tests/integration/platform/test_app_portable_refs.py -v`
Expected: FAIL (portable refs not being transformed)

**Step 3: Update the app indexer**

Modify `api/src/services/file_storage/indexers/app.py`:

Add imports at top (after existing imports):

```python
from src.services.file_storage.ref_translation import (
    build_ref_to_uuid_map,
    transform_app_source_refs_to_uuids,
)
from src.services.file_storage.diagnostics import DiagnosticsService
```

Update the `index_app_file` method to transform refs. Replace the section that decodes and stores the source (around lines 224-256):

```python
    async def index_app_file(
        self,
        path: str,
        content: bytes,
    ) -> bool:
        """
        Parse and index an app code file.

        Creates or updates the AppFile record in the app's draft version.
        Transforms portable workflow refs to UUIDs.

        Args:
            path: File path (e.g., "apps/my-app/pages/index.tsx")
            content: File content bytes

        Returns:
            True if content was modified, False otherwise
        """
        # Extract slug and relative path
        # Path format: apps/{slug}/{relative_path}
        parts = path.split("/", 2)
        if len(parts) < 3 or parts[0] != "apps":
            logger.warning(f"Invalid app file path format: {path}")
            return False

        slug = parts[1]
        relative_path = parts[2]

        # Skip app.json - handled by index_app_json
        if relative_path == "app.json":
            return False

        # Get the app by slug
        app = await self._get_app_by_slug(slug)
        if not app:
            logger.warning(f"App not found for file {path}. Index app.json first.")
            return False

        # Ensure draft version exists
        if not app.draft_version_id:
            logger.warning(f"App {slug} has no draft version")
            return False

        # Decode content
        try:
            source = content.decode("utf-8")
        except UnicodeDecodeError:
            logger.warning(f"Invalid UTF-8 in app file: {path}")
            return False

        # Transform portable workflow refs to UUIDs
        ref_to_uuid = await build_ref_to_uuid_map(self.db)
        transformed_source, unresolved_refs = transform_app_source_refs_to_uuids(
            source, ref_to_uuid
        )

        # Create notification for unresolved refs (or clear if resolved)
        diagnostics = DiagnosticsService(self.db)
        await diagnostics.scan_for_unresolved_refs(
            path=path,
            entity_type="app_file",
            unresolved_refs=unresolved_refs,
        )

        now = datetime.now(timezone.utc)

        # Upsert the file with transformed source
        file_id = uuid4()
        stmt = insert(AppFile).values(
            id=file_id,
            app_version_id=app.draft_version_id,
            path=relative_path,
            source=transformed_source,
            compiled=None,
            created_at=now,
            updated_at=now,
        ).on_conflict_do_update(
            index_elements=["app_version_id", "path"],
            set_={
                "source": transformed_source,
                "compiled": None,  # Clear compiled on update
                "updated_at": now,
            },
        ).returning(AppFile.id)
        result = await self.db.execute(stmt)
        actual_file_id = result.scalar_one()

        # Sync dependencies for this file (uses transformed source with UUIDs)
        await self._sync_file_dependencies(actual_file_id, transformed_source)

        logger.debug(f"Indexed app file: {relative_path} in app {slug}")
        return False
```

**Step 4: Run tests to verify they pass**

Run: `./test.sh api/tests/integration/platform/test_app_portable_refs.py -v`
Expected: All tests PASS

**Step 5: Run type checking**

Run: `cd api && pyright src/services/file_storage/indexers/app.py`
Expected: 0 errors

**Step 6: Commit**

```bash
git add api/src/services/file_storage/indexers/app.py api/tests/integration/platform/test_app_portable_refs.py
git commit -m "feat(app-indexer): transform portable refs to UUIDs on import

App files now have useWorkflow(portable_ref) resolved to UUIDs during indexing.
Unresolved refs create persistent notifications."
```

---

## Task 4: Update Virtual Files Provider for Export (UUIDs → refs)

**Files:**
- Modify: `api/src/services/github_sync_virtual_files.py`
- Test: `api/tests/unit/services/test_github_sync_virtual_files.py` (extend)

**Step 1: Write the failing test**

Add to existing test file or create `api/tests/unit/services/test_app_virtual_files_export.py`:

```python
"""
Unit tests for app file export with portable refs.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from src.services.github_sync_virtual_files import VirtualFileProvider


class TestAppFileExportPortableRefs:
    """Tests for app file export with workflow ref transformation."""

    @pytest.fixture
    def mock_db(self):
        """Create mock database session."""
        return AsyncMock()

    @pytest.mark.asyncio
    async def test_app_file_uuids_transformed_to_refs(self, mock_db):
        """App file UUIDs in useWorkflow are transformed to portable refs."""
        workflow_id = str(uuid4())
        portable_ref = "workflows/test.py::my_func"

        # Mock workflow ref map
        with patch(
            "src.services.github_sync_virtual_files.build_workflow_ref_map",
            new_callable=AsyncMock,
        ) as mock_build_map:
            mock_build_map.return_value = {workflow_id: portable_ref}

            # Mock app query
            mock_app = MagicMock()
            mock_app.id = uuid4()
            mock_app.slug = "test-app"
            mock_app.name = "Test App"
            mock_app.description = None
            mock_app.icon = None
            mock_app.navigation = {}

            mock_version = MagicMock()
            mock_version.id = uuid4()

            mock_file = MagicMock()
            mock_file.id = uuid4()
            mock_file.path = "pages/index.tsx"
            mock_file.source = f"const w = useWorkflow('{workflow_id}');"

            mock_version.files = [mock_file]
            mock_app.active_version = mock_version
            mock_app.draft_version_ref = None

            mock_result = MagicMock()
            mock_result.scalars.return_value.all.return_value = [mock_app]
            mock_db.execute = AsyncMock(return_value=mock_result)

            provider = VirtualFileProvider(mock_db)
            result = await provider._get_app_files()

            # Find the tsx file in results
            tsx_file = next(
                (f for f in result.files if f.path.endswith(".tsx")),
                None
            )
            assert tsx_file is not None

            content = tsx_file.content.decode("utf-8")
            assert portable_ref in content
            assert workflow_id not in content
```

**Step 2: Run tests to verify they fail**

Run: `./test.sh api/tests/unit/services/test_app_virtual_files_export.py -v`
Expected: FAIL (UUIDs not being transformed)

**Step 3: Update virtual files provider**

Modify `api/src/services/github_sync_virtual_files.py`:

Add import at top:

```python
from src.services.file_storage.ref_translation import (
    build_workflow_ref_map,
    transform_app_source_uuids_to_refs,
)
```

Update `_get_app_files` method to transform source before exporting. Modify around line 347-363:

```python
    async def _get_app_files(self) -> VirtualFileResult:
        """
        Generate virtual files for all applications.

        Each app produces multiple virtual files:
        - apps/{slug}/app.json - portable metadata
        - apps/{slug}/{path} - each code file (pages/*.tsx, components/*.tsx, etc.)

        Uses the app's active_version if published, otherwise draft_version.
        Code files have useWorkflow UUIDs transformed to portable refs.
        """
        # Build workflow ref map for transforming UUIDs to portable refs
        workflow_map = await build_workflow_ref_map(self.db)

        # Query apps with their versions and files eagerly loaded
        stmt = (
            select(Application)
            .options(
                selectinload(Application.active_version).selectinload(AppVersion.files),
                selectinload(Application.draft_version_ref).selectinload(AppVersion.files),
            )
        )
        result = await self.db.execute(stmt)
        apps = result.scalars().all()

        virtual_files: list[VirtualFile] = []
        errors: list[SerializationError] = []

        for app in apps:
            # Use active_version if published, otherwise draft
            version = app.active_version or app.draft_version_ref
            if not version:
                logger.debug(f"App {app.slug} has no version, skipping")
                continue

            app_dir = f"apps/{app.slug}"

            # 1. Serialize app.json (portable metadata only)
            try:
                content = _serialize_app_to_json(app)
                computed_sha = compute_git_blob_sha(content)

                virtual_files.append(
                    VirtualFile(
                        path=f"{app_dir}/app.json",
                        entity_type="app",
                        entity_id=str(app.id),
                        content=content,
                        computed_sha=computed_sha,
                    )
                )
            except Exception as e:
                logger.warning(f"Failed to serialize app {app.slug}: {e}")
                errors.append(
                    SerializationError(
                        entity_type="app",
                        entity_id=str(app.id),
                        entity_name=app.name,
                        path=f"{app_dir}/app.json",
                        error=str(e),
                    )
                )
                continue  # Skip files if app.json fails

            # 2. Serialize each code file with UUID -> ref transformation
            for file in version.files:
                file_path = f"{app_dir}/{file.path}"
                try:
                    # Transform UUIDs to portable refs
                    transformed_source, _ = transform_app_source_uuids_to_refs(
                        file.source, workflow_map
                    )
                    content = transformed_source.encode("utf-8")
                    computed_sha = compute_git_blob_sha(content)

                    virtual_files.append(
                        VirtualFile(
                            path=file_path,
                            entity_type="app_file",
                            entity_id=str(file.id),
                            content=content,
                            computed_sha=computed_sha,
                        )
                    )
                except Exception as e:
                    logger.warning(f"Failed to serialize app file {file.path}: {e}")
                    errors.append(
                        SerializationError(
                            entity_type="app_file",
                            entity_id=str(file.id),
                            entity_name=file.path,
                            path=file_path,
                            error=str(e),
                        )
                    )

        return VirtualFileResult(files=virtual_files, errors=errors)
```

**Step 4: Run tests to verify they pass**

Run: `./test.sh api/tests/unit/services/test_app_virtual_files_export.py -v`
Expected: All tests PASS

**Step 5: Run type checking**

Run: `cd api && pyright src/services/github_sync_virtual_files.py`
Expected: 0 errors

**Step 6: Commit**

```bash
git add api/src/services/github_sync_virtual_files.py api/tests/unit/services/test_app_virtual_files_export.py
git commit -m "feat(virtual-files): transform app file UUIDs to portable refs on export

App files now have useWorkflow UUIDs transformed to portable refs when
exporting to git for cross-environment portability."
```

---

## Task 5: Cleanup app_dependencies.py

**Files:**
- Modify: `api/src/services/app_dependencies.py`
- Test: `api/tests/unit/services/test_app_dependencies.py` (update existing)

**Step 1: Update app_dependencies.py**

Modify `api/src/services/app_dependencies.py`:

```python
"""
App file dependency parser.

Parses app source code to extract references to workflows.
Used by:
- App code file CRUD operations (app_code_files router)
- GitHub sync app file indexer

Patterns detected:
- useWorkflow('uuid')
- useWorkflow("uuid")
"""

import re
from uuid import UUID

# Regex pattern for extracting workflow dependencies
# Captures UUIDs from hook calls like useWorkflow('550e8400-e29b-41d4-a716-446655440000')
DEPENDENCY_PATTERNS: dict[str, re.Pattern[str]] = {
    "workflow": re.compile(r'useWorkflow\([\'"]([a-f0-9-]{36})[\'"]\)', re.IGNORECASE),
}


def parse_dependencies(source: str) -> list[tuple[str, UUID]]:
    """
    Parse source code and extract workflow dependencies.

    Scans for patterns like useWorkflow('uuid').
    Returns a list of (dependency_type, dependency_id) tuples.

    Args:
        source: The source code to parse

    Returns:
        List of (type, uuid) tuples. Types are: "workflow"
    """
    dependencies: list[tuple[str, UUID]] = []
    seen: set[tuple[str, str]] = set()  # Deduplicate within same file

    for dep_type, pattern in DEPENDENCY_PATTERNS.items():
        for match in pattern.finditer(source):
            uuid_str = match.group(1)
            key = (dep_type, uuid_str)

            if key not in seen:
                seen.add(key)
                try:
                    dependencies.append((dep_type, UUID(uuid_str)))
                except ValueError:
                    # Invalid UUID format, skip
                    pass

    return dependencies
```

**Step 2: Update or verify existing tests**

Check `api/tests/unit/services/test_app_dependencies.py` exists and update if needed:

```python
"""
Unit tests for app dependency parsing.
"""

import pytest
from uuid import UUID

from src.services.app_dependencies import parse_dependencies


class TestParseDependencies:
    """Tests for parse_dependencies function."""

    def test_parses_single_use_workflow(self):
        """Single useWorkflow call is parsed."""
        source = "const w = useWorkflow('550e8400-e29b-41d4-a716-446655440000');"

        deps = parse_dependencies(source)

        assert len(deps) == 1
        assert deps[0][0] == "workflow"
        assert deps[0][1] == UUID("550e8400-e29b-41d4-a716-446655440000")

    def test_parses_double_quoted_uuid(self):
        """Double-quoted UUIDs are also parsed."""
        source = 'const w = useWorkflow("550e8400-e29b-41d4-a716-446655440000");'

        deps = parse_dependencies(source)

        assert len(deps) == 1

    def test_parses_multiple_workflows(self):
        """Multiple useWorkflow calls are all parsed."""
        source = """
const w1 = useWorkflow('11111111-1111-1111-1111-111111111111');
const w2 = useWorkflow('22222222-2222-2222-2222-222222222222');
"""
        deps = parse_dependencies(source)

        assert len(deps) == 2

    def test_deduplicates_same_uuid(self):
        """Same UUID used multiple times is deduplicated."""
        source = """
const w1 = useWorkflow('550e8400-e29b-41d4-a716-446655440000');
const w2 = useWorkflow('550e8400-e29b-41d4-a716-446655440000');
"""
        deps = parse_dependencies(source)

        assert len(deps) == 1

    def test_ignores_non_uuid_strings(self):
        """Non-UUID strings in useWorkflow are ignored."""
        source = "const w = useWorkflow('not-a-valid-uuid');"

        deps = parse_dependencies(source)

        assert len(deps) == 0

    def test_ignores_portable_refs(self):
        """Portable refs (not UUIDs) are ignored by dependency parser."""
        source = "const w = useWorkflow('workflows/test.py::my_func');"

        deps = parse_dependencies(source)

        assert len(deps) == 0

    def test_empty_source(self):
        """Empty source returns empty list."""
        deps = parse_dependencies("")

        assert len(deps) == 0

    def test_no_use_workflow_calls(self):
        """Source without useWorkflow returns empty list."""
        source = "const x = 1; const y = 2;"

        deps = parse_dependencies(source)

        assert len(deps) == 0
```

**Step 3: Run tests**

Run: `./test.sh api/tests/unit/services/test_app_dependencies.py -v`
Expected: All tests PASS

**Step 4: Run type checking**

Run: `cd api && pyright src/services/app_dependencies.py`
Expected: 0 errors

**Step 5: Commit**

```bash
git add api/src/services/app_dependencies.py api/tests/unit/services/test_app_dependencies.py
git commit -m "refactor(app-dependencies): remove unused useForm and useDataProvider patterns

Only useWorkflow is used in App Builder apps. Removed speculative patterns
that were never implemented."
```

---

## Task 6: Run Full Test Suite and Final Verification

**Step 1: Run all unit tests**

Run: `./test.sh api/tests/unit/ -v`
Expected: All tests PASS

**Step 2: Run all integration tests**

Run: `./test.sh api/tests/integration/ -v`
Expected: All tests PASS

**Step 3: Run type checking on all modified files**

Run:
```bash
cd api && pyright \
  src/services/file_storage/ref_translation.py \
  src/services/file_storage/diagnostics.py \
  src/services/file_storage/indexers/app.py \
  src/services/github_sync_virtual_files.py \
  src/services/app_dependencies.py
```
Expected: 0 errors

**Step 4: Run linting**

Run: `cd api && ruff check .`
Expected: No errors

**Step 5: Final commit (if any fixups needed)**

```bash
git add -A
git commit -m "chore: final cleanup for app portable refs feature"
```

---

## Summary

This plan implements portable workflow references for App Builder files:

1. **Task 1**: Add `transform_app_source_uuids_to_refs` and `transform_app_source_refs_to_uuids` to ref_translation.py
2. **Task 2**: Add `scan_for_unresolved_refs` and `clear_unresolved_refs_notification` to DiagnosticsService
3. **Task 3**: Update app indexer to transform refs → UUIDs on import
4. **Task 4**: Update virtual files provider to transform UUIDs → refs on export
5. **Task 5**: Clean up unused useForm/useDataProvider patterns
6. **Task 6**: Full test suite verification

Total: ~6 commits, TDD approach with tests before implementation.
