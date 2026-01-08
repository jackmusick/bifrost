"""
Package Installation Consumer

Processes package installation requests from RabbitMQ fanout exchange.
Uses broadcast delivery so all worker instances install the package.
"""

import logging
from typing import Any

from src.core.pubsub import manager as pubsub_manager
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

    async def process_message(self, message_data: dict[str, Any]) -> None:
        """Process a package installation message."""
        job_id = message_data.get("job_id", "unknown")
        package = message_data.get("package")
        version = message_data.get("version")
        connection_id = message_data.get("connection_id")

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
