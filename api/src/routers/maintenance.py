"""
Maintenance Router

API endpoints for workspace maintenance operations.
Platform admin resource - no org scoping.
"""

import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.auth import Context, CurrentSuperuser
from src.core.database import get_db
from src.core.workspace_sync import WORKSPACE_PATH
from src.models import (
    MaintenanceStatus,
    ReindexRequest,
    ReindexResponse,
)
from src.models.contracts.notifications import NotificationStatus, NotificationUpdate
from src.services.file_storage_service import FileStorageService
from src.services.notification_service import get_notification_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/maintenance", tags=["Maintenance"])


@router.get(
    "/status",
    response_model=MaintenanceStatus,
    summary="Get maintenance status",
    description="Get current workspace maintenance status (Platform admin only)",
)
async def get_maintenance_status(
    ctx: Context,
    user: CurrentSuperuser,
    db: AsyncSession = Depends(get_db),
) -> MaintenanceStatus:
    """
    Get the current maintenance status of the workspace.

    Returns:
        - files_needing_ids: List of Python files with decorators missing IDs
        - total_files: Total number of files in workspace
        - last_reindex: Timestamp of last reindex (not tracked currently)
    """
    from src.services.decorator_property_service import DecoratorPropertyService
    from src.services.editor.file_filter import is_excluded_path

    files_needing_ids: list[str] = []
    total_files = 0

    try:
        # Scan workspace for Python files with missing IDs
        workspace_path = Path(WORKSPACE_PATH)
        if not workspace_path.exists():
            return MaintenanceStatus(
                files_needing_ids=[],
                total_files=0,
                last_reindex=None,
            )

        decorator_service = DecoratorPropertyService()

        for file_path in workspace_path.rglob("*.py"):
            rel_path = str(file_path.relative_to(workspace_path))

            # Skip excluded paths
            if is_excluded_path(rel_path):
                continue

            total_files += 1

            try:
                content = file_path.read_text(encoding="utf-8", errors="replace")
                inject_result = decorator_service.inject_ids_if_missing(content)

                if inject_result.modified:
                    files_needing_ids.append(rel_path)
            except Exception as e:
                logger.warning(f"Failed to check {rel_path}: {e}")

        return MaintenanceStatus(
            files_needing_ids=files_needing_ids,
            total_files=total_files,
            last_reindex=None,  # Not tracked currently
        )

    except Exception as e:
        logger.error(f"Error getting maintenance status: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get maintenance status",
        )


@router.post(
    "/reindex",
    response_model=ReindexResponse,
    summary="Run workspace reindex",
    description="Reindex workspace files, optionally injecting IDs (Platform admin only)",
)
async def run_reindex(
    ctx: Context,
    user: CurrentSuperuser,
    request: ReindexRequest,
    db: AsyncSession = Depends(get_db),
) -> ReindexResponse:
    """
    Run a workspace reindex operation.

    Args:
        request: ReindexRequest with inject_ids flag and optional notification_id

    Returns:
        ReindexResponse with operation results

    When inject_ids=True:
        - Scans all Python files
        - Injects stable UUIDs into @workflow, @data_provider, @tool decorators
        - Writes modified files back to S3
        - Updates database metadata

    When inject_ids=False:
        - Detection only - reports files that would need IDs
        - No files are modified

    When notification_id is provided:
        - Updates the notification to RUNNING status at start
        - Updates to COMPLETED/FAILED on finish with result details
    """
    notification_service = get_notification_service()

    # Update notification to running if provided
    if request.notification_id:
        await notification_service.update_notification(
            request.notification_id,
            NotificationUpdate(
                status=NotificationStatus.RUNNING,
                description="Indexing workflow files...",
            ),
        )

    try:
        workspace_path = Path(WORKSPACE_PATH)
        if not workspace_path.exists():
            # Update notification to completed (no work to do)
            if request.notification_id:
                await notification_service.update_notification(
                    request.notification_id,
                    NotificationUpdate(
                        status=NotificationStatus.COMPLETED,
                        description="Workspace directory does not exist",
                    ),
                )
            return ReindexResponse(
                status="completed",
                files_indexed=0,
                files_needing_ids=[],
                ids_injected=0,
                message="Workspace directory does not exist",
            )

        storage = FileStorageService(db)

        # Run reindex with the inject_ids flag
        counts = await storage.reindex_workspace_files(
            workspace_path, inject_ids=request.inject_ids
        )

        await db.commit()

        files_needing_ids = counts.get("files_needing_ids", [])
        if not isinstance(files_needing_ids, list):
            files_needing_ids = []

        files_indexed = counts.get("files_indexed", 0)
        if not isinstance(files_indexed, int):
            files_indexed = 0

        # Count IDs injected (when inject_ids=True, this is the files that were modified)
        ids_injected = 0
        if request.inject_ids:
            # In inject mode, files_needing_ids will be empty because they were fixed
            # We need to track this differently - for now use a simple approach
            ids_injected = counts.get("ids_injected", 0)
            if not isinstance(ids_injected, int):
                ids_injected = 0

        if request.inject_ids:
            message = f"Reindexed {files_indexed} files, injected IDs into {ids_injected} files"
        else:
            message = f"Reindexed {files_indexed} files, found {len(files_needing_ids)} files needing IDs"

        logger.info(f"Reindex completed: {message}")

        # Update notification to completed
        if request.notification_id:
            logger.info(f"Updating notification {request.notification_id} to COMPLETED")
            update_result = await notification_service.update_notification(
                request.notification_id,
                NotificationUpdate(
                    status=NotificationStatus.COMPLETED,
                    description=message,
                    result={
                        "files_indexed": files_indexed,
                        "ids_injected": ids_injected,
                    },
                ),
            )
            logger.info(f"Notification update result: {update_result}")

        return ReindexResponse(
            status="completed",
            files_indexed=files_indexed,
            files_needing_ids=files_needing_ids,
            ids_injected=ids_injected,
            message=message,
        )

    except Exception as e:
        logger.error(f"Error running reindex: {e}", exc_info=True)

        # Update notification to failed
        if request.notification_id:
            await notification_service.update_notification(
                request.notification_id,
                NotificationUpdate(
                    status=NotificationStatus.FAILED,
                    error=str(e),
                ),
            )

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to run reindex: {str(e)}",
        )
