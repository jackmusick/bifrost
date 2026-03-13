"""
Package Installation Consumer

Processes package installation requests from RabbitMQ fanout exchange.
Uses broadcast delivery so all worker instances install the package.

Flow:
1. API handler updates requirements.txt in S3 + Redis cache (persistence)
2. API broadcasts message to this consumer on all workers
3. Consumer runs pip install (makes package available on worker filesystem)
4. Consumer recycles processes (clears Python import cache)
5. Consumer updates package list in Redis (so /api/packages reflects changes)

Progress is streamed via WebSocket to the shared package:install channel.
"""

import asyncio
import logging
import sys
from typing import Any

from src.core.pubsub import manager as pubsub_manager
from src.jobs.rabbitmq import BroadcastConsumer

logger = logging.getLogger(__name__)

# Exchange name for broadcast
EXCHANGE_NAME = "package-installations"


class PackageInstallConsumer(BroadcastConsumer):
    """
    Broadcast consumer for package installation.

    Uses fanout exchange so ALL worker instances receive the message,
    pip install the package, and recycle their process pools.

    Message format:
    {
        "type": "recycle_workers",
        "package": "package-name" (optional),
        "version": "1.0.0" (optional)
    }
    """

    def __init__(self):
        super().__init__(exchange_name=EXCHANGE_NAME)

    async def _send_log(self, message: str, level: str = "info") -> None:
        """Send a log message via WebSocket to the shared package:install channel."""
        await pubsub_manager.broadcast(
            "package:install",
            {"type": "log", "level": level, "message": message},
        )

    async def _send_complete(self, status: str, message: str) -> None:
        """Send a completion message via WebSocket to the shared package:install channel."""
        await pubsub_manager.broadcast(
            "package:install",
            {"type": "complete", "status": status, "message": message},
        )

    async def _pip_install(self, package: str, version: str | None) -> bool:
        """
        Run pip install for a specific package on this worker.

        Installs into the worker's Python environment so all child processes
        (which share the same filesystem) can import it after recycle.

        Returns True on success, False on failure.
        """
        package_spec = f"{package}=={version}" if version else package

        try:
            proc = await asyncio.create_subprocess_exec(
                sys.executable, "-m", "pip", "install", package_spec, "--quiet",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await asyncio.wait_for(proc.communicate(), timeout=300)

            if proc.returncode == 0:
                logger.info(f"Installed {package_spec}")
                return True
            else:
                logger.warning(f"pip install {package_spec} failed: {stderr.decode()}")
                return False
        except asyncio.TimeoutError:
            logger.error(f"pip install {package_spec} timed out")
            return False
        except Exception as e:
            logger.error(f"pip install {package_spec} error: {e}")
            return False

    async def _pip_install_requirements(self) -> bool:
        """
        Run pip install from the cached requirements.txt.

        Used when no specific package is provided (e.g., "Install from
        requirements.txt" button).

        Returns True on success, False on failure.
        """
        import tempfile

        from src.core.requirements_cache import get_requirements

        cached = await get_requirements()
        if not cached or not cached["content"].strip():
            logger.info("No cached requirements.txt to install from")
            return True

        try:
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".txt", delete=False
            ) as f:
                f.write(cached["content"])
                temp_path = f.name

            proc = await asyncio.create_subprocess_exec(
                sys.executable, "-m", "pip", "install", "-r", temp_path, "--quiet",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await asyncio.wait_for(proc.communicate(), timeout=300)

            import os
            os.unlink(temp_path)

            if proc.returncode == 0:
                pkg_count = len([
                    line for line in cached["content"].strip().split("\n") if line.strip()
                ])
                logger.info(f"Installed {pkg_count} packages from requirements.txt")
                return True
            else:
                logger.warning(f"pip install -r requirements.txt failed: {stderr.decode()}")
                return False
        except asyncio.TimeoutError:
            logger.error("pip install -r requirements.txt timed out")
            return False
        except Exception as e:
            logger.error(f"pip install -r requirements.txt error: {e}")
            return False

    async def _update_pool_packages(self) -> None:
        """Update the pool's packages in Redis after installation."""
        try:
            from src.services.execution.process_pool import get_process_pool

            pool = get_process_pool()
            if pool._started:
                await pool.update_packages()
        except Exception as e:
            logger.warning(f"Failed to update packages in Redis: {e}")

    def _mark_workers_for_recycle(self) -> None:
        """
        Mark all worker processes for recycling after their current execution.

        Recycling clears Python's import cache (sys.modules) so child processes
        can see newly installed packages on the shared filesystem.
        """
        try:
            from src.services.execution.process_pool import get_process_pool

            pool = get_process_pool()
            if pool._started:
                count, idle_handles = pool.mark_for_recycle()
                logger.info(f"Marked {count} worker processes for recycle")
                for handle in idle_handles:
                    asyncio.create_task(pool._recycle_idle_process(handle))
            else:
                logger.warning("Pool not started, skipping worker recycle")
        except Exception as e:
            logger.warning(f"Failed to mark workers for recycle: {e}")

    async def process_message(self, body: dict[str, Any]) -> None:
        """Process a package installation message."""
        package = body.get("package")
        version = body.get("version")
        package_spec = f"{package}=={version}" if package and version else (package or "requirements.txt")

        logger.info(f"Processing package install: {package_spec}")

        # Step 1: pip install on this worker
        await self._send_log(f"Installing {package_spec}...")

        if package:
            success = await self._pip_install(package, version)
        else:
            success = await self._pip_install_requirements()

        if success:
            await self._send_log(f"Installed {package_spec}")
        else:
            await self._send_log(f"Failed to install {package_spec}", "error")
            await self._send_complete("error", f"Installation failed: {package_spec}")
            return

        # Step 2: Recycle processes only when updating an already-imported package.
        # New packages don't need recycle — Python doesn't cache "not found".
        is_update = body.get("is_update", True)
        if is_update:
            await self._send_log("Recycling worker processes...")
            self._mark_workers_for_recycle()

        # Step 3: Update package list in Redis
        await self._update_pool_packages()

        await self._send_complete("success", "Installation complete")
        logger.info("Package install completed")
