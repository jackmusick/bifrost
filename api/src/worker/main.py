"""
Bifrost Worker - Background Worker Service

Main entry point for the background job worker.
Handles RabbitMQ message consumption for workflow execution, git sync, and package installation.

This container is responsible for:
- Consuming workflow execution messages from RabbitMQ
- Executing workflow code (with thread pool for blocking code)
- Pushing results to Redis for sync execution requests
- Git sync operations
- Package installation

Can be scaled horizontally (replicas: N) for increased throughput.
"""

import asyncio
import logging
import signal
import sys

from src.config import get_settings
from src.core.database import init_db, close_db
from src.core.workspace_sync import workspace_sync
from src.jobs.rabbitmq import rabbitmq
from src.jobs.consumers.workflow_execution import WorkflowExecutionConsumer
from src.jobs.consumers.git_sync import GitSyncConsumer
from src.jobs.consumers.package_install import PackageInstallConsumer

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

# Suppress noisy third-party loggers
logging.getLogger("watchdog").setLevel(logging.WARNING)
logging.getLogger("watchdog.observers.inotify_buffer").setLevel(logging.WARNING)
logging.getLogger("aiormq").setLevel(logging.WARNING)
logging.getLogger("aio_pika").setLevel(logging.WARNING)

# Enable DEBUG for execution engine to troubleshoot workflows
logging.getLogger("src.services.execution").setLevel(logging.DEBUG)
logging.getLogger("bifrost").setLevel(logging.DEBUG)
logging.getLogger("src.jobs.consumers.workflow_execution").setLevel(logging.DEBUG)

logger = logging.getLogger(__name__)


class Worker:
    """
    Background jobs worker.

    Manages RabbitMQ consumers for:
    - Workflow execution (with Redis result push for sync requests)
    - Git sync operations
    - Package installation
    """

    def __init__(self):
        self.settings = get_settings()
        self.running = False
        self._shutdown_event = asyncio.Event()
        self._consumers: list = []

    async def start(self) -> None:
        """Start the worker."""
        self.running = True
        logger.info("Starting Bifrost Worker...")
        logger.info(f"Environment: {self.settings.environment}")

        # Initialize database connection
        logger.info("Initializing database connection...")
        await init_db()
        logger.info("Database connection established")

        # Initialize workspace sync (downloads from S3, starts pub/sub listener)
        logger.info("Initializing workspace sync...")
        await workspace_sync.start()
        logger.info("Workspace sync initialized")

        # Initialize and start RabbitMQ consumers
        logger.info("Starting RabbitMQ consumers...")
        await self._start_consumers()

        logger.info("Bifrost Worker started")
        logger.info("Waiting for messages... (Ctrl+C to stop)")

        # Keep running until shutdown
        await self._shutdown_event.wait()

    async def _start_consumers(self) -> None:
        """Start all RabbitMQ consumers."""
        # Create consumer instances
        self._consumers = [
            WorkflowExecutionConsumer(),
            GitSyncConsumer(),
            PackageInstallConsumer(),
        ]

        # Start each consumer
        for consumer in self._consumers:
            try:
                await consumer.start()
                logger.info(f"Started consumer: {consumer.queue_name}")
            except Exception as e:
                logger.error(f"Failed to start consumer {consumer.queue_name}: {e}")
                raise

    async def stop(self) -> None:
        """Stop the worker gracefully."""
        logger.info("Stopping Bifrost Worker...")
        self.running = False

        # Stop consumers
        for consumer in self._consumers:
            try:
                await consumer.stop()
                logger.info(f"Stopped consumer: {consumer.queue_name}")
            except Exception as e:
                logger.error(f"Error stopping consumer {consumer.queue_name}: {e}")

        # Stop workspace sync
        await workspace_sync.stop()
        logger.info("Workspace sync stopped")

        # Close RabbitMQ connections
        await rabbitmq.close()
        logger.info("RabbitMQ connections closed")

        # Close database connections
        await close_db()
        logger.info("Database connections closed")

        self._shutdown_event.set()
        logger.info("Bifrost Worker stopped")

    def handle_signal(self, signum: int, frame) -> None:
        """Handle shutdown signals."""
        logger.info(f"Received signal {signum}, initiating shutdown...")
        asyncio.create_task(self.stop())


async def main() -> None:
    """Main entry point."""
    worker = Worker()

    # Register signal handlers
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda s=sig: worker.handle_signal(s, None))

    try:
        await worker.start()
    except Exception as e:
        logger.error(f"Worker error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
