"""
Git Sync Consumer

Processes git operations from RabbitMQ queue.
Replaces the Azure Queue trigger version.
"""

import logging
from typing import Any

from src.core.pubsub import manager as pubsub_manager
from src.jobs.rabbitmq import BaseConsumer

logger = logging.getLogger(__name__)

# Queue name
QUEUE_NAME = "git-sync-jobs"


class GitSyncConsumer(BaseConsumer):
    """
    Consumer for git sync operations queue.

    Message format:
    {
        "type": "git_sync" | "git_refresh" | "git_commit" | "git_discard",
        "job_id": "uuid",
        "org_id": "organization-id",
        "connection_id": "websocket-connection-id" (optional),
        "user_id": "user-id",
        "user_email": "user@example.com",
        ... (additional fields based on operation type)
    }
    """

    def __init__(self):
        super().__init__(
            queue_name=QUEUE_NAME,
            prefetch_count=1,
        )

    async def process_message(self, message_data: dict[str, Any]) -> None:
        """Process a git operation message."""
        operation_type = message_data.get("type", "git_sync")

        if operation_type == "git_sync":
            await self._handle_git_sync(message_data)
        elif operation_type == "git_refresh":
            await self._handle_git_refresh(message_data)
        elif operation_type == "git_commit":
            logger.warning("git_commit operation not yet implemented")
        elif operation_type == "git_discard":
            logger.warning("git_discard operation not yet implemented")
        else:
            logger.error(f"Unknown git operation type: {operation_type}")
            raise ValueError(f"Unknown operation type: {operation_type}")

    async def _handle_git_sync(self, message_data: dict[str, Any]) -> None:
        """Handle git sync - atomic pull + push operation."""
        job_id = message_data.get("job_id", "unknown")
        org_id = message_data.get("org_id")
        connection_id = message_data.get("connection_id")

        logger.info("Processing git sync operation", extra={"job_id": job_id, "org_id": org_id})

        async def send_log(message: str, level: str = "info"):
            """Send log message via WebSocket."""
            if connection_id:
                await pubsub_manager.broadcast(
                    f"git:{connection_id}",
                    {"type": "log", "level": level, "message": message},
                )

        async def send_completion(status: str, message: str, **kwargs):
            """Send completion message via WebSocket."""
            if connection_id:
                await pubsub_manager.broadcast(
                    f"git:{connection_id}",
                    {"type": "complete", "status": status, "message": message, **kwargs},
                )

        try:
            if not org_id:
                raise ValueError("org_id is required for git sync operation")

            # Create context object
            class Context:
                def __init__(self, org_id: str):
                    self.org_id = org_id
                    self.scope = org_id

            context = Context(org_id)

            from src.services.git_integration import GitIntegrationService

            git_service = GitIntegrationService()

            # Step 1: Pull from remote
            await send_log("Starting sync: pulling changes from GitHub...")
            pull_result = await git_service.pull(context, connection_id=connection_id)

            if not pull_result.get("success"):
                error_msg = pull_result.get("error", "Pull failed")
                raise Exception(f"Pull failed: {error_msg}")

            # Check for conflicts
            conflicts = pull_result.get("conflicts", [])
            if conflicts:
                conflict_count = len(conflicts)
                await send_log(
                    f"⚠️ Sync stopped: {conflict_count} conflict(s) detected. "
                    "Resolve conflicts in the editor and try again.",
                    "warning",
                )
                await send_completion(
                    "conflict",
                    f"Sync stopped due to {conflict_count} conflict(s)",
                    conflicts=conflicts,
                )
                logger.info(f"Git sync stopped due to conflicts: {job_id}")
                return

            # NOTE: Discovery is no longer needed here - FileStorageService
            # extracts workflow/data provider metadata at write time during git pull.

            # Step 2: Push to remote
            await send_log("No conflicts detected, pushing changes to GitHub...")
            push_result = await git_service.push(context, connection_id=connection_id)

            if not push_result.get("success"):
                error_msg = push_result.get("error", "Push failed")
                await send_log(f"✗ Push failed: {error_msg}", "error")
                raise Exception(f"Push failed: {error_msg}")

            # Success!
            files_updated = pull_result.get("updated_files", [])
            commits_pushed = push_result.get("commits_pushed", 0)

            success_msg = (
                f"✓ Sync complete! "
                f"Updated {len(files_updated)} file(s), "
                f"pushed {commits_pushed} commit(s)"
            )
            await send_log(success_msg, "success")
            await send_completion(
                "success",
                success_msg,
                updated_files=files_updated,
                commits_pushed=commits_pushed,
            )

            logger.info(f"Git sync completed successfully: {job_id}")

        except Exception as e:
            error_msg = str(e)
            if not error_msg.startswith(("Pull failed:", "Push failed:")):
                error_msg = f"Sync failed: {error_msg}"
                await send_log(f"✗ {error_msg}", "error")

            await send_completion("error", error_msg)
            logger.error(f"Git sync error: {job_id}", extra={"error": str(e)}, exc_info=True)
            # Don't re-raise - job is complete (failed)

    async def _handle_git_refresh(self, message_data: dict[str, Any]) -> None:
        """Handle git refresh - fetch from remote and return status."""
        job_id = message_data.get("job_id", "unknown")
        org_id = message_data.get("org_id")
        connection_id = message_data.get("connection_id")

        logger.info("Processing git refresh operation", extra={"job_id": job_id, "org_id": org_id})

        async def send_log(message: str, level: str = "info"):
            if connection_id:
                await pubsub_manager.broadcast(
                    f"git:{connection_id}",
                    {"type": "log", "level": level, "message": message},
                )

        async def send_completion(status: str, message: str, **kwargs):
            if connection_id:
                await pubsub_manager.broadcast(
                    f"git:{connection_id}",
                    {"type": "complete", "status": status, "message": message, **kwargs},
                )

        try:
            if not org_id:
                raise ValueError("org_id is required for git refresh operation")

            class Context:
                def __init__(self, org_id: str):
                    self.org_id = org_id
                    self.scope = org_id

            context = Context(org_id)

            from src.services.git_integration import GitIntegrationService

            git_service = GitIntegrationService()

            await send_log("Fetching latest changes from GitHub...")
            result = await git_service.refresh_status(context)

            if result.get("success"):
                await send_log("✓ Status refreshed successfully", "success")
                # NOTE: Discovery is no longer needed here - FileStorageService
                # extracts workflow/data provider metadata at write time.
                await send_completion("success", "Status refreshed", data=result)
                logger.info(f"Git refresh completed successfully: {job_id}")
            else:
                error_msg = result.get("error", "Refresh failed")
                await send_log(f"✗ Refresh failed: {error_msg}", "error")
                raise Exception(error_msg)

        except Exception as e:
            error_msg = f"Refresh failed: {str(e)}"
            await send_log(f"✗ {error_msg}", "error")
            await send_completion("error", error_msg)
            logger.error(f"Git refresh error: {job_id}", extra={"error": str(e)}, exc_info=True)
