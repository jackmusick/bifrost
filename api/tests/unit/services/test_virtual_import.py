"""
Unit tests for the virtual import hook.

Tests the MetaPathFinder implementation that loads modules from Redis cache.
"""

import sys
from unittest.mock import MagicMock, patch

import pytest


class TestVirtualModuleFinder:
    """Tests for VirtualModuleFinder class."""

    @pytest.fixture(autouse=True)
    def cleanup(self):
        """Clean up after each test."""
        yield
        # Remove any virtual import hooks from sys.meta_path
        sys.meta_path = [
            finder
            for finder in sys.meta_path
            if not finder.__class__.__name__ == "VirtualModuleFinder"
        ]
        # Reset global finder
        import src.services.execution.virtual_import as module

        module._finder = None

    def test_module_name_to_paths_simple_module(self):
        """Test path conversion for simple module names."""
        from src.services.execution.virtual_import import VirtualModuleFinder

        finder = VirtualModuleFinder()
        paths = finder._module_name_to_paths("shared")

        assert paths == [
            ("shared.py", False),
            ("shared/__init__.py", True),
        ]

    def test_module_name_to_paths_nested_module(self):
        """Test path conversion for nested module names."""
        from src.services.execution.virtual_import import VirtualModuleFinder

        finder = VirtualModuleFinder()
        paths = finder._module_name_to_paths("shared.halopsa")

        assert paths == [
            ("shared/halopsa.py", False),
            ("shared/halopsa/__init__.py", True),
        ]

    def test_module_name_to_paths_deeply_nested(self):
        """Test path conversion for deeply nested modules."""
        from src.services.execution.virtual_import import VirtualModuleFinder

        finder = VirtualModuleFinder()
        paths = finder._module_name_to_paths("modules.helpers.utils.string")

        assert paths == [
            ("modules/helpers/utils/string.py", False),
            ("modules/helpers/utils/string/__init__.py", True),
        ]

    def test_find_spec_module_not_in_cache(self):
        """Test find_spec returns None when module is not in cache."""
        from src.services.execution.virtual_import import VirtualModuleFinder

        finder = VirtualModuleFinder()

        with patch(
            "src.services.execution.virtual_import.get_module_index_sync",
            return_value=set(),
        ):
            spec = finder.find_spec("nonexistent.module")

            assert spec is None

    def test_find_spec_module_in_cache(self):
        """Test find_spec returns spec when module is in cache."""
        from src.services.execution.virtual_import import VirtualModuleFinder

        finder = VirtualModuleFinder()

        with patch(
            "src.services.execution.virtual_import.get_module_index_sync",
            return_value={"shared/halopsa.py"},
        ), patch(
            "src.services.execution.virtual_import.get_module_sync",
            return_value={"content": "x = 1", "path": "shared/halopsa.py", "hash": "abc"},
        ):
            spec = finder.find_spec("shared.halopsa")

            assert spec is not None
            assert spec.name == "shared.halopsa"
            assert spec.loader is not None
            assert spec.origin == "shared/halopsa.py"
            assert not spec.submodule_search_locations  # Not a package

    def test_find_spec_package_in_cache(self):
        """Test find_spec returns package spec for __init__.py."""
        from src.services.execution.virtual_import import VirtualModuleFinder

        finder = VirtualModuleFinder()

        with patch(
            "src.services.execution.virtual_import.get_module_index_sync",
            return_value={"shared/__init__.py"},
        ), patch(
            "src.services.execution.virtual_import.get_module_sync",
            return_value={"content": "# package", "path": "shared/__init__.py", "hash": "abc"},
        ):
            spec = finder.find_spec("shared")

            assert spec is not None
            assert spec.name == "shared"
            assert spec.submodule_search_locations is not None  # Is a package

    def test_find_spec_prefers_module_over_package(self):
        """Test that .py file is tried before __init__.py."""
        from src.services.execution.virtual_import import VirtualModuleFinder

        finder = VirtualModuleFinder()

        # Both exist, but .py is checked first
        with patch(
            "src.services.execution.virtual_import.get_module_index_sync",
            return_value={"shared.py", "shared/__init__.py"},
        ), patch(
            "src.services.execution.virtual_import.get_module_sync",
            return_value={"content": "x = 1", "path": "shared.py", "hash": "abc"},
        ):
            spec = finder.find_spec("shared")

            assert spec is not None
            assert spec.origin == "shared.py"

    def test_find_spec_module_in_index_but_not_in_cache(self):
        """Test find_spec when module is in index but missing from cache."""
        from src.services.execution.virtual_import import VirtualModuleFinder

        finder = VirtualModuleFinder()

        with patch(
            "src.services.execution.virtual_import.get_module_index_sync",
            return_value={"shared/test.py"},
        ), patch(
            "src.services.execution.virtual_import.get_module_sync",
            return_value=None,  # Cache miss
        ):
            spec = finder.find_spec("shared.test")

            # Should return None and let filesystem finder try
            assert spec is None

    def test_invalidate_index(self):
        """Test that invalidate_index clears the cached index."""
        from src.services.execution.virtual_import import VirtualModuleFinder

        finder = VirtualModuleFinder()

        # Populate index
        with patch(
            "src.services.execution.virtual_import.get_module_index_sync",
            return_value={"shared/a.py"},
        ):
            finder._get_module_index()

        assert finder._module_index is not None

        # Invalidate
        finder.invalidate_index()

        assert finder._module_index is None

    def test_lazy_index_loading(self):
        """Test that index is only loaded on first access."""
        from src.services.execution.virtual_import import VirtualModuleFinder

        finder = VirtualModuleFinder()

        assert finder._module_index is None

        mock_get_index = MagicMock(return_value={"test.py"})
        with patch(
            "src.services.execution.virtual_import.get_module_index_sync",
            mock_get_index,
        ):
            # First access - should call get_module_index_sync
            finder._get_module_index()
            assert mock_get_index.call_count == 1

            # Second access - should use cached value
            finder._get_module_index()
            assert mock_get_index.call_count == 1


