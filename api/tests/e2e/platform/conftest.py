"""Shared fixtures for ``test_cli_*`` E2E tests.

Two pieces consolidated here:

* ``cli_client`` — constructs a :class:`bifrost.client.BifrostClient` bound to
  the live E2E stack + the platform admin's JWT and installs it on the
  :data:`bifrost.client._thread_local` singleton for the duration of the test
  so each command's ``pass_resolver`` plumbing hands our client to the
  command body. The previous singleton (if any) is restored on teardown.
* ``invoke_cli`` — returns a callable ``(group, args) -> click.testing.Result``
  wrapping :class:`click.testing.CliRunner` with the project's standard
  invocation flags (``standalone_mode=False``, ``catch_exceptions=False``).

Also bumps ``sys.path`` so the standalone ``bifrost`` package (``api/bifrost``)
imports cleanly from these tests — mirrors the per-file shim that used to
live at the top of every ``test_cli_*.py``.
"""

from __future__ import annotations

import asyncio
import logging
import pathlib
import sys

import pytest

logger = logging.getLogger(__name__)

# Standalone bifrost package import — mirrors the shim that used to live at
# the top of every ``test_cli_*.py``. ``parents[3]`` resolves to ``api/``.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))


@pytest.fixture
def cli_client(e2e_api_url, platform_admin):
    """Bind a ``BifrostClient`` to the E2E API + admin JWT for the CLI run."""
    from bifrost import client as bifrost_client_module
    from bifrost.client import BifrostClient

    client = BifrostClient(e2e_api_url, platform_admin.access_token)
    previous = getattr(bifrost_client_module._thread_local, "bifrost_client", None)
    bifrost_client_module._thread_local.bifrost_client = client
    try:
        yield client
    finally:
        if previous is None:
            bifrost_client_module._thread_local.__dict__.pop("bifrost_client", None)
        else:
            bifrost_client_module._thread_local.bifrost_client = previous


@pytest.fixture
def invoke_cli():
    """Return a callable that invokes a Click group with the project's defaults."""
    from click.testing import CliRunner

    def _invoke(group, args):
        return CliRunner().invoke(
            group, args, standalone_mode=False, catch_exceptions=False
        )

    return _invoke


def _clear_s3_bifrost_sync() -> None:
    """Delete all .bifrost/ files from S3 repo storage, using a fresh event loop.

    Creates its own loop so this works regardless of whether pytest-asyncio
    has a loop already running in the current thread.
    """
    async def _clear() -> None:
        from src.config import get_settings
        from src.services.repo_storage import RepoStorage

        settings = get_settings()
        if not settings.s3_configured:
            return
        repo = RepoStorage(settings)
        paths = await repo.list(".bifrost/")
        for path in paths:
            try:
                await repo.delete(path)
            except Exception as e:
                # Per-path delete is best-effort during cleanup
                logger.debug(f"_clear_s3_bifrost_sync could not delete {path}: {e}")

    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(_clear())
    except Exception as e:
        # S3 not configured / unreachable — fixture is best-effort
        logger.debug(f"_clear_s3_bifrost_sync skipped: {e}")
    finally:
        loop.close()


@pytest.fixture(autouse=True)
def isolate_s3_sync() -> None:
    """Wipe .bifrost/ from S3 before every test in this package.

    Runs on a fresh event loop to avoid conflicting with pytest-asyncio's
    managed loop. Covers the sync HTTP-client tests that can't use the
    async ``isolate_s3`` fixture from tests/conftest.py.
    """
    _clear_s3_bifrost_sync()
