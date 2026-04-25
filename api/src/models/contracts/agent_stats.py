"""Agent stats response models."""
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel


class AgentStatsResponse(BaseModel):
    agent_id: UUID
    runs_7d: int
    success_rate: float
    avg_duration_ms: int
    total_cost_7d: Decimal
    last_run_at: datetime | None
    runs_by_day: list[int]
    needs_review: int
    unreviewed: int


class FleetStatsResponse(BaseModel):
    total_runs: int
    avg_success_rate: float
    total_cost_7d: Decimal
    active_agents: int
    needs_review: int
