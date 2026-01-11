"""
Package Installation Consumer

Processes package installation requests from RabbitMQ fanout exchange.
Uses broadcast delivery so all worker instances install the package.

Persistence: After installing a package, this consumer saves requirements.txt
to the database via save_requirements_to_db(). This ensures packages survive
container restarts. See api/src/core/requirements_cache.py for the full flow.
"""

import logging
from typing import Any

from src.core.pubsub import manager as pubsub_manager
from src.core.requirements_cache import get_requirements, save_requirements_to_db
from src.jobs.rabbitmq import BroadcastConsumer

logger = logging.getLogger(__name__)

# Exchange name for broadcast
EXCHANGE_NAME = "package-installations"


class PackageInstallConsumer(BroadcastConsumer):
    """
    Broadcast consumer for package installation.

    Uses fanout exchange so ALL worker instances receive the message
    and install the package. This ensures packages are available on
    every worker for workflow execution.

    Message format:
    {
        "type": "package_install",
        "job_id": "uuid",
        "package": "package-name" (optional - if not provided, installs from requirements.txt),
        "version": "1.0.0" (optional),
        "connection_id": "websocket-connection-id" (optional),
        "user_id": "user-id",
        "user_email": "user@example.com"
    }
    """

    def __init__(self):
        super().__init__(exchange_name=EXCHANGE_NAME)

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

        When packages are installed, existing worker processes won't see them
        due to Python's import caching. Recycling processes ensures fresh
        Python interpreters that can import newly installed packages.
        """
        try:
            import asyncio
            from src.services.execution.process_pool import get_process_pool

            pool = get_process_pool()
            if pool._started:
                count, idle_handles = pool.mark_for_recycle()
                logger.info(f"Marked {count} worker processes for recycle")
                # Recycle idle processes immediately via tasks
                for handle in idle_handles:
                    asyncio.create_task(pool._recycle_idle_process(handle))
            else:
                logger.warning("Pool not started, skipping worker recycle")
        except Exception as e:
            logger.warning(f"Failed to mark workers for recycle: {e}")

    async def _get_current_requirements(self) -> str:
        """Get current requirements.txt content from cache."""
        cached = await get_requirements()
        if cached:
            return cached["content"]
        return ""

    @staticmethod
    def _append_package_to_requirements(
        current: str, package: str, version: str | None
    ) -> str:
        """
        Append or update a package in requirements.txt content.

        Args:
            current: Current requirements.txt content
            package: Package name
            version: Optional version specifier

        Returns:
            Updated requirements.txt content
        """
        lines = current.strip().split("\n") if current.strip() else []
        package_lower = package.lower()
        package_spec = f"{package}=={version}" if version else package

        # Find and update existing entry, or append
        found = False
        for i, line in enumerate(lines):
            # Parse package name from line (handles ==, >=, etc.)
            line_package = (
                line.split("==")[0].split(">=")[0].split("<=")[0].split("~=")[0].strip()
            )
            if line_package.lower() == package_lower:
                lines[i] = package_spec
                found = True
                break

        if not found:
            lines.append(package_spec)

        # Filter empty lines and ensure trailing newline
        lines = [line for line in lines if line.strip()]
        return "\n".join(lines) + "\n" if lines else ""

    async def process_message(self, body: dict[str, Any]) -> None:
        """Process a package installation message."""
        job_id = body.get("job_id", "unknown")
        package = body.get("package")
        version = body.get("version")
        connection_id = body.get("connection_id")

        logger.info(
            f"Processing package installation: {package or 'requirements.txt'}",
            extra={"job_id": job_id, "package": package, "version": version},
        )

        async def send_log(message: str, level: str = "info"):
            """Send log message via WebSocket."""
            if connection_id:
                await pubsub_manager.broadcast(
                    f"package:{connection_id}",
                    {"type": "log", "level": level, "message": message},
                )

        async def send_completion(status: str, message: str):
            """Send completion message via WebSocket."""
            if connection_id:
                await pubsub_manager.broadcast(
                    f"package:{connection_id}",
                    {"type": "complete", "status": status, "message": message},
                )

        try:
            # Use ephemeral temp directory for package installation
            # This is for installing packages into a workspace that can be cleaned up
            from src.core.paths import create_ephemeral_temp_dir
            from src.services.package_manager import WorkspacePackageManager

            workspace_path = create_ephemeral_temp_dir()
            pkg_manager = WorkspacePackageManager(workspace_path)

            if package:
                # Install specific package
                package_spec = f"{package}=={version}" if version else package
                await send_log(f"Installing package: {package_spec}")
                await pkg_manager.install_package(
                    package_name=package,
                    version=version,
                    log_callback=send_log,
                    append_to_requirements=True,
                )
            else:
                # Install from requirements.txt
                await send_log("Installing packages from requirements.txt")
                await pkg_manager.install_requirements_streaming(log_callback=send_log)

            await send_completion("success", "Package installation completed successfully")

            # Persist requirements to database for startup recovery
            # Only when a specific package is installed, not from requirements.txt
            if package:
                try:
                    current_requirements = await self._get_current_requirements()
                    updated_requirements = self._append_package_to_requirements(
                        current_requirements, package, version
                    )
                    await save_requirements_to_db(updated_requirements)
                    await send_log("Saved requirements.txt to database")
                except Exception as e:
                    logger.warning(f"Failed to persist requirements.txt: {e}")
                    # Don't fail the install if persistence fails

            # Mark worker processes for recycling so they pick up the new package.
            # Fresh Python interpreters will see packages installed after spawn.
            self._mark_workers_for_recycle()

            # Update packages in Redis so /api/packages reflects the new package
            await self._update_pool_packages()

            logger.info(
                f"Package installation completed: {package or 'requirements.txt'}",
                extra={"job_id": job_id},
            )

        except Exception as e:
            error_msg = f"Package installation failed: {str(e)}"
            await send_log(f"✗ {error_msg}", "error")
            await send_completion("error", error_msg)

            logger.error(
                f"Package installation error: {job_id}",
                extra={"job_id": job_id, "error": str(e), "error_type": type(e).__name__},
                exc_info=True,
            )
            raise
