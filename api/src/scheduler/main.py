"""
Bifrost Scheduler - Background Scheduler Service

Main entry point for the scheduler service.
Handles APScheduler for cron jobs, cleanup tasks, and OAuth token refresh.

This container is responsible for:
- Running APScheduler for scheduled tasks (CRON workflows, cleanup, OAuth refresh)

IMPORTANT: This container MUST run as a single instance (replicas: 1)
because APScheduler jobs should not run in parallel across multiple instances.

NOTE: File watching and DB sync has been moved to the Discovery container.
"""

import asyncio
import logging
import signal
import sys
from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from src.config import get_settings
from src.core.database import init_db, close_db
from src.jobs.schedulers.cron_scheduler import process_scheduled_workflows
from src.jobs.schedulers.execution_cleanup import cleanup_stuck_executions


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

# Suppress noisy third-party loggers
logging.getLogger("apscheduler").setLevel(logging.WARNING)
logging.getLogger("apscheduler.executors").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)


class Scheduler:
    """
    Background scheduler service.

    Manages APScheduler for scheduled tasks:
    - CRON workflow execution
    - Stuck execution cleanup
    - OAuth token refresh
    """

    def __init__(self):
        self.settings = get_settings()
        self.running = False
        self._shutdown_event = asyncio.Event()
        self._scheduler: AsyncIOScheduler | None = None

    async def start(self) -> None:
        """Start the scheduler."""
        self.running = True
        logger.info("Starting Bifrost Scheduler...")
        logger.info(f"Environment: {self.settings.environment}")

        # Initialize database connection
        logger.info("Initializing database connection...")
        await init_db()
        logger.info("Database connection established")

        # Start APScheduler
        logger.info("Starting APScheduler...")
        await self._start_scheduler()

        logger.info("Bifrost Scheduler started")
        logger.info("Running... (Ctrl+C to stop)")

        # Keep running until shutdown
        await self._shutdown_event.wait()

    async def _start_scheduler(self) -> None:
        """Start APScheduler with all scheduled jobs."""
        scheduler = AsyncIOScheduler()

        # Common job options for misfire handling
        misfire_options = {
            "misfire_grace_time": 60 * 10,  # 10 minute grace period
            "coalesce": True,  # Combine missed runs into one
        }

        # Schedule processor - every 5 minutes
        scheduler.add_job(
            process_scheduled_workflows,
            CronTrigger(minute="*/5"),  # Every 5 minutes
            id="schedule_processor",
            name="Process scheduled workflows",
            replace_existing=True,
            **misfire_options,
        )

        # Execution cleanup - every 5 minutes (run immediately at startup)
        scheduler.add_job(
            cleanup_stuck_executions,
            CronTrigger(minute="*/5"),  # Every 5 minutes
            id="execution_cleanup",
            name="Cleanup stuck executions",
            replace_existing=True,
            next_run_time=datetime.now(),  # Run immediately at startup
            **misfire_options,
        )

        # OAuth token refresh - every 15 minutes (run immediately at startup)
        try:
            from src.jobs.schedulers.oauth_token_refresh import refresh_expiring_tokens
            scheduler.add_job(
                refresh_expiring_tokens,
                IntervalTrigger(minutes=15),
                id="oauth_token_refresh",
                name="Refresh expiring OAuth tokens",
                replace_existing=True,
                next_run_time=datetime.now(),  # Run immediately at startup
                **misfire_options,
            )
            logger.info("OAuth token refresh job scheduled (every 15 min)")
        except ImportError:
            logger.warning("OAuth token refresh job not available")

        # Metrics snapshot refresh - every 60 minutes (run immediately at startup)
        try:
            from src.jobs.schedulers.metrics_refresh import refresh_metrics_snapshot
            scheduler.add_job(
                refresh_metrics_snapshot,
                IntervalTrigger(minutes=60),
                id="metrics_refresh",
                name="Refresh platform metrics snapshot",
                replace_existing=True,
                next_run_time=datetime.now(),  # Run immediately at startup
                **misfire_options,
            )
            logger.info("Metrics snapshot refresh job scheduled (every 60 min)")
        except ImportError:
            logger.warning("Metrics snapshot refresh job not available")

        scheduler.start()
        self._scheduler = scheduler
        logger.info("APScheduler started with scheduled jobs")

    async def stop(self) -> None:
        """Stop the scheduler gracefully."""
        logger.info("Stopping Bifrost Scheduler...")
        self.running = False

        # Stop scheduler
        if self._scheduler:
            self._scheduler.shutdown(wait=False)
            logger.info("APScheduler stopped")

        # Close database connections
        await close_db()
        logger.info("Database connections closed")

        self._shutdown_event.set()
        logger.info("Bifrost Scheduler stopped")

    def handle_signal(self, signum: int, frame) -> None:
        """Handle shutdown signals."""
        logger.info(f"Received signal {signum}, initiating shutdown...")
        asyncio.create_task(self.stop())


async def main() -> None:
    """Main entry point."""
    scheduler = Scheduler()

    # Register signal handlers
    def make_handler(s: signal.Signals) -> None:
        scheduler.handle_signal(int(s), None)

    loop = asyncio.get_running_loop()
    loop.add_signal_handler(signal.SIGINT, make_handler, signal.SIGINT)
    loop.add_signal_handler(signal.SIGTERM, make_handler, signal.SIGTERM)

    try:
        await scheduler.start()
    except Exception as e:
        logger.error(f"Scheduler error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
