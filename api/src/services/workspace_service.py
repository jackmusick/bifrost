"""
Workspace Service.

Business logic for workspaces (chat-ux-design §2):
- Visibility/access checks for personal/org/role-scoped workspaces.
- Tool-intersection rule when assembling agent context inside a workspace.

Conversations may belong to a workspace OR live in the general pool
(`Conversation.workspace_id IS NULL`) — the unscoped default chat list. There
is no synthetic "Personal" workspace; users create private (scope=personal)
workspaces explicitly when they want one.

Routers stay thin: they delegate to functions here.
"""

from __future__ import annotations

import logging

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.auth import UserPrincipal
from src.models.enums import WorkspaceScope
from src.models.orm.users import UserRole
from src.models.orm.workspaces import Workspace

logger = logging.getLogger(__name__)


async def list_visible_workspaces(
    db: AsyncSession,
    user: UserPrincipal,
    active_only: bool = True,
) -> list[Workspace]:
    """List workspaces the user can see.

    Visibility rules (chat-ux-design §2.3):
    - Platform admins see everything.
    - Personal (private) workspaces: only the owner sees them.
    - Org workspaces: visible to anyone in the workspace's organization.
    - Role workspaces: visible to users that hold the workspace's role.
    """
    query = select(Workspace)
    if active_only:
        query = query.where(Workspace.is_active.is_(True))

    if user.is_platform_admin:
        query = query.order_by(Workspace.name)
        result = await db.execute(query)
        return list(result.scalars().all())

    role_ids_result = await db.execute(
        select(UserRole.role_id).where(UserRole.user_id == user.user_id)
    )
    user_role_ids = list(role_ids_result.scalars().all())

    conditions = [
        # Private workspaces I own.
        (Workspace.scope == WorkspaceScope.PERSONAL)
        & (Workspace.user_id == user.user_id),
    ]

    if user.organization_id is not None:
        conditions.append(
            (Workspace.scope == WorkspaceScope.ORG)
            & (Workspace.organization_id == user.organization_id)
        )

    if user_role_ids:
        conditions.append(
            (Workspace.scope == WorkspaceScope.ROLE)
            & (Workspace.role_id.in_(user_role_ids))
        )

    query = query.where(or_(*conditions)).order_by(Workspace.name)
    result = await db.execute(query)
    return list(result.scalars().all())


async def can_access_workspace(
    db: AsyncSession,
    user: UserPrincipal,
    workspace: Workspace,
) -> bool:
    """Read-access check for a single workspace."""
    if user.is_platform_admin:
        return True

    if workspace.scope == WorkspaceScope.PERSONAL:
        return workspace.user_id == user.user_id

    if workspace.scope == WorkspaceScope.ORG:
        return (
            user.organization_id is not None
            and workspace.organization_id == user.organization_id
        )

    if workspace.scope == WorkspaceScope.ROLE:
        if workspace.role_id is None:
            return False
        result = await db.execute(
            select(UserRole.role_id).where(
                UserRole.user_id == user.user_id,
                UserRole.role_id == workspace.role_id,
            )
        )
        return result.scalar_one_or_none() is not None

    return False


async def can_manage_workspace(
    user: UserPrincipal,
    workspace: Workspace,
) -> bool:
    """Write-access check (create/update/soft-delete).

    Rules:
    - Platform admins manage anything.
    - Personal workspaces: the owner manages them.
    - Org / role workspaces: any member of the workspace's organization can
      manage. Role membership controls visibility, not management — same as
      forms/agents today.
    """
    if user.is_platform_admin:
        return True

    if workspace.scope == WorkspaceScope.PERSONAL:
        return workspace.user_id == user.user_id

    if workspace.scope in (WorkspaceScope.ORG, WorkspaceScope.ROLE):
        return (
            user.organization_id is not None
            and workspace.organization_id == user.organization_id
        )

    return False


def effective_tool_ids(
    agent_tool_ids: list[str],
    workspace: Workspace | None,
) -> list[str]:
    """Apply the workspace tool-intersection rule (chat-ux-design §2.4).

    `agent.tool_ids ∩ workspace.enabled_tool_ids` when the workspace restricts;
    otherwise the agent's tool list passes through unchanged. Workspaces can
    restrict but never expand an agent's tool set.
    """
    if workspace is None or workspace.enabled_tool_ids is None:
        return list(agent_tool_ids)
    enabled = set(workspace.enabled_tool_ids)
    return [tid for tid in agent_tool_ids if tid in enabled]
