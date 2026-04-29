"""
Model Registry Sync

Fetches `models.json` from GitHub raw on an interval and upserts
`platform_models`, `model_deprecations` from it. Falls back to the bundled
copy on first boot when the table is empty and the network is unreachable.

The file itself is kept fresh by a separate GitHub Action that pulls from
OpenRouter (out of scope for M2 — landed as a follow-up).
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any

import httpx
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from shared.model_registry import (
    DEFAULT_REGISTRY_URL,
    RegistryFile,
    load_bundled,
    parse,
)
from src.core.cache import get_redis
from src.core.database import get_db_context
from src.models.orm.platform_models import ModelDeprecation, PlatformModel

logger = logging.getLogger(__name__)


REGISTRY_URL_ENV = "BIFROST_MODEL_REGISTRY_URL"
ETAG_REDIS_KEY = "bifrost:model_registry:etag"


def _registry_url() -> str:
    return os.environ.get(REGISTRY_URL_ENV, DEFAULT_REGISTRY_URL)


async def sync_model_registry() -> dict[str, Any]:
    """Refresh `platform_models` from the registry file.

    Order of operations:
    1. Try GitHub raw with ETag. On 200 → upsert. On 304 → no-op. On error → step 2.
    2. If `platform_models` is empty, seed from the bundled file.
    3. Otherwise leave the table alone (last-known-good wins on transient failures).

    Returns a summary dict suitable for logging.
    """
    summary: dict[str, Any] = {
        "url": _registry_url(),
        "fetched": False,
        "source": None,
        "models_upserted": 0,
        "models_deactivated": 0,
        "deprecations_upserted": 0,
        "errors": [],
    }

    file: RegistryFile | None = None
    new_etag: str | None = None

    headers: dict[str, str] = {}
    async with get_redis() as r:
        cached_etag = await r.get(ETAG_REDIS_KEY)
    if cached_etag:
        headers["If-None-Match"] = (
            cached_etag.decode() if isinstance(cached_etag, bytes) else cached_etag
        )

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(_registry_url(), headers=headers)
        if resp.status_code == 304:
            summary["fetched"] = True
            summary["source"] = "github-raw-304"
            logger.info("model_registry_sync: ETag matched, skipping upsert")
            return summary
        resp.raise_for_status()
        file = parse(resp.content)
        new_etag = resp.headers.get("ETag")
        summary["fetched"] = True
        summary["source"] = "github-raw"
    except Exception as e:  # network, DNS, JSON parse
        logger.warning("model_registry_sync: remote fetch failed: %s", e)
        summary["errors"].append(f"remote_fetch: {e}")

    async with get_db_context() as db:
        if file is None:
            existing = await db.scalar(select(PlatformModel.model_id).limit(1))
            if existing is None:
                logger.info("model_registry_sync: seeding from bundled models.json")
                file = load_bundled()
                summary["source"] = "bundled-seed"
            else:
                logger.info(
                    "model_registry_sync: remote unavailable, table populated, no-op"
                )
                return summary

        # Upsert models
        seen_model_ids: set[str] = set()
        for m in file.models:
            seen_model_ids.add(m.model_id)
            stmt = pg_insert(PlatformModel).values(
                model_id=m.model_id,
                provider=m.provider,
                display_name=m.display_name,
                capabilities=m.capabilities.model_dump(),
                cost_tier=m.cost_tier,
                context_window=m.context_window,
                max_output_tokens=m.max_output_tokens,
                input_price_per_million=m.input_price_per_million,
                output_price_per_million=m.output_price_per_million,
                deprecated_at=m.deprecated_at,
                is_active=True,
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=[PlatformModel.model_id],
                set_={
                    "provider": stmt.excluded.provider,
                    "display_name": stmt.excluded.display_name,
                    "capabilities": stmt.excluded.capabilities,
                    "cost_tier": stmt.excluded.cost_tier,
                    "context_window": stmt.excluded.context_window,
                    "max_output_tokens": stmt.excluded.max_output_tokens,
                    "input_price_per_million": stmt.excluded.input_price_per_million,
                    "output_price_per_million": stmt.excluded.output_price_per_million,
                    "deprecated_at": stmt.excluded.deprecated_at,
                    "is_active": True,
                    "updated_at": datetime.now(timezone.utc),
                },
            )
            await db.execute(stmt)
            summary["models_upserted"] += 1

        # Deactivate rows missing from the file (don't delete — preserves FK refs).
        result = await db.execute(
            select(PlatformModel.model_id).where(PlatformModel.is_active.is_(True))
        )
        existing_active = {row[0] for row in result.all()}
        to_deactivate = existing_active - seen_model_ids
        if to_deactivate:
            for mid in to_deactivate:
                pm = await db.get(PlatformModel, mid)
                if pm is not None:
                    pm.is_active = False
                    pm.updated_at = datetime.now(timezone.utc)
            summary["models_deactivated"] = len(to_deactivate)

        # Replace platform-wide deprecations (organization_id IS NULL) atomically.
        await db.execute(
            delete(ModelDeprecation).where(ModelDeprecation.organization_id.is_(None))
        )
        for d in file.deprecations:
            db.add(
                ModelDeprecation(
                    old_model_id=d.old_model_id,
                    new_model_id=d.new_model_id,
                    deprecated_at=d.deprecated_at,
                    organization_id=None,
                    notes=d.notes,
                )
            )
            summary["deprecations_upserted"] += 1

        await db.commit()

    if new_etag:
        async with get_redis() as r:
            await r.set(ETAG_REDIS_KEY, new_etag)

    logger.info("model_registry_sync: %s", summary)
    return summary
