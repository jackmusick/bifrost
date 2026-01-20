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
from sqlalchemy import select
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
from src.models.orm import (
    AppFile,
    AppFileDependency,
    Application,
    Form,
    Workflow,
)
from src.services.app_dependencies import parse_dependencies
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


class AppDependencyIssue(BaseModel):
    """A missing dependency issue in an app."""

    app_id: str
    app_name: str
    app_slug: str
    file_path: str
    dependency_type: str
    dependency_id: str


class AppDependencyScanResponse(BaseModel):
    """Response from app dependency scan."""

    apps_scanned: int
    files_scanned: int
    dependencies_rebuilt: int
    issues_found: int
    issues: list[AppDependencyIssue]
    notification_created: bool


@router.post(
    "/scan-app-dependencies",
    response_model=AppDependencyScanResponse,
    summary="Rebuild app dependencies",
    description="Rebuild AppFileDependency table by parsing all app source files (Platform admin only)",
)
async def scan_app_dependencies(
    ctx: Context,
    user: CurrentSuperuser,
    db: AsyncSession = Depends(get_db),
) -> AppDependencyScanResponse:
    """
    Rebuild app file dependencies from source code.

    This endpoint:
    1. Clears all existing AppFileDependency records
    2. Parses all app file source code to find useWorkflow(), useForm(), and
       useDataProvider() calls
    3. Inserts new AppFileDependency records for each found dependency
    4. Reports any dependencies that reference non-existent entities

    This populates the data used by the dependency graph feature.

    Creates a platform admin notification if issues are found.

    Returns:
        AppDependencyScanResponse with rebuild results
    """
    from sqlalchemy import delete as sql_delete

    from src.models.orm.applications import AppVersion

    try:
        # Step 1: Clear all existing app file dependencies
        await db.execute(sql_delete(AppFileDependency))
        logger.info("Cleared existing AppFileDependency records")

        # Step 2: Get all app files with their app info
        files_result = await db.execute(
            select(AppFile, Application)
            .join(AppVersion, AppFile.app_version_id == AppVersion.id)
            .join(Application, AppVersion.application_id == Application.id)
        )
        file_rows = files_result.all()

        all_issues: list[AppDependencyIssue] = []
        total_deps_rebuilt = 0
        files_scanned = 0
        apps_seen: set[str] = set()

        for file, app in file_rows:
            apps_seen.add(str(app.id))
            files_scanned += 1

            # Parse dependencies from source code
            if not file.source:
                continue

            dependencies = parse_dependencies(file.source)

            for dep_type, dep_id in dependencies:
                # Step 3: Insert new dependency record
                dependency = AppFileDependency(
                    app_file_id=file.id,
                    dependency_type=dep_type,
                    dependency_id=dep_id,
                )
                db.add(dependency)
                total_deps_rebuilt += 1

                # Step 4: Check if the referenced entity exists
                if dep_type == "workflow":
                    # Workflows are in Workflow table with type='workflow'
                    result = await db.execute(
                        select(Workflow.id).where(
                            Workflow.id == dep_id,
                            Workflow.type == "workflow",
                        )
                    )
                    exists = result.scalar_one_or_none() is not None

                elif dep_type == "form":
                    # Forms are in their own table
                    result = await db.execute(
                        select(Form.id).where(Form.id == dep_id)
                    )
                    exists = result.scalar_one_or_none() is not None

                elif dep_type == "data_provider":
                    # Data providers are in Workflow table with type='data_provider'
                    result = await db.execute(
                        select(Workflow.id).where(
                            Workflow.id == dep_id,
                            Workflow.type == "data_provider",
                        )
                    )
                    exists = result.scalar_one_or_none() is not None

                else:
                    # Unknown dependency type, still record it but skip validation
                    continue

                if not exists:
                    all_issues.append(
                        AppDependencyIssue(
                            app_id=str(app.id),
                            app_name=app.name,
                            app_slug=app.slug,
                            file_path=file.path,
                            dependency_type=dep_type,
                            dependency_id=str(dep_id),
                        )
                    )

        # Commit all the new dependency records
        await db.commit()

        # Create notification if issues found
        notification_created = False
        if all_issues:
            notification_service = get_notification_service()

            apps_with_issues = len({i.app_slug for i in all_issues})
            title = f"Missing App Dependencies: {apps_with_issues} app(s)"

            # Check for existing notification to avoid duplicates
            existing = await notification_service.find_admin_notification_by_title(
                title=title,
                category=NotificationCategory.SYSTEM,
            )

            if not existing:
                # Build description with first few issues
                app_names = list({i.app_name for i in all_issues})[:3]
                description = f"{len(all_issues)} missing: {', '.join(app_names)}"
                if len(all_issues) > 3:
                    description += "..."

                await notification_service.create_notification(
                    user_id="system",
                    request=NotificationCreate(
                        category=NotificationCategory.SYSTEM,
                        title=title,
                        description=description,
                        metadata={
                            "action": "view_apps",
                            "issues": [
                                {
                                    "app_id": i.app_id,
                                    "app_name": i.app_name,
                                    "app_slug": i.app_slug,
                                    "file_path": i.file_path,
                                    "dependency_type": i.dependency_type,
                                    "dependency_id": i.dependency_id,
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
            f"App dependency rebuild completed: scanned {len(apps_seen)} apps, "
            f"{files_scanned} files, rebuilt {total_deps_rebuilt} dependencies, "
            f"found {len(all_issues)} issues"
        )

        return AppDependencyScanResponse(
            apps_scanned=len(apps_seen),
            files_scanned=files_scanned,
            dependencies_rebuilt=total_deps_rebuilt,
            issues_found=len(all_issues),
            issues=all_issues,
            notification_created=notification_created,
        )

    except Exception as e:
        logger.error(f"Error rebuilding app dependencies: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to rebuild app dependencies: {str(e)}",
        )