class TestVirtualModuleLoader:
    """Tests for VirtualModuleLoader class."""

    def test_create_module_returns_none(self):
        """Test create_module returns None for default semantics."""
        from importlib.machinery import ModuleSpec

        from src.services.execution.virtual_import import VirtualModuleLoader

        loader = VirtualModuleLoader("test.py", "x = 1", is_package=False)
        spec = ModuleSpec("test", loader)

        result = loader.create_module(spec)

        assert result is None

    def test_exec_module_sets_file_attribute(self):
        """Test exec_module sets __file__ to virtual path."""
        from types import ModuleType

        from src.services.execution.virtual_import import VirtualModuleLoader

        loader = VirtualModuleLoader("shared/test.py", "x = 1", is_package=False)
        module = ModuleType("shared.test")

        loader.exec_module(module)

        assert module.__file__ == "shared/test.py"
        assert module.__loader__ is loader

    def test_exec_module_sets_path_for_package(self):
        """Test exec_module sets __path__ for packages."""
        from types import ModuleType

        from src.services.execution.virtual_import import VirtualModuleLoader

        loader = VirtualModuleLoader("shared/__init__.py", "# package", is_package=True)
        module = ModuleType("shared")

        loader.exec_module(module)

        assert hasattr(module, "__path__")
        assert module.__path__ == ["shared"]

    def test_exec_module_executes_code(self):
        """Test exec_module executes the Python code."""
        from types import ModuleType

        from src.services.execution.virtual_import import VirtualModuleLoader

        loader = VirtualModuleLoader("test.py", "x = 42\ndef hello(): return 'world'")
        module = ModuleType("test")

        loader.exec_module(module)

        assert module.x == 42
        assert module.hello() == "world"

    def test_exec_module_raises_on_syntax_error(self):
        """Test exec_module raises SyntaxError for invalid code."""
        from types import ModuleType

        from src.services.execution.virtual_import import VirtualModuleLoader

        loader = VirtualModuleLoader("test.py", "def broken(")
        module = ModuleType("test")

        with pytest.raises(SyntaxError):
            loader.exec_module(module)

    def test_exec_module_raises_on_runtime_error(self):
        """Test exec_module propagates runtime errors."""
        from types import ModuleType

        from src.services.execution.virtual_import import VirtualModuleLoader

        loader = VirtualModuleLoader("test.py", "raise ValueError('test error')")
        module = ModuleType("test")

        with pytest.raises(ValueError, match="test error"):
            loader.exec_module(module)


