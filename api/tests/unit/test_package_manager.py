"""
Unit tests for WorkspacePackageManager
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.package_manager import PackageInfo, PackageNotFoundError, WorkspacePackageManager


@pytest.fixture
def workspace_path(tmp_path):
    """Create a temporary workspace directory"""
    return tmp_path / "workspace"


@pytest.fixture
def pkg_manager(workspace_path):
    """Create a WorkspacePackageManager instance"""
    workspace_path.mkdir(parents=True, exist_ok=True)
    return WorkspacePackageManager(workspace_path)


class TestWorkspacePackageManager:
    """Tests for WorkspacePackageManager"""

    def test_init(self, workspace_path):
        """Test package manager initialization"""
        workspace_path.mkdir(parents=True, exist_ok=True)
        pkg_manager = WorkspacePackageManager(workspace_path)

        assert pkg_manager.workspace_path == workspace_path
        assert pkg_manager.requirements_file == workspace_path / "requirements.txt"

    @pytest.mark.asyncio
    async def test_get_package_info_success(self, pkg_manager):
        """Test getting package info from PyPI"""
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={
            "info": {
                "name": "requests",
                "version": "2.31.0",
                "summary": "Python HTTP for Humans."
            }
        })

        with patch('src.services.package_manager.aiohttp.ClientSession') as mock_session_class:
            mock_session = MagicMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)
            mock_session.get = MagicMock()
            mock_session.get.return_value.__aenter__ = AsyncMock(return_value=mock_response)
            mock_session.get.return_value.__aexit__ = AsyncMock(return_value=None)
            mock_session_class.return_value = mock_session

            info = await pkg_manager.get_package_info("requests")

            assert isinstance(info, PackageInfo)
            assert info.name == "requests"
            assert info.version == "2.31.0"
            assert info.summary == "Python HTTP for Humans."

    @pytest.mark.asyncio
    async def test_get_package_info_not_found(self, pkg_manager):
        """Test getting package info for non-existent package"""
        mock_response = MagicMock()
        mock_response.status = 404

        with patch('src.services.package_manager.aiohttp.ClientSession') as mock_session_class:
            mock_session = MagicMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)
            mock_session.get = MagicMock()
            mock_session.get.return_value.__aenter__ = AsyncMock(return_value=mock_response)
            mock_session.get.return_value.__aexit__ = AsyncMock(return_value=None)
            mock_session_class.return_value = mock_session

            with pytest.raises(PackageNotFoundError, match="Package 'nonexistent' not found on PyPI"):
                await pkg_manager.get_package_info("nonexistent")

    @pytest.mark.asyncio
    async def test_list_installed_packages(self, pkg_manager):
        """Test listing installed packages"""
        mock_process = AsyncMock()
        mock_process.returncode = 0
        mock_process.communicate = AsyncMock(return_value=(
            json.dumps([
                {"name": "requests", "version": "2.31.0"},
                {"name": "pandas", "version": "2.0.3"}
            ]).encode(),
            b""
        ))

        with patch('asyncio.create_subprocess_exec', return_value=mock_process):
            packages = await pkg_manager.list_installed_packages()

            assert len(packages) == 2
            assert packages[0]["name"] == "requests"
            assert packages[0]["version"] == "2.31.0"
            assert packages[1]["name"] == "pandas"
            assert packages[1]["version"] == "2.0.3"

    @pytest.mark.asyncio
    async def test_append_to_requirements_new_file(self, pkg_manager):
        """Test appending to requirements.txt when file doesn't exist"""
        await pkg_manager._append_to_requirements("requests", "2.31.0")

        assert pkg_manager.requirements_file.exists()
        content = pkg_manager.requirements_file.read_text()
        assert content.strip() == "requests==2.31.0"

    @pytest.mark.asyncio
    async def test_append_to_requirements_existing_file(self, pkg_manager):
        """Test appending to existing requirements.txt"""
        # Create existing requirements.txt
        pkg_manager.requirements_file.parent.mkdir(parents=True, exist_ok=True)
        pkg_manager.requirements_file.write_text("pandas==2.0.3\n")

        await pkg_manager._append_to_requirements("requests", "2.31.0")

        content = pkg_manager.requirements_file.read_text()
        lines = content.strip().split("\n")
        assert len(lines) == 2
        assert "pandas==2.0.3" in lines
        assert "requests==2.31.0" in lines

    @pytest.mark.asyncio
    async def test_append_to_requirements_update_existing(self, pkg_manager):
        """Test updating existing package in requirements.txt"""
        # Create existing requirements.txt with old version
        pkg_manager.requirements_file.parent.mkdir(parents=True, exist_ok=True)
        pkg_manager.requirements_file.write_text("requests==2.30.0\npandas==2.0.3\n")

        await pkg_manager._append_to_requirements("requests", "2.31.0")

        content = pkg_manager.requirements_file.read_text()
        lines = content.strip().split("\n")
        assert len(lines) == 2
        assert "requests==2.31.0" in lines
        assert "pandas==2.0.3" in lines
        # Old version should not be present
        assert "requests==2.30.0" not in lines
