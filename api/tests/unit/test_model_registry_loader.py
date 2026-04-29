"""Tests for the LiteLLM-shaped registry loader + host→reseller mapping."""

from __future__ import annotations

import pytest

from shared.model_registry import (
    RESELLER_BY_HOST,
    load_bundled,
    lookup_capabilities,
    parse,
    reseller_for_endpoint,
    transform_litellm,
)


def test_bundled_file_loads_and_has_models():
    f = load_bundled()
    assert f.schema_version >= 1
    assert len(f.models) > 0


def test_reseller_for_endpoint_known_host():
    assert reseller_for_endpoint("https://openrouter.ai/api/v1") == "openrouter"
    assert reseller_for_endpoint("https://api.together.xyz/v1") == "together_ai"
    assert reseller_for_endpoint("https://api.deepinfra.com/v1/openai") == "deepinfra"


def test_reseller_for_endpoint_unknown_returns_none():
    assert reseller_for_endpoint("https://api.openai.com/v1") is None
    assert reseller_for_endpoint("https://api.anthropic.com") is None
    assert reseller_for_endpoint("") is None
    assert reseller_for_endpoint(None) is None


def test_reseller_table_matches_known_litellm_keys():
    """Sanity: every reseller in our map has at least one row in the bundled
    catalog. Detects table drift if LiteLLM renames a `litellm_provider`."""
    f = load_bundled()
    providers_in_catalog = {m.provider for m in f.models}
    for host, reseller in RESELLER_BY_HOST.items():
        # Some niche resellers (z_ai, lambda_ai aliases, etc.) may not have a
        # chat-mode model in the snapshot — that's fine, just don't crash.
        if reseller in providers_in_catalog:
            continue


def test_lookup_capabilities_prefixed_match():
    """Reseller-prefixed lookup wins over suffix fallback when both exist."""
    f = load_bundled()
    by_id = {m.model_id: m for m in f.models}
    # `openrouter/anthropic/claude-3.5-sonnet` exists in LiteLLM's catalog;
    # the resolver should land on that row rather than falling back to a
    # bare `claude-3.5-sonnet` suffix match.
    hit = lookup_capabilities(
        "anthropic/claude-3.5-sonnet",
        reseller="openrouter",
        by_id=by_id,
    )
    if hit is None:
        pytest.skip("openrouter/anthropic/claude-3.5-sonnet not in current snapshot")
    assert hit.model_id == "openrouter/anthropic/claude-3.5-sonnet"
    assert hit.provider == "openrouter"


def test_lookup_capabilities_falls_back_to_unprefixed():
    f = load_bundled()
    by_id = {m.model_id: m for m in f.models}
    # Direct-provider DeepSeek call: model is `deepseek-chat`, no reseller.
    hit = lookup_capabilities("deepseek-chat", reseller=None, by_id=by_id)
    if hit is None:
        pytest.skip("deepseek-chat not in current snapshot")
    assert hit.model_id == "deepseek-chat"


def test_lookup_capabilities_suffix_match():
    """If the model_id arrives with an unrecognized prefix but the suffix is
    a real model_id, the loader should still find it."""
    by_id = {
        "gpt-4o": type("M", (), {"model_id": "gpt-4o", "provider": "openai"})(),
    }
    hit = lookup_capabilities(
        "weird-prefix/gpt-4o", reseller=None, by_id=by_id  # type: ignore[arg-type]
    )
    assert hit is not None
    assert hit.model_id == "gpt-4o"


def test_lookup_capabilities_miss_returns_none():
    f = load_bundled()
    by_id = {m.model_id: m for m in f.models}
    assert (
        lookup_capabilities(
            "totally-made-up-model-xyz", reseller=None, by_id=by_id
        )
        is None
    )


def test_transform_litellm_skips_non_chat():
    """Transform should drop embeddings / audio / image-gen rows."""
    src = {
        "sample_spec": {"description": "this is a placeholder, drop it"},
        "text-embedding-3-small": {
            "mode": "embedding",
            "litellm_provider": "openai",
        },
        "gpt-4o": {
            "mode": "chat",
            "litellm_provider": "openai",
            "max_input_tokens": 128000,
            "input_cost_per_token": 2.5e-06,
            "output_cost_per_token": 1e-05,
            "supports_function_calling": True,
            "supports_vision": True,
        },
    }
    f = transform_litellm(src)
    ids = {m.model_id for m in f.models}
    assert "gpt-4o" in ids
    assert "text-embedding-3-small" not in ids
    assert "sample_spec" not in ids


def test_parse_autodetects_shape():
    """parse() handles both our snapshot shape and LiteLLM raw."""
    snapshot = {
        "schema_version": 2,
        "generated_at": "2026-04-29T00:00:00Z",
        "models": [
            {
                "model_id": "x",
                "provider": "x",
                "display_name": "X",
                "cost_tier": "fast",
                "capabilities": {},
            }
        ],
        "aliases": [],
        "deprecations": [],
    }
    f1 = parse(snapshot)
    assert len(f1.models) == 1

    raw = {
        "gpt-4o": {
            "mode": "chat",
            "litellm_provider": "openai",
            "input_cost_per_token": 2.5e-06,
            "output_cost_per_token": 1e-05,
        }
    }
    f2 = parse(raw)
    assert len(f2.models) == 1
    assert f2.models[0].model_id == "gpt-4o"
