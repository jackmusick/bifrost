"""
Unit tests for AI Usage contract models.

Tests Pydantic models for AI usage tracking and model pricing.
"""

from datetime import date, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from src.models.contracts.ai_usage import (
    AIModelPricingCreate,
    AIModelPricingPublic,
    AIUsagePublic,
    AIUsageTotals,
    UsageTrend,
)


class TestAIModelPricingCreate:
    """Tests for AIModelPricingCreate model."""

    def test_provider_max_length(self):
        """Test provider field respects max length."""
        with pytest.raises(ValidationError):
            AIModelPricingCreate(
                provider="x" * 51,  # Exceeds 50 char limit
                model="gpt-4o",
                input_price_per_million=Decimal("5.00"),
                output_price_per_million=Decimal("15.00"),
            )

    def test_model_max_length(self):
        """Test model field respects max length."""
        with pytest.raises(ValidationError):
            AIModelPricingCreate(
                provider="openai",
                model="x" * 101,  # Exceeds 100 char limit
                input_price_per_million=Decimal("5.00"),
                output_price_per_million=Decimal("15.00"),
            )


class TestAIModelPricingPublic:
    """Tests for AIModelPricingPublic model."""

    def test_serializes_decimals_to_string(self):
        """Test Decimal fields serialize to strings."""
        pricing = AIModelPricingPublic(
            id=1,
            provider="openai",
            model="gpt-4o",
            input_price_per_million=Decimal("5.00"),
            output_price_per_million=Decimal("15.00"),
            effective_date=date(2025, 1, 1),
            created_at=datetime(2025, 1, 1, 12, 0, 0),
            updated_at=datetime(2025, 1, 1, 12, 0, 0),
        )

        data = pricing.model_dump()
        assert data["input_price_per_million"] == "5.00"
        assert data["output_price_per_million"] == "15.00"

    def test_serializes_dates_to_iso_format(self):
        """Test date/datetime fields serialize to ISO format."""
        pricing = AIModelPricingPublic(
            id=1,
            provider="openai",
            model="gpt-4o",
            input_price_per_million=Decimal("5.00"),
            output_price_per_million=Decimal("15.00"),
            effective_date=date(2025, 1, 1),
            created_at=datetime(2025, 1, 1, 12, 0, 0),
            updated_at=datetime(2025, 1, 1, 12, 0, 0),
        )

        data = pricing.model_dump()
        assert data["effective_date"] == "2025-01-01"
        assert "T" in data["created_at"]  # ISO format includes T


class TestAIUsagePublic:
    """Tests for AIUsagePublic model."""

    def test_tokens_must_be_non_negative(self):
        """Test token counts must be >= 0."""
        with pytest.raises(ValidationError):
            AIUsagePublic(
                id=1,
                provider="openai",
                model="gpt-4o",
                input_tokens=-100,  # Invalid
                output_tokens=500,
                timestamp=datetime.now(),
                sequence=1,
            )

    def test_serializes_cost_to_string_or_none(self):
        """Test cost serializes to string when present, None otherwise."""
        usage_with_cost = AIUsagePublic(
            id=1,
            provider="openai",
            model="gpt-4o",
            input_tokens=1000,
            output_tokens=500,
            cost=Decimal("0.0125"),
            timestamp=datetime.now(),
            sequence=1,
        )

        usage_without_cost = AIUsagePublic(
            id=2,
            provider="openai",
            model="gpt-4o",
            input_tokens=1000,
            output_tokens=500,
            cost=None,
            timestamp=datetime.now(),
            sequence=1,
        )

        assert usage_with_cost.model_dump()["cost"] == "0.0125"
        assert usage_without_cost.model_dump()["cost"] is None


class TestAIUsageTotals:
    """Tests for AIUsageTotals model."""

    def test_serializes_cost_to_string(self):
        """Test cost serializes to string."""
        totals = AIUsageTotals(
            total_input_tokens=1000,
            total_output_tokens=500,
            total_cost=Decimal("0.0125"),
            total_duration_ms=150,
            call_count=1,
        )

        data = totals.model_dump()
        assert data["total_cost"] == "0.0125"


class TestUsageTrend:
    """Tests for UsageTrend model."""

    def test_serializes_date_to_iso(self):
        """Test date serializes to ISO format."""
        trend = UsageTrend(
            date=date(2025, 1, 15),
            ai_cost=Decimal("1.50"),
            input_tokens=10000,
            output_tokens=5000,
        )

        data = trend.model_dump()
        assert data["date"] == "2025-01-15"


