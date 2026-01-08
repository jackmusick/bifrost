"""
Virtual Module Import System

Loads Python modules from Redis cache instead of filesystem.
Follows the MetaPathFinder pattern from import_restrictor.py.

This allows workers to load workspace modules without needing
the actual files synced to disk - everything comes from Redis cache.

Usage:
    from src.services.execution.virtual_import import install_virtual_import_hook
    install_virtual_import_hook()

    # Now workspace imports are loaded from Redis
    from shared import halopsa  # Loaded from Redis, not filesystem

IMPORTANT: This module must be careful about imports and Redis calls
during find_spec() because the import system itself may trigger imports
(e.g., socket.getaddrinfo imports encodings.idna). We use:
1. A thread-local recursion guard to prevent infinite recursion
2. Early exit for known stdlib module prefixes
"""

import logging
import sys
import threading
from importlib.abc import Loader, MetaPathFinder
from importlib.machinery import ModuleSpec
from pathlib import Path
from types import ModuleType
from typing import Any

from src.core.module_cache_sync import get_module_index_sync, get_module_sync

logger = logging.getLogger(__name__)

# Thread-local storage for recursion guard
_thread_local = threading.local()

# Standard library module prefixes that we should NEVER try to load from Redis.
# These modules are needed by Python's import system itself or by Redis client.
# Adding to this list prevents infinite recursion.
STDLIB_PREFIXES = frozenset([
    "encodings",  # Used by socket.getaddrinfo for hostname resolution
    "codecs",     # Used by encodings
    "_",          # All C extension modules (_socket, _ssl, etc.)
    "builtins",
    "sys",
    "importlib",
    "abc",
    "io",
    "os",
    "posix",
    "errno",
    "socket",
    "ssl",
    "select",
    "selectors",
    "threading",
    "concurrent",
    "asyncio",
    "redis",      # Redis library itself
    "json",       # Used to deserialize cached modules
    "functools",  # Used by lru_cache in module_cache_sync
    "typing",
    "collections",
    "logging",
    "warnings",
    "traceback",
    "linecache",
    "tokenize",
    "re",
    "sre_compile",
    "sre_parse",
    "sre_constants",
    "stringprep",  # Used by encodings.idna
    "copyreg",
    "copy",
    "types",
    "weakref",
    "contextlib",
    "dataclasses",
    "enum",
    "atexit",
    "signal",
    "time",
    "datetime",
    "calendar",
    "locale",
    "struct",
    "decimal",
    "numbers",
    "fractions",
    "random",
    "hashlib",
    "hmac",
    "secrets",
    "base64",
    "binascii",
    "urllib",
    "http",
    "email",
    "html",
    "mimetypes",
    "pathlib",
    "fnmatch",
    "glob",
    "shutil",
    "stat",
    "fileinput",
    "tempfile",
    "zipfile",
    "gzip",
    "bz2",
    "lzma",
    "tarfile",
    "csv",
    "configparser",
    "pickle",
    "marshal",
    "shelve",
    "dbm",
    "sqlite3",
    "zlib",
    "platform",
    "ctypes",
    "multiprocessing",
    "subprocess",
    "queue",
    "heapq",
    "bisect",
    "array",
    "operator",
    "itertools",
    "gettext",
    "argparse",
    "uuid",
    "ipaddress",
    "unittest",
    "pydantic",
    "sqlalchemy",
    "alembic",
    "pika",
    "aio_pika",
    "aiormq",
    "httpx",
    "anyio",
    "sniffio",
    "certifi",
    "charset_normalizer",
    "idna",
    "requests",
    "starlette",
    "fastapi",
    "uvicorn",
    "pytest",
])



class VirtualModuleLoader(Loader):
    """
    Loads module content from cached source code.

    Compiles and executes Python code in the module's namespace,
    setting __file__ to the relative path for meaningful tracebacks.
    """

    def __init__(self, path: str, content: str, is_package: bool = False):
        """
        Initialize loader with module content.

        Args:
            path: Relative file path (e.g., "shared/halopsa.py")
            content: Python source code
            is_package: True if this is a package (__init__.py)
        """
        self.path = path
        self.content = content
        self.is_package = is_package

    def create_module(self, spec: ModuleSpec) -> ModuleType | None:
        """Return None to use default module creation semantics."""
        return None

    def exec_module(self, module: ModuleType) -> None:
        """Execute the module code in the module's namespace."""
        # Use relative path directly for __file__ - no virtual prefix needed
        # Tracebacks will show: "shared/halopsa.py", line 42
        module.__file__ = self.path
        module.__loader__ = self

        if self.is_package:
            # Packages need __path__ for submodule imports
            # Use the directory portion of the relative path
            module.__path__ = [str(Path(self.path).parent)]

        # Compile and execute
        try:
            code = compile(self.content, filename=self.path, mode="exec")
            exec(code, module.__dict__)
        except SyntaxError as e:
            logger.error(f"Syntax error in virtual module {self.path}: {e}")
            raise
        except Exception as e:
            logger.error(f"Error executing virtual module {self.path}: {e}")
            raise


