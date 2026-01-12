"""
Jobs API Router.

Provides HTTP endpoints for polling job status/results.
Primary use case: E2E tests and fallback when WebSockets unavailable.
"""

import json
import logging

from fastapi import APIRouter
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/jobs", tags=["Jobs"])


class JobStatusResponse(BaseModel):
    """Response for job status query."""

    status: str = Field(
        description="Job status: 'pending', 'running', 'completed', 'failed', etc."
    )
    message: str | None = Field(default=None, description="Status message")
    # Additional fields from completion (when available)
    pulled: int = Field(default=0, description="Number of files pulled (git sync)")
    pushed: int = Field(default=0, description="Number of files pushed (git sync)")
    commit_sha: str | None = Field(default=None, description="Commit SHA if created")
    error: str | None = Field(default=None, description="Error message if failed")


@router.get(
    "/{job_id}",
    response_model=JobStatusResponse,
    summary="Get job status",
    description="Poll for job completion status. Returns 'pending' if job not yet complete.",
)
async def get_job_status(job_id: str) -> JobStatusResponse:
    """
    Get the status of a job by ID.

    Jobs are stored in Redis when they complete (5-minute TTL).
    Returns 'pending' if job hasn't completed or result expired.

    Used primarily for:
    - E2E tests that can't use WebSockets
    - Fallback when WebSocket connection fails
    """
    from src.core.redis_client import get_redis_client

    try:
        redis_client = get_redis_client()
        if redis_client:
            result_key = f"bifrost:job:{job_id}"
            data = await redis_client.get(result_key)
            logger.debug(f"Job {job_id} Redis data: {data[:100] if data else 'None'}...")
            if data:
                result = json.loads(data)
                logger.info(f"Job {job_id} found with status: {result.get('status')}")
                return JobStatusResponse(
                    status=result.get("status", "unknown"),
                    message=result.get("message"),
                    pulled=result.get("pulled", 0),
                    pushed=result.get("pushed", 0),
                    commit_sha=result.get("commit_sha"),
                    error=result.get("error"),
                )
        else:
            logger.warning(f"Redis client is None for job {job_id}")
    except Exception as e:
        logger.warning(f"Error fetching job status from Redis: {e}")

    # Job not found or not yet complete
    return JobStatusResponse(status="pending")
