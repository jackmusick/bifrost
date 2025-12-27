"""
Email Configuration Admin Router

Admin endpoints for managing email workflow configuration.
Requires platform admin access.
"""

import logging

from fastapi import APIRouter, HTTPException, status

from src.core.auth import CurrentActiveUser, RequirePlatformAdmin
from src.core.database import DbSession
from src.models.contracts.email import (
    EmailWorkflowConfigRequest,
    EmailWorkflowConfigResponse,
    EmailWorkflowValidationResponse,
)
from src.services.email_service import EmailService

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/admin/email",
    tags=["Email Configuration"],
    dependencies=[RequirePlatformAdmin],
)


@router.get("/config")
async def get_email_config(
    db: DbSession,
    user: CurrentActiveUser,
) -> EmailWorkflowConfigResponse | None:
    """
    Get current email workflow configuration.

    Requires platform admin access.
    """
    service = EmailService(db)
    config = await service.get_config()

    if not config:
        return None

    return EmailWorkflowConfigResponse(
        workflow_id=config.workflow_id,
        workflow_name=config.workflow_name,
        is_configured=config.is_configured,
        configured_at=config.configured_at,
        configured_by=config.configured_by,
    )


@router.post("/config", status_code=status.HTTP_200_OK)
async def set_email_config(
    request: EmailWorkflowConfigRequest,
    db: DbSession,
    user: CurrentActiveUser,
) -> EmailWorkflowConfigResponse:
    """
    Set email workflow configuration.

    Validates the workflow has the correct signature before saving.
    Requires platform admin access.
    """
    service = EmailService(db)

    try:
        config = await service.save_config(
            workflow_id=request.workflow_id,
            updated_by=user.email,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        )

    await db.commit()

    logger.info(f"Email workflow config set by {user.email}: {request.workflow_id}")

    return EmailWorkflowConfigResponse(
        workflow_id=config.workflow_id,
        workflow_name=config.workflow_name,
        is_configured=True,
        configured_at=config.configured_at,
        configured_by=config.configured_by,
    )


@router.delete("/config", status_code=status.HTTP_204_NO_CONTENT)
async def delete_email_config(
    db: DbSession,
    user: CurrentActiveUser,
) -> None:
    """
    Delete email workflow configuration.

    Requires platform admin access.
    """
    service = EmailService(db)
    deleted = await service.delete_config()

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Email configuration not found",
        )

    await db.commit()
    logger.info(f"Email config deleted by {user.email}")


@router.post("/validate/{workflow_id}")
async def validate_email_workflow(
    workflow_id: str,
    db: DbSession,
    user: CurrentActiveUser,
) -> EmailWorkflowValidationResponse:
    """
    Validate a workflow for use as email provider.

    Checks that the workflow has the required signature:
    - Required: recipient (str), subject (str), body (str)
    - Optional: html_body (str | None)

    Requires platform admin access.
    """
    service = EmailService(db)
    result = await service.validate_workflow(workflow_id)

    return EmailWorkflowValidationResponse(
        valid=result.valid,
        message=result.message,
        workflow_name=result.workflow_name,
        missing_params=result.missing_params,
        extra_required_params=result.extra_required_params,
    )
