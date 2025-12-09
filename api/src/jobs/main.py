"""
Bifrost Jobs - Background Worker Service

DEPRECATED: This combined jobs container is replaced by separate containers:
- Discovery: File watching and DB sync (src.discovery.main)
- Scheduler: APScheduler for cron jobs (src.scheduler.main)
- Worker: RabbitMQ consumers for background tasks (src.worker.main)

This module is kept for backward compatibility during the transition.
New deployments should use the separate containers in docker-compose.yml.

Main entry point for the background job worker.
Handles RabbitMQ message consumption and scheduled tasks.
"""

import asyncio
import logging
import signal
import sys

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from src.config import get_settings
from src.core.database import init_db, close_db
from src.jobs.rabbitmq import rabbitmq
from src.jobs.consumers.workflow_execution import WorkflowExecutionConsumer
from src.jobs.consumers.git_sync import GitSyncConsumer
from src.jobs.consumers.package_install import PackageInstallConsumer
from src.jobs.schedulers.cron_scheduler import process_scheduled_workflows
from src.jobs.schedulers.execution_cleanup import cleanup_stuck_executions

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


class JobsWorker:
    """
    Background jobs worker.

    Manages:
    - RabbitMQ consumers for workflow execution, git sync, package installation
    - APScheduler for scheduled tasks (CRON jobs, cleanup)
    """

    def __init__(self):
        self.settings = get_settings()
        self.running = False
        self._shutdown_event = asyncio.Event()
        self._scheduler: AsyncIOScheduler | None = None
        self._consumers: list = []

    async def start(self) -> None:
        """Start the worker."""
        self.running = True
        logger.info("Starting Bifrost Jobs Worker...")
        logger.info(f"Environment: {self.settings.environment}")

        # Initialize database connection
        logger.info("Initializing database connection...")
        await init_db()
        logger.info("Database connection established")

        # NOTE: Discovery watcher has been removed!
        # Workflow/form metadata extraction now happens at write time in FileStorageService.
        # This eliminates the need for file watching and enables horizontal scaling.

        # Initialize and start RabbitMQ consumers
        logger.info("Starting RabbitMQ consumers...")
        await self._start_consumers()

        # Initialize and start APScheduler
        logger.info("Starting scheduler...")
        await self._start_scheduler()

        logger.info("Bifrost Jobs Worker started")
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

    async def _start_scheduler(self) -> None:
        """Start the APScheduler for cron jobs."""
        self._scheduler = AsyncIOScheduler()

        # Schedule processor - every 5 minutes
        self._scheduler.add_job(
            process_scheduled_workflows,
            CronTrigger(minute="*/5"),  # Every 5 minutes
            id="schedule_processor",
            name="Process scheduled workflows",
            replace_existing=True,
        )

        # Execution cleanup - every 5 minutes
        self._scheduler.add_job(
            cleanup_stuck_executions,
            CronTrigger(minute="*/5"),  # Every 5 minutes
            id="execution_cleanup",
            name="Cleanup stuck executions",
            replace_existing=True,
        )

        # Start the scheduler
        self._scheduler.start()
        logger.info("Scheduler started with 2 jobs")

    async def stop(self) -> None:
        """Stop the worker gracefully."""
        logger.info("Stopping Bifrost Jobs Worker...")
        self.running = False

        # Stop scheduler
        if self._scheduler:
            self._scheduler.shutdown(wait=False)
            logger.info("Scheduler stopped")

        # Stop consumers
        for consumer in self._consumers:
            try:
                await consumer.stop()
                logger.info(f"Stopped consumer: {consumer.queue_name}")
            except Exception as e:
                logger.error(f"Error stopping consumer {consumer.queue_name}: {e}")

        # NOTE: Discovery watcher has been removed - no cleanup needed

        # Close RabbitMQ connections
        await rabbitmq.close()
        logger.info("RabbitMQ connections closed")

        # Close database connections
        await close_db()
        logger.info("Database connections closed")

        self._shutdown_event.set()
        logger.info("Bifrost Jobs Worker stopped")

    def handle_signal(self, signum: int, frame) -> None:
        """Handle shutdown signals."""
        logger.info(f"Received signal {signum}, initiating shutdown...")
        asyncio.create_task(self.stop())


async def main() -> None:
    """Main entry point."""
    worker = JobsWorker()

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
