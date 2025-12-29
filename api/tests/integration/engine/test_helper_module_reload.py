"""Test module import behavior in subprocess workers.

Since workflow executions run in fresh subprocess workers, sys.modules starts
empty and no module cache clearing is needed. These tests verify the basic
import behavior works correctly.
"""

import sys
from pathlib import Path
from unittest.mock import patch


class TestModuleImport:
    """Test module import functionality."""

    def test_workflow_imports_helper_module(self, tmp_path: Path) -> None:
        """Verify a workflow can import helper modules from workspace."""
        # Create helper module
        helper_dir = tmp_path / "utils"
        helper_dir.mkdir()
        (helper_dir / "__init__.py").write_text("")
        helper_file = helper_dir / "helpers.py"
        helper_file.write_text("VALUE = 'test_value'")

        # Create workflow that imports helper
        workflow_file = tmp_path / "my_workflow.py"
        workflow_file.write_text(
            """
from utils.helpers import VALUE

def get_value():
    return VALUE
"""
        )

        # Add tmp_path to sys.path and mock workspace paths
        sys.path.insert(0, str(tmp_path))
        try:
            from src.services.execution.module_loader import import_module, get_workspace_paths

            original_paths = get_workspace_paths()
            with patch(
                "src.services.execution.module_loader.get_workspace_paths",
                return_value=[tmp_path] + original_paths,
            ):
                # Import and verify
                module = import_module(workflow_file)
                assert module.get_value() == "test_value"
        finally:
            sys.path.remove(str(tmp_path))
            # Cleanup sys.modules
            for mod in list(sys.modules.keys()):
                if "my_workflow" in mod or mod.startswith("utils"):
                    del sys.modules[mod]

    def test_nested_imports_work(self, tmp_path: Path) -> None:
        """Verify nested imports (A imports B imports C) work correctly."""
        # Create nested helper structure
        lib_dir = tmp_path / "lib"
        lib_dir.mkdir()
        (lib_dir / "__init__.py").write_text("")

        # Create base helper (deepest level)
        (lib_dir / "base.py").write_text("BASE_VALUE = 100")

        # Create middle helper that imports base
        (lib_dir / "middle.py").write_text(
            """
from lib.base import BASE_VALUE

def get_doubled():
    return BASE_VALUE * 2
"""
        )

        # Create workflow that imports middle
        workflow_file = tmp_path / "nested_workflow.py"
        workflow_file.write_text(
            """
from lib.middle import get_doubled

def get_result():
    return get_doubled()
"""
        )

        sys.path.insert(0, str(tmp_path))
        try:
            from src.services.execution.module_loader import import_module, get_workspace_paths

            original_paths = get_workspace_paths()
            with patch(
                "src.services.execution.module_loader.get_workspace_paths",
                return_value=[tmp_path] + original_paths,
            ):
                module = import_module(workflow_file)
                assert module.get_result() == 200  # 100 * 2
        finally:
            sys.path.remove(str(tmp_path))
            for mod in list(sys.modules.keys()):
                if "nested_workflow" in mod or mod.startswith("lib"):
                    del sys.modules[mod]

    def test_packages_directory_imports_work(self, tmp_path: Path) -> None:
        """Verify .packages directory modules can be imported."""
        # Create a fake .packages module
        packages_dir = tmp_path / ".packages"
        packages_dir.mkdir()
        (packages_dir / "__init__.py").write_text("")
        fake_package = packages_dir / "fake_package.py"
        fake_package.write_text("PACKAGE_VALUE = 'from_package'")

        # Create workflow that imports from .packages
        workflow_file = tmp_path / "pkg_workflow.py"
        workflow_file.write_text(
            """
from fake_package import PACKAGE_VALUE

def get_value():
    return PACKAGE_VALUE
"""
        )

        sys.path.insert(0, str(tmp_path))
        sys.path.insert(0, str(packages_dir))
        try:
            from src.services.execution.module_loader import import_module, get_workspace_paths

            original_paths = get_workspace_paths()
            with patch(
                "src.services.execution.module_loader.get_workspace_paths",
                return_value=[tmp_path] + original_paths,
            ):
                module = import_module(workflow_file)
                assert module.get_value() == "from_package"
        finally:
            if str(tmp_path) in sys.path:
                sys.path.remove(str(tmp_path))
            if str(packages_dir) in sys.path:
                sys.path.remove(str(packages_dir))
            for mod in list(sys.modules.keys()):
                if "pkg_workflow" in mod or "fake_package" in mod:
                    del sys.modules[mod]