class TestInstallRemoveHook:
    """Tests for hook installation and removal functions."""

    @pytest.fixture(autouse=True)
    def cleanup(self):
        """Clean up after each test."""
        yield
        # Remove any virtual import hooks
        sys.meta_path = [
            finder
            for finder in sys.meta_path
            if not finder.__class__.__name__ == "VirtualModuleFinder"
        ]
        # Reset global finder
        import src.services.execution.virtual_import as module

        module._finder = None

    def test_install_virtual_import_hook(self):
        """Test installing the virtual import hook."""
        from src.services.execution.virtual_import import (
            VirtualModuleFinder,
            install_virtual_import_hook,
        )

        initial_count = len(sys.meta_path)

        finder = install_virtual_import_hook()

        assert isinstance(finder, VirtualModuleFinder)
        assert len(sys.meta_path) == initial_count + 1
        assert sys.meta_path[0] is finder

    def test_install_virtual_import_hook_idempotent(self):
        """Test that installing twice returns same finder."""
        from src.services.execution.virtual_import import install_virtual_import_hook

        finder1 = install_virtual_import_hook()
        initial_count = len(sys.meta_path)

        finder2 = install_virtual_import_hook()

        assert finder1 is finder2
        assert len(sys.meta_path) == initial_count  # Not added again

    def test_remove_virtual_import_hook(self):
        """Test removing the virtual import hook."""
        from src.services.execution.virtual_import import (
            install_virtual_import_hook,
            remove_virtual_import_hook,
        )

        install_virtual_import_hook()
        initial_count = len(sys.meta_path)

        remove_virtual_import_hook()

        assert len(sys.meta_path) == initial_count - 1
        assert not any(
            finder.__class__.__name__ == "VirtualModuleFinder" for finder in sys.meta_path
        )

    def test_remove_virtual_import_hook_noop_when_not_installed(self):
        """Test removing when hook is not installed."""
        from src.services.execution.virtual_import import remove_virtual_import_hook

        initial_count = len(sys.meta_path)

        # Should not raise
        remove_virtual_import_hook()

        assert len(sys.meta_path) == initial_count


class TestInvalidateModuleIndex:
    """Tests for invalidate_module_index function."""

    @pytest.fixture(autouse=True)
    def cleanup(self):
        """Clean up after each test."""
        yield
        sys.meta_path = [
            finder
            for finder in sys.meta_path
            if not finder.__class__.__name__ == "VirtualModuleFinder"
        ]
        import src.services.execution.virtual_import as module

        module._finder = None

    def test_invalidate_module_index(self):
        """Test invalidating the module index."""
        from src.services.execution.virtual_import import (
            install_virtual_import_hook,
            invalidate_module_index,
        )

        finder = install_virtual_import_hook()

        # Populate index
        with patch(
            "src.services.execution.virtual_import.get_module_index_sync",
            return_value={"test.py"},
        ):
            finder._get_module_index()

        assert finder._module_index is not None

        invalidate_module_index()

        assert finder._module_index is None

    def test_invalidate_module_index_noop_when_not_installed(self):
        """Test invalidating when hook is not installed."""
        from src.services.execution.virtual_import import invalidate_module_index

        # Should not raise
        invalidate_module_index()


