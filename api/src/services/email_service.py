"""
Email Service

Manages email workflow configuration and provides send_email() function
that delegates to the configured workflow.

Pattern follows LLMConfigService for SystemConfig storage.
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.orm import SystemConfig, Workflow

logger = logging.getLogger(__name__)

# SystemConfig keys
EMAIL_CONFIG_CATEGORY = "email"
EMAIL_CONFIG_KEY = "workflow_config"

# Required email workflow signature
REQUIRED_PARAMS = {"recipient", "subject", "body"}
OPTIONAL_PARAMS = {"html_body"}


@dataclass
class EmailWorkflowConfig:
    """Email workflow configuration."""

    workflow_id: str
    workflow_name: str
    configured_at: datetime | None = None
    configured_by: str | None = None
    is_configured: bool = True


@dataclass
class EmailValidationResult:
    """Result of validating a workflow for email sending."""

    valid: bool
    message: str
    workflow_name: str | None = None
    missing_params: list[str] | None = None
    extra_required_params: list[str] | None = None


@dataclass
class SendEmailResult:
    """Result of sending an email."""

    success: bool
    execution_id: str | None = None
    error: str | None = None


class EmailService:
    """
    Service for managing email workflow configuration.

    Stores configuration in system_configs table with:
    - category: "email"
    - key: "workflow_config"
    - value_json: JSON object with workflow_id and metadata
    - organization_id: NULL (platform-level only)
    """

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_config(self) -> EmailWorkflowConfig | None:
        """Get current email workflow configuration."""
        result = await self.session.execute(
            select(SystemConfig).where(
                SystemConfig.category == EMAIL_CONFIG_CATEGORY,
                SystemConfig.key == EMAIL_CONFIG_KEY,
                SystemConfig.organization_id.is_(None),
            )
        )
        config = result.scalars().first()

        if not config or not config.value_json:
            return None

        data = config.value_json
        configured_at = None
        if data.get("configured_at"):
            try:
                configured_at = datetime.fromisoformat(data["configured_at"])
            except (ValueError, TypeError):
                pass

        return EmailWorkflowConfig(
            workflow_id=data["workflow_id"],
            workflow_name=data.get("workflow_name", "unknown"),
            configured_at=configured_at,
            configured_by=data.get("configured_by"),
            is_configured=True,
        )

    async def validate_workflow(self, workflow_id: str) -> EmailValidationResult:
        """
        Validate that a workflow has the correct signature for email sending.

        Required: recipient (str), subject (str), body (str)
        Optional: html_body (str | None)
        """
        # Look up workflow
        result = await self.session.execute(
            select(Workflow).where(
                Workflow.id == workflow_id,
                Workflow.is_active == True,  # noqa: E712
            )
        )
        workflow = result.scalar_one_or_none()

        if not workflow:
            return EmailValidationResult(
                valid=False,
                message=f"Workflow with ID '{workflow_id}' not found or is inactive",
            )

        # Parse parameters from workflow
        params_schema = workflow.parameters_schema or []
        workflow_params = {p.get("name"): p for p in params_schema}
        workflow_param_names = set(workflow_params.keys())

        # Check required params exist
        missing = REQUIRED_PARAMS - workflow_param_names
        if missing:
            return EmailValidationResult(
                valid=False,
                message=f"Workflow missing required parameters: {', '.join(sorted(missing))}",
                workflow_name=workflow.name,
                missing_params=sorted(missing),
            )

        # Check for extra required params (workflow has required params we don't provide)
        allowed_params = REQUIRED_PARAMS | OPTIONAL_PARAMS
        extra_required = []
        for name, param in workflow_params.items():
            if name not in allowed_params and param.get("required", True):
                extra_required.append(name)

        if extra_required:
            return EmailValidationResult(
                valid=False,
                message=f"Workflow has extra required parameters we cannot provide: {', '.join(sorted(extra_required))}",
                workflow_name=workflow.name,
                extra_required_params=sorted(extra_required),
            )

        return EmailValidationResult(
            valid=True,
            message="Workflow signature is valid for email sending",
            workflow_name=workflow.name,
        )

    async def save_config(
        self,
        workflow_id: str,
        updated_by: str,
    ) -> EmailWorkflowConfig:
        """
        Save email workflow configuration after validation.

        Raises ValueError if workflow doesn't pass validation.
        """
        # Validate first
        validation = await self.validate_workflow(workflow_id)
        if not validation.valid:
            raise ValueError(validation.message)

        now = datetime.utcnow()
        config_data = {
            "workflow_id": workflow_id,
            "workflow_name": validation.workflow_name,
            "configured_at": now.isoformat(),
            "configured_by": updated_by,
        }

        # Check if config exists
        result = await self.session.execute(
            select(SystemConfig).where(
                SystemConfig.category == EMAIL_CONFIG_CATEGORY,
                SystemConfig.key == EMAIL_CONFIG_KEY,
                SystemConfig.organization_id.is_(None),
            )
        )
        existing = result.scalars().first()

        if existing:
            existing.value_json = config_data
            existing.updated_at = now
            existing.updated_by = updated_by
            logger.info(f"Updated email workflow config: {workflow_id}")
        else:
            new_config = SystemConfig(
                id=uuid4(),
                category=EMAIL_CONFIG_CATEGORY,
                key=EMAIL_CONFIG_KEY,
                value_json=config_data,
                value_bytes=None,
                organization_id=None,
                created_by=updated_by,
                updated_by=updated_by,
            )
            self.session.add(new_config)
            logger.info(f"Created email workflow config: {workflow_id}")

        await self.session.flush()

        return EmailWorkflowConfig(
            workflow_id=workflow_id,
            workflow_name=validation.workflow_name or "unknown",
            configured_at=now,
            configured_by=updated_by,
        )

    async def delete_config(self) -> bool:
        """Delete email workflow configuration."""
        result = await self.session.execute(
            select(SystemConfig).where(
                SystemConfig.category == EMAIL_CONFIG_CATEGORY,
                SystemConfig.key == EMAIL_CONFIG_KEY,
                SystemConfig.organization_id.is_(None),
            )
        )
        config = result.scalars().first()

        if config:
            await self.session.delete(config)
            await self.session.flush()
            logger.info("Deleted email workflow config")
            return True

        return False


async def send_email(
    recipient: str,
    subject: str,
    body: str,
    html_body: str | None = None,
) -> SendEmailResult:
    """
    Send an email using the configured email workflow.

    This is a fire-and-forget function for system emails (password resets, etc.).
    It logs errors but doesn't throw - caller should check result.success.

    Usage:
        result = await send_email(
            recipient="user@example.com",
            subject="Password Reset",
            body="Click here to reset your password...",
        )
        if not result.success:
            logger.warning(f"Failed to send email: {result.error}")
    """
    from src.core.database import get_session_factory
    from src.sdk.context import ExecutionContext
    from src.services.execution.service import run_workflow

    try:
        # Get config from database
        session_factory = get_session_factory()
        async with session_factory() as db:
            service = EmailService(db)
            config = await service.get_config()

        if not config:
            return SendEmailResult(
                success=False,
                error="Email workflow not configured. Configure in admin settings.",
            )

        # Build execution context for system-level email sending
        context = ExecutionContext(
            user_id="system",
            email="system@internal.gobifrost.com",
            name="Bifrost System",
            scope="GLOBAL",
            organization=None,
            is_platform_admin=True,
            is_function_key=False,
            execution_id=str(uuid4()),
        )

        # Execute the workflow synchronously
        result = await run_workflow(
            context=context,
            workflow_id=config.workflow_id,
            input_data={
                "recipient": recipient,
                "subject": subject,
                "body": body,
                "html_body": html_body,
            },
            transient=True,  # Don't persist execution record for system emails
            sync=True,  # Wait for result
        )

        if result.status == "Success":
            logger.info(f"Email sent successfully to {recipient}")
            return SendEmailResult(
                success=True,
                execution_id=result.execution_id,
            )
        else:
            error_msg = result.error or f"Email workflow failed with status: {result.status}"
            logger.error(f"Failed to send email to {recipient}: {error_msg}")
            await _notify_admins_of_failure(recipient, subject, error_msg)
            return SendEmailResult(
                success=False,
                execution_id=result.execution_id,
                error=error_msg,
            )

    except Exception as e:
        error_msg = str(e)
        logger.exception(f"Exception sending email to {recipient}: {error_msg}")
        await _notify_admins_of_failure(recipient, subject, error_msg)
        return SendEmailResult(
            success=False,
            error=error_msg,
        )


async def _notify_admins_of_failure(recipient: str, subject: str, error: str) -> None:
    """
    Notify platform admins when email sending fails.

    This is fire-and-forget - we log but don't throw if notification fails.
    """
    from src.models.contracts.notifications import (
        NotificationCategory,
        NotificationCreate,
        NotificationStatus,
    )
    from src.services.notification_service import get_notification_service

    try:
        notification_service = get_notification_service()
        await notification_service.create_notification(
            user_id="system",
            request=NotificationCreate(
                category=NotificationCategory.SYSTEM,
                title="Email Send Failed",
                description=f"Failed to send '{subject}' to {recipient}: {error}"[:500],
            ),
            for_admins=True,
            initial_status=NotificationStatus.FAILED,
        )
        logger.info(f"Notified admins of email failure to {recipient}")
    except Exception as e:
        # Don't let notification failure break the email flow
        logger.warning(f"Failed to notify admins of email failure: {e}")
