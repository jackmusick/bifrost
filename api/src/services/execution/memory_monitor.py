"""
Memory monitoring for execution throttling.

Provides system memory checks to prevent OOM conditions by delaying
subprocess spawning when available memory is low.
"""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Track if we've warned about missing /proc/meminfo (only warn once)
_warned_no_proc_meminfo = False


def get_available_memory_mb() -> int:
    """
    Get available system memory in MB.

    Reads /proc/meminfo (Linux/Docker). Returns -1 if unavailable.

    Returns:
        Available memory in MB, or -1 if unable to determine.
    """
    global _warned_no_proc_meminfo

    proc_meminfo = Path("/proc/meminfo")

    if not proc_meminfo.exists():
        if not _warned_no_proc_meminfo:
            logger.warning(
                "/proc/meminfo not found - memory throttling disabled. "
                "This is expected on macOS local development."
            )
            _warned_no_proc_meminfo = True
        return -1

    try:
        with open(proc_meminfo) as f:
            for line in f:
                if line.startswith("MemAvailable:"):
                    # Format: "MemAvailable:    12345678 kB"
                    parts = line.split()
                    if len(parts) >= 2:
                        kb = int(parts[1])
                        return kb // 1024  # Convert to MB
        # MemAvailable not found (older kernels)
        logger.warning("MemAvailable not found in /proc/meminfo")
        return -1
    except (OSError, ValueError) as e:
        logger.warning(f"Failed to read /proc/meminfo: {e}")
        return -1


def has_sufficient_memory(threshold_mb: int = 300) -> bool:
    """
    Check if system has enough memory to start a new subprocess.

    Args:
        threshold_mb: Minimum available memory required (default 300MB)

    Returns:
        True if memory is sufficient or if unable to check (non-Linux).
        False if available memory is below threshold.
    """
    available = get_available_memory_mb()

    # If we can't determine memory, assume it's OK (don't block on macOS dev)
    if available < 0:
        return True

    return available >= threshold_mb
