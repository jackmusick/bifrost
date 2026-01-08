"""
Maintenance Router

API endpoints for workspace maintenance operations.
Platform admin resource - no org scoping.
"""

import asyncio
import logging
from pathlib import Path
from typing import Any

import aiofiles
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.auth import Context, CurrentSuperuser
from src.core.database import get_db
from src.core.paths import WORKSPACE_PATH
from src.models import (
    DocsIndexResponse,
    MaintenanceStatus,
    ReindexJobResponse,
    ReindexRequest,
)
from src.models.contracts.notifications import (
    NotificationCategory,
    NotificationCreate,
    NotificationStatus,
)
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
        - total_files: Total number of Python files in workspace
        - last_reindex: Timestamp of last reindex (not tracked currently)
    """
    from src.services.editor.file_filter import is_excluded_path

    total_files = 0

    try:
        # Count Python files in workspace
        workspace_path = Path(WORKSPACE_PATH)
        if not workspace_path.exists():
            return MaintenanceStatus(
                total_files=0,
                last_reindex=None,
            )

        # Get all Python files (rglob is I/O bound, run in thread)
        python_files = await asyncio.to_thread(lambda: list(workspace_path.rglob("*.py")))

        for file_path in python_files:
            rel_path = str(file_path.relative_to(workspace_path))

            # Skip excluded paths
            if is_excluded_path(rel_path):
                continue

            total_files += 1

        return MaintenanceStatus(
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
    response_model=ReindexJobResponse,
    summary="Start workspace reindex (non-blocking)",
    description="Queue a reindex job with reference validation (Platform admin only)",
)
async def run_reindex(
    ctx: Context,
    user: CurrentSuperuser,
    request: ReindexRequest,
) -> ReindexJobResponse:
    """
    Start a non-blocking reindex operation.

    The reindex runs in the scheduler container and publishes progress via WebSocket.
    Connect to `reindex:{job_id}` channel to receive updates.

    Features:
        - Downloads all workspace files from S3
        - Indexes workflows/data_providers to database
        - Validates form/agent references point to existing workflows
        - Reports errors for unresolvable references

    Returns:
        ReindexJobResponse with job_id for tracking via WebSocket
    """
    from uuid import uuid4

    from src.core.pubsub import publish_reindex_request

    job_id = str(uuid4())

    await publish_reindex_request(
        job_id=job_id,
        user_id=str(user.user_id),
    )

    logger.info(f"Reindex job {job_id} queued by user {user.user_id}")

    return ReindexJobResponse(
        status="queued",
        job_id=job_id,
    )


class SDKScanResponse(BaseModel):
    """Response from SDK reference scan."""

    files_scanned: int
    issues_found: int
    issues: list[dict[str, Any]]
    notification_created: bool


@router.post(
    "/scan-sdk",
    response_model=SDKScanResponse,
    summary="Scan workspace for missing SDK references",
    description="Scan all Python files for missing config.get() and integrations.get() references (Platform admin only)",
)
async def scan_sdk_references(
    ctx: Context,
    user: CurrentSuperuser,
    db: AsyncSession = Depends(get_db),
) -> SDKScanResponse:
    """
    Scan the entire workspace for missing SDK references.

    Detects:
        - config.get("key") calls where "key" doesn't exist in Config table
        - integrations.get("name") calls where "name" doesn't have any IntegrationMapping

    Creates a platform admin notification if issues are found.

    Returns:
        SDKScanResponse with scan results
    """
    from src.services.editor.file_filter import is_excluded_path
    from src.services.sdk_reference_scanner import SDKReferenceScanner

    try:
        workspace_path = Path(WORKSPACE_PATH)
        if not workspace_path.exists():
            return SDKScanResponse(
                files_scanned=0,
                issues_found=0,
                issues=[],
                notification_created=False,
            )

        scanner = SDKReferenceScanner(db)
        all_issues = []
        files_scanned = 0

        # Get all Python files
        python_files = await asyncio.to_thread(lambda: list(workspace_path.rglob("*.py")))

        for file_path in python_files:
            rel_path = str(file_path.relative_to(workspace_path))

            # Skip excluded paths
            if is_excluded_path(rel_path):
                continue

            files_scanned += 1

            try:
                async with aiofiles.open(file_path, "r", encoding="utf-8", errors="replace") as f:
                    content = await f.read()
                issues = await scanner.scan_file(rel_path, content)
                all_issues.extend(issues)
            except Exception as e:
                logger.warning(f"Failed to scan {rel_path} for SDK issues: {e}")

        # Create notification if issues found
        notification_created = False
        if all_issues:
            notification_service = get_notification_service()

            files_with_issues = len({i.file_path for i in all_issues})
            title = f"Missing SDK References: {files_with_issues} file(s)"

            # Check for existing notification to avoid duplicates
            existing = await notification_service.find_admin_notification_by_title(
                title=title,
                category=NotificationCategory.SYSTEM,
            )

            if not existing:
                # Build description with first few issues
                issue_keys = [i.key for i in all_issues[:3]]
                description = f"{len(all_issues)} missing: {', '.join(issue_keys)}"
                if len(all_issues) > 3:
                    description += "..."

                await notification_service.create_notification(
                    user_id="system",
                    request=NotificationCreate(
                        category=NotificationCategory.SYSTEM,
                        title=title,
                        description=description,
                        metadata={
                            "action": "view_file",
                            "file_path": all_issues[0].file_path,
                            "line_number": all_issues[0].line_number,
                            "issues": [
                                {
                                    "type": i.issue_type,
                                    "key": i.key,
                                    "line": i.line_number,
                                    "file": i.file_path,
                                }
                                for i in all_issues
                            ],
                        },
                    ),
                    for_admins=True,
                    initial_status=NotificationStatus.AWAITING_ACTION,
                )
                notification_created = True

        logger.info(
            f"SDK scan completed: scanned {files_scanned} files, "
            f"found {len(all_issues)} issues"
        )

        return SDKScanResponse(
            files_scanned=files_scanned,
            issues_found=len(all_issues),
            issues=[
                {
                    "file_path": i.file_path,
                    "line_number": i.line_number,
                    "issue_type": i.issue_type,
                    "key": i.key,
                }
                for i in all_issues
            ],
            notification_created=notification_created,
        )

    except Exception as e:
        logger.error(f"Error running SDK scan: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to run SDK scan: {str(e)}",
        )


@router.post(
    "/index-docs",
    response_model=DocsIndexResponse,
    summary="Index platform documentation",
    description="Manually trigger indexing of Bifrost platform documentation into the knowledge store (Platform admin only)",
)
async def index_documentation(
    ctx: Context,
    user: CurrentSuperuser,
    db: AsyncSession = Depends(get_db),
) -> DocsIndexResponse:
    """
    Manually index platform documentation into the knowledge store.

    This indexes all .txt files from the bundled documentation into embeddings
    for use by the Coding Assistant. Uses content hashing to avoid re-indexing
    unchanged files.

    Requires:
        - Platform admin access
        - Embeddings to be configured (OpenAI API key)

    Returns:
        DocsIndexResponse with indexing statistics
    """
    import time

    from src.services.docs_indexer import index_platform_docs

    start_time = time.time()

    try:
        result = await index_platform_docs()
        duration_ms = int((time.time() - start_time) * 1000)

        if result["status"] == "skipped":
            return DocsIndexResponse(
                status="skipped",
                files_indexed=0,
                files_unchanged=0,
                files_deleted=0,
                duration_ms=duration_ms,
                message=result.get("reason", "Indexing skipped"),
            )

        if result["status"] == "complete":
            indexed = result.get("indexed", 0)
            skipped = result.get("skipped", 0)
            deleted = result.get("deleted", 0)

            parts = [f"Indexed {indexed} files"]
            if skipped > 0:
                parts.append(f"{skipped} unchanged")
            if deleted > 0:
                parts.append(f"{deleted} orphaned removed")
            message = ", ".join(parts)

            return DocsIndexResponse(
                status="complete",
                files_indexed=indexed,
                files_unchanged=skipped,
                files_deleted=deleted,
                duration_ms=duration_ms,
                message=message,
            )

        return DocsIndexResponse(
            status="failed",
            duration_ms=duration_ms,
            message=f"Unexpected result: {result}",
        )

    except Exception as e:
        logger.error(f"Error indexing documentation: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to index documentation: {str(e)}",
        )
