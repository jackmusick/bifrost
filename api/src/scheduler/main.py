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
from src.core.pubsub import (
    publish_git_sync_log,
    publish_git_sync_preview_completed,
    publish_git_sync_progress,
    publish_git_sync_completed,
)
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
    - Git sync requests (bifrost:scheduler:git-sync)
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
            await self._pubsub.subscribe("bifrost:scheduler:git-sync")
            await self._pubsub.subscribe("bifrost:scheduler:git-sync-preview")

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
        elif channel == "bifrost:scheduler:git-sync":
            await self._handle_git_sync_request(data)
        elif channel == "bifrost:scheduler:git-sync-preview":
            await self._handle_git_sync_preview_request(data)
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

    async def _handle_git_sync_request(self, data: dict) -> None:
        """
        Handle git sync request from API.

        Runs the GitHub sync and publishes progress via WebSocket.
        """
        from src.models import SystemConfig
        from src.services.github_sync import (  # type: ignore[import-not-found]
            GitHubSyncService,
            ConflictError,
            OrphanError,
            UnresolvedRefsError,
        )

        job_id = data.get("jobId", "unknown")
        org_id = data.get("orgId")
        conflict_resolutions = data.get("conflictResolutions", {})
        confirm_orphans = data.get("confirmOrphans", False)
        confirm_unresolved_refs = data.get("confirmUnresolvedRefs", False)

        logger.info(f"Starting git sync job {job_id} for org {org_id}")

        try:
            # Publish started status
            await publish_git_sync_log(job_id, "info", "Starting GitHub sync...")

            async with get_db_context() as db:
                # Get GitHub config from database
                from uuid import UUID
                from sqlalchemy import select

                # Parse org_id to UUID
                org_uuid = None
                if org_id:
                    try:
                        org_uuid = UUID(org_id)
                    except ValueError:
                        pass

                # Look for github integration config in system_configs table
                stmt = select(SystemConfig).where(
                    SystemConfig.category == "github",
                    SystemConfig.key == "integration",
                    SystemConfig.organization_id == org_uuid
                )
                result = await db.execute(stmt)
                config = result.scalars().first()

                if not config:
                    # Try GLOBAL fallback (organization_id = NULL)
                    stmt = select(SystemConfig).where(
                        SystemConfig.category == "github",
                        SystemConfig.key == "integration",
                        SystemConfig.organization_id.is_(None)
                    )
                    result = await db.execute(stmt)
                    config = result.scalars().first()

                if not config or not config.value_json:
                    await publish_git_sync_completed(
                        job_id,
                        status="failed",
                        message="GitHub not configured for this organization",
                    )
                    return

                github_config = config.value_json or {}
                encrypted_token = github_config.get("encrypted_token")
                repo_url = github_config.get("repo_url")
                branch = github_config.get("branch", "main")

                # Decrypt token if present
                token = None
                if encrypted_token:
                    try:
                        import base64
                        from cryptography.fernet import Fernet
                        from src.config import get_settings
                        settings = get_settings()
                        # Use secret_key (same as github.py pattern)
                        key_bytes = settings.secret_key.encode()[:32].ljust(32, b'0')
                        fernet = Fernet(base64.urlsafe_b64encode(key_bytes))
                        token = fernet.decrypt(encrypted_token.encode()).decode()
                    except Exception as e:
                        logger.warning(f"Failed to decrypt GitHub token: {e}")

                if not token or not repo_url:
                    await publish_git_sync_completed(
                        job_id,
                        status="failed",
                        message="GitHub token or repository not configured",
                    )
                    return

                # Extract repo from URL (https://github.com/owner/repo -> owner/repo)
                if repo_url.startswith("https://github.com/"):
                    repo = repo_url.replace("https://github.com/", "").rstrip(".git")
                else:
                    repo = repo_url

                await publish_git_sync_log(
                    job_id, "info", f"Syncing with repository: {repo}"
                )

                # Create sync service
                sync_service = GitHubSyncService(
                    db=db,
                    github_token=token,
                    repo=repo,
                    branch=branch,
                )

                # Define progress callback
                async def progress_callback(progress: dict) -> None:
                    await publish_git_sync_progress(
                        job_id,
                        progress.get("phase", "syncing"),
                        progress.get("current", 0),
                        progress.get("total", 0),
                        progress.get("path"),
                    )

                # Define log callback for milestone/error logging
                async def log_callback(level: str, message: str) -> None:
                    await publish_git_sync_log(job_id, level, message)

                # Execute the sync
                sync_result = await sync_service.execute_sync(
                    conflict_resolutions=conflict_resolutions,
                    confirm_orphans=confirm_orphans,
                    confirm_unresolved_refs=confirm_unresolved_refs,
                    progress_callback=progress_callback,
                    log_callback=log_callback,
                )

                # Publish completion
                if sync_result.success:
                    await publish_git_sync_log(
                        job_id, "success",
                        f"Sync complete: {sync_result.pulled} pulled, {sync_result.pushed} pushed"
                    )
                    await publish_git_sync_completed(
                        job_id,
                        status="success",
                        message=f"Sync completed: {sync_result.pulled} pulled, {sync_result.pushed} pushed",
                        pulled=sync_result.pulled,
                        pushed=sync_result.pushed,
                        orphaned_workflows=sync_result.orphaned_workflows,
                        commit_sha=sync_result.commit_sha,
                    )
                    logger.info(
                        f"Git sync job {job_id} completed: "
                        f"pulled={sync_result.pulled}, pushed={sync_result.pushed}"
                    )
                else:
                    await publish_git_sync_completed(
                        job_id,
                        status="failed",
                        message=sync_result.error or "Sync failed",
                    )
                    logger.error(f"Git sync job {job_id} failed: {sync_result.error}")

        except ConflictError as e:
            logger.warning(f"Git sync job {job_id} has conflicts: {e.conflicts}")
            await publish_git_sync_completed(
                job_id,
                status="conflict",
                message="Unresolved conflicts exist",
                conflicts=e.conflicts,
            )

        except OrphanError as e:
            logger.warning(f"Git sync job {job_id} requires orphan confirmation: {e.orphans}")
            await publish_git_sync_completed(
                job_id,
                status="orphans_detected",
                message="Must confirm orphan workflows before proceeding",
                orphans=e.orphans,
            )

        except UnresolvedRefsError as e:
            logger.warning(f"Git sync job {job_id} has unresolved refs: {len(e.unresolved_refs)}")
            await publish_git_sync_completed(
                job_id,
                status="unresolved_refs",
                message="Unresolved workflow refs detected. Set confirm_unresolved_refs=True to proceed.",
                unresolved_refs=[
                    {
                        "entity_type": r.entity_type,
                        "entity_path": r.entity_path,
                        "field_path": r.field_path,
                        "portable_ref": r.portable_ref,
                    }
                    for r in e.unresolved_refs
                ],
            )

        except Exception as e:
            logger.error(f"Git sync job {job_id} failed: {e}", exc_info=True)
            await publish_git_sync_completed(
                job_id,
                status="failed",
                message=str(e),
            )

    async def _handle_git_sync_preview_request(self, data: dict) -> None:
        """
        Handle git sync preview request from API.

        Runs the sync preview and publishes progress via WebSocket.
        """
        from src.models import SystemConfig
        from src.services.github_sync import GitHubSyncService, SyncError

        job_id = data.get("jobId", "unknown")
        org_id = data.get("orgId")

        logger.info(f"Starting git sync preview job {job_id} for org {org_id}")

        try:
            # Publish started status
            await publish_git_sync_log(job_id, "info", "Starting sync preview...")

            async with get_db_context() as db:
                # Get GitHub config from database
                from uuid import UUID
                from sqlalchemy import select

                # Parse org_id to UUID
                org_uuid = None
                if org_id:
                    try:
                        org_uuid = UUID(org_id)
                    except ValueError:
                        pass

                # Look for github integration config in system_configs table
                stmt = select(SystemConfig).where(
                    SystemConfig.category == "github",
                    SystemConfig.key == "integration",
                    SystemConfig.organization_id == org_uuid
                )
                result = await db.execute(stmt)
                config = result.scalars().first()

                if not config:
                    # Try GLOBAL fallback (organization_id = NULL)
                    stmt = select(SystemConfig).where(
                        SystemConfig.category == "github",
                        SystemConfig.key == "integration",
                        SystemConfig.organization_id.is_(None)
                    )
                    result = await db.execute(stmt)
                    config = result.scalars().first()

                if not config or not config.value_json:
                    await publish_git_sync_preview_completed(
                        job_id,
                        status="error",
                        error="GitHub not configured for this organization",
                    )
                    return

                github_config = config.value_json or {}
                encrypted_token = github_config.get("encrypted_token")
                repo_url = github_config.get("repo_url")
                branch = github_config.get("branch", "main")

                # Decrypt token if present
                token = None
                if encrypted_token:
                    try:
                        import base64
                        from cryptography.fernet import Fernet
                        from src.config import get_settings
                        settings = get_settings()
                        # Use secret_key (same as github.py pattern)
                        key_bytes = settings.secret_key.encode()[:32].ljust(32, b'0')
                        fernet = Fernet(base64.urlsafe_b64encode(key_bytes))
                        token = fernet.decrypt(encrypted_token.encode()).decode()
                    except Exception as e:
                        logger.warning(f"Failed to decrypt GitHub token: {e}")

                if not token or not repo_url:
                    await publish_git_sync_preview_completed(
                        job_id,
                        status="error",
                        error="GitHub token or repository not configured",
                    )
                    return

                # Extract repo from URL (https://github.com/owner/repo -> owner/repo)
                if repo_url.startswith("https://github.com/"):
                    repo = repo_url.replace("https://github.com/", "").rstrip(".git")
                else:
                    repo = repo_url

                await publish_git_sync_log(
                    job_id, "info", f"Analyzing repository: {repo}"
                )

                # Create sync service
                sync_service = GitHubSyncService(
                    db=db,
                    github_token=token,
                    repo=repo,
                    branch=branch,
                )

                # Define progress callback
                async def progress_callback(progress: dict) -> None:
                    await publish_git_sync_progress(
                        job_id,
                        progress.get("phase", "analyzing"),
                        progress.get("current", 0),
                        progress.get("total", 0),
                        progress.get("path"),
                    )

                # Define log callback for milestone/error logging
                async def log_callback(level: str, message: str) -> None:
                    await publish_git_sync_log(job_id, level, message)

                # Execute the preview with progress callbacks
                preview = await sync_service.get_sync_preview(
                    progress_callback=progress_callback,
                    log_callback=log_callback,
                )

                # Convert preview to dict for serialization
                # Import the necessary contract types
                from src.models.contracts.github import (
                    OrphanInfo,
                    SyncAction,
                    SyncActionType,
                    SyncConflictInfo,
                    SyncSerializationError,
                    SyncUnresolvedRefInfo,
                    WorkflowReference,
                )
                from src.services.github_sync_entity_metadata import extract_entity_metadata

                preview_response = {
                    "to_pull": [
                        SyncAction(
                            path=a.path,
                            action=SyncActionType(a.action.value),
                            sha=a.sha,
                            display_name=a.display_name,
                            entity_type=a.entity_type,
                            parent_slug=a.parent_slug,
                        ).model_dump()
                        for a in preview.to_pull
                    ],
                    "to_push": [
                        SyncAction(
                            path=a.path,
                            action=SyncActionType(a.action.value),
                            sha=a.sha,
                            display_name=a.display_name,
                            entity_type=a.entity_type,
                            parent_slug=a.parent_slug,
                        ).model_dump()
                        for a in preview.to_push
                    ],
                    "conflicts": [
                        SyncConflictInfo(
                            path=c.path,
                            local_content=c.local_content,
                            remote_content=c.remote_content,
                            local_sha=c.local_sha,
                            remote_sha=c.remote_sha,
                            display_name=(
                                metadata := extract_entity_metadata(
                                    c.path,
                                    (c.remote_content or c.local_content or "").encode("utf-8"),
                                )
                            ).display_name,
                            entity_type=metadata.entity_type,
                            parent_slug=metadata.parent_slug,
                        ).model_dump()
                        for c in preview.conflicts
                    ],
                    "will_orphan": [
                        OrphanInfo(
                            workflow_id=o.workflow_id,
                            workflow_name=o.workflow_name,
                            function_name=o.function_name,
                            last_path=o.last_path,
                            used_by=[
                                WorkflowReference(
                                    type=r.type,
                                    id=r.id,
                                    name=r.name,
                                )
                                for r in o.used_by
                            ],
                        ).model_dump()
                        for o in preview.will_orphan
                    ],
                    "unresolved_refs": [
                        SyncUnresolvedRefInfo(
                            entity_type=u.entity_type,
                            entity_path=u.entity_path,
                            field_path=u.field_path,
                            portable_ref=u.portable_ref,
                        ).model_dump()
                        for u in preview.unresolved_refs
                    ],
                    "serialization_errors": [
                        SyncSerializationError(
                            entity_type=e.entity_type,
                            entity_id=e.entity_id,
                            entity_name=e.entity_name,
                            path=e.path,
                            error=e.error,
                        ).model_dump()
                        for e in preview.serialization_errors
                    ],
                    "is_empty": preview.is_empty,
                }

                # Publish completion with preview data
                await publish_git_sync_log(
                    job_id, "success",
                    f"Preview complete: {len(preview.to_pull)} to pull, {len(preview.to_push)} to push"
                )
                await publish_git_sync_preview_completed(
                    job_id,
                    status="success",
                    preview=preview_response,
                )
                logger.info(
                    f"Git sync preview job {job_id} completed: "
                    f"to_pull={len(preview.to_pull)}, to_push={len(preview.to_push)}"
                )

        except SyncError as e:
            logger.error(f"Git sync preview job {job_id} failed: {e}")
            await publish_git_sync_preview_completed(
                job_id,
                status="error",
                error=str(e),
            )

        except Exception as e:
            logger.error(f"Git sync preview job {job_id} failed: {e}", exc_info=True)
            await publish_git_sync_preview_completed(
                job_id,
                status="error",
                error=str(e),
            )

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
