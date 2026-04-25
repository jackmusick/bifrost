"""Force glibc to return cached arena memory to the OS.

Called at known allocation-burst boundaries (end of a bundle build) to
prevent fragmentation drift on long-lived pods. Python's GC reclaims
objects but glibc holds the freed pages in per-arena free lists and
never returns them — on a 2-CPU / 1GiB pod this caches ~1GiB of
inactive_anon and guarantees OOM on the next spike.

Safe no-op on non-glibc platforms (macOS, musl).
"""
from __future__ import annotations

import ctypes
import logging

logger = logging.getLogger(__name__)

_libc: ctypes.CDLL | None = None


def trim_malloc() -> None:
    global _libc
    try:
        if _libc is None:
            _libc = ctypes.CDLL("libc.so.6")
        _libc.malloc_trim(0)
    except OSError as e:
        # Non-glibc platform (macOS, musl) — libc.so.6 not present
        logger.debug(f"malloc_trim unavailable on this platform: {e}")
    except Exception as e:
        logger.debug(f"malloc_trim skipped: {e}")
