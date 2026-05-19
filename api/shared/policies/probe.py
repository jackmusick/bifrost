"""High-level policy helpers used by REST handlers and the websocket layer.

These wrap the evaluator and compiler with action-aware logic and provide
the seeded admin-bypass default.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import or_ as sa_or
from sqlalchemy import true as sa_true
from sqlalchemy.sql import ColumnElement

from shared.policies.compile import compile_to_sql
from shared.policies.evaluate import evaluate
from src.models.contracts.policies import TablePolicies


# TEMPORARY: Task 6 replaces this with `from shared.table_policies import RowResolver`.
# Defined inline here so the engine refactor of Task 4 keeps tests green without
# requiring shared.table_policies (which doesn't exist yet).
class _RowResolverForEngine:
    """Mirrors the pre-Task-4 hardcoded {row: ...} resolution semantics."""
    namespace = "row"

    def resolve(self, path: str, ctx: Any) -> Any:
        parts = path.split(".")
        cur = ctx
        for p in parts:
            if not isinstance(cur, dict):
                return None
            cur = cur.get(p)
            if cur is None:
                return None
        return cur


# TEMPORARY: Task 6 replaces this with `from shared.table_policies import TableBinding`.
# Mirrors the pre-Task-5 hardcoded column mapping inside compile.py.
class _TableBindingForEngine:
    """Mirrors the pre-Task-5 hardcoded {row: ...} → Document column logic."""
    namespace = "row"

    def resolve_reference(self, path):
        from src.models.orm.tables import Document
        _COLUMN_MAPPED_ROW_FIELDS = {
            "id": Document.id,
            "organization_id": None,
            "created_by": Document.created_by,
            "updated_by": Document.updated_by,
            "created_at": Document.created_at,
            "updated_at": Document.updated_at,
            "table_id": Document.table_id,
        }
        parts = path.split(".")
        if len(parts) == 1 and parts[0] in _COLUMN_MAPPED_ROW_FIELDS:
            col = _COLUMN_MAPPED_ROW_FIELDS[parts[0]]
            if col is not None:
                return col
        if len(parts) == 1:
            return Document.data[parts[0]].astext
        return Document.data[parts].astext


def evaluate_action(
    action: str,
    policies: TablePolicies,
    row: dict,
    user: Any,
) -> bool:
    """OR across all rules whose `actions` includes `action`. Default deny."""
    for policy in policies.policies:
        if action not in policy.actions:
            continue
        if policy.when is None:
            return True
        if evaluate(policy.when, ctx=row, user=user, resolver=_RowResolverForEngine()):
            return True
    return False


def compile_read_filter(
    policies: TablePolicies,
    user: Any,
) -> ColumnElement | None:
    """Compile the OR of all read-allowing rules into a single WHERE clause.

    Returns None if no policy grants read (the handler must deny).
    """
    fragments: list[ColumnElement] = []
    for policy in policies.policies:
        if "read" not in policy.actions:
            continue
        if policy.when is None:
            fragments.append(sa_true())
            continue
        fragments.append(compile_to_sql(policy.when, user, _TableBindingForEngine()))
    if not fragments:
        return None
    if len(fragments) == 1:
        return fragments[0]
    return sa_or(*fragments)


def is_subscribe_authorized(policies: TablePolicies, user: Any) -> bool:
    """Probe: would ANY read message ever reach this user on this table?

    For row-data-dependent policies, we conservatively allow subscribe and
    let the per-message filter do the actual gating. For user-only policies
    (e.g. is_platform_admin), we resolve at probe time.
    """
    for policy in policies.policies:
        if "read" not in policy.actions:
            continue
        if policy.when is None:
            return True
        if _is_purely_user_dependent(policy.when.root):
            # Resolve immediately — no row context affects the answer
            if evaluate(policy.when, ctx={}, user=user, resolver=_RowResolverForEngine()):
                return True
            continue
        # Row-data-dependent → conservatively allow
        return True
    return False


def _is_purely_user_dependent(node: Any) -> bool:
    """True if the expression references only USER fields and literals."""
    if isinstance(node, (str, int, float, bool)) or node is None:
        return True
    if isinstance(node, list):
        return all(_is_purely_user_dependent(x) for x in node)
    if isinstance(node, dict):
        keys = set(node.keys())
        if keys == {"row"}:
            return False
        if keys == {"user"}:
            return True
        if "call" in keys:
            return all(_is_purely_user_dependent(a) for a in node.get("args", []))
        if len(keys) == 1:
            return _is_purely_user_dependent(node[next(iter(keys))])
    return False


def make_seed_admin_bypass() -> dict:
    """The default policies dict for a freshly-created table.

    Stored verbatim into Table.access at create time. Visible/editable
    in the policy editor; can be removed if an org wants strict audit.
    """
    return {
        "policies": [
            {
                "name": "admin_bypass",
                "description": "Platform admins bypass all checks. Edit or delete to enforce stricter audit.",
                "actions": ["read", "create", "update", "delete"],
                "when": {"user": "is_platform_admin"},
            }
        ]
    }
