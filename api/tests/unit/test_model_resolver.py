"""Unit tests for the chat-V2 model resolver and capability helpers.

Covers every cascade level (platform → org → role → workspace → user →
conversation → message), alias resolution, deprecation remap, and the
capability fallback that picks a peer model when the chosen one can't handle
attached content.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from shared.model_resolver import (
    ModelResolutionContext,
    ModelResolutionError,
    check_message_compat,
    has_capabilities,
    pick_compatible_from_set,
    resolve_model,
)
from src.models.enums import WorkspaceScope
from src.models.orm import (
    ModelDeprecation,
    Organization,
    OrgModelAlias,
    PlatformModel,
    Role,
    User,
    Workspace,
)


# Async-only mark — pure-function helper tests below opt out individually.
pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _caps(
    images_in: bool = False,
    images_out: bool = False,
    pdf_in: bool = False,
    tools: bool = False,
) -> dict:
    return {
        "supports_images_in": images_in,
        "supports_images_out": images_out,
        "supports_pdf_in": pdf_in,
        "supports_tool_use": tools,
        "supports_audio_in": False,
        "supports_audio_out": False,
    }


async def _seed_catalog(db: AsyncSession) -> None:
    """Three models across three tiers; vision capability varies."""
    await db.execute(delete(PlatformModel))
    db.add_all(
        [
            PlatformModel(
                model_id="anthropic/claude-haiku-4-5",
                provider="anthropic",
                display_name="Claude Haiku 4.5",
                cost_tier="fast",
                context_window=200_000,
                max_output_tokens=8192,
                capabilities=_caps(images_in=True, pdf_in=True, tools=True),
                is_active=True,
            ),
            PlatformModel(
                model_id="anthropic/claude-sonnet-4-6",
                provider="anthropic",
                display_name="Claude Sonnet 4.6",
                cost_tier="balanced",
                context_window=1_000_000,
                max_output_tokens=64_000,
                capabilities=_caps(images_in=True, pdf_in=True, tools=True),
                is_active=True,
            ),
            PlatformModel(
                model_id="anthropic/claude-opus-4-7",
                provider="anthropic",
                display_name="Claude Opus 4.7",
                cost_tier="premium",
                context_window=1_000_000,
                max_output_tokens=32_000,
                capabilities=_caps(images_in=True, pdf_in=True, tools=True),
                is_active=True,
            ),
            PlatformModel(
                model_id="text-only/example-mini",
                provider="example",
                display_name="Example Mini (text only)",
                cost_tier="fast",
                context_window=32_000,
                capabilities=_caps(),
                is_active=True,
            ),
        ]
    )
    await db.flush()


async def _make_org(
    db: AsyncSession,
    *,
    allowed: list[str] | None = None,
    default: str | None = None,
) -> Organization:
    org = Organization(
        id=uuid4(),
        name=f"Org {uuid4().hex[:6]}",
        is_active=True,
        is_provider=False,
        settings={},
        allowed_chat_models=allowed or [],
        default_chat_model=default,
        created_by="test",
    )
    db.add(org)
    await db.flush()
    return org


# ---------------------------------------------------------------------------
# Cascade levels
# ---------------------------------------------------------------------------


async def test_no_allowlist_no_default_raises(db_session):
    """With no allowlist AND no default, the resolver has nothing to call."""
    await _seed_catalog(db_session)
    org = await _make_org(db_session)

    with pytest.raises(ModelResolutionError):
        await resolve_model(
            db_session,
            ModelResolutionContext(organization_id=org.id),
        )


async def test_empty_allowlist_uses_only_org_default(db_session):
    """Empty allowlist = the safety guardrail. Only the org default is
    selectable; cascade values that don't equal it fall through."""
    await _seed_catalog(db_session)
    org = await _make_org(db_session, default="anthropic/claude-haiku-4-5")
    user = User(
        id=uuid4(),
        email=f"{uuid4().hex[:6]}@example.com",
        organization_id=org.id,
        # User would prefer Sonnet, but allowlist is empty so only
        # the org default (Haiku) is permitted.
        default_chat_model="anthropic/claude-sonnet-4-6",
    )
    db_session.add(user)
    await db_session.flush()

    choice = await resolve_model(
        db_session,
        ModelResolutionContext(organization_id=org.id, user_id=user.id),
    )
    assert choice.model_id == "anthropic/claude-haiku-4-5"
    assert choice.provenance == "org"


