"""
Integration tests for ROI metrics aggregation.

Tests that ROI values are correctly aggregated into daily metrics tables.
"""

import pytest
import pytest_asyncio
from datetime import date
from uuid import uuid4
from sqlalchemy import select

from src.core.metrics import (
    update_daily_metrics,
    update_workflow_roi_daily,
)
from src.models.orm import (
    ExecutionMetricsDaily,
    WorkflowROIDaily,
    Workflow,
    Organization,
)
from src.models.enums import ExecutionStatus


@pytest.mark.asyncio
class TestROIAggregation:
    """Test ROI aggregation into daily metrics."""

    @pytest_asyncio.fixture
    async def test_org(self, db_session):
        """Create a test organization."""
        org_uuid = uuid4()
        org = Organization(
            id=org_uuid,
            name=f"test-org-{org_uuid.hex[:8]}",
            created_by="test-system",
        )
        db_session.add(org)
        await db_session.commit()
        await db_session.refresh(org)
        return org

    @pytest_asyncio.fixture
    async def test_workflow(self, db_session):
        """Create a test workflow with ROI values."""
        # Use unique values to avoid unique constraint violations
        workflow_uuid = uuid4()
        workflow = Workflow(
            id=workflow_uuid,
            name=f"test-roi-workflow-{workflow_uuid.hex[:8]}",
            function_name=f"test_function_{workflow_uuid.hex[:8]}",  # Unique per test
            description="Test workflow with ROI",
            category="Testing",
            file_path=f"/workspace/test_{workflow_uuid.hex[:8]}.py",  # Unique per test
            is_active=True,
            time_saved=30,  # 30 minutes per execution
            value=100.0,  # 100 USD per execution
        )
        db_session.add(workflow)
        await db_session.commit()
        await db_session.refresh(workflow)
        return workflow

    async def test_update_daily_metrics_with_roi_success(
        self, db_session, test_workflow, test_org
    ):
        """Test update_daily_metrics with ROI values for SUCCESS execution."""
        org_id = f"ORG:{test_org.id}"
        today = date.today()

        # Update metrics for a successful execution with ROI
        await update_daily_metrics(
            org_id=org_id,
            status=ExecutionStatus.SUCCESS.value,
            duration_ms=5000,
            time_saved=30,  # 30 minutes
            value=100.0,  # 100 USD
            workflow_id=str(test_workflow.id),
            db=db_session,
        )

        # Verify org-level metrics were updated
        result = await db_session.execute(
            select(ExecutionMetricsDaily).where(
                ExecutionMetricsDaily.date == today,
                ExecutionMetricsDaily.organization_id == test_org.id,
            )
        )
        org_metrics = result.scalar_one()

        # update_daily_metrics upserts once for the org, once for global
        assert org_metrics.execution_count == 1
        assert org_metrics.success_count == 1
        assert org_metrics.total_time_saved == 30
        assert org_metrics.total_value == 100.0

    async def test_update_daily_metrics_roi_only_for_success(
        self, db_session, test_workflow, test_org
    ):
        """Test that ROI are only counted for SUCCESS executions."""
        org_id = f"ORG:{test_org.id}"
        today = date.today()

        # Update metrics for a FAILED execution (should NOT count ROI)
        await update_daily_metrics(
            org_id=org_id,
            status=ExecutionStatus.FAILED.value,
            duration_ms=3000,
            time_saved=30,  # Provided but should be ignored
            value=100.0,  # Provided but should be ignored
            workflow_id=str(test_workflow.id),
            db=db_session,
        )

        # Verify metrics were created but ROI are zero
        result = await db_session.execute(
            select(ExecutionMetricsDaily).where(
                ExecutionMetricsDaily.date == today,
                ExecutionMetricsDaily.organization_id == test_org.id,
            )
        )
        metrics = result.scalar_one()

        assert metrics.execution_count == 1
        assert metrics.failed_count == 1
        assert metrics.success_count == 0
        assert metrics.total_time_saved == 0  # Not counted for FAILED
        assert metrics.total_value == 0.0  # Not counted for FAILED

    async def test_update_daily_metrics_roi_accumulate(
        self, db_session, test_workflow, test_org
    ):
        """Test that ROI accumulate correctly across multiple executions."""
        org_id = f"ORG:{test_org.id}"
        today = date.today()

        # First execution: 30 min, 100 USD
        await update_daily_metrics(
            org_id=org_id,
            status=ExecutionStatus.SUCCESS.value,
            duration_ms=5000,
            time_saved=30,
            value=100.0,
            workflow_id=str(test_workflow.id),
            db=db_session,
        )

        # Second execution: 45 min, 150 USD
        await update_daily_metrics(
            org_id=org_id,
            status=ExecutionStatus.SUCCESS.value,
            duration_ms=6000,
            time_saved=45,
            value=150.0,
            workflow_id=str(test_workflow.id),
            db=db_session,
        )

        # Third execution: FAILED (should not add ROI)
        await update_daily_metrics(
            org_id=org_id,
            status=ExecutionStatus.FAILED.value,
            duration_ms=2000,
            time_saved=20,  # Ignored
            value=80.0,  # Ignored
            workflow_id=str(test_workflow.id),
            db=db_session,
        )

        # Verify accumulated metrics
        result = await db_session.execute(
            select(ExecutionMetricsDaily).where(
                ExecutionMetricsDaily.date == today,
                ExecutionMetricsDaily.organization_id == test_org.id,
            )
        )
        metrics = result.scalar_one()

        assert metrics.execution_count == 3
        assert metrics.success_count == 2
        assert metrics.failed_count == 1
        assert metrics.total_time_saved == 75  # 30 + 45 (FAILED not counted)
        assert metrics.total_value == 250.0  # 100 + 150 (FAILED not counted)

    async def test_update_workflow_roi_daily_creates_record(
        self, db_session, test_workflow, test_org
    ):
        """Test update_workflow_roi_daily creates record for new workflow+date."""
        org_id = f"ORG:{test_org.id}"
        today = date.today()

        await update_workflow_roi_daily(
            workflow_id=str(test_workflow.id),
            org_id=org_id,
            status=ExecutionStatus.SUCCESS.value,
            time_saved=30,
            value=100.0,
            db=db_session,
        )

        # Verify record was created
        result = await db_session.execute(
            select(WorkflowROIDaily).where(
                WorkflowROIDaily.date == today,
                WorkflowROIDaily.workflow_id == test_workflow.id,
                WorkflowROIDaily.organization_id == test_org.id,
            )
        )
        record = result.scalar_one()

        assert record.execution_count == 1
        assert record.success_count == 1
        assert record.total_time_saved == 30
        assert record.total_value == 100.0

    async def test_update_workflow_roi_daily_updates_existing(
        self, db_session, test_workflow, test_org
    ):
        """Test update_workflow_roi_daily updates existing record."""
        org_id = f"ORG:{test_org.id}"
        today = date.today()

        # First execution
        await update_workflow_roi_daily(
            workflow_id=str(test_workflow.id),
            org_id=org_id,
            status=ExecutionStatus.SUCCESS.value,
            time_saved=30,
            value=100.0,
            db=db_session,
        )

        # Second execution
        await update_workflow_roi_daily(
            workflow_id=str(test_workflow.id),
            org_id=org_id,
            status=ExecutionStatus.SUCCESS.value,
            time_saved=45,
            value=150.0,
            db=db_session,
        )

        # Verify accumulated values
        result = await db_session.execute(
            select(WorkflowROIDaily).where(
                WorkflowROIDaily.date == today,
                WorkflowROIDaily.workflow_id == test_workflow.id,
                WorkflowROIDaily.organization_id == test_org.id,
            )
        )
        record = result.scalar_one()

        assert record.execution_count == 2
        assert record.success_count == 2
        assert record.total_time_saved == 75  # 30 + 45
        assert record.total_value == 250.0  # 100 + 150

    async def test_update_workflow_roi_daily_only_success_counts(
        self, db_session, test_workflow, test_org
    ):
        """Test that only SUCCESS executions count toward ROI."""
        org_id = f"ORG:{test_org.id}"
        today = date.today()

        # Success execution
        await update_workflow_roi_daily(
            workflow_id=str(test_workflow.id),
            org_id=org_id,
            status=ExecutionStatus.SUCCESS.value,
            time_saved=30,
            value=100.0,
            db=db_session,
        )

        # Failed execution (should increment execution_count but not ROI)
        await update_workflow_roi_daily(
            workflow_id=str(test_workflow.id),
            org_id=org_id,
            status=ExecutionStatus.FAILED.value,
            time_saved=20,  # Ignored
            value=80.0,  # Ignored
            db=db_session,
        )

        # Timeout execution (should increment execution_count but not ROI)
        await update_workflow_roi_daily(
            workflow_id=str(test_workflow.id),
            org_id=org_id,
            status=ExecutionStatus.TIMEOUT.value,
            time_saved=25,  # Ignored
            value=90.0,  # Ignored
            db=db_session,
        )

        # Verify only success execution counted
        result = await db_session.execute(
            select(WorkflowROIDaily).where(
                WorkflowROIDaily.date == today,
                WorkflowROIDaily.workflow_id == test_workflow.id,
                WorkflowROIDaily.organization_id == test_org.id,
            )
        )
        record = result.scalar_one()

        assert record.execution_count == 3
        assert record.success_count == 1  # Only SUCCESS counted
        assert record.total_time_saved == 30  # Only from SUCCESS
        assert record.total_value == 100.0  # Only from SUCCESS

    async def test_update_workflow_roi_daily_handles_zero_roi(
        self, db_session, test_workflow, test_org
    ):
        """Test that zero ROI values are handled correctly."""
        org_id = f"ORG:{test_org.id}"
        today = date.today()

        await update_workflow_roi_daily(
            workflow_id=str(test_workflow.id),
            org_id=org_id,
            status=ExecutionStatus.SUCCESS.value,
            time_saved=0,  # No time saved
            value=0.0,  # No value
            db=db_session,
        )

        # Verify record was created with zero ROI
        result = await db_session.execute(
            select(WorkflowROIDaily).where(
                WorkflowROIDaily.date == today,
                WorkflowROIDaily.workflow_id == test_workflow.id,
                WorkflowROIDaily.organization_id == test_org.id,
            )
        )
        record = result.scalar_one()

        assert record.execution_count == 1
        assert record.success_count == 1
        assert record.total_time_saved == 0
        assert record.total_value == 0.0

    async def test_workflow_roi_separate_by_org(
        self, db_session, test_workflow
    ):
        """Test that workflow ROI are tracked separately per organization."""
        # Create two test organizations
        org1_uuid = uuid4()
        org1 = Organization(
            id=org1_uuid,
            name=f"test-org1-{org1_uuid.hex[:8]}",
            created_by="test-system",
        )
        db_session.add(org1)

        org2_uuid = uuid4()
        org2 = Organization(
            id=org2_uuid,
            name=f"test-org2-{org2_uuid.hex[:8]}",
            created_by="test-system",
        )
        db_session.add(org2)

        await db_session.commit()

        org1_id = f"ORG:{org1.id}"
        org2_id = f"ORG:{org2.id}"
        today = date.today()

        # Org 1 execution
        await update_workflow_roi_daily(
            workflow_id=str(test_workflow.id),
            org_id=org1_id,
            status=ExecutionStatus.SUCCESS.value,
            time_saved=30,
            value=100.0,
            db=db_session,
        )

        # Org 2 execution
        await update_workflow_roi_daily(
            workflow_id=str(test_workflow.id),
            org_id=org2_id,
            status=ExecutionStatus.SUCCESS.value,
            time_saved=45,
            value=150.0,
            db=db_session,
        )

        # Verify org1 metrics
        result = await db_session.execute(
            select(WorkflowROIDaily).where(
                WorkflowROIDaily.date == today,
                WorkflowROIDaily.workflow_id == test_workflow.id,
                WorkflowROIDaily.organization_id == org1.id,
            )
        )
        org1_record = result.scalar_one()

        assert org1_record.total_time_saved == 30
        assert org1_record.total_value == 100.0

        # Verify org2 metrics
        result = await db_session.execute(
            select(WorkflowROIDaily).where(
                WorkflowROIDaily.date == today,
                WorkflowROIDaily.workflow_id == test_workflow.id,
                WorkflowROIDaily.organization_id == org2.id,
            )
        )
        org2_record = result.scalar_one()

        assert org2_record.total_time_saved == 45
        assert org2_record.total_value == 150.0
