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

    async def _pip_uninstall(self, package: str) -> bool:
        """Run pip uninstall for a package on this worker."""
        try:
            proc = await asyncio.create_subprocess_exec(
                sys.executable, "-m", "pip", "uninstall", "-y", package, "--quiet",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)
            if proc.returncode == 0:
                logger.info(f"Uninstalled {package}")
                return True
            err = stderr.decode()
            # pip exits non-zero when the package isn't installed; that's fine
            # for our purposes — the post-condition (package absent) holds.
            if "not installed" in err.lower() or "skipping" in err.lower():
                logger.info(f"Package {package} was not installed; nothing to do")
                return True
            logger.warning(f"pip uninstall {package} failed: {err}")
            return False
        except asyncio.TimeoutError:
            logger.error(f"pip uninstall {package} timed out")
            return False
        except Exception as e:
            logger.error(f"pip uninstall {package} error: {e}")
            return False

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

    async def _recycle_workers(self) -> None:
        """
        Drain all worker processes and restart the template so that child
        processes forked afterward have a fresh sys.modules that can see
        newly installed packages.
        """
        try:
            from src.services.execution.process_pool import get_process_pool

            pool = get_process_pool()
            if pool._started:
                await pool.drain_and_restart_template()
                logger.info("Drained workers and restarted template after pip install")
            else:
                logger.warning("Pool not started, skipping worker recycle")
        except Exception as e:
            logger.warning(f"Failed to drain/restart after pip install: {e}")

    async def process_message(self, body: dict[str, Any]) -> None:
        """Process a package install or uninstall message.

        `action` is "install" (default) or "uninstall". For "install" with
        `package=None`, runs pip install -r requirements.txt (sync from cache).
        """
        action = body.get("action", "install")
        package = body.get("package")
        version = body.get("version")
        package_spec = f"{package}=={version}" if package and version else (package or "requirements.txt")

        logger.info(f"Processing package {action}: {package_spec}")

        if action == "uninstall":
            if not package:
                await self._send_complete("error", "uninstall requires a package name")
                return
            await self._send_log(f"Uninstalling {package}...")
            success = await self._pip_uninstall(package)
        elif package:
            await self._send_log(f"Installing {package_spec}...")
            success = await self._pip_install(package, version)
        else:
            await self._send_log("Installing from requirements.txt...")
            success = await self._pip_install_requirements()

        if success:
            await self._send_log(f"{action.capitalize()}ed {package_spec}")
        else:
            await self._send_log(f"Failed to {action} {package_spec}", "error")
            await self._send_complete("error", f"{action.capitalize()} failed: {package_spec}")
            return

        # Worker subprocesses are forked before pip runs; recycle so they pick
        # up the new on-disk state.
        await self._send_log("Recycling worker processes...")
        await self._recycle_workers()

        await self._update_pool_packages()

        await self._send_complete("success", f"{action.capitalize()} complete")
        logger.info(f"Package {action} completed")
