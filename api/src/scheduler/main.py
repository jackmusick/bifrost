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
from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from src.config import get_settings
from src.core.database import init_db, close_db, get_db_context
from src.core.pubsub import publish_git_op_completed
from src.core.redis_reconnect import ResilientPubSubListener
from src.jobs.schedulers.cron_scheduler import process_schedule_sources
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
    - Git sync requests (bifrost:scheduler:git-sync)
    """

    def __init__(self):
        self.settings = get_settings()
        self.running = False
        self._shutdown_event = asyncio.Event()
        self._scheduler: AsyncIOScheduler | None = None
        self._pubsub_listener: ResilientPubSubListener | None = None

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

        # Schedule processor - every 1 minute
        scheduler.add_job(
            process_schedule_sources,
            CronTrigger(minute="*/1"),  # Every 1 minute
            id="schedule_processor",
            name="Process schedule sources",
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
            next_run_time=datetime.now(timezone.utc),  # Run immediately at startup
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
                next_run_time=datetime.now(timezone.utc),  # Run immediately at startup
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
                next_run_time=datetime.now(timezone.utc),  # Run immediately at startup
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
                next_run_time=datetime.now(timezone.utc),  # Run immediately at startup
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
                next_run_time=datetime.now(timezone.utc),  # Run immediately at startup
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
                next_run_time=datetime.now(timezone.utc),  # Run immediately at startup
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
        self._pubsub_listener = ResilientPubSubListener(
            redis_url=self.settings.redis_url,
            channels=[
                "bifrost:scheduler:reindex",
                "bifrost:scheduler:git-op",
            ],
            on_message=self._handle_pubsub_message,
        )
        await self._pubsub_listener.start()
        logger.info("Redis pub/sub listener started (with auto-reconnect)")

    async def _handle_pubsub_message(self, channel: str, data: dict) -> None:
        """Handle incoming pub/sub message."""
        if channel == "bifrost:scheduler:reindex":
            await self._handle_reindex_request(data)
        elif channel == "bifrost:scheduler:git-op":
            await self._handle_git_operation(data)
        else:
            logger.warning(f"Unknown channel: {channel}")

    @staticmethod
    def _build_clone_url_from_config(config) -> str:
        """Build an authenticated git clone URL from a GitHubConfig object."""
        repo_url = config.repo_url

        # Extract owner/repo from URL
        if repo_url.startswith("https://github.com/"):
            repo = repo_url.replace("https://github.com/", "").rstrip(".git")
        else:
            repo = repo_url

        return f"https://x-access-token:{config.token}@github.com/{repo}.git"

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

    async def _handle_git_operation(self, data: dict) -> None:
        """
        Handle a desktop-style git operation request.

        Dispatches to the appropriate GitHubSyncService method based on op_type.
        """
        from src.services.github_config import get_github_config
        from src.services.github_sync import GitHubSyncService

        op_type = data.get("type", "unknown")
        job_id = data.get("jobId", "unknown")
        org_id = data.get("orgId")

        logger.info(f"Starting git operation {op_type} job {job_id} for org {org_id}")

        try:
            async with get_db_context() as db:
                github_config = await get_github_config(db, org_id)

                if not github_config:
                    await publish_git_op_completed(
                        job_id, status="failed", result_type=op_type.replace("git_", ""),
                        error="GitHub not configured",
                    )
                    return

                if not github_config.token or not github_config.repo_url:
                    await publish_git_op_completed(
                        job_id, status="failed", result_type=op_type.replace("git_", ""),
                        error="GitHub token or repository not configured",
                    )
                    return

                clone_url = self._build_clone_url_from_config(github_config)
                branch = github_config.branch

                sync_service = GitHubSyncService(
                    db=db,
                    repo_url=clone_url,
                    branch=branch,
                    settings=get_settings(),
                )

                result_type = op_type.replace("git_", "")

                if op_type == "git_fetch":
                    op_result = await sync_service.desktop_fetch()
                    await publish_git_op_completed(
                        job_id, status="success" if op_result.success else "failed",
                        result_type="fetch",
                        data=op_result.model_dump() if op_result.success else None,
                        error=op_result.error,
                    )

                elif op_type == "git_status":
                    op_result = await sync_service.desktop_status()
                    await publish_git_op_completed(
                        job_id, status="success", result_type="status",
                        data=op_result.model_dump(),
                    )

                elif op_type == "git_commit":
                    message = data.get("message", "Commit from Bifrost")
                    op_result = await sync_service.desktop_commit(message)
                    await publish_git_op_completed(
                        job_id, status="success" if op_result.success else "failed",
                        result_type="commit",
                        data=op_result.model_dump() if op_result.success else None,
                        error=op_result.error,
                    )

                elif op_type == "git_pull":
                    op_result = await sync_service.desktop_pull()
                    status_str = "success" if op_result.success else ("conflict" if op_result.conflicts else "failed")
                    await publish_git_op_completed(
                        job_id, status=status_str, result_type="pull",
                        data=op_result.model_dump(),
                        error=op_result.error,
                    )

                elif op_type == "git_push":
                    op_result = await sync_service.desktop_push()
                    await publish_git_op_completed(
                        job_id, status="success" if op_result.success else "failed",
                        result_type="push",
                        data=op_result.model_dump() if op_result.success else None,
                        error=op_result.error,
                    )

                elif op_type == "git_resolve":
                    resolutions = data.get("resolutions", {})
                    op_result = await sync_service.desktop_resolve(resolutions)
                    await publish_git_op_completed(
                        job_id, status="success" if op_result.success else "failed",
                        result_type="resolve",
                        data=op_result.model_dump() if op_result.success else None,
                        error=op_result.error,
                    )

                elif op_type == "git_diff":
                    path = data.get("path", "")
                    op_result = await sync_service.desktop_diff(path)
                    await publish_git_op_completed(
                        job_id, status="success", result_type="diff",
                        data=op_result.model_dump(),
                    )

                elif op_type == "git_sync_preview":
                    # Sync preview: fetch + status + preflight
                    fetch_result = await sync_service.desktop_fetch()
                    if not fetch_result.success:
                        await publish_git_op_completed(
                            job_id, status="failed", result_type="sync_preview",
                            error=fetch_result.error,
                        )
                    else:
                        status_result = await sync_service.desktop_status()
                        preflight_result = await sync_service.preflight()
                        await publish_git_op_completed(
                            job_id, status="success", result_type="sync_preview",
                            data={
                                "fetch": fetch_result.model_dump(),
                                "status": status_result.model_dump(),
                                "preflight": preflight_result.model_dump(),
                            },
                        )

                elif op_type == "git_sync_execute":
                    # Full sync: commit + pull (with resolutions) + push
                    conflict_resolutions = data.get("conflict_resolutions", {})

                    # Step 1: Commit local changes
                    commit_result = await sync_service.desktop_commit("Sync from Bifrost")
                    # Commit may have nothing to commit -- that's OK

                    # Step 2: Pull remote changes
                    pull_result = await sync_service.desktop_pull()
                    if not pull_result.success:
                        if pull_result.conflicts and conflict_resolutions:
                            # Auto-resolve with provided resolutions
                            resolve_result = await sync_service.desktop_resolve(conflict_resolutions)
                            if not resolve_result.success:
                                await publish_git_op_completed(
                                    job_id, status="conflict", result_type="sync_execute",
                                    data={"pull": pull_result.model_dump()},
                                    error=resolve_result.error,
                                )
                            else:
                                # Resolution succeeded, continue to push
                                push_result = await sync_service.desktop_push()
                                await publish_git_op_completed(
                                    job_id,
                                    status="success" if push_result.success else "failed",
                                    result_type="sync_execute",
                                    data={
                                        "commit": commit_result.model_dump() if commit_result else None,
                                        "pull": pull_result.model_dump(),
                                        "push": push_result.model_dump() if push_result.success else None,
                                    },
                                    error=push_result.error if not push_result.success else None,
                                )
                        elif pull_result.conflicts:
                            await publish_git_op_completed(
                                job_id, status="conflict", result_type="sync_execute",
                                data={"pull": pull_result.model_dump()},
                                error="Merge conflicts detected",
                            )
                        else:
                            await publish_git_op_completed(
                                job_id, status="failed", result_type="sync_execute",
                                error=pull_result.error,
                            )
                    else:
                        # Step 3: Push
                        push_result = await sync_service.desktop_push()
                        await publish_git_op_completed(
                            job_id,
                            status="success" if push_result.success else "failed",
                            result_type="sync_execute",
                            data={
                                "commit": commit_result.model_dump() if commit_result else None,
                                "pull": pull_result.model_dump(),
                                "push": push_result.model_dump() if push_result.success else None,
                            },
                            error=push_result.error if not push_result.success else None,
                        )

                else:
                    await publish_git_op_completed(
                        job_id, status="failed", result_type=result_type,
                        error=f"Unknown operation type: {op_type}",
                    )

                logger.info(f"Git operation {op_type} job {job_id} completed")

        except Exception as e:
            logger.error(f"Git operation {op_type} job {job_id} failed: {e}", exc_info=True)
            await publish_git_op_completed(
                job_id, status="failed", result_type=op_type.replace("git_", ""),
                error=str(e),
            )

    async def stop(self) -> None:
        """Stop the scheduler gracefully."""
        logger.info("Stopping Bifrost Scheduler...")
        self.running = False

        # Stop pub/sub listener
        if self._pubsub_listener:
            await self._pubsub_listener.stop()
            logger.info("Pub/sub listener stopped")

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
