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
import json
import logging
import signal
import sys
from datetime import datetime
import redis.asyncio as redis
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from src.config import get_settings
from src.core.database import init_db, close_db, get_db_context
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

    Also listens for on-demand requests via Redis pub/sub:
    - Reindex requests (bifrost:scheduler:reindex)
    """

    def __init__(self):
        self.settings = get_settings()
        self.running = False
        self._shutdown_event = asyncio.Event()
        self._scheduler: AsyncIOScheduler | None = None
        self._redis: redis.Redis | None = None
        self._pubsub: redis.client.PubSub | None = None
        self._listener_task: asyncio.Task | None = None

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

        # Start Redis pub/sub listener for on-demand requests
        logger.info("Starting Redis pub/sub listener...")
        await self._start_pubsub_listener()

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

        # Knowledge storage refresh - daily at 2:00 AM UTC (run immediately at startup)
        try:
            from src.jobs.schedulers.knowledge_storage_refresh import (
                refresh_knowledge_storage_daily,
            )
            scheduler.add_job(
                refresh_knowledge_storage_daily,
                CronTrigger(hour=2, minute=0),  # Daily at 2:00 AM UTC
                id="knowledge_storage_refresh",
                name="Refresh knowledge storage daily metrics",
                replace_existing=True,
                next_run_time=datetime.now(),  # Run immediately at startup
                **misfire_options,
            )
            logger.info("Knowledge storage refresh job scheduled (daily at 2:00 AM)")
        except ImportError:
            logger.warning("Knowledge storage refresh job not available")

        # Webhook subscription renewal - every 6 hours
        try:
            from src.jobs.schedulers.webhook_renewal import renew_expiring_webhooks
            scheduler.add_job(
                renew_expiring_webhooks,
                IntervalTrigger(hours=6),
                id="webhook_renewal",
                name="Renew expiring webhook subscriptions",
                replace_existing=True,
                next_run_time=datetime.now(),  # Run immediately at startup
                **misfire_options,
            )
            logger.info("Webhook renewal job scheduled (every 6 hours)")
        except ImportError:
            logger.warning("Webhook renewal job not available")

        # Event cleanup - daily at 3:00 AM UTC (30-day retention)
        try:
            from src.jobs.schedulers.event_cleanup import cleanup_old_events
            scheduler.add_job(
                cleanup_old_events,
                CronTrigger(hour=3, minute=0),  # Daily at 3:00 AM UTC
                id="event_cleanup",
                name="Cleanup old events (30-day retention)",
                replace_existing=True,
                **misfire_options,
            )
            logger.info("Event cleanup job scheduled (daily at 3:00 AM)")
        except ImportError:
            logger.warning("Event cleanup job not available")

        # Stuck event delivery cleanup - every 5 minutes (run immediately at startup)
        try:
            from src.jobs.schedulers.event_cleanup import cleanup_stuck_events
            scheduler.add_job(
                cleanup_stuck_events,
                CronTrigger(minute="*/5"),  # Every 5 minutes
                id="stuck_event_cleanup",
                name="Cleanup stuck event deliveries",
                replace_existing=True,
                next_run_time=datetime.now(),  # Run immediately at startup
                **misfire_options,
            )
            logger.info("Stuck event cleanup job scheduled (every 5 min)")
        except ImportError:
            logger.warning("Stuck event cleanup job not available")

        scheduler.start()
        self._scheduler = scheduler
        logger.info("APScheduler started with scheduled jobs")

    async def _start_pubsub_listener(self) -> None:
        """Start Redis pub/sub listener for on-demand requests."""
        try:
            self._redis = redis.from_url(self.settings.redis_url)
            self._pubsub = self._redis.pubsub()

            # Subscribe to scheduler channels
            await self._pubsub.subscribe("bifrost:scheduler:reindex")

            # Start listener task
            self._listener_task = asyncio.create_task(self._pubsub_listener())
            logger.info("Redis pub/sub listener started")
        except Exception as e:
            logger.warning(f"Failed to start Redis pub/sub listener: {e}")

    async def _pubsub_listener(self) -> None:
        """Listen for messages on scheduler channels."""
        if not self._pubsub:
            return

        try:
            while self.running:
                message = await self._pubsub.get_message(
                    ignore_subscribe_messages=True,
                    timeout=0.5
                )
                if message and message["type"] == "message":
                    channel = message["channel"].decode()
                    try:
                        data = json.loads(message["data"])
                        await self._handle_pubsub_message(channel, data)
                    except json.JSONDecodeError:
                        logger.warning(f"Invalid JSON in message: {message['data']}")
        except asyncio.CancelledError:
            logger.debug("Pub/sub listener cancelled")
        except Exception as e:
            logger.error(f"Pub/sub listener error: {e}")

    async def _handle_pubsub_message(self, channel: str, data: dict) -> None:
        """Handle incoming pub/sub message."""
        if channel == "bifrost:scheduler:reindex":
            await self._handle_reindex_request(data)
        else:
            logger.warning(f"Unknown channel: {channel}")

    async def _handle_reindex_request(self, data: dict) -> None:
        """
        Handle reindex request from API.

        Runs the smart_reindex and publishes progress via WebSocket.
        """
        from src.core.pubsub import (
            publish_reindex_completed,
            publish_reindex_failed,
            publish_reindex_progress,
        )
        from src.core.paths import WORKSPACE_PATH
        from src.services.file_storage import FileStorageService

        job_id = data.get("job_id", "unknown")
        user_id = data.get("user_id", "system")

        logger.info(f"Starting reindex job {job_id} for user {user_id}")

        try:
            # Publish started status
            await publish_reindex_progress(job_id, "started", 0, 0)

            # Create progress callback
            async def progress_callback(progress: dict) -> None:
                await publish_reindex_progress(
                    job_id,
                    progress.get("phase", "processing"),
                    progress.get("current", 0),
                    progress.get("total", 0),
                    progress.get("current_file"),
                )

            # Run smart reindex with database session
            async with get_db_context() as db:
                storage = FileStorageService(db)
                result = await storage.smart_reindex(
                    local_path=WORKSPACE_PATH,
                    progress_callback=progress_callback,
                )

            # Publish completion
            await publish_reindex_completed(
                job_id,
                counts=result.counts.model_dump(),
                warnings=result.warnings,
                errors=[e.model_dump() for e in result.errors],
            )

            logger.info(f"Reindex job {job_id} completed: {result.counts}")

        except Exception as e:
            logger.error(f"Reindex job {job_id} failed: {e}", exc_info=True)
            await publish_reindex_failed(job_id, str(e))

    async def stop(self) -> None:
        """Stop the scheduler gracefully."""
        logger.info("Stopping Bifrost Scheduler...")
        self.running = False

        # Stop pub/sub listener
        if self._listener_task:
            self._listener_task.cancel()
            try:
                await self._listener_task
            except asyncio.CancelledError:
                pass
            logger.info("Pub/sub listener stopped")

        if self._pubsub:
            await self._pubsub.close()

        if self._redis:
            await self._redis.close()

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
