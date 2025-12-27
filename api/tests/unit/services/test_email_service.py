"""
Unit tests for EmailService.

Tests email workflow configuration and validation with mocked database.
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.services.email_service import (
    EmailService,
    EmailWorkflowConfig,
    EmailValidationResult,
    SendEmailResult,
    send_email,
    EMAIL_CONFIG_CATEGORY,
    EMAIL_CONFIG_KEY,
    REQUIRED_PARAMS,
    OPTIONAL_PARAMS,
)


@pytest.fixture
def mock_session():
    """Mock database session."""
    session = AsyncMock()
    session.execute = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.delete = AsyncMock()
    return session


@pytest.fixture
def valid_workflow():
    """Mock workflow with valid email signature."""
    workflow = MagicMock()
    workflow.id = str(uuid4())
    workflow.name = "send_email"
    workflow.is_active = True
    workflow.parameters_schema = [
        {"name": "recipient", "type": "string", "required": True},
        {"name": "subject", "type": "string", "required": True},
        {"name": "body", "type": "string", "required": True},
        {"name": "html_body", "type": "string", "required": False},
    ]
    return workflow


@pytest.fixture
def mock_system_config():
    """Mock SystemConfig for email workflow."""
    config = MagicMock()
    config.id = uuid4()
    config.category = EMAIL_CONFIG_CATEGORY
    config.key = EMAIL_CONFIG_KEY
    config.value_json = {
        "workflow_id": str(uuid4()),
        "workflow_name": "send_email",
        "configured_at": "2025-01-15T10:30:00",
        "configured_by": "admin@test.com",
    }
    config.organization_id = None
    return config


class TestEmailServiceGetConfig:
    """Test EmailService.get_config method."""

    @pytest.mark.asyncio
    async def test_returns_none_when_not_configured(self, mock_session):
        """Returns None when no config exists."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = None
        mock_session.execute.return_value = mock_result

        service = EmailService(mock_session)
        result = await service.get_config()

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_config_when_exists(self, mock_session, mock_system_config):
        """Returns EmailWorkflowConfig when config exists."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = mock_system_config
        mock_session.execute.return_value = mock_result

        service = EmailService(mock_session)
        result = await service.get_config()

        assert result is not None
        assert isinstance(result, EmailWorkflowConfig)
        assert result.workflow_name == "send_email"
        assert result.is_configured is True

    @pytest.mark.asyncio
    async def test_handles_missing_configured_at(self, mock_session):
        """Handles missing configured_at field gracefully."""
        config = MagicMock()
        config.value_json = {
            "workflow_id": str(uuid4()),
            "workflow_name": "test_email",
        }
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = config
        mock_session.execute.return_value = mock_result

        service = EmailService(mock_session)
        result = await service.get_config()

        assert result is not None
        assert result.configured_at is None


class TestEmailServiceValidateWorkflow:
    """Test EmailService.validate_workflow method."""

    @pytest.mark.asyncio
    async def test_returns_invalid_when_workflow_not_found(self, mock_session):
        """Returns invalid when workflow doesn't exist."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        service = EmailService(mock_session)
        result = await service.validate_workflow("non-existent-id")

        assert result.valid is False
        assert "not found" in result.message

    @pytest.mark.asyncio
    async def test_returns_invalid_when_missing_required_params(self, mock_session):
        """Returns invalid when workflow missing required params."""
        workflow = MagicMock()
        workflow.name = "incomplete_email"
        workflow.is_active = True
        workflow.parameters_schema = [
            {"name": "recipient", "type": "string", "required": True},
            # Missing subject and body
        ]

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = workflow
        mock_session.execute.return_value = mock_result

        service = EmailService(mock_session)
        result = await service.validate_workflow("test-id")

        assert result.valid is False
        assert "missing required parameters" in result.message.lower()
        assert set(result.missing_params) == {"subject", "body"}

    @pytest.mark.asyncio
    async def test_returns_invalid_when_extra_required_params(self, mock_session):
        """Returns invalid when workflow has extra required params."""
        workflow = MagicMock()
        workflow.name = "extra_params_email"
        workflow.is_active = True
        workflow.parameters_schema = [
            {"name": "recipient", "type": "string", "required": True},
            {"name": "subject", "type": "string", "required": True},
            {"name": "body", "type": "string", "required": True},
            {"name": "api_key", "type": "string", "required": True},  # Extra required
        ]

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = workflow
        mock_session.execute.return_value = mock_result

        service = EmailService(mock_session)
        result = await service.validate_workflow("test-id")

        assert result.valid is False
        assert "extra required parameters" in result.message.lower()
        assert "api_key" in result.extra_required_params

    @pytest.mark.asyncio
    async def test_returns_valid_with_correct_signature(
        self, mock_session, valid_workflow
    ):
        """Returns valid when workflow has correct signature."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = valid_workflow
        mock_session.execute.return_value = mock_result

        service = EmailService(mock_session)
        result = await service.validate_workflow(valid_workflow.id)

        assert result.valid is True
        assert result.workflow_name == "send_email"

    @pytest.mark.asyncio
    async def test_allows_extra_optional_params(self, mock_session):
        """Allows extra optional params in workflow signature."""
        workflow = MagicMock()
        workflow.name = "extended_email"
        workflow.is_active = True
        workflow.parameters_schema = [
            {"name": "recipient", "type": "string", "required": True},
            {"name": "subject", "type": "string", "required": True},
            {"name": "body", "type": "string", "required": True},
            {"name": "html_body", "type": "string", "required": False},
            {"name": "cc", "type": "string", "required": False},  # Extra optional - OK
            {"name": "bcc", "type": "string", "required": False},  # Extra optional - OK
        ]

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = workflow
        mock_session.execute.return_value = mock_result

        service = EmailService(mock_session)
        result = await service.validate_workflow("test-id")

        assert result.valid is True

    @pytest.mark.asyncio
    async def test_handles_empty_parameters_schema(self, mock_session):
        """Handles workflow with no parameters."""
        workflow = MagicMock()
        workflow.name = "no_params"
        workflow.is_active = True
        workflow.parameters_schema = None

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = workflow
        mock_session.execute.return_value = mock_result

        service = EmailService(mock_session)
        result = await service.validate_workflow("test-id")

        assert result.valid is False
        assert result.missing_params is not None
        assert set(result.missing_params) == REQUIRED_PARAMS


class TestEmailServiceSaveConfig:
    """Test EmailService.save_config method."""

    @pytest.mark.asyncio
    async def test_raises_on_invalid_workflow(self, mock_session):
        """Raises ValueError when workflow is invalid."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        service = EmailService(mock_session)

        with pytest.raises(ValueError, match="not found"):
            await service.save_config("invalid-id", "admin@test.com")

    @pytest.mark.asyncio
    async def test_creates_new_config(self, mock_session, valid_workflow):
        """Creates new config when none exists."""
        # First call for validate_workflow, second for checking existing config
        mock_result_workflow = MagicMock()
        mock_result_workflow.scalar_one_or_none.return_value = valid_workflow

        mock_result_config = MagicMock()
        mock_result_config.scalars.return_value.first.return_value = None

        mock_session.execute.side_effect = [mock_result_workflow, mock_result_config]

        service = EmailService(mock_session)
        result = await service.save_config(valid_workflow.id, "admin@test.com")

        assert result.workflow_id == valid_workflow.id
        assert result.workflow_name == "send_email"
        mock_session.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_updates_existing_config(
        self, mock_session, valid_workflow, mock_system_config
    ):
        """Updates existing config when one exists."""
        mock_result_workflow = MagicMock()
        mock_result_workflow.scalar_one_or_none.return_value = valid_workflow

        mock_result_config = MagicMock()
        mock_result_config.scalars.return_value.first.return_value = mock_system_config

        mock_session.execute.side_effect = [mock_result_workflow, mock_result_config]

        service = EmailService(mock_session)
        result = await service.save_config(valid_workflow.id, "admin@test.com")

        assert result.workflow_id == valid_workflow.id
        # Should not call add() when updating
        mock_session.add.assert_not_called()
        # Should have updated the existing config
        assert mock_system_config.value_json["workflow_id"] == valid_workflow.id


