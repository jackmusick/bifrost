"""
NinjaOne Extension Helpers

Extension functions for the auto-generated NinjaOne SDK module.
Provides remote PowerShell execution via a fetch-and-execute pattern:
script content is stored in a table, a pre-deployed NinjaRMM script
fetches it, executes, and posts results back via webhook.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import uuid4

from bifrost import tables, config, UserError
from modules import ninjaone

logger = logging.getLogger(__name__)

SCRIPT_JOBS_TABLE = "script_jobs"


@dataclass
class PowerShellResult:
    """Result of a remote PowerShell execution."""

    job_id: str
    status: str  # "completed", "failed", "pending", "running", "timeout"
    result: str | None = None
    error: str | None = None
    device_id: int | None = None


async def _resolve_script_id(device_id: int) -> int:
    """
    Find the pre-deployed "Bifrost (Windows)" script ID via NinjaRMM scripting options.

    Checks config cache first. On miss, queries the device's scripting options
    and caches the result for future calls.
    """
    cached_id = await config.get("ninja_script_id")
    if cached_id:
        return int(cached_id)

    script_name = await config.get("ninja_script_name", default="Bifrost (Windows)")

    try:
        options = await ninjaone.get_options(str(device_id))
    except Exception as e:
        raise UserError(
            f"Failed to query scripting options for device {device_id}: {e}\n"
            "Ensure the device is online and supports scripting."
        )

    scripts = []
    if hasattr(options, "scripts"):
        scripts = options.scripts or []
    elif isinstance(options, dict):
        scripts = options.get("scripts", [])

    for script in scripts:
        name = script.get("name", "") if isinstance(script, dict) else getattr(script, "name", "")
        if name == script_name:
            script_id = script.get("id") if isinstance(script, dict) else getattr(script, "id", None)
            if script_id:
                await config.set("ninja_script_id", int(script_id))
                logger.info(f"Resolved script '{script_name}' -> ID {script_id}")
                return int(script_id)

    raise UserError(
        f"Script '{script_name}' not found in NinjaRMM scripting options for device {device_id}.\n"
        "Deploy the 'Bifrost (Windows)' script to the NinjaRMM script library first."
    )


def _check_required_config(values: dict[str, str | None]) -> None:
    """Raise UserError if any required config values are missing."""
    missing = [k for k, v in values.items() if not v]
    if missing:
        raise UserError(
            f"Missing required NinjaOne config keys: {', '.join(missing)}.\n"
            "Set them with: config.set('key', 'value')"
        )


async def execute_powershell(
    device_id: int,
    script_content: str,
    *,
    params: dict | None = None,
    wait_seconds: int | None = None,
    run_as: str | None = None,
) -> PowerShellResult:
    """
    Execute a PowerShell script on a remote device via NinjaRMM.

    Flow:
    1. Store script content in script_jobs table with a new UUID.
    2. Trigger the pre-deployed NinjaRMM script on the device, passing
       the job_id plus the get/post URLs so the device can fetch content
       and report results.
    3. If wait_seconds is set, poll the table until completed/failed/timeout.
    """
    get_url = await config.get("ninja_get_script_endpoint")
    post_url = await config.get("ninja_post_result_webhook_url")
    api_key = await config.get("ninja_bifrost_api_key")
    _check_required_config({
        "ninja_get_script_endpoint": get_url,
        "ninja_post_result_webhook_url": post_url,
        "ninja_bifrost_api_key": api_key,
    })

    if not run_as:
        run_as = await config.get("ninja_run_as", default="system")

    job_id = str(uuid4())
    await tables.insert(
        SCRIPT_JOBS_TABLE,
        {
            "script_content": script_content,
            "params": params,
            "device_id": device_id,
            "status": "pending",
            "result": None,
            "error": None,
            "created_at": datetime.now(timezone.utc).isoformat(),
        },
        id=job_id,
    )
    logger.info(f"Created script job {job_id} for device {device_id}")

    script_id = await _resolve_script_id(device_id)

    try:
        await ninjaone.create_run(
            str(device_id),
            data={
                "id": script_id,
                "parameters": f"-job_id {job_id} -get_url {get_url} -post_url {post_url} -api_key {api_key}",
                "runAs": run_as,
            },
        )
    except Exception as e:
        await tables.update(SCRIPT_JOBS_TABLE, job_id, {"status": "failed", "error": str(e)})
        raise UserError(f"Failed to trigger script on device {device_id}: {e}")

    logger.info(f"Triggered script {script_id} on device {device_id} (job {job_id})")

    if wait_seconds is None:
        return PowerShellResult(
            job_id=job_id,
            status="pending",
            device_id=device_id,
        )

    return await _poll_job(job_id, device_id, wait_seconds)


async def _poll_job(job_id: str, device_id: int, wait_seconds: int) -> PowerShellResult:
    """Poll script_jobs table until job completes, fails, or times out."""
    poll_interval = 3
    elapsed = 0

    while elapsed < wait_seconds:
        await asyncio.sleep(poll_interval)
        elapsed += poll_interval

        doc = await tables.get(SCRIPT_JOBS_TABLE, job_id)
        if not doc:
            raise UserError(f"Script job {job_id} disappeared from table")

        status = doc.data.get("status", "pending")

        if status in ("completed", "failed"):
            logger.info(f"Job {job_id} finished with status={status} after {elapsed}s")
            return PowerShellResult(
                job_id=job_id,
                status=status,
                result=doc.data.get("result"),
                error=doc.data.get("error"),
                device_id=device_id,
            )

    # Don't mutate status — device may still complete the job after we stop waiting
    logger.warning(f"Job {job_id} poll timed out after {wait_seconds}s (job still active)")
    return PowerShellResult(
        job_id=job_id,
        status="timeout",
        device_id=device_id,
    )
