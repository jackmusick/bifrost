"""
Reusable polling helper for E2E tests.

Consolidates the ``poll_until`` implementations that were duplicated in
``tests/e2e/conftest.py`` and ``tests/e2e/fixtures/entity_setup.py``.

Usage:
    from tests.helpers.polling import poll_until
"""

import time
from typing import Callable, TypeVar

T = TypeVar("T")


def poll_until(
    condition: Callable[[], T | None],
    max_wait: float = 5.0,
    interval: float = 0.1,
    backoff: float = 1.5,
    max_interval: float = 1.0,
) -> T | None:
    """
    Poll until *condition* returns a truthy value or timeout.

    Uses exponential backoff starting at *interval*, multiplying by *backoff*
    each iteration, capped at *max_interval*.

    Args:
        condition: Callable that returns a truthy value on success,
                   ``None`` / falsy on failure.
        max_wait:  Maximum total time to wait in seconds.
        interval:  Initial polling interval in seconds.
        backoff:   Multiplier for interval after each attempt.
        max_interval: Maximum interval between attempts.

    Returns:
        The truthy value returned by *condition*, or ``None`` on timeout.
    """
    elapsed = 0.0
    current_interval = interval

    while elapsed < max_wait:
        result = condition()
        if result:
            return result
        time.sleep(current_interval)
        elapsed += current_interval
        current_interval = min(current_interval * backoff, max_interval)

    return None
