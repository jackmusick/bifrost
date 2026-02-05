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
            result = await provider._get_app_files(workflow_map={workflow_id: portable_ref})

            # Find the tsx file in results
            tsx_file = next(
                (f for f in result.files if f.path.endswith(".tsx")),
                None
            )
            assert tsx_file is not None

            content = tsx_file.content.decode("utf-8")
            assert portable_ref in content
            assert workflow_id not in content
