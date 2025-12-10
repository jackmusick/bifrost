"""
Packages Router

Python package management for the workflow runtime.
Allows listing, installing, and uninstalling Python packages.
"""

import asyncio
import logging
import json
import uuid

from fastapi import APIRouter, HTTPException, status

from src.models import (
    InstallPackageRequest,
    InstalledPackage,
    InstalledPackagesResponse,
    PackageInstallResponse,
    PackageUpdate,
    PackageUpdatesResponse,
)
from src.core.auth import Context, CurrentActiveUser, CurrentSuperuser
from src.jobs.rabbitmq import publish_broadcast

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/packages", tags=["Packages"])


# =============================================================================
# Helper Functions
# =============================================================================


async def check_package_updates() -> list[PackageUpdate]:
    """
    Check for available package updates using pip.

    Uses async subprocess to avoid blocking the event loop.

    Returns:
        List of packages with available updates
    """
    try:
        proc = await asyncio.create_subprocess_exec(
            "pip", "list", "--outdated", "--format=json",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=60)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            logger.error("pip list --outdated timed out")
            return []

        if proc.returncode != 0:
            logger.error(f"pip list --outdated failed: {stderr.decode()}")
            return []

        packages_data = json.loads(stdout.decode())
        return [
            PackageUpdate(
                name=pkg["name"],
                current_version=pkg["version"],
                latest_version=pkg["latest_version"],
            )
            for pkg in packages_data
        ]

    except json.JSONDecodeError:
        logger.error("Failed to parse pip outdated output")
        return []
    except Exception as e:
        logger.error(f"Error checking package updates: {str(e)}")
        return []


async def get_installed_packages() -> list[InstalledPackage]:
    """
    Get list of installed Python packages.

    Uses async subprocess to avoid blocking the event loop.
    """
    try:
        proc = await asyncio.create_subprocess_exec(
            "pip", "list", "--format=json",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            logger.error("pip list timed out")
            return []

        if proc.returncode != 0:
            logger.error(f"pip list failed: {stderr.decode()}")
            return []

        packages_data = json.loads(stdout.decode())
        return [
            InstalledPackage(name=pkg["name"], version=pkg["version"])
            for pkg in packages_data
        ]

    except json.JSONDecodeError:
        logger.error("Failed to parse pip output")
        return []
    except Exception as e:
        logger.error(f"Error getting installed packages: {str(e)}")
        return []


# =============================================================================
# HTTP Endpoints
# =============================================================================


@router.get(
    "",
    response_model=InstalledPackagesResponse,
    summary="List installed packages",
    description="List all installed Python packages",
)
async def list_packages(
    ctx: Context,
    user: CurrentActiveUser,
) -> InstalledPackagesResponse:
    """
    List all installed Python packages.

    Returns:
        List of installed packages with versions
    """
    try:
        packages = await get_installed_packages()
        logger.info(f"Listed {len(packages)} installed packages")
        return InstalledPackagesResponse(packages=packages)

    except Exception as e:
        logger.error(f"Error listing packages: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list packages",
        )


@router.get(
    "/updates",
    response_model=PackageUpdatesResponse,
    summary="Check for package updates",
    description="Check for available updates to installed packages",
)
async def check_updates(
    ctx: Context,
    user: CurrentActiveUser,
) -> PackageUpdatesResponse:
    """
    Check for available package updates.

    Returns:
        List of packages with available updates
    """
    try:
        updates = await check_package_updates()
        logger.info(f"Found {len(updates)} package updates available")
        return PackageUpdatesResponse(updates=updates)

    except Exception as e:
        logger.error(f"Error checking package updates: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to check for package updates",
        )


@router.post(
    "/install",
    response_model=PackageInstallResponse,
    summary="Install a Python package",
    description="Install a Python package (Platform admin only)",
)
async def install_package(
    request: InstallPackageRequest,
    ctx: Context,
    user: CurrentSuperuser,
) -> PackageInstallResponse:
    """
    Install a Python package via RabbitMQ job queue.

    Queues the installation job and returns immediately. Installation progress
    is streamed via WebSocket to the package:{user_id} channel.

    Args:
        request: Package install request with name and optional version

    Returns:
        Installation response with job_id for tracking
    """
    try:
        job_id = str(uuid.uuid4())
        package_spec = request.package
        if request.version:
            package_spec = f"{request.package}=={request.version}"

        logger.info(f"Broadcasting package installation: {package_spec}", extra={"job_id": job_id})

        # Broadcast installation to all workers via fanout exchange
        # The connection_id is the user_id so they can subscribe to package:{user_id}
        await publish_broadcast(
            exchange_name="package-installations",
            message={
                "type": "package_install",
                "job_id": job_id,
                "package": request.package if request.package else None,
                "version": request.version if request.version else None,
                "connection_id": str(user.user_id),  # User subscribes to package:{user_id}
                "user_id": str(user.user_id),
                "user_email": user.email,
            },
        )

        logger.info(f"Package installation broadcast: {package_spec}", extra={"job_id": job_id})

        return PackageInstallResponse(
            job_id=job_id,
            status="queued",
        )

    except Exception as e:
        logger.error(f"Error queueing package installation: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to queue package installation",
        )


@router.delete(
    "/{package_name}",
    summary="Uninstall a Python package",
    description="Uninstall a Python package (Platform admin only)",
)
async def uninstall_package(
    package_name: str,
    ctx: Context,
    user: CurrentSuperuser,
) -> dict:
    """
    Uninstall a Python package.

    In production, this would queue a RabbitMQ job for background uninstall.
    For now, it attempts direct uninstallation using async subprocess.

    Args:
        package_name: Name of the package to uninstall

    Returns:
        Confirmation message
    """
    try:
        logger.info(f"Uninstalling package: {package_name}")

        # In production, this would be queued as a job
        # For now, attempt direct uninstallation using async subprocess
        proc = await asyncio.create_subprocess_exec(
            "pip", "uninstall", "-y", package_name,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=300)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            logger.error(f"Package uninstallation timed out: {package_name}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Package uninstallation timed out",
            )

        if proc.returncode != 0:
            logger.error(f"pip uninstall failed: {stderr.decode()}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Package uninstallation failed: {stderr.decode()}",
            )

        logger.info(f"Successfully uninstalled package: {package_name}")

        return {
            "message": f"Package '{package_name}' uninstalled successfully",
            "status": "uninstalled",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error uninstalling package: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to uninstall package",
        )
