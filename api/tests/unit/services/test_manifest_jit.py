"""Tests for JIT manifest generation before git commit."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path


@pytest.mark.asyncio
async def test_desktop_commit_regenerates_manifest_before_staging():
    """desktop_commit() should regenerate manifest into working tree before git add."""
    from src.services.github_sync import GitHubSyncService

    # Track call order
    call_order = []

    mock_db = AsyncMock()
    service = GitHubSyncService.__new__(GitHubSyncService)
    service.db = mock_db
    service.branch = "main"

    mock_work_dir = MagicMock(spec=Path)
    mock_repo = MagicMock()
    mock_repo.head.is_valid.return_value = True
    mock_repo.index.diff.return_value = [MagicMock()]  # Has changes
    mock_repo.untracked_files = []
    mock_repo.index.commit.return_value = MagicMock(hexsha="abc12345")

    # Set repo_manager before patching (bypass __init__)
    mock_rm = MagicMock()
    mock_rm.checkout.return_value.__aenter__ = AsyncMock(return_value=mock_work_dir)
    mock_rm.checkout.return_value.__aexit__ = AsyncMock(return_value=False)
    service.repo_manager = mock_rm

    with patch.object(service, '_open_or_init', return_value=mock_repo), \
         patch.object(service, '_regenerate_manifest_to_dir') as mock_regen, \
         patch.object(service, '_run_preflight') as mock_preflight:

        # Track call order
        async def regen_side_effect(db, work_dir):
            call_order.append("regenerate_manifest")
        mock_regen.side_effect = regen_side_effect

        def add_side_effect(*args, **kwargs):
            call_order.append("git_add")
        mock_repo.git.add.side_effect = add_side_effect

        mock_preflight.return_value = MagicMock(valid=True)

        result = await service.desktop_commit("test commit")

        # Manifest must be regenerated BEFORE git add
        assert call_order == ["regenerate_manifest", "git_add"]
        mock_regen.assert_called_once_with(mock_db, mock_work_dir)
