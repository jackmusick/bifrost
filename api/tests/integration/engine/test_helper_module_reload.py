"""Test that helper module changes are reflected without restart."""

import sys
from pathlib import Path
from unittest.mock import patch


class TestHelperModuleReload:
    """Test helper module hot-reload functionality."""

    def test_helper_changes_reflected_after_reload(self, tmp_path: Path) -> None:
        """Verify editing a helper module affects workflow execution.

        This tests the fix for the issue where changes to helper modules
        (non-workflow Python files) were not picked up until restart.
        """
        # 1. Create helper module with initial value
        helper_dir = tmp_path / "utils"
        helper_dir.mkdir()
        (helper_dir / "__init__.py").write_text("")
        helper_file = helper_dir / "helpers.py"
        helper_file.write_text("VALUE = 'original'")

        # 2. Create workflow that imports helper
        workflow_file = tmp_path / "my_workflow.py"
        workflow_file.write_text(
            """
from utils.helpers import VALUE

def get_value():
    return VALUE
"""
        )

        # 3. Add tmp_path to sys.path and mock workspace paths to include tmp_path
        sys.path.insert(0, str(tmp_path))
        try:
            from src.services.execution.module_loader import reload_single_module, get_workspace_paths

            # Mock get_workspace_paths to include our tmp_path
            original_paths = get_workspace_paths()
            with patch(
                "src.services.execution.module_loader.get_workspace_paths",
                return_value=[str(tmp_path)] + original_paths,
            ):
                # Import workflow, check initial value
                import my_workflow  # type: ignore[import-not-found]

                assert my_workflow.get_value() == "original"

                # 4. Modify helper
                helper_file.write_text("VALUE = 'modified'")

                # 5. Reload workflow (should also reload helper)
                reload_single_module(workflow_file)

                # 6. Re-import and verify new value
                import my_workflow as reloaded  # type: ignore[import-not-found]

                assert reloaded.get_value() == "modified"
        finally:
            sys.path.remove(str(tmp_path))
            # Cleanup sys.modules
            for mod in list(sys.modules.keys()):
                if "my_workflow" in mod or mod.startswith("utils"):
                    del sys.modules[mod]

    def test_nested_helper_changes_reflected(self, tmp_path: Path) -> None:
        """Verify changes to nested helper modules (A imports B imports C)."""
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
            from src.services.execution.module_loader import reload_single_module, get_workspace_paths

            # Mock get_workspace_paths to include our tmp_path
            original_paths = get_workspace_paths()
            with patch(
                "src.services.execution.module_loader.get_workspace_paths",
                return_value=[str(tmp_path)] + original_paths,
            ):
                import nested_workflow  # type: ignore[import-not-found]

                assert nested_workflow.get_result() == 200  # 100 * 2

                # Modify the base helper
                (lib_dir / "base.py").write_text("BASE_VALUE = 500")

                # Reload workflow (should also reload helper chain)
                reload_single_module(workflow_file)

                # Re-import and verify chain reloaded
                import nested_workflow as reloaded  # type: ignore[import-not-found]

                assert reloaded.get_result() == 1000  # 500 * 2
        finally:
            sys.path.remove(str(tmp_path))
            for mod in list(sys.modules.keys()):
                if "nested_workflow" in mod or mod.startswith("lib."):
                    del sys.modules[mod]

    def test_packages_directory_not_cleared(self, tmp_path: Path) -> None:
        """Verify .packages directory modules are NOT cleared during reload.

        User-installed third-party packages in .packages should be preserved.
        """
        # Create a fake .packages module
        packages_dir = tmp_path / ".packages"
        packages_dir.mkdir()
        (packages_dir / "__init__.py").write_text("")
        fake_package = packages_dir / "fake_package.py"
        fake_package.write_text("PACKAGE_VALUE = 'should_not_reload'")

        # Create workflow
        workflow_file = tmp_path / "pkg_workflow.py"
        workflow_file.write_text(
            """
def get_value():
    return 'workflow_value'
"""
        )

        sys.path.insert(0, str(tmp_path))
        sys.path.insert(0, str(packages_dir))
        try:
            from src.services.execution.module_loader import reload_single_module, get_workspace_paths

            # Mock get_workspace_paths to include our tmp_path
            original_paths = get_workspace_paths()
            with patch(
                "src.services.execution.module_loader.get_workspace_paths",
                return_value=[str(tmp_path)] + original_paths,
            ):
                # Import fake package
                import fake_package  # type: ignore[import-not-found]

                original_module = sys.modules.get("fake_package")
                assert original_module is not None

                # Reload workflow
                reload_single_module(workflow_file)

                # Verify .packages module was NOT cleared
                # (it should still be the same object, not re-imported)
                assert sys.modules.get("fake_package") is original_module
        finally:
            if str(tmp_path) in sys.path:
                sys.path.remove(str(tmp_path))
            if str(packages_dir) in sys.path:
                sys.path.remove(str(packages_dir))
            for mod in list(sys.modules.keys()):
                if "pkg_workflow" in mod or "fake_package" in mod:
                    del sys.modules[mod]
