"""
Email Configuration Pydantic Models

Request/response models for email workflow configuration.
"""

from datetime import datetime

from pydantic import BaseModel, Field


class EmailWorkflowConfigRequest(BaseModel):
    """Request to set the email workflow."""

    workflow_id: str = Field(
        ...,
        description="UUID of the workflow to use for sending emails",
    )


class EmailWorkflowConfigResponse(BaseModel):
    """Email workflow configuration response."""

    workflow_id: str
    workflow_name: str
    is_configured: bool = True
    configured_at: datetime | None = None
    configured_by: str | None = None


class EmailWorkflowValidationResponse(BaseModel):
    """Response from validating a workflow for email sending."""

    valid: bool
    message: str
    workflow_name: str | None = None
    missing_params: list[str] | None = None
    extra_required_params: list[str] | None = None
