"""
HaloPSA async client wrapper.

Wraps the generated sync SDK (sdk.py) with asyncio.to_thread() so it can be
called from async Bifrost workflows without blocking the event loop.

Usage:
    from workflows.halopsa import client as halo

    async def my_workflow():
        clients = await halo.list_clients()
        tickets = await halo.list_tickets()

The generated SDK handles OAuth credential fetching from the HaloPSA
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

    This means `from workflows.halopsa import client as halo` followed by
    `await halo.list_clients()` works without manually listing every method.
    """
    if name.startswith("_"):
        raise AttributeError(name)
    if not hasattr(_sdk, name):
        raise AttributeError(f"HaloPSA SDK has no method '{name}'")
    return _wrap(name)