class VirtualModuleFinder(MetaPathFinder):
    """
    Meta path finder that loads workspace modules from Redis cache.

    Converts Python module names to file paths and checks if they exist
    in the cached module index. If found, loads content from Redis.

    Key design points:
    - No hardcoded prefix required - works with any module name
    - Lazy index loading - only fetches from Redis on first import
    - Supports both modules (.py) and packages (__init__.py)
    """

    def __init__(self) -> None:
        """Initialize finder with empty index (loaded on first use)."""
        self._module_index: set[str] | None = None

    def find_spec(
        self,
        fullname: str,
        path: Any | None = None,
        target: Any | None = None,
    ) -> ModuleSpec | None:
        """
        Find module spec for a given module name.

        This is called by Python's import system for every import.
        We check if the module exists in our Redis cache and return
        a spec with our custom loader if found.

        IMPORTANT: This method must be careful to avoid recursion.
        Redis calls may trigger imports (e.g., socket -> encodings.idna),
        which would call find_spec again. We use:
        1. A recursion guard to prevent re-entrant calls during Redis ops
        2. Early exit for stdlib modules that could never be workspace code

        Args:
            fullname: Fully qualified module name (e.g., "shared.halopsa")
            path: Module search path (ignored, we use our cache)
            target: Target module (optional, rarely used)

        Returns:
            ModuleSpec if module is in our cache, None otherwise
            (None tells Python to try the next finder)
        """
        # Fast path: skip stdlib/3rd-party modules that can't be workspace code
        # This also prevents recursion since Redis client imports these
        top_level = fullname.split(".")[0]
        if top_level in STDLIB_PREFIXES:
            return None

        # Recursion guard: if we're already in find_spec (e.g., Redis triggered
        # an import), return None to let the normal import system handle it
        if getattr(_thread_local, "in_find_spec", False):
            return None

        # Set recursion guard
        _thread_local.in_find_spec = True
        try:
            return self._find_spec_impl(fullname)
        finally:
            _thread_local.in_find_spec = False

    def _find_spec_impl(self, fullname: str) -> ModuleSpec | None:
        """
        Internal implementation of find_spec.

        Separated from find_spec to keep the recursion guard clean.
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
                origin=file_path,  # Use relative path directly
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

        Args:
            fullname: Fully qualified module name

        Returns:
            List of (path, is_package) tuples to try
        """
        parts = fullname.split(".")
        base_path = "/".join(parts)

        return [
            (f"{base_path}.py", False),  # Module file
            (f"{base_path}/__init__.py", True),  # Package __init__
        ]

    def _get_module_index(self) -> set[str]:
        """Get or refresh the module index from Redis."""
        if self._module_index is None:
            self._module_index = get_module_index_sync()
            logger.debug(f"Loaded module index: {len(self._module_index)} modules")
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
    The hook is installed at the front of sys.meta_path so it
    takes precedence over the filesystem finder.

    IMPORTANT: We pre-load the module index BEFORE installing the hook.
    This ensures all encoding modules (like encodings.idna for hostname
    resolution) are loaded before our hook can intercept imports.

    Returns:
        The installed finder instance (for testing/invalidation)
    """
    global _finder

    if _finder is not None:
        logger.debug("Virtual import hook already installed")
        return _finder

    # Pre-load encodings that Redis might need for hostname resolution.
    # This must happen BEFORE we install the hook, otherwise the hook
    # might try to fetch from Redis before Redis can even connect.
    _preload_required_modules()

    # Pre-load the module index BEFORE installing the hook.
    # This ensures the Redis connection is established while our hook
    # is NOT yet active, avoiding import deadlocks.
    _finder = VirtualModuleFinder()
    _finder._module_index = get_module_index_sync()
    logger.debug(f"Pre-loaded module index: {len(_finder._module_index)} modules")

    # NOW install the hook - it already has a cached index
    sys.meta_path.insert(0, _finder)

    logger.info("Virtual import hook installed")
    return _finder


def _preload_required_modules() -> None:
    """
    Pre-load modules that Redis/socket might need.

    This is called BEFORE installing the import hook to ensure
    all encoding and network modules are available without
    triggering our custom finder.
    """
    # Force encodings.idna to be loaded (needed for hostname resolution)
    try:
        import encodings.idna  # noqa: F401
    except ImportError:
        pass

    # Force other encoding modules that might be needed
    try:
        import encodings.utf_8  # noqa: F401
        import encodings.ascii  # noqa: F401
    except ImportError:
        pass

    # Force stringprep (needed by encodings.idna)
    try:
        import stringprep  # noqa: F401
    except ImportError:
        pass

    # Ensure codecs is loaded
    try:
        import codecs  # noqa: F401
    except ImportError:
        pass


def remove_virtual_import_hook() -> None:
    """
    Remove the virtual import hook.

    Used for testing cleanup.
    """
    global _finder

    if _finder is not None:
        sys.meta_path = [f for f in sys.meta_path if f is not _finder]
        _finder = None
        logger.info("Virtual import hook removed")


def invalidate_module_index() -> None:
    """
    Force the finder to refresh its module index.

    Call this after modules are added/removed from cache
    to ensure the finder picks up the changes.
    """
    if _finder is not None:
        _finder.invalidate_index()
        logger.debug("Module index invalidated")


def get_virtual_finder() -> VirtualModuleFinder | None:
    """
    Get the current virtual finder instance.

    Returns:
        The active VirtualModuleFinder or None if not installed
    """
    return _finder
