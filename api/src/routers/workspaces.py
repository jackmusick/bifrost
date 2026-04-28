"""
Workspaces Router.

CRUD for chat workspaces. Workspaces have three scopes:
- ``personal`` — private to the owner (Claude-Projects-style).
- ``org`` — shared with the workspace's organization.
- ``role`` — shared with members of a specific role.

Conversations may live in a workspace OR in the general pool
(``Conversation.workspace_id IS NULL``). There is no synthetic "Personal"
workspace; users create private workspaces explicitly when they want one.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from src.core.auth import CurrentActiveUser
from src.core.database import DbSession
from src.models.contracts.workspaces import (
    WorkspaceCreate,
    WorkspacePublic,
    WorkspaceSummary,
    WorkspaceUpdate,
)
from src.models.enums import WorkspaceScope
from src.models.orm import Conversation, Workspace
from src.services.workspace_service import (
    can_access_workspace,
    can_manage_workspace,
    list_visible_workspaces,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/workspaces", tags=["Workspaces"])


def _to_summary(ws: Workspace, conversation_count: int) -> WorkspaceSummary:
    return WorkspaceSummary(
        id=ws.id,
        name=ws.name,
        description=ws.description,
        scope=ws.scope,
        organization_id=ws.organization_id,
        role_id=ws.role_id,
        user_id=ws.user_id,
        is_active=ws.is_active,
        created_at=ws.created_at,
        conversation_count=conversation_count,
    )


@router.get("")
async def list_workspaces(
    db: DbSession,
    user: CurrentActiveUser,
    active_only: bool = True,
) -> list[WorkspaceSummary]:
    """List workspaces visible to the current user."""
    workspaces = await list_visible_workspaces(db, user, active_only=active_only)

    if not workspaces:
        return []

    counts_result = await db.execute(
        select(Conversation.workspace_id, func.count())
        .where(
            Conversation.workspace_id.in_([w.id for w in workspaces]),
            Conversation.is_active.is_(True),
        )
        .group_by(Conversation.workspace_id)
    )
    counts: dict[UUID, int] = {row[0]: row[1] for row in counts_result.all()}

    return [_to_summary(ws, counts.get(ws.id, 0)) for ws in workspaces]


@router.get("/{workspace_id}")
async def get_workspace(
    workspace_id: UUID,
    db: DbSession,
    user: CurrentActiveUser,
) -> WorkspacePublic:
    """Get a workspace by ID."""
    result = await db.execute(
        select(Workspace)
        .options(selectinload(Workspace.default_agent))
        .where(Workspace.id == workspace_id)
    )
    workspace = result.scalar_one_or_none()
    if workspace is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workspace {workspace_id} not found",
        )
    if not await can_access_workspace(db, user, workspace):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this workspace",
        )
    return WorkspacePublic.model_validate(workspace)


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_workspace(
    payload: WorkspaceCreate,
    db: DbSession,
    user: CurrentActiveUser,
) -> WorkspacePublic:
    """Create a workspace at any scope.

    - ``personal`` — owned by the caller, ignores any org/role hints.
    - ``org`` — organization-scoped. Admins can target any org; org users are
      pinned to their own.
    - ``role`` — role-scoped within an org. Same org rules as above.
    """
    now = datetime.now(timezone.utc)

    if payload.scope == WorkspaceScope.PERSONAL:
        workspace = Workspace(
            id=uuid4(),
            name=payload.name,
            description=payload.description,
            scope=WorkspaceScope.PERSONAL,
            organization_id=None,
            role_id=None,
            user_id=user.user_id,
            default_agent_id=payload.default_agent_id,
            enabled_tool_ids=payload.enabled_tool_ids,
            enabled_knowledge_source_ids=payload.enabled_knowledge_source_ids,
            instructions=payload.instructions,
            is_active=True,
            created_by=user.email or str(user.user_id),
            created_at=now,
            updated_at=now,
        )
        db.add(workspace)
        await db.flush()
        return WorkspacePublic.model_validate(workspace)

    # Pin org_id for non-admins; admins can target any org via the payload.
    if user.is_platform_admin:
        target_org_id = payload.organization_id
    else:
        if user.organization_id is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You must belong to an organization to create a shared workspace",
            )
        target_org_id = user.organization_id

    if target_org_id is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="organization_id is required for shared workspaces",
        )

    if payload.scope == WorkspaceScope.ROLE and payload.role_id is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="role_id is required for scope=role",
        )

    workspace = Workspace(
        id=uuid4(),
        name=payload.name,
        description=payload.description,
        scope=payload.scope,
        organization_id=target_org_id,
        role_id=payload.role_id if payload.scope == WorkspaceScope.ROLE else None,
        user_id=None,
        default_agent_id=payload.default_agent_id,
        enabled_tool_ids=payload.enabled_tool_ids,
        enabled_knowledge_source_ids=payload.enabled_knowledge_source_ids,
        instructions=payload.instructions,
        is_active=True,
        created_by=user.email or str(user.user_id),
        created_at=now,
        updated_at=now,
    )
    db.add(workspace)
    await db.flush()
    return WorkspacePublic.model_validate(workspace)


@router.patch("/{workspace_id}")
async def update_workspace(
    workspace_id: UUID,
    payload: WorkspaceUpdate,
    db: DbSession,
    user: CurrentActiveUser,
) -> WorkspacePublic:
    """Update mutable fields of a workspace.

    Scope and ownership (organization_id, role_id, user_id) are immutable.
    """
    result = await db.execute(select(Workspace).where(Workspace.id == workspace_id))
    workspace = result.scalar_one_or_none()
    if workspace is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workspace {workspace_id} not found",
        )
    if not await can_manage_workspace(user, workspace):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to edit this workspace",
        )

    update_fields = payload.model_dump(exclude_unset=True)
    for field_name, value in update_fields.items():
        setattr(workspace, field_name, value)
    workspace.updated_at = datetime.now(timezone.utc)
    await db.flush()
    return WorkspacePublic.model_validate(workspace)


@router.delete("/{workspace_id}", status_code=status.HTTP_204_NO_CONTENT)
async def soft_delete_workspace(
    workspace_id: UUID,
    db: DbSession,
    user: CurrentActiveUser,
) -> None:
    """Soft-delete (deactivate) a workspace.

    Conversations inside the workspace stay around — they revert to the general
    pool because of the ``ondelete=SET NULL`` FK. (Soft-delete sets is_active
    rather than deleting; the FK only kicks in on hard delete. We mirror the
    same effect here by leaving conversations alone — they keep their
    workspace_id pointing at the inactive workspace; the UI filters by is_active.)
    """
    result = await db.execute(select(Workspace).where(Workspace.id == workspace_id))
    workspace = result.scalar_one_or_none()
    if workspace is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workspace {workspace_id} not found",
        )
    if not await can_manage_workspace(user, workspace):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to delete this workspace",
        )
    workspace.is_active = False
    workspace.updated_at = datetime.now(timezone.utc)
    await db.flush()
