"""Tests for execution service functions."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4


class TestGetWorkflowForExecution:
    """Test get_workflow_for_execution with optional session."""

    @pytest.mark.asyncio
    async def test_uses_provided_session(self):
        """Should use provided session instead of creating new one."""
        from src.services.execution.service import get_workflow_for_execution

        workflow_id = str(uuid4())
        mock_session = AsyncMock()

        # Create mock workflow record
        mock_workflow = MagicMock()
        mock_workflow.name = "test_workflow"
        mock_workflow.function_name = "run"
        mock_workflow.path = "workflows/test.py"
        mock_workflow.code = "def run(): pass"
        mock_workflow.timeout_seconds = 300
        mock_workflow.time_saved = 5
        mock_workflow.value = 10.0
        mock_workflow.execution_mode = "async"
        mock_workflow.organization_id = uuid4()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_workflow
        mock_session.execute = AsyncMock(return_value=mock_result)

        result = await get_workflow_for_execution(workflow_id, db=mock_session)

        assert result["name"] == "test_workflow"
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_creates_session_when_not_provided(self):
        """Should create own session when none provided."""
        from src.services.execution.service import get_workflow_for_execution

        workflow_id = str(uuid4())

        mock_workflow = MagicMock()
        mock_workflow.name = "test_workflow"
        mock_workflow.function_name = "run"
        mock_workflow.path = "workflows/test.py"
        mock_workflow.code = "def run(): pass"
        mock_workflow.timeout_seconds = 300
        mock_workflow.time_saved = 5
        mock_workflow.value = 10.0
        mock_workflow.execution_mode = "async"
        mock_workflow.organization_id = uuid4()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_workflow

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        mock_factory = MagicMock()
        mock_factory.return_value = mock_session

        # Patch at src.core.database since it's imported inside the function
        with patch("src.core.database.get_session_factory", return_value=mock_factory):
            result = await get_workflow_for_execution(workflow_id)

        assert result["name"] == "test_workflow"
        mock_factory.assert_called_once()
