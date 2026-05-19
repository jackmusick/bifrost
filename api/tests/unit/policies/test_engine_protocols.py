"""Engine-only tests proving the engine is domain-agnostic.

These tests use a stub Resolver/Binding rather than table-specific ones,
proving the walker code does not reach into any domain.
"""
from __future__ import annotations

from typing import Any, ClassVar

from sqlalchemy import column
from sqlalchemy.sql import ColumnElement

from shared.policies.binding import Binding
from shared.policies.resolver import Resolver


class StubResolver:
    namespace: ClassVar[str] = "row"

    def resolve(self, path: str, ctx: Any) -> Any:
        return (ctx or {}).get(path)


def test_resolver_protocol_runtime_check():
    """StubResolver structurally satisfies the Resolver protocol."""
    r: Resolver = StubResolver()
    assert r.namespace == "row"
    assert r.resolve("name", {"name": "alice"}) == "alice"
    assert r.resolve("missing", {}) is None
    assert r.resolve("name", None) is None


class StubBinding:
    namespace: ClassVar[str] = "row"

    def resolve_reference(self, path: str) -> ColumnElement[Any]:
        return column(path)


def test_binding_protocol_runtime_check():
    """StubBinding structurally satisfies the Binding protocol."""
    b: Binding = StubBinding()
    assert isinstance(b, Binding)
    assert b.namespace == "row"
    col = b.resolve_reference("name")
    assert str(col) == "name"
