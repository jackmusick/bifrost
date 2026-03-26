"""
NinjaOne async client wrapper.

Wraps the generated sync SDK (sdk.py) with asyncio.to_thread() so it can be
called from async Bifrost workflows without blocking the event loop.

Usage:
    from workflows.ninjaone import client as ninja

    async def my_workflow():
        devices = await ninja.list_devices()
        org = await ninja.get_organization(org_id="123")

The generated SDK handles OAuth credential fetching from the NinjaOne
Bifrost integration automatically.
"""

import asyncio
import functools
from typing import Any

from . import sdk as _sdk


def _wrap(method_name: str):
    """Return an async function that runs the named SDK method in a thread."""
    sdk_method = getattr(_sdk, method_name)

    async def wrapper(*args, **kwargs):
        return await asyncio.to_thread(functools.partial(sdk_method, *args, **kwargs))

    wrapper.__name__ = method_name
    wrapper.__doc__ = sdk_method.__doc__ if hasattr(sdk_method, '__doc__') else None
    return wrapper


# ---------------------------------------------------------------------------
# Expose every public SDK method as an awaitable module-level function.
# ---------------------------------------------------------------------------

def __getattr__(name: str) -> Any:
    """
    Lazily wrap any public SDK method on first access.

    This means `from workflows.ninjaone import client as ninja` followed by
    `await ninja.list_devices()` works without manually listing every method.
    """
    if name.startswith("_"):
        raise AttributeError(name)
    if not hasattr(_sdk, name):
        raise AttributeError(f"NinjaOne SDK has no method '{name}'")
    return _wrap(name)
