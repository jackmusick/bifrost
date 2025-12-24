"""ROI settings and reports contracts."""

from pydantic import BaseModel, Field


class ROISettingsResponse(BaseModel):
    """Response model for ROI settings."""

    time_saved_unit: str = Field(
        default="minutes",
        description="Display label for time saved (stored in minutes)",
    )
    value_unit: str = Field(
        default="USD",
        description="Display label for value (ISP defines meaning)",
    )


class ROISettingsRequest(BaseModel):
    """Request model for updating ROI settings."""

    time_saved_unit: str = Field(
        description="Display label for time saved",
    )
    value_unit: str = Field(
        description="Display label for value (e.g., 'USD', 'credits', 'points')",
    )


# =============================================================================
# ROI Reports
# =============================================================================


class ROISummaryResponse(BaseModel):
    """Summary of ROI for a period."""

    start_date: str
    end_date: str
    total_executions: int
    successful_executions: int
    total_time_saved: int  # in minutes
    total_value: float
    time_saved_unit: str
    value_unit: str


class WorkflowROIEntry(BaseModel):
    """ROI data for a single workflow."""

    workflow_id: str
    workflow_name: str
    execution_count: int
    success_count: int
    time_saved_per_execution: int  # workflow default
    value_per_execution: float  # workflow default
    total_time_saved: int
    total_value: float


class ROIByWorkflowResponse(BaseModel):
    """Workflow breakdown of ROI."""

    workflows: list[WorkflowROIEntry]
    total_workflows: int
    time_saved_unit: str
    value_unit: str


class OrganizationROIEntry(BaseModel):
    """ROI data for a single organization."""

    organization_id: str
    organization_name: str
    execution_count: int
    success_count: int
    total_time_saved: int
    total_value: float


class ROIByOrganizationResponse(BaseModel):
    """Organization breakdown of ROI."""

    organizations: list[OrganizationROIEntry]
    time_saved_unit: str
    value_unit: str


class ROITrendEntry(BaseModel):
    """ROI data for a single time period."""

    period: str  # date string
    execution_count: int
    success_count: int
    time_saved: int
    value: float


class ROITrendsResponse(BaseModel):
    """Time series ROI data."""

    entries: list[ROITrendEntry]
    granularity: str
    time_saved_unit: str
    value_unit: str
