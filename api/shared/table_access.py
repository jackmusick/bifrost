"""Pure-function table access checker.

Resolves access rules additively across three scopes (Everyone, Role, Creator).
The caller is responsible for loading Table.access, the user's role IDs, and
(for read/update/delete on a single row) the row's created_by before invoking.
"""
from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID


class Action(str, enum.Enum):
    READ = "read"
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"


@dataclass(frozen=True)
class Caller:
    """A logged-in user invoking a tables endpoint."""

    user_id: UUID
    role_ids: frozenset[UUID] = field(default_factory=frozenset)
    is_admin: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.role_ids, frozenset):
            object.__setattr__(self, "role_ids", frozenset(self.role_ids))


@dataclass(frozen=True)
class WorkflowCaller:
    """Sentinel for SDK callers running inside a workflow execution."""


@dataclass(frozen=True)
class CheckResult:
    allow: bool
    # True iff the only scope granting read is Creator. The caller (list/query
    # endpoint) is expected to add `WHERE created_by = caller.user_id` to the SQL.
    creator_filter_required: bool = False


def _scope_flag(block: dict[str, Any] | None, action: Action) -> bool:
    if not block:
        return False
    return bool(block.get(action.value, False))


def check_table_access(
    *,
    action: Action,
    access: dict[str, Any] | None,
    caller: Caller | WorkflowCaller,
    row_created_by: UUID | None = None,
) -> CheckResult:
    """Resolve whether the caller can perform `action` on the table/row.

    `row_created_by` semantics:
      - `None` and action in {CREATE} → row doesn't exist yet; Creator.create applies.
      - `None` and action == READ     → list/query mode; Creator scope sets the
                                        `creator_filter_required` flag instead of
                                        gating on a specific row owner.
      - `UUID`                        → single-row check; Creator grants apply
                                        only if `row_created_by == caller.user_id`.
    """
    if isinstance(caller, WorkflowCaller):
        return CheckResult(allow=True)
    if caller.is_admin:
        return CheckResult(allow=True)
    if not access:
        return CheckResult(allow=False)

    everyone_grants = _scope_flag(access.get("everyone"), action)

    role_grants = False
    for role_block in (access.get("roles") or []):
        if not isinstance(role_block, dict):
            continue
        if not _scope_flag(role_block, action):
            continue
        role_ids_raw = role_block.get("roles") or []
        role_ids = {UUID(r) if isinstance(r, str) else r for r in role_ids_raw}
        if caller.role_ids & role_ids:
            role_grants = True
            break

    creator_grants_action = _scope_flag(access.get("creator"), action)
    if action == Action.CREATE:
        # Creator.create means "logged-in user can insert"; no row owner yet.
        creator_grants = creator_grants_action
    elif row_created_by is None:
        # List/query mode for READ; non-row-bound for UPDATE/DELETE means
        # we can't evaluate Creator (caller bug). Treat as not-granted; the
        # `creator_filter_required` flag handles the list case below.
        creator_grants = False
    else:
        creator_grants = creator_grants_action and row_created_by == caller.user_id

    allow = everyone_grants or role_grants or creator_grants

    creator_filter_required = (
        action == Action.READ
        and row_created_by is None
        and creator_grants_action
        and not everyone_grants
        and not role_grants
    )
    if creator_filter_required:
        allow = True

    return CheckResult(allow=allow, creator_filter_required=creator_filter_required)