class TestEmailServiceDeleteConfig:
    """Test EmailService.delete_config method."""

    @pytest.mark.asyncio
    async def test_returns_false_when_not_exists(self, mock_session):
        """Returns False when config doesn't exist."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = None
        mock_session.execute.return_value = mock_result

        service = EmailService(mock_session)
        result = await service.delete_config()

        assert result is False
        mock_session.delete.assert_not_called()

    @pytest.mark.asyncio
    async def test_deletes_existing_config(self, mock_session, mock_system_config):
        """Deletes config when it exists."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = mock_system_config
        mock_session.execute.return_value = mock_result

        service = EmailService(mock_session)
        result = await service.delete_config()

        assert result is True
        mock_session.delete.assert_called_once_with(mock_system_config)


class TestSendEmail:
    """Test send_email standalone function."""

    @pytest.mark.asyncio
    async def test_returns_error_when_not_configured(self):
        """Returns error when email workflow not configured."""
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = None
        mock_session.execute.return_value = mock_result

        # Mock the async context manager
        mock_session_factory = MagicMock()
        mock_session_factory.return_value.__aenter__ = AsyncMock(
            return_value=mock_session
        )
        mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=None)

        with patch(
            "src.core.database.get_session_factory",
            return_value=mock_session_factory,
        ):
            result = await send_email(
                recipient="test@example.com",
                subject="Test",
                body="Test body",
            )

        assert result.success is False
        assert "not configured" in result.error.lower()

    @pytest.mark.asyncio
    async def test_calls_workflow_with_correct_params(self):
        """Calls the configured workflow with email parameters."""
        workflow_id = str(uuid4())

        # Mock config retrieval
        mock_session = AsyncMock()
        mock_config = MagicMock()
        mock_config.value_json = {
            "workflow_id": workflow_id,
            "workflow_name": "send_email",
        }
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = mock_config
        mock_session.execute.return_value = mock_result

        mock_session_factory = MagicMock()
        mock_session_factory.return_value.__aenter__ = AsyncMock(
            return_value=mock_session
        )
        mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=None)

        # Mock run_workflow
        mock_execution_response = MagicMock()
        mock_execution_response.status = "Success"
        mock_execution_response.execution_id = "exec-123"

        with patch(
            "src.core.database.get_session_factory",
            return_value=mock_session_factory,
        ):
            with patch(
                "src.services.execution.service.run_workflow",
                new_callable=AsyncMock,
                return_value=mock_execution_response,
            ) as mock_run:
                result = await send_email(
                    recipient="user@example.com",
                    subject="Password Reset",
                    body="Click here...",
                    html_body="<p>Click here...</p>",
                )

                assert result.success is True
                mock_run.assert_called_once()
                call_kwargs = mock_run.call_args.kwargs
                assert call_kwargs["workflow_id"] == workflow_id
                assert call_kwargs["input_data"]["recipient"] == "user@example.com"
                assert call_kwargs["input_data"]["subject"] == "Password Reset"
                assert call_kwargs["input_data"]["body"] == "Click here..."
                assert call_kwargs["input_data"]["html_body"] == "<p>Click here...</p>"
                assert call_kwargs["sync"] is True
                assert call_kwargs["transient"] is True

    @pytest.mark.asyncio
    async def test_returns_failure_on_workflow_error(self):
        """Returns failure when workflow execution fails."""
        workflow_id = str(uuid4())

        mock_session = AsyncMock()
        mock_config = MagicMock()
        mock_config.value_json = {
            "workflow_id": workflow_id,
            "workflow_name": "send_email",
        }
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = mock_config
        mock_session.execute.return_value = mock_result

        mock_session_factory = MagicMock()
        mock_session_factory.return_value.__aenter__ = AsyncMock(
            return_value=mock_session
        )
        mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=None)

        # Mock failed workflow
        mock_execution_response = MagicMock()
        mock_execution_response.status = "Failed"
        mock_execution_response.error = "SMTP connection refused"
        mock_execution_response.execution_id = "exec-456"

        with patch(
            "src.core.database.get_session_factory",
            return_value=mock_session_factory,
        ):
            with patch(
                "src.services.execution.service.run_workflow",
                new_callable=AsyncMock,
                return_value=mock_execution_response,
            ):
                result = await send_email(
                    recipient="user@example.com",
                    subject="Test",
                    body="Test body",
                )

                assert result.success is False
                assert "SMTP connection refused" in result.error
                assert result.execution_id == "exec-456"

    @pytest.mark.asyncio
    async def test_handles_exception_gracefully(self):
        """Handles exceptions without throwing."""
        mock_session_factory = MagicMock()
        mock_session_factory.return_value.__aenter__ = AsyncMock(
            side_effect=Exception("Database connection failed")
        )
        mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=None)

        with patch(
            "src.core.database.get_session_factory",
            return_value=mock_session_factory,
        ):
            result = await send_email(
                recipient="user@example.com",
                subject="Test",
                body="Test body",
            )

            assert result.success is False
            assert "Database connection failed" in result.error
