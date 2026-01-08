#!/usr/bin/env python3
"""
Init container script for Bifrost.

Runs before API and workers start:
1. Run database migrations (alembic upgrade head)
2. Warm Redis module cache from database

Usage:
    python -m scripts.init_container

Exit codes:
    0 - Success
    1 - Migration failure
    2 - Cache warming failure
"""

from __future__ import annotations

import asyncio
import logging
import subprocess
import sys
from pathlib import Path

# Configure logging first
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [init] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("init_container")


def run_migrations() -> bool:
    """
    Run alembic migrations.

    Returns:
        True if migrations succeeded, False otherwise
    """
    logger.info("Running database migrations...")

    # Get the api/ directory (parent of scripts/)
    api_dir = Path(__file__).parent.parent

    try:
        result = subprocess.run(
            ["alembic", "upgrade", "head"],
            cwd=api_dir,
            capture_output=True,
            text=True,
            check=True,
            timeout=300,  # 5 minute timeout
        )

        # Log migration output
        if result.stdout:
            for line in result.stdout.strip().split("\n"):
                if line.strip():
                    logger.info(f"alembic: {line}")

        logger.info("Database migrations completed successfully")
        return True

    except subprocess.TimeoutExpired:
        logger.error("Migration timed out after 5 minutes")
        return False

    except subprocess.CalledProcessError as e:
        logger.error(f"Migration failed with exit code {e.returncode}")
        if e.stderr:
            for line in e.stderr.strip().split("\n"):
                logger.error(f"alembic: {line}")
        if e.stdout:
            for line in e.stdout.strip().split("\n"):
                logger.info(f"alembic: {line}")
        return False

    except FileNotFoundError:
        logger.error("alembic command not found - ensure it's installed")
        return False


async def warm_module_cache() -> int:
    """
    Warm Redis module cache from database.

    Loads all module content from workspace_files table into Redis cache
    so workers can import modules without filesystem access.

    Returns:
        Number of modules cached

    Raises:
        Exception: If cache warming fails
    """
    logger.info("Warming module cache from database...")

    try:
        from src.core.module_cache import warm_cache_from_db

        count = await warm_cache_from_db()
        logger.info(f"Module cache warmed with {count} modules")
        return count

    except ImportError as e:
        logger.error(f"Failed to import module_cache: {e}")
        raise

    except Exception as e:
        logger.error(f"Failed to warm module cache: {e}")
        raise


async def main() -> int:
    """
    Main entry point for init container.

    Returns:
        Exit code (0 for success, non-zero for failure)
    """
    logger.info("=" * 60)
    logger.info("Bifrost Init Container Starting")
    logger.info("=" * 60)

    # Step 1: Run migrations
    logger.info("")
    logger.info("Step 1/2: Database Migrations")
    logger.info("-" * 40)

    if not run_migrations():
        logger.error("FAILED: Database migrations failed - aborting startup")
        return 1

    # Step 2: Warm module cache
    logger.info("")
    logger.info("Step 2/2: Module Cache Warming")
    logger.info("-" * 40)

    try:
        module_count = await warm_module_cache()
    except Exception as e:
        logger.error(f"FAILED: Cache warming failed - {e}")
        return 2

    # Success
    logger.info("")
    logger.info("=" * 60)
    logger.info("Init Container Completed Successfully")
    logger.info("  - Migrations: Applied")
    logger.info(f"  - Module cache: {module_count} modules loaded")
    logger.info("=" * 60)

    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
