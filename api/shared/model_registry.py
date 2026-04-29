"""
Platform model registry — loader for `models.json`.

This module owns the schema of `api/shared/data/models.json` and provides:
- Pydantic types for the file's contents (`RegistryFile`, `RegistryModel`, etc.).
- Loaders for the bundled file (offline / first-boot seed) and for the remote
  GitHub-raw URL (kept fresh by a scheduled GitHub Action).

The registry is a CACHE in `platform_models` table; the sync job in
`api/src/jobs/schedulers/model_registry_sync.py` reads this loader's output and
upserts the table.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)


# LiteLLM publishes a 2k+ entry registry with per-model pricing, capability
# flags, and context window. Updated multiple times per day (median ~3h between
# commits). MIT-licensed. We snapshot it on a 6h interval, validating + tier-
# binning along the way; the bundled file in `data/models.json` is the offline
# / first-boot seed.
DEFAULT_REGISTRY_URL = (
    "https://raw.githubusercontent.com/BerriAI/litellm/main/"
    "model_prices_and_context_window.json"
)

BUNDLED_REGISTRY_PATH = Path(__file__).parent / "data" / "models.json"


# Reseller hostnames → reseller key, matching LiteLLM's get_llm_provider_logic.
# When the configured LLM endpoint hostname matches one of these, the model_id
# returned by /v1/models is prefixed with `<reseller>/` to form the key into
# this registry. Empty match (None) means "direct provider call" — the model_id
# is the key as-is. List lifted verbatim from LiteLLM upstream.
RESELLER_BY_HOST: dict[str, str] = {
    "openrouter.ai": "openrouter",
    "api.together.xyz": "together_ai",
    "api.fireworks.ai": "fireworks_ai",
    "api.deepinfra.com": "deepinfra",
    "api.groq.com": "groq",
    "integrate.api.nvidia.com": "nvidia_nim",
    "api.cerebras.ai": "cerebras",
    "inference.baseten.co": "baseten",
    "api.sambanova.ai": "sambanova",
    "api.ai21.com": "ai21_chat",
    "api.perplexity.ai": "perplexity",
    "api.mistral.ai": "mistral",
    "api.deepseek.com": "deepseek",
    "api.friendli.ai": "friendliai",
    "api.lambdalabs.com": "lambda_ai",
    "api.novita.ai": "novita",
    "api.hyperbolic.xyz": "hyperbolic",
    "api.replicate.com": "replicate",
    "ollama.com": "ollama",
    "api.z.ai": "z_ai",
}


def reseller_for_endpoint(endpoint: str | None) -> str | None:
    """Map a configured LLM endpoint URL to a LiteLLM-style reseller key.

    Returns None when the endpoint is the model maker's own API (direct call,
    no prefix needed in the registry lookup) or when we don't recognize the
    host. Direct calls and unknown hosts both fall through to the unprefixed
    `model_id` key in `lookup_capabilities()`.
    """
    if not endpoint:
        return None
    from urllib.parse import urlparse

    host = urlparse(endpoint).hostname or ""
    return RESELLER_BY_HOST.get(host)


def lookup_capabilities(
    model_id: str,
    *,
    reseller: str | None = None,
    by_id: dict[str, "RegistryModel"] | None = None,
) -> "RegistryModel | None":
    """Resolve a returned-from-provider model_id into a registry row.

    Tries, in order:
      1. `<reseller>/<model_id>` exact match (handles OpenRouter/Together/etc.)
      2. `model_id` exact match (handles direct provider calls)
      3. Same as 1 + 2 with leading `~` stripped (OpenRouter aliases use `~`)
      4. Suffix-after-last-slash exact match (odd routing forms)
      5. Endswith-match: any key whose suffix equals our suffix. Handles
         OpenRouter `moonshotai/kimi-k2.6` ↔ LiteLLM `moonshot/kimi-k2.6`.
    """
    if by_id is None:
        return None

    # Strip OpenRouter's `~` redirect-marker, both globally (`~author/model`)
    # and after a slash (`reseller/~author/model`).
    import re

    clean = re.sub(r"(^|/)~", r"\1", model_id)

    candidates = []
    if reseller:
        candidates.append(f"{reseller}/{model_id}")
        if clean != model_id:
            candidates.append(f"{reseller}/{clean}")
    candidates.append(model_id)
    if clean != model_id:
        candidates.append(clean)

    for k in candidates:
        hit = by_id.get(k)
        if hit is not None:
            return hit

    # Suffix exact, then endswith-any
    suffix = clean.rsplit("/", 1)[-1]
    if suffix != clean:
        hit = by_id.get(suffix)
        if hit is not None:
            return hit
        target = "/" + suffix
        for k in by_id:
            if k.endswith(target):
                return by_id[k]
    return None


class RegistryCapabilities(BaseModel):
    model_config = ConfigDict(extra="allow")

    supports_images_in: bool = False
    supports_images_out: bool = False
    supports_pdf_in: bool = False
    supports_tool_use: bool = False
    supports_audio_in: bool = False
    supports_audio_out: bool = False


class RegistryModel(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    model_id: str
    provider: str
    display_name: str
    cost_tier: str
    context_window: int | None = None
    max_output_tokens: int | None = None
    input_price_per_million: Decimal | None = None
    output_price_per_million: Decimal | None = None
    capabilities: RegistryCapabilities = Field(default_factory=RegistryCapabilities)
    deprecated_at: datetime | None = None


class RegistryAlias(BaseModel):
    alias: str
    target_model_id: str
    display_name: str | None = None
    description: str | None = None


class RegistryDeprecation(BaseModel):
    old_model_id: str
    new_model_id: str
    deprecated_at: datetime
    notes: str | None = None


class RegistryFile(BaseModel):
    schema_version: int
    generated_at: datetime
    source: str | None = None
    models: list[RegistryModel]
    aliases: list[RegistryAlias] = Field(default_factory=list)
    deprecations: list[RegistryDeprecation] = Field(default_factory=list)


def load_bundled() -> RegistryFile:
    """Load the bundled `models.json` from disk. Used as the offline seed."""
    raw = BUNDLED_REGISTRY_PATH.read_text(encoding="utf-8")
    return RegistryFile.model_validate_json(raw)


def parse(raw: str | bytes | dict[str, Any]) -> RegistryFile:
    """Validate-and-parse a registry payload from JSON text or a dict.

    Auto-detects shape: our own snapshot (dict with `schema_version`) is
    parsed directly; LiteLLM's raw upstream shape (flat dict keyed by model_id)
    is transformed first via `transform_litellm()`.
    """
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    if isinstance(raw, str):
        raw = json.loads(raw)
    assert isinstance(raw, dict)
    if "schema_version" in raw and "models" in raw:
        return RegistryFile.model_validate(raw)
    return transform_litellm(raw)


def _derive_tier(output_price_per_token: float | None) -> str:
    """Bin a model into a cost tier based on its output price.

    LiteLLM has price but no tier label, so derive on import. Thresholds
    chosen to put Haiku/Mini-class in `fast`, Sonnet/4o in `balanced`, and
    Opus/o1/Gemini-Pro in `premium`. Free / unknown lands in `uncategorized`.
    """
    if output_price_per_token is None or output_price_per_token == 0:
        return "uncategorized"
    per_million = output_price_per_token * 1_000_000
    if per_million < 1.0:
        return "fast"
    if per_million < 10.0:
        return "balanced"
    return "premium"


def transform_litellm(litellm_doc: dict[str, Any]) -> RegistryFile:
    """Convert LiteLLM's flat catalog into our `RegistryFile` shape.

    LiteLLM publishes 2k+ entries keyed by model_id. We keep chat models only
    (skip embeddings, audio-only, image gen) and project the fields we use.
    """
    from datetime import datetime, timezone
    from decimal import Decimal

    models: list[RegistryModel] = []
    for k, v in litellm_doc.items():
        if not isinstance(v, dict):
            continue
        # Skip "sample_spec" pseudo-rows and any non-chat modes (LiteLLM marks
        # embeddings as "embedding", audio TTS as "audio_speech", etc.).
        if k == "sample_spec":
            continue
        mode = v.get("mode")
        if mode is not None and mode != "chat":
            continue
        cap = RegistryCapabilities(
            supports_images_in=bool(v.get("supports_vision")),
            supports_images_out=False,
            supports_pdf_in=bool(v.get("supports_pdf_input")),
            supports_tool_use=bool(v.get("supports_function_calling")),
            supports_audio_in=bool(v.get("supports_audio_input")),
            supports_audio_out=bool(v.get("supports_audio_output")),
        )
        inp = v.get("input_cost_per_token")
        outp = v.get("output_cost_per_token")
        models.append(
            RegistryModel(
                model_id=k,
                provider=v.get("litellm_provider", "unknown"),
                display_name=k.split("/")[-1],
                cost_tier=_derive_tier(outp),
                context_window=v.get("max_input_tokens") or v.get("max_tokens"),
                max_output_tokens=v.get("max_output_tokens"),
                input_price_per_million=(
                    Decimal(str(round(inp * 1_000_000, 6))) if inp else None
                ),
                output_price_per_million=(
                    Decimal(str(round(outp * 1_000_000, 6))) if outp else None
                ),
                capabilities=cap,
            )
        )
    return RegistryFile(
        schema_version=2,
        generated_at=datetime.now(timezone.utc),
        source=DEFAULT_REGISTRY_URL,
        models=models,
        aliases=[],
        deprecations=[],
    )
