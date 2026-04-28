"""
Unit tests for per-source webhook rate limiting in the hooks router.

These tests verify that:
- Requests past the per-source rate limit return 429 with Retry-After header
- The 429 response contains a JSON body (not an Event/EventDelivery row)
- rate_limit_enabled=False bypasses the limiter
- rate_limit_per_minute=None bypasses the limiter
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.routers.hooks import receive_webhook


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_event_source(source_id=None):
    """Build a minimal EventSource-like object."""
    es = MagicMock()
    es.id = source_id or uuid4()
    es.is_active = True
    return es


def _make_webhook_source(
    *,
    rate_limit_enabled: bool = True,
    rate_limit_per_minute: int | None = 3,
    rate_limit_window_seconds: int = 60,
):
    """Build a minimal WebhookSource-like object."""
    ws = MagicMock()
    ws.rate_limit_enabled = rate_limit_enabled
    ws.rate_limit_per_minute = rate_limit_per_minute
    ws.rate_limit_window_seconds = rate_limit_window_seconds
    ws.adapter_name = None
    ws.config = {}
    ws.state = {}
    ws.integration = None
    return ws


def _make_request(source_id: str, body: bytes = b"{}") -> MagicMock:
    """Build a minimal FastAPI-like Request mock."""
    req = MagicMock()
    req.method = "POST"
    req.headers = {}
    req.query_params = {}
    req.client = None

    async def _body():
        return body

    req.body = _body
    return req


async def _fake_resolve(resolved):
    """Return a coroutine that yields *resolved*."""
    return resolved


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_webhook_returns_429_when_rate_limit_exceeded():
    """Requests past the per-source rate limit return 429 with Retry-After."""
    source_id = uuid4()
    event_source = _make_event_source(source_id=source_id)
    webhook_source = _make_webhook_source(rate_limit_per_minute=3, rate_limit_window_seconds=60)

    # In-memory counter that the limiter will increment
    counter = {"n": 0}

    async def fake_check(endpoint: str, identifier: str, force: bool = False) -> None:
        from fastapi import HTTPException, status

        counter["n"] += 1
        if counter["n"] > 3:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many requests.",
                headers={"Retry-After": "42"},
            )

    db = AsyncMock()

    with (
        patch(
            "src.routers.hooks.resolve_webhook_source",
            return_value=(event_source, webhook_source),
        ),
        patch("src.routers.hooks.RateLimiter") as MockLimiter,
    ):
        instance = AsyncMock()
        instance.check = fake_check
        MockLimiter.return_value = instance

        # First 3 calls should NOT be rate-limited (we need a non-429 path)
        # For this we patch the processor to return a Rejected so we don't
        # need to stand up DB/queue — we only care about rate limiting.
        from src.services.webhooks.protocol import Rejected

        with patch(
            "src.routers.hooks.EventProcessor"
        ) as MockProcessor:
            proc_instance = AsyncMock()
            proc_instance.process_webhook = AsyncMock(return_value=Rejected(message="ok", status_code=200))
            MockProcessor.return_value = proc_instance

            for _ in range(3):
                request = _make_request(str(source_id))
                response = await receive_webhook(str(source_id), request, db)
                assert response.status_code != 429, f"Expected non-429 on call {_ + 1}"

        # 4th call hits the limit — processor should NOT be called
        with patch("src.routers.hooks.EventProcessor") as MockProcessor:
            proc_instance = AsyncMock()
            proc_instance.process_webhook = AsyncMock()
            MockProcessor.return_value = proc_instance

            request = _make_request(str(source_id))
            response = await receive_webhook(str(source_id), request, db)

            assert response.status_code == 429
            assert "Retry-After" in response.headers
            assert int(response.headers["Retry-After"]) > 0

            # Body must be JSON
            body = json.loads(bytes(response.body))
            assert body["error"] == "rate_limit_exceeded"
            assert body["source_id"] == str(source_id)

            # Processor must NOT have been invoked — no Event/EventDelivery rows
            proc_instance.process_webhook.assert_not_called()


@pytest.mark.asyncio
async def test_webhook_rate_limit_disabled_per_source():
    """When rate_limit_enabled=False, no throttling regardless of per_minute."""
    source_id = uuid4()
    event_source = _make_event_source(source_id=source_id)
    webhook_source = _make_webhook_source(
        rate_limit_enabled=False,
        rate_limit_per_minute=1,
        rate_limit_window_seconds=60,
    )

    db = AsyncMock()

    from src.services.webhooks.protocol import Rejected

    with (
        patch(
            "src.routers.hooks.resolve_webhook_source",
            return_value=(event_source, webhook_source),
        ),
        patch("src.routers.hooks.RateLimiter") as MockLimiter,
        patch("src.routers.hooks.EventProcessor") as MockProcessor,
    ):
        proc_instance = AsyncMock()
        proc_instance.process_webhook = AsyncMock(return_value=Rejected(message="ok", status_code=200))
        MockProcessor.return_value = proc_instance

        for _ in range(5):
            request = _make_request(str(source_id))
            response = await receive_webhook(str(source_id), request, db)
            assert response.status_code != 429, f"Disabled limiter should not throttle (call {_ + 1})"

        # RateLimiter should never have been instantiated
        MockLimiter.assert_not_called()


@pytest.mark.asyncio
async def test_rate_limit_hits_counter_incremented_on_429():
    """Each 429 increments bifrost:rate_limit_hits:{source_id} with 24h TTL."""
    from unittest.mock import call
    from src.core.rate_limit import RateLimiter

    identifier = str(uuid4())
    limiter = RateLimiter(max_requests=2, window_seconds=60)

    # Build a mock redis pipeline
    mock_pipeline = AsyncMock()
    mock_pipeline.incr = MagicMock()
    mock_pipeline.expire = MagicMock()
    mock_pipeline.execute = AsyncMock(return_value=[1, True])

    mock_redis = AsyncMock()
    # incr: first two calls allowed (1, 2), third call exceeds (3)
    mock_redis.incr = AsyncMock(side_effect=[1, 2, 3])
    mock_redis.expire = AsyncMock()
    mock_redis.ttl = AsyncMock(return_value=55)
    mock_redis.pipeline = MagicMock(return_value=mock_pipeline)

    with patch("src.core.rate_limit.get_shared_redis", return_value=mock_redis):
        # First two calls: no 429
        await limiter.check("test_endpoint", identifier, force=True)
        await limiter.check("test_endpoint", identifier, force=True)
        mock_pipeline.incr.assert_not_called()

        # Third call: exceeds limit → pipeline.incr called
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            await limiter.check("test_endpoint", identifier, force=True)

        assert exc_info.value.status_code == 429

        hit_key = f"bifrost:rate_limit_hits:{identifier}"
        mock_pipeline.incr.assert_called_once_with(hit_key)
        mock_pipeline.expire.assert_called_once_with(hit_key, 86400)
        mock_pipeline.execute.assert_called_once()


@pytest.mark.asyncio
async def test_webhook_rate_limit_none_per_minute_bypasses_limiter():
    """When rate_limit_per_minute is None, no throttling."""
    source_id = uuid4()
    event_source = _make_event_source(source_id=source_id)
    webhook_source = _make_webhook_source(
        rate_limit_enabled=True,
        rate_limit_per_minute=None,
    )

    db = AsyncMock()

    from src.services.webhooks.protocol import Rejected

    with (
        patch(
            "src.routers.hooks.resolve_webhook_source",
            return_value=(event_source, webhook_source),
        ),
        patch("src.routers.hooks.RateLimiter") as MockLimiter,
        patch("src.routers.hooks.EventProcessor") as MockProcessor,
    ):
        proc_instance = AsyncMock()
        proc_instance.process_webhook = AsyncMock(return_value=Rejected(message="ok", status_code=200))
        MockProcessor.return_value = proc_instance

        request = _make_request(str(source_id))
        response = await receive_webhook(str(source_id), request, db)
        assert response.status_code != 429

        # RateLimiter should never have been instantiated
        MockLimiter.assert_not_called()