async def test_org_default_wins_over_platform_floor(db_session):
    await _seed_catalog(db_session)
    org = await _make_org(db_session, default="anthropic/claude-sonnet-4-6")

    choice = await resolve_model(
        db_session,
        ModelResolutionContext(organization_id=org.id),
    )
    assert choice.model_id == "anthropic/claude-sonnet-4-6"
    assert choice.provenance == "org"


async def test_user_default_beats_org_default(db_session):
    await _seed_catalog(db_session)
    org = await _make_org(
        db_session,
        allowed=["anthropic/claude-sonnet-4-6", "anthropic/claude-opus-4-7"],
        default="anthropic/claude-sonnet-4-6",
    )
    user = User(
        id=uuid4(),
        email=f"{uuid4().hex[:6]}@example.com",
        organization_id=org.id,
        default_chat_model="anthropic/claude-opus-4-7",
    )
    db_session.add(user)
    await db_session.flush()

    choice = await resolve_model(
        db_session,
        ModelResolutionContext(organization_id=org.id, user_id=user.id),
    )
    assert choice.model_id == "anthropic/claude-opus-4-7"
    assert choice.provenance == "user"


async def test_user_default_beats_workspace_default(db_session):
    """Cascade: ... workspace → user → conversation → message (per master plan).

    A user's personal default overrides the workspace's group default — the
    user is the more specific layer.
    """
    await _seed_catalog(db_session)
    org = await _make_org(
        db_session,
        allowed=[
            "anthropic/claude-sonnet-4-6",
            "anthropic/claude-haiku-4-5",
            "anthropic/claude-opus-4-7",
        ],
        default="anthropic/claude-sonnet-4-6",
    )
    user = User(
        id=uuid4(),
        email=f"{uuid4().hex[:6]}@example.com",
        organization_id=org.id,
        default_chat_model="anthropic/claude-opus-4-7",
    )
    db_session.add(user)
    await db_session.flush()
    ws = Workspace(
        id=uuid4(),
        name="WS",
        scope=WorkspaceScope.ORG,
        organization_id=org.id,
        default_model="anthropic/claude-haiku-4-5",
        created_by="test",
    )
    db_session.add(ws)
    await db_session.flush()

    choice = await resolve_model(
        db_session,
        ModelResolutionContext(
            organization_id=org.id,
            user_id=user.id,
            workspace_id=ws.id,
        ),
    )
    assert choice.model_id == "anthropic/claude-opus-4-7"
    assert choice.provenance == "user"


async def test_workspace_default_used_when_user_has_none(db_session):
    """Workspace default applies when the user hasn't set a personal default."""
    await _seed_catalog(db_session)
    org = await _make_org(
        db_session,
        allowed=["anthropic/claude-sonnet-4-6", "anthropic/claude-haiku-4-5"],
        default="anthropic/claude-sonnet-4-6",
    )
    user = User(
        id=uuid4(),
        email=f"{uuid4().hex[:6]}@example.com",
        organization_id=org.id,
        default_chat_model=None,
    )
    db_session.add(user)
    await db_session.flush()
    ws = Workspace(
        id=uuid4(),
        name="WS",
        scope=WorkspaceScope.ORG,
        organization_id=org.id,
        default_model="anthropic/claude-haiku-4-5",
        created_by="test",
    )
    db_session.add(ws)
    await db_session.flush()

    choice = await resolve_model(
        db_session,
        ModelResolutionContext(
            organization_id=org.id,
            user_id=user.id,
            workspace_id=ws.id,
        ),
    )
    assert choice.model_id == "anthropic/claude-haiku-4-5"
    assert choice.provenance == "workspace"


async def test_message_override_wins(db_session):
    await _seed_catalog(db_session)
    org = await _make_org(
        db_session,
        allowed=[
            "anthropic/claude-sonnet-4-6",
            "anthropic/claude-haiku-4-5",
            "anthropic/claude-opus-4-7",
        ],
        default="anthropic/claude-sonnet-4-6",
    )

    choice = await resolve_model(
        db_session,
        ModelResolutionContext(
            organization_id=org.id,
            conversation_current_model="anthropic/claude-haiku-4-5",
            message_override="anthropic/claude-opus-4-7",
        ),
    )
    assert choice.model_id == "anthropic/claude-opus-4-7"
    assert choice.provenance == "message"


