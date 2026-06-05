"""CLI _resolve_target_install — a disconnected deploy must not silently
full-replace the wrong client's install when multiple org-scoped installs share
a slug (success-criteria §3.4, Codex G5)."""
from __future__ import annotations

import pytest

from bifrost.commands.solution import _AmbiguousInstall, _resolve_target_install


def test_no_match_returns_none():
    assert _resolve_target_install([], "mysol", "global") is None


def test_single_global_match():
    installs = [{"id": "g1", "slug": "mysol", "organization_id": None}]
    assert _resolve_target_install(installs, "mysol", "global") == "g1"


def test_single_org_match():
    installs = [{"id": "o1", "slug": "mysol", "organization_id": "org-a"}]
    assert _resolve_target_install(installs, "mysol", "org") == "o1"


def test_two_org_installs_same_slug_is_ambiguous():
    installs = [
        {"id": "o1", "slug": "mysol", "organization_id": "org-a"},
        {"id": "o2", "slug": "mysol", "organization_id": "org-b"},
    ]
    with pytest.raises(_AmbiguousInstall) as e:
        _resolve_target_install(installs, "mysol", "org")
    # Error must name both ids so the user can pick --solution.
    assert "o1" in str(e.value) and "o2" in str(e.value)
    assert "--solution" in str(e.value)


def test_scope_filters_out_wrong_scope():
    installs = [
        {"id": "g1", "slug": "mysol", "organization_id": None},   # global
        {"id": "o1", "slug": "mysol", "organization_id": "org-a"},  # org
    ]
    # Deploying the org-scoped descriptor must only see the org install.
    assert _resolve_target_install(installs, "mysol", "org") == "o1"
    # And the global descriptor only the global one.
    assert _resolve_target_install(installs, "mysol", "global") == "g1"