class TestGetVirtualFinder:
    """Tests for get_virtual_finder function."""

    @pytest.fixture(autouse=True)
    def cleanup(self):
        """Clean up after each test."""
        yield
        sys.meta_path = [
            finder
            for finder in sys.meta_path
            if not finder.__class__.__name__ == "VirtualModuleFinder"
        ]
        import src.services.execution.virtual_import as module

        module._finder = None

    def test_get_virtual_finder_when_installed(self):
        """Test getting finder when installed."""
        from src.services.execution.virtual_import import (
            get_virtual_finder,
            install_virtual_import_hook,
        )

        installed = install_virtual_import_hook()
        result = get_virtual_finder()

        assert result is installed

    def test_get_virtual_finder_when_not_installed(self):
        """Test getting finder when not installed."""
        from src.services.execution.virtual_import import get_virtual_finder

        result = get_virtual_finder()

        assert result is None


class TestIntegration:
    """Integration tests for the virtual import system."""

    @pytest.fixture(autouse=True)
    def cleanup(self):
        """Clean up after each test."""
        yield
        # Remove virtual import hooks
        sys.meta_path = [
            finder
            for finder in sys.meta_path
            if not finder.__class__.__name__ == "VirtualModuleFinder"
        ]
        # Remove test modules from sys.modules
        to_remove = [k for k in sys.modules if k.startswith("virtual_test_")]
        for k in to_remove:
            del sys.modules[k]
        # Reset global finder
        import src.services.execution.virtual_import as module

        module._finder = None

    def test_import_module_from_cache(self):
        """Test actually importing a module from cache."""
        from src.services.execution.virtual_import import (
            install_virtual_import_hook,
            invalidate_module_index,
        )

        install_virtual_import_hook()

        with patch(
            "src.services.execution.virtual_import.get_module_index_sync",
            return_value={"virtual_test_module.py"},
        ), patch(
            "src.services.execution.virtual_import.get_module_sync",
            return_value={
                "content": "MAGIC_VALUE = 12345\ndef get_magic(): return MAGIC_VALUE",
                "path": "virtual_test_module.py",
                "hash": "abc",
            },
        ):
            # Invalidate any cached index so the patch takes effect
            invalidate_module_index()

            import virtual_test_module  # type: ignore[import-not-found]

            assert virtual_test_module.MAGIC_VALUE == 12345
            assert virtual_test_module.get_magic() == 12345
            assert virtual_test_module.__file__ == "virtual_test_module.py"

    def test_import_nested_module_from_cache(self):
        """Test importing a nested module from cache."""
        from src.services.execution.virtual_import import (
            install_virtual_import_hook,
            invalidate_module_index,
        )

        install_virtual_import_hook()

        # First import the package
        with patch(
            "src.services.execution.virtual_import.get_module_index_sync",
            return_value={"virtual_test_pkg/__init__.py", "virtual_test_pkg/submod.py"},
        ), patch(
            "src.services.execution.virtual_import.get_module_sync",
            side_effect=lambda path: {
                "virtual_test_pkg/__init__.py": {
                    "content": "PKG_VALUE = 'package'",
                    "path": "virtual_test_pkg/__init__.py",
                    "hash": "abc",
                },
                "virtual_test_pkg/submod.py": {
                    "content": "SUB_VALUE = 'submodule'",
                    "path": "virtual_test_pkg/submod.py",
                    "hash": "def",
                },
            }.get(path),
        ):
            # Invalidate any cached index so the patch takes effect
            invalidate_module_index()

            import virtual_test_pkg  # type: ignore[import-not-found]
            from virtual_test_pkg import submod  # type: ignore[import-not-found]

            assert virtual_test_pkg.PKG_VALUE == "package"
            assert submod.SUB_VALUE == "submodule"