async def test_conversation_override_wins_over_user_default(db_session):
    await _seed_catalog(db_session)
    org = await _make_org(
        db_session,
        allowed=[
            "anthropic/claude-sonnet-4-6",
            "anthropic/claude-haiku-4-5",
            "anthropic/claude-opus-4-7",
        ],
        default="anthropic/claude-sonnet-4-6",
    )
    user = User(
        id=uuid4(),
        email=f"{uuid4().hex[:6]}@example.com",
        organization_id=org.id,
        default_chat_model="anthropic/claude-opus-4-7",
    )
    db_session.add(user)
    await db_session.flush()

    choice = await resolve_model(
        db_session,
        ModelResolutionContext(
            organization_id=org.id,
            user_id=user.id,
            conversation_current_model="anthropic/claude-haiku-4-5",
        ),
    )
    assert choice.model_id == "anthropic/claude-haiku-4-5"
    assert choice.provenance == "conversation"


# ---------------------------------------------------------------------------
# Allowlist intersection
# ---------------------------------------------------------------------------


async def test_org_allowlist_excludes_default(db_session):
    """If the user-default points at a model the org disallows, fall through."""
    await _seed_catalog(db_session)
    org = await _make_org(
        db_session,
        allowed=["anthropic/claude-sonnet-4-6", "anthropic/claude-haiku-4-5"],
        default="anthropic/claude-sonnet-4-6",
    )
    user = User(
        id=uuid4(),
        email=f"{uuid4().hex[:6]}@example.com",
        organization_id=org.id,
        default_chat_model="anthropic/claude-opus-4-7",  # NOT in allowlist
    )
    db_session.add(user)
    await db_session.flush()

    choice = await resolve_model(
        db_session,
        ModelResolutionContext(organization_id=org.id, user_id=user.id),
    )
    assert choice.model_id == "anthropic/claude-sonnet-4-6"
    assert choice.provenance == "org"


async def test_uncached_allowlist_passes_through(db_session):
    """Catalog is for enrichment, not gating. An allowlist entry that isn't
    in platform_models is still callable — the resolver returns it as-is."""
    await _seed_catalog(db_session)
    org = await _make_org(
        db_session,
        allowed=["some-new-provider/some-new-model"],
        default="some-new-provider/some-new-model",
    )

    choice = await resolve_model(
        db_session,
        ModelResolutionContext(organization_id=org.id),
    )
    assert choice.model_id == "some-new-provider/some-new-model"


# ---------------------------------------------------------------------------
# Aliases + deprecations
# ---------------------------------------------------------------------------


async def test_org_alias_resolves_to_target(db_session):
    await _seed_catalog(db_session)
    org = await _make_org(db_session, default="acme-default")
    db_session.add(
        OrgModelAlias(
            organization_id=org.id,
            alias="acme-default",
            target_model_id="anthropic/claude-sonnet-4-6",
            display_name="Acme Default",
        )
    )
    await db_session.flush()

    choice = await resolve_model(
        db_session,
        ModelResolutionContext(organization_id=org.id),
    )
    assert choice.model_id == "anthropic/claude-sonnet-4-6"


async def test_platform_deprecation_remap_at_lookup(db_session):
    await _seed_catalog(db_session)
    org = await _make_org(db_session, default="claude-3-5-sonnet-20240620")
    db_session.add(
        ModelDeprecation(
            old_model_id="claude-3-5-sonnet-20240620",
            new_model_id="anthropic/claude-sonnet-4-6",
            deprecated_at=datetime.now(timezone.utc),
            organization_id=None,  # platform-wide
        )
    )
    await db_session.flush()

    choice = await resolve_model(
        db_session,
        ModelResolutionContext(organization_id=org.id),
    )
    assert choice.model_id == "anthropic/claude-sonnet-4-6"


