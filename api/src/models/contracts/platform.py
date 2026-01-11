"""
Platform admin contracts for worker management API.

Provides Pydantic models for:
- Worker/pool registration and heartbeat data
- Process recycle requests
- Queue status tracking
- Pool statistics
- Stuck execution history
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


# =============================================================================
# Worker/Pool Models
# =============================================================================

# Process states from ProcessPoolManager
ProcessState = Literal["idle", "busy", "killed"]


class ProcessInfo(BaseModel):
    """Information about a worker process in the pool."""

    process_id: str = Field(..., description="Internal process handle ID (e.g., 'process-1')")
    pid: int = Field(..., description="OS process ID")
    state: ProcessState = Field(..., description="Current process state: idle, busy, or killed")
    current_execution_id: str | None = Field(
        default=None,
        description="Execution ID if state is busy"
    )
    executions_completed: int = Field(
        default=0,
        description="Number of executions this process has completed"
    )
    started_at: str | None = Field(
        default=None,
        description="ISO timestamp when process was spawned"
    )
    uptime_seconds: float = Field(
        default=0,
        description="Seconds since process was spawned"
    )
    memory_mb: float = Field(
        default=0,
        description="Process memory usage in MB"
    )
    is_alive: bool = Field(
        default=True,
        description="Whether the OS process is still running"
    )


class PoolSummary(BaseModel):
    """Summary of a process pool for list endpoint."""

    worker_id: str = Field(..., description="Pool identifier (container hostname)")
    hostname: str | None = None
    status: str | None = Field(
        default=None,
        description="Pool status: online or offline"
    )
    started_at: str | None = None
    pool_size: int = Field(default=0, description="Total number of processes in pool")
    idle_count: int = Field(default=0, description="Number of idle processes")
    busy_count: int = Field(default=0, description="Number of busy processes")
    last_heartbeat: str | None = None


class PoolDetail(BaseModel):
    """Detailed pool information including all processes."""

    worker_id: str
    hostname: str | None = None
    status: str | None = None
    started_at: str | None = None
    last_heartbeat: str | None = None
    min_workers: int = Field(default=2, description="Minimum pool size")
    max_workers: int = Field(default=10, description="Maximum pool size")
    processes: list[ProcessInfo] = Field(default_factory=list)


class PoolsListResponse(BaseModel):
    """Response for list pools endpoint."""

    pools: list[PoolSummary]
    total: int


class PoolStatsResponse(BaseModel):
    """Response for pool statistics endpoint."""

    total_pools: int = Field(..., description="Number of registered pools")
    total_processes: int = Field(..., description="Total processes across all pools")
    total_idle: int = Field(..., description="Total idle processes across all pools")
    total_busy: int = Field(..., description="Total busy processes across all pools")


class RecycleProcessRequest(BaseModel):
    """Request to recycle a specific process in a pool."""

    reason: str | None = Field(
        default=None,
        description="Reason for the recycle request (for audit logging)"
    )


class RecycleProcessResponse(BaseModel):
    """Response from recycle request."""

    success: bool
    message: str
    worker_id: str
    process_id: str | None = None
    pid: int | None = None


class PoolConfigUpdateRequest(BaseModel):
    """Request to update pool configuration."""

    min_workers: int = Field(
        ...,
        ge=2,
        description="Minimum worker processes to maintain (must be >= 2)"
    )
    max_workers: int = Field(
        ...,
        ge=2,
        description="Maximum worker processes for scaling"
    )

    def model_post_init(self, __context: object) -> None:
        """Validate min_workers <= max_workers."""
        if self.min_workers > self.max_workers:
            raise ValueError(
                f"min_workers ({self.min_workers}) cannot be greater than max_workers ({self.max_workers})"
            )


class PoolConfigUpdateResponse(BaseModel):
    """Response from pool config update."""

    success: bool
    message: str
    worker_id: str
    old_min: int
    old_max: int
    new_min: int
    new_max: int
    processes_spawned: int = 0
    processes_marked_for_removal: int = 0


class RecycleAllRequest(BaseModel):
    """Request to recycle all processes in a pool."""

    reason: str | None = Field(
        default=None,
        description="Reason for the recycle request (for audit logging)"
    )


class RecycleAllResponse(BaseModel):
    """Response from recycle-all request."""

    success: bool
    message: str
    worker_id: str
    processes_affected: int


# =============================================================================
# Queue Models
# =============================================================================


class QueueItem(BaseModel):
    """An item in the execution queue."""

    execution_id: str
    position: int
    queued_at: str | None = None


class QueueStatusResponse(BaseModel):
    """Response for queue status endpoint."""

    total: int
    items: list[QueueItem]


# =============================================================================
# Stuck History Models
# =============================================================================


class StuckWorkflowStats(BaseModel):
    """Aggregated stuck execution statistics for a workflow."""

    workflow_id: str
    workflow_name: str
    stuck_count: int
    last_stuck_at: datetime


class StuckHistoryResponse(BaseModel):
    """Response for stuck history endpoint."""

    hours: int
    workflows: list[StuckWorkflowStats]


