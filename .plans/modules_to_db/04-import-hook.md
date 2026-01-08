# Phase 4: Virtual Import Hook

## Overview

Implement a `MetaPathFinder` that intercepts Python imports and loads modules from Redis cache instead of the filesystem.

## Pattern Reference

Follow the existing pattern in `api/src/services/execution/import_restrictor.py`:

```python
class WorkspaceImportRestrictor(MetaPathFinder):
    def find_spec(self, fullname, path, target):
        # Returns None to allow import to proceed
        # Raises ImportError to block
```

## Implementation

**File:** `api/src/services/execution/virtual_import.py`

```python
"""
Virtual Module Import System

Loads Python modules from Redis cache instead of filesystem.
Follows the MetaPathFinder pattern from import_restrictor.py.

Usage:
    from src.services.execution.virtual_import import install_virtual_import_hook
    install_virtual_import_hook()

    # Now workspace imports are loaded from Redis
    from shared import halopsa  # Loaded from Redis, not filesystem
"""

import logging
import sys
from importlib.abc import MetaPathFinder, Loader
from importlib.machinery import ModuleSpec
from pathlib import Path
from types import ModuleType
from typing import Any

from src.core.module_cache_sync import get_module_sync, get_module_index_sync

logger = logging.getLogger(__name__)

# Virtual workspace path for __file__ attributes (tracebacks)
VIRTUAL_WORKSPACE = Path("/tmp/bifrost/workspace")


class VirtualModuleLoader(Loader):
    """Loads module content from cached source code."""

    def __init__(self, path: str, content: str, is_package: bool = False):
        self.path = path
        self.content = content
        self.is_package = is_package

    def create_module(self, spec: ModuleSpec) -> ModuleType | None:
        """Return None to use default module creation semantics."""
        return None

    def exec_module(self, module: ModuleType) -> None:
        """Execute the module code in the module's namespace."""
        # Set virtual __file__ for tracebacks
        virtual_file = VIRTUAL_WORKSPACE / self.path
        module.__file__ = str(virtual_file)
        module.__loader__ = self

        if self.is_package:
            # Packages need __path__ for submodule imports
            module.__path__ = [str(virtual_file.parent)]

        # Compile and execute
        try:
            code = compile(self.content, filename=str(virtual_file), mode="exec")
            exec(code, module.__dict__)
        except Exception as e:
            logger.error(f"Error executing virtual module {self.path}: {e}")
            raise


class VirtualModuleFinder(MetaPathFinder):
    """
    Meta path finder that loads workspace modules from Redis cache.

    Converts Python module names to file paths and checks if they exist
    in the cached module index. If found, loads content from Redis.
    """

    def __init__(self):
        self._module_index: set[str] | None = None

    def find_spec(
        self,
        fullname: str,
        path: Any | None = None,
        target: Any | None = None,
    ) -> ModuleSpec | None:
        """
        Find module spec for a given module name.

        Args:
            fullname: Fully qualified module name (e.g., "shared.halopsa")
            path: Module search path
            target: Target module (optional)

        Returns:
            ModuleSpec if module is in our cache, None otherwise
        """
        # Convert module name to potential file paths
        possible_paths = self._module_name_to_paths(fullname)

        # Check if any path exists in our cached index
        module_index = self._get_module_index()

        for file_path, is_package in possible_paths:
            if file_path not in module_index:
                continue

            # Fetch content from Redis
            cached = get_module_sync(file_path)
            if not cached:
                logger.warning(f"Module in index but not in cache: {file_path}")
                continue

            # Create loader and spec
            loader = VirtualModuleLoader(file_path, cached["content"], is_package)
            spec = ModuleSpec(
                fullname,
                loader,
                is_package=is_package,
                origin=str(VIRTUAL_WORKSPACE / file_path),
            )

            logger.debug(f"Virtual import: {fullname} -> {file_path}")
            return spec

        # Not in our cache - let filesystem finder handle it
        return None

    def _module_name_to_paths(self, fullname: str) -> list[tuple[str, bool]]:
        """
        Convert module name to potential file paths.

        Examples:
            "shared.halopsa" -> [
                ("shared/halopsa.py", False),
                ("shared/halopsa/__init__.py", True)
            ]
            "shared" -> [
                ("shared.py", False),
                ("shared/__init__.py", True)
            ]

        Returns:
            List of (path, is_package) tuples to try
        """
        parts = fullname.split(".")
        base_path = "/".join(parts)

        return [
            (f"{base_path}.py", False),           # Module file
            (f"{base_path}/__init__.py", True),   # Package __init__
        ]

    def _get_module_index(self) -> set[str]:
        """Get or refresh the module index from Redis."""
        if self._module_index is None:
            self._module_index = get_module_index_sync()
        return self._module_index

    def invalidate_index(self) -> None:
        """Force refresh of module index on next lookup."""
        self._module_index = None


# Global finder instance (for invalidation access)
_finder: VirtualModuleFinder | None = None


def install_virtual_import_hook() -> VirtualModuleFinder:
    """
    Install the virtual import hook.

    Must be called in worker before any workspace imports.

    Returns:
        The installed finder instance (for testing/invalidation)
    """
    global _finder

    if _finder is not None:
        logger.debug("Virtual import hook already installed")
        return _finder

    _finder = VirtualModuleFinder()
    sys.meta_path.insert(0, _finder)

    logger.info("Virtual import hook installed")
    return _finder


def remove_virtual_import_hook() -> None:
    """Remove the virtual import hook (for testing)."""
    global _finder

    if _finder is not None:
        sys.meta_path = [f for f in sys.meta_path if f is not _finder]
        _finder = None
        logger.info("Virtual import hook removed")


def invalidate_module_index() -> None:
    """Force the finder to refresh its module index."""
    if _finder is not None:
        _finder.invalidate_index()
```

## How Import Resolution Works

When code does `from shared import halopsa`:

1. Python calls `find_spec("shared.halopsa", ...)`
2. Our finder converts to paths: `["shared/halopsa.py", "shared/halopsa/__init__.py"]`
3. Checks if either path exists in Redis module index
4. If found, fetches content from Redis
5. Creates `VirtualModuleLoader` with the content
6. Returns `ModuleSpec` - Python calls `exec_module()` on our loader
7. Loader compiles and executes code in module namespace

## Key Design Points

### No Hardcoded Prefix

The import hook doesn't require a special prefix like `workspace.*`. It simply:
1. Converts any module name to a file path
2. Checks if that path exists in our cache

This means developers write natural imports:
```python
from shared import halopsa          # Works if shared/halopsa.py is cached
from modules.helpers import utils   # Works if modules/helpers/utils.py is cached
```

### Virtual __file__ Path

Even though files don't exist on disk, we set `__file__` to the virtual path for:
- Meaningful tracebacks during debugging
- Code that uses `__file__` for relative paths (will fail, but with clear error)

### Package Support

Packages (directories with `__init__.py`) are supported:
- `__path__` is set for submodule resolution
- `is_package=True` in the spec

### Lazy Index Loading

The module index is loaded from Redis on first import, not on hook installation. This avoids blocking worker startup if Redis is slow.