async def test_org_deprecation_overrides_platform(db_session):
    """Org-level remap wins over platform-wide."""
    await _seed_catalog(db_session)
    org = await _make_org(db_session, default="claude-3-5-sonnet-20240620")
    db_session.add(
        ModelDeprecation(
            old_model_id="claude-3-5-sonnet-20240620",
            new_model_id="anthropic/claude-haiku-4-5",  # org wants haiku
            deprecated_at=datetime.now(timezone.utc),
            organization_id=org.id,
        )
    )
    db_session.add(
        ModelDeprecation(
            old_model_id="claude-3-5-sonnet-20240620",
            new_model_id="anthropic/claude-sonnet-4-6",
            deprecated_at=datetime.now(timezone.utc),
            organization_id=None,
        )
    )
    await db_session.flush()

    choice = await resolve_model(
        db_session,
        ModelResolutionContext(organization_id=org.id),
    )
    assert choice.model_id == "anthropic/claude-haiku-4-5"


# ---------------------------------------------------------------------------
# Role default
# ---------------------------------------------------------------------------


async def test_role_default_used_when_set(db_session):
    await _seed_catalog(db_session)
    org = await _make_org(
        db_session,
        allowed=["anthropic/claude-sonnet-4-6", "anthropic/claude-haiku-4-5"],
        default="anthropic/claude-sonnet-4-6",
    )
    role = Role(
        id=uuid4(),
        name=f"role-{uuid4().hex[:6]}",
        permissions={},
        default_chat_model="anthropic/claude-haiku-4-5",
        created_by="test",
    )
    db_session.add(role)
    await db_session.flush()

    choice = await resolve_model(
        db_session,
        ModelResolutionContext(organization_id=org.id, role_ids=(role.id,)),
    )
    assert choice.model_id == "anthropic/claude-haiku-4-5"
    assert choice.provenance == "role"


# ---------------------------------------------------------------------------
# Capability fallback
# ---------------------------------------------------------------------------


async def test_capability_fallback_swaps_to_peer_with_cap(db_session):
    """Picked default is text-only; required capability forces a peer."""
    await _seed_catalog(db_session)
    org = await _make_org(
        db_session,
        allowed=["text-only/example-mini", "anthropic/claude-sonnet-4-6"],
        default="text-only/example-mini",
    )

    choice = await resolve_model(
        db_session,
        ModelResolutionContext(
            organization_id=org.id,
            required_capabilities=frozenset({"supports_images_in"}),
        ),
    )
    # Text-only model can't satisfy; resolver picks the balanced peer.
    assert choice.model_id == "anthropic/claude-sonnet-4-6"
    assert choice.provenance == "capability-fallback"


async def test_capability_fallback_raises_when_nothing_compatible(db_session):
    await _seed_catalog(db_session)
    org = await _make_org(
        db_session,
        allowed=["text-only/example-mini"],
        default="text-only/example-mini",
    )

    with pytest.raises(ModelResolutionError):
        await resolve_model(
            db_session,
            ModelResolutionContext(
                organization_id=org.id,
                required_capabilities=frozenset({"supports_images_in"}),
            ),
        )


# ---------------------------------------------------------------------------
# Pure-function helpers
# ---------------------------------------------------------------------------


def test_has_capabilities_strict_match():
    pm = PlatformModel(
        model_id="x",
        provider="x",
        display_name="x",
        cost_tier="fast",
        capabilities=_caps(images_in=True),
        is_active=True,
    )
    assert has_capabilities(pm, frozenset({"supports_images_in"}))
    assert not has_capabilities(pm, frozenset({"supports_pdf_in"}))


def test_pick_compatible_prefers_balanced():
    fast = PlatformModel(
        model_id="fast",
        provider="x",
        display_name="fast",
        cost_tier="fast",
        capabilities=_caps(images_in=True),
        is_active=True,
    )
    balanced = PlatformModel(
        model_id="balanced",
        provider="x",
        display_name="balanced",
        cost_tier="balanced",
        capabilities=_caps(images_in=True),
        is_active=True,
    )
    by_id = {"fast": fast, "balanced": balanced}
    chosen = pick_compatible_from_set(
        {"fast", "balanced"}, by_id, frozenset({"supports_images_in"})
    )
    assert chosen == "balanced"


def test_check_message_compat_lists_reasons():
    pm = PlatformModel(
        model_id="x",
        provider="x",
        display_name="Tiny",
        cost_tier="fast",
        capabilities=_caps(),
        is_active=True,
    )
    reasons = check_message_compat(pm, has_image=True, needs_tool_use=True)
    assert len(reasons) == 2
    assert any("can't read images" in r for r in reasons)
    assert any("doesn't support tools" in r for r in reasons)
