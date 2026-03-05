"""Tests for usage reports agent source filter."""

from decimal import Decimal
from uuid import uuid4
from datetime import datetime, timezone

from src.models.orm.ai_usage import AIUsage


class TestUsageReportsAgentSource:
    """Test that AIUsage model supports agent_run_id for source='agents' filter."""

    def test_ai_usage_model_accepts_agent_run_id(self):
        """AIUsage ORM model can be created with agent_run_id."""
        run_id = uuid4()
        usage = AIUsage(
            id=uuid4(),
            agent_run_id=run_id,
            provider="anthropic",
            model="claude-sonnet-4-20250514",
            input_tokens=100,
            output_tokens=50,
            cost=Decimal("0.001"),
            duration_ms=500,
            timestamp=datetime.now(timezone.utc),
        )
        assert usage.agent_run_id == run_id
        assert usage.execution_id is None
        assert usage.conversation_id is None

    def test_ai_usage_agent_run_filter_expression(self):
        """AIUsage.agent_run_id supports SQLAlchemy filter expressions."""
        # Verify the column exists and supports .isnot(None)
        filter_expr = AIUsage.agent_run_id.isnot(None)
        assert filter_expr is not None
