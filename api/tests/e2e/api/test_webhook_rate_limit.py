"""
E2E: webhook rate limit caps Event row creation.

Regression prevention for the headline scenario: 100 inbound webhooks from a
misbehaving source must not produce 100 workflow runs. The rate limit caps the
count at the configured threshold.

Strategy
--------
1. Create an event source via the HTTP API so the API server owns it.
2. Directly update the WebhookSource rate-limit columns via db_session + commit
   (the API does not yet expose those fields in its create/update endpoints —
   that is Task 3.5).
3. Fire requests at /api/hooks/{source_id} using e2e_client (no auth required,
   public endpoint).
4. Assert HTTP 429s appear after the threshold and that Event row count
   in the DB does not exceed the limit.

Redis isolation: the RateLimiter key is
  rate_limit:<endpoint>:<identifier>
  = rate_limit:webhook_ingress:<source_id>

Fresh UUID per test → fresh Redis key → no carry-over between runs.
"""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.orm.events import Event, WebhookSource


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def rate_limited_source(e2e_client, platform_admin, db_session: AsyncSession):
    """
    Create a webhook event source with a rate limit of 3 req/60s.

    The source is created via the HTTP API (so the API server owns it),
    then the rate-limit columns are written directly into the DB
    (since the REST API doesn't expose those fields yet — Task 3.5).
    """
    source_name = f"rate-limit-e2e-{uuid.uuid4().hex[:8]}"

    # 1. Create via API — gets a proper WebhookSource row with adapter plumbing
    resp = e2e_client.post(
        "/api/events/sources",
        headers=platform_admin.headers,
        json={
            "name": source_name,
            "source_type": "webhook",
            "webhook": {"adapter_name": "generic", "config": {}},
        },
    )
    assert resp.status_code == 201, f"Create source failed: {resp.text}"
    source = resp.json()
    source_id = source["id"]

    # 2. Patch rate-limit columns directly — not yet in the REST contract
    await db_session.execute(
        update(WebhookSource)
        .where(WebhookSource.event_source_id == uuid.UUID(source_id))
        .values(
            rate_limit_enabled=True,
            rate_limit_per_minute=3,
            rate_limit_window_seconds=60,
        )
    )
    await db_session.commit()

    yield source

    # 3. Cleanup — hard delete the source (cascades to WebhookSource + Event rows)
    e2e_client.delete(
        f"/api/events/sources/{source_id}",
        headers=platform_admin.headers,
    )


# ---------------------------------------------------------------------------
# Test
# ---------------------------------------------------------------------------


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_webhook_rate_limit_caps_event_creation(
    e2e_client,
    platform_admin,  # noqa: ARG001  — pulled in to ensure session fixtures boot
    rate_limited_source,
    db_session: AsyncSession,
):
    """Past threshold, requests get 429 and Event rows are capped at the limit."""
    source_id = rate_limited_source["id"]

    accepted = 0
    rejected = 0

    # Fire 10 requests — limit is 3, so at most 3 should succeed
    for _ in range(10):
        r = e2e_client.post(
            f"/api/hooks/{source_id}",
            content=b"{}",
            headers={"Content-Type": "application/json"},
        )
        if r.status_code == 429:
            rejected += 1
            assert "Retry-After" in r.headers, "429 must carry Retry-After header"
            body = r.json()
            assert body["error"] == "rate_limit_exceeded"
            assert body["source_id"] == source_id
        else:
            # 202 Accepted (or rarely a non-429 transient) — counts as accepted
            accepted += 1

    assert accepted == 3, f"Expected exactly 3 accepted, got {accepted}"
    assert rejected == 7, f"Expected exactly 7 rejected, got {rejected}"

    # Event rows must be capped — 429 responses must not have created DB rows
    events = (
        await db_session.execute(
            select(Event).where(Event.event_source_id == uuid.UUID(source_id))
        )
    ).scalars().all()

    assert len(events) <= 3, (
        f"Expected at most 3 Event rows (one per accepted request), "
        f"found {len(events)}"
    )

    # The rate_limited_count_24h on the source response must reflect the rejections
    src_response = e2e_client.get(
        f"/api/events/sources/{source_id}",
        headers=platform_admin.headers,
    )
    assert src_response.status_code == 200
    webhook_data = src_response.json()["webhook"]
    assert webhook_data is not None
    assert webhook_data["rate_limited_count_24h"] >= 7, (
        f"Expected at least 7 rate-limit hits recorded, "
        f"got {webhook_data['rate_limited_count_24h']}"
    )
