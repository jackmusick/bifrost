"""
Integration tests for the execution logs list endpoint.

Tests the admin-only endpoint GET /api/executions/logs for listing logs
across all executions with filtering and pagination.
"""

import pytest
import pytest_asyncio
from datetime import datetime
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from src.models import Execution, ExecutionLog
from src.models.enums import ExecutionStatus
from src.models.orm.users import User
from src.models.orm.organizations import Organization
from src.repositories.execution_logs import ExecutionLogRepository


@pytest_asyncio.fixture
async def test_organization(db_session: AsyncSession):
    """Create a test organization."""
    org = Organization(
        id=uuid4(),
        name=f"Test Logs Org {uuid4().hex[:8]}",
        domain=f"test-logs-{uuid4().hex[:8]}.com",
        created_by="test@example.com",
    )
    db_session.add(org)
    await db_session.flush()
    return org


@pytest_asyncio.fixture
async def test_user(db_session: AsyncSession, test_organization):
    """Create a test user."""
    user = User(
        id=uuid4(),
        email=f"test_{uuid4().hex[:8]}@example.com",
        name="Test User",
        organization_id=test_organization.id,
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest_asyncio.fixture
async def admin_user(db_session: AsyncSession):
    """Create an admin user (superuser)."""
    user = User(
        id=uuid4(),
        email=f"admin_{uuid4().hex[:8]}@platform.com",
        name="Platform Admin",
        organization_id=None,  # Platform admins don't need org
        is_superuser=True,
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest_asyncio.fixture
async def sample_execution_with_logs(
    db_session: AsyncSession,
    test_user: User,
    test_organization: Organization,
):
    """Create a sample execution with logs for testing."""
    execution = Execution(
        id=uuid4(),
        workflow_name="test_workflow",
        status=ExecutionStatus.SUCCESS,
        parameters={},
        started_at=datetime.utcnow(),
        completed_at=datetime.utcnow(),
        executed_by=test_user.id,
        executed_by_name=test_user.name,
        organization_id=test_organization.id,
    )
    db_session.add(execution)
    await db_session.flush()

    # Add various log levels
    logs = [
        ExecutionLog(
            execution_id=execution.id,
            level="INFO",
            message="Workflow started",
            timestamp=datetime.utcnow(),
            sequence=1,
        ),
        ExecutionLog(
            execution_id=execution.id,
            level="WARNING",
            message="Resource limit approaching",
            timestamp=datetime.utcnow(),
            sequence=2,
        ),
        ExecutionLog(
            execution_id=execution.id,
            level="ERROR",
            message="Connection timeout",
            timestamp=datetime.utcnow(),
            sequence=3,
        ),
        ExecutionLog(
            execution_id=execution.id,
            level="INFO",
            message="Workflow completed",
            timestamp=datetime.utcnow(),
            sequence=4,
        ),
    ]
    for log in logs:
        db_session.add(log)
    await db_session.flush()

    return execution


@pytest.mark.integration
@pytest.mark.asyncio
class TestLogsListRepository:
    """Tests for ExecutionLogRepository.list_logs method."""

    async def test_list_logs_returns_paginated_results(
        self,
        db_session: AsyncSession,
        sample_execution_with_logs: Execution,
    ):
        """Can list logs with pagination."""
        repo = ExecutionLogRepository(db_session)

        logs, next_token = await repo.list_logs(
            limit=10,
            offset=0,
        )

        assert isinstance(logs, list)
        assert len(logs) >= 1  # At least one log from our fixture
        # Each log should have expected fields
        for log in logs:
            assert "id" in log
            assert "execution_id" in log
            assert "level" in log
            assert "message" in log
            assert "timestamp" in log
            assert "workflow_name" in log

    async def test_list_logs_filters_by_level(
        self,
        db_session: AsyncSession,
        sample_execution_with_logs: Execution,
    ):
        """Can filter logs by level."""
        repo = ExecutionLogRepository(db_session)

        logs, _ = await repo.list_logs(
            levels=["ERROR", "WARNING"],
            limit=50,
            offset=0,
        )

        assert isinstance(logs, list)
        # All returned logs should be ERROR or WARNING
        for log in logs:
            assert log["level"] in ["ERROR", "WARNING"]

    async def test_list_logs_filters_by_workflow_name(
        self,
        db_session: AsyncSession,
        sample_execution_with_logs: Execution,
    ):
        """Can filter logs by workflow name."""
        repo = ExecutionLogRepository(db_session)

        logs, _ = await repo.list_logs(
            workflow_name="test_workflow",
            limit=50,
            offset=0,
        )

        assert isinstance(logs, list)
        # All returned logs should be from test_workflow
        for log in logs:
            assert log["workflow_name"] == "test_workflow"

    async def test_list_logs_message_search(
        self,
        db_session: AsyncSession,
        sample_execution_with_logs: Execution,
    ):
        """Can search in log message content."""
        repo = ExecutionLogRepository(db_session)

        logs, _ = await repo.list_logs(
            message_search="timeout",
            limit=50,
            offset=0,
        )

        assert isinstance(logs, list)
        # All returned logs should contain "timeout" in message
        for log in logs:
            assert "timeout" in log["message"].lower()

    async def test_list_logs_filters_by_organization(
        self,
        db_session: AsyncSession,
        sample_execution_with_logs: Execution,
        test_organization: Organization,
    ):
        """Can filter logs by organization."""
        repo = ExecutionLogRepository(db_session)

        logs, _ = await repo.list_logs(
            organization_id=test_organization.id,
            limit=50,
            offset=0,
        )

        assert isinstance(logs, list)
        # Should have logs from our fixture execution
        assert len(logs) >= 1

    async def test_list_logs_pagination_token(
        self,
        db_session: AsyncSession,
        sample_execution_with_logs: Execution,
    ):
        """Pagination returns correct continuation token."""
        repo = ExecutionLogRepository(db_session)

        # Request exactly 2 logs (our fixture has 4)
        logs, next_token = await repo.list_logs(
            limit=2,
            offset=0,
        )

        assert len(logs) == 2
        # Should have a continuation token if there are more logs
        if next_token is not None:
            assert next_token == "2"  # Next offset

            # Fetch next page
            logs2, _ = await repo.list_logs(
                limit=2,
                offset=2,
            )
            assert len(logs2) >= 1

    async def test_list_logs_filters_by_date_range(
        self,
        db_session: AsyncSession,
        sample_execution_with_logs: Execution,
    ):
        """Can filter logs by date range."""
        repo = ExecutionLogRepository(db_session)

        # All fixture logs were created just now, so use a range that includes them
        start_date = datetime(2020, 1, 1)
        end_date = datetime(2030, 12, 31)

        logs, _ = await repo.list_logs(
            start_date=start_date,
            end_date=end_date,
            limit=50,
            offset=0,
        )

        assert isinstance(logs, list)
        assert len(logs) >= 1  # Should include our fixture logs

    async def test_list_logs_empty_filters_returns_all(
        self,
        db_session: AsyncSession,
        sample_execution_with_logs: Execution,
    ):
        """Empty filters return all logs."""
        repo = ExecutionLogRepository(db_session)

        logs, _ = await repo.list_logs(
            limit=50,
            offset=0,
        )

        assert isinstance(logs, list)
        # Should have all 4 logs from our fixture
        assert len(logs) >= 4
