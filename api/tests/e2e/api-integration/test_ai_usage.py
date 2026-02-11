"""
Integration tests for AI Usage API endpoints.

Tests AI pricing and usage service features with real database.
These tests require PostgreSQL and Redis to be running (via docker-compose.test.yml).

Note: Tests that require execution_id or conversation_id FKs are skipped as they
require complex test data setup. Those scenarios are covered by the unit tests.
"""

import pytest
import pytest_asyncio
from decimal import Decimal
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from src.repositories.ai_usage import AIPricingRepository


class TestAIPricingRepositoryIntegration:
    """Integration tests for AIPricingRepository with real database."""

    @pytest.mark.asyncio
    async def test_create_and_get_pricing(self, db_session: AsyncSession):
        """Test creating and retrieving pricing record."""
        repo = AIPricingRepository(db_session)

        # Create unique model name to avoid conflicts
        model_name = f"test-model-{uuid4()}"

        pricing = await repo.create_pricing(
            provider="test-provider",
            model=model_name,
            input_price_per_million=Decimal("5.00"),
            output_price_per_million=Decimal("15.00"),
        )

        assert pricing.id is not None
        assert pricing.provider == "test-provider"
        assert pricing.model == model_name
        assert pricing.input_price_per_million == Decimal("5.00")
        assert pricing.output_price_per_million == Decimal("15.00")

        # Retrieve pricing
        retrieved = await repo.get_by_model("test-provider", model_name)

        assert retrieved is not None
        assert retrieved.id == pricing.id
        assert retrieved.input_price_per_million == Decimal("5.00")

        # Cleanup
        await db_session.delete(pricing)
        await db_session.commit()

    @pytest.mark.asyncio
    async def test_update_pricing(self, db_session: AsyncSession):
        """Test updating pricing record."""
        repo = AIPricingRepository(db_session)

        model_name = f"test-model-{uuid4()}"

        pricing = await repo.create_pricing(
            provider="test-provider",
            model=model_name,
            input_price_per_million=Decimal("5.00"),
            output_price_per_million=Decimal("15.00"),
        )

        # Update pricing
        updated = await repo.update_pricing(
            pricing_id=pricing.id,
            input_price_per_million=Decimal("6.00"),
        )

        assert updated is not None
        assert updated.input_price_per_million == Decimal("6.00")
        assert updated.output_price_per_million == Decimal("15.00")  # Unchanged

        # Cleanup
        await db_session.delete(pricing)
        await db_session.commit()

    @pytest.mark.asyncio
    async def test_list_all_pricing(self, db_session: AsyncSession):
        """Test listing all pricing records."""
        repo = AIPricingRepository(db_session)

        # Create test pricing
        model_name = f"test-model-{uuid4()}"
        pricing = await repo.create_pricing(
            provider="test-provider",
            model=model_name,
            input_price_per_million=Decimal("5.00"),
            output_price_per_million=Decimal("15.00"),
        )

        # List all
        all_pricing = await repo.list_all()

        assert len(all_pricing) >= 1
        model_names = [p.model for p in all_pricing]
        assert model_name in model_names

        # Cleanup
        await db_session.delete(pricing)
        await db_session.commit()


class TestAIUsageServiceIntegration:
    """Integration tests for AI usage service with real Redis."""

    @pytest_asyncio.fixture
    async def redis_client(self):
        """Create a Redis client for testing."""
        import os
        import redis.asyncio as async_redis

        redis_url = os.getenv("BIFROST_REDIS_URL", "redis://redis:6379/0")
        client = async_redis.from_url(redis_url, decode_responses=True)
        yield client
        await client.aclose()

    @pytest.mark.asyncio
    async def test_get_cached_price_from_redis(
        self,
        db_session: AsyncSession,
        redis_client,
    ):
        """Test pricing cache lookup from Redis."""
        from src.services.ai_usage_service import get_cached_price, PRICING_KEY_PREFIX

        # Pre-populate cache
        await redis_client.setex(
            f"{PRICING_KEY_PREFIX}openai:gpt-4o",
            3600,
            '{"input_price": "5.00", "output_price": "15.00"}',
        )

        input_price, output_price = await get_cached_price(
            redis_client, db_session, "openai", "gpt-4o"
        )

        assert input_price == Decimal("5.00")
        assert output_price == Decimal("15.00")

        # Cleanup
        await redis_client.delete(f"{PRICING_KEY_PREFIX}openai:gpt-4o")

    @pytest.mark.asyncio
    async def test_get_cached_price_from_db(
        self,
        db_session: AsyncSession,
        redis_client,
    ):
        """Test pricing lookup falls back to database."""
        from src.services.ai_usage_service import get_cached_price, PRICING_KEY_PREFIX

        # Ensure no cache exists
        model_name = f"test-model-{uuid4()}"
        cache_key = f"{PRICING_KEY_PREFIX}test-provider:{model_name}"
        await redis_client.delete(cache_key)

        # Create pricing in DB
        repo = AIPricingRepository(db_session)
        pricing = await repo.create_pricing(
            provider="test-provider",
            model=model_name,
            input_price_per_million=Decimal("7.00"),
            output_price_per_million=Decimal("21.00"),
        )
        await db_session.commit()

        # Should find it from DB
        input_price, output_price = await get_cached_price(
            redis_client, db_session, "test-provider", model_name
        )

        assert input_price == Decimal("7.00")
        assert output_price == Decimal("21.00")

        # Should have cached it
        cached = await redis_client.get(cache_key)
        assert cached is not None

        # Cleanup
        await redis_client.delete(cache_key)
        await db_session.delete(pricing)
        await db_session.commit()

    @pytest.mark.asyncio
    async def test_invalidate_usage_cache(
        self,
        redis_client,
    ):
        """Test invalidating usage cache."""
        from src.services.ai_usage_service import (
            invalidate_usage_cache,
            USAGE_TOTALS_KEY_PREFIX,
        )

        test_execution_id = uuid4()

        # Set up cache
        cache_key = f"{USAGE_TOTALS_KEY_PREFIX}{test_execution_id}"
        await redis_client.set(cache_key, '{"input_tokens": 1000}')

        # Verify it exists
        assert await redis_client.exists(cache_key)

        # Invalidate
        await invalidate_usage_cache(redis_client, execution_id=test_execution_id)

        # Verify it's gone
        assert not await redis_client.exists(cache_key)

    @pytest.mark.asyncio
    async def test_invalidate_pricing_cache(
        self,
        redis_client,
    ):
        """Test invalidating pricing cache."""
        from src.services.ai_usage_service import (
            invalidate_pricing_cache,
            PRICING_KEY_PREFIX,
        )

        # Set up cache
        cache_key = f"{PRICING_KEY_PREFIX}openai:gpt-4o"
        await redis_client.set(cache_key, '{"input_price": "5.00", "output_price": "15.00"}')

        # Verify it exists
        assert await redis_client.exists(cache_key)

        # Invalidate
        await invalidate_pricing_cache(redis_client, "openai", "gpt-4o")

        # Verify it's gone
        assert not await redis_client.exists(cache_key)
