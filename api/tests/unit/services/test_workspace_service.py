"""
Unit tests for the workspace service helpers.

Covers scope-based visibility and the agent/workspace tool-intersection rule
from chat-ux-design §2.4. Workspaces are explicit (no synthetic auto-create);
conversations may live in a workspace OR in the general pool (workspace_id IS
NULL).
"""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.auth import UserPrincipal
from src.models.enums import WorkspaceScope
from src.models.orm.organizations import Organization
from src.models.orm.users import Role, User, UserRole
from src.models.orm.workspaces import Workspace
from src.services.workspace_service import (
    can_access_workspace,
    can_manage_workspace,
    effective_tool_ids,
    list_visible_workspaces,
)


def _principal(user: User, *, is_superuser: bool = False) -> UserPrincipal:
    return UserPrincipal(
        user_id=user.id,
        email=user.email,
        organization_id=user.organization_id,
        name=user.name or "",
        is_active=True,
        is_superuser=is_superuser,
        is_verified=True,
    )


async def _make_personal_ws(db: AsyncSession, user: User) -> Workspace:
    """Create a private (scope=personal) workspace owned by ``user``.

    Replaces the old synthetic auto-create — workspaces are explicit now.
    """
    ws = Workspace(
        id=uuid4(),
        name="My private workspace",
        scope=WorkspaceScope.PERSONAL,
        user_id=user.id,
        is_active=True,
        created_by=user.email or "test",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(ws)
    await db.flush()
    return ws


@pytest_asyncio.fixture
async def org(db_session: AsyncSession):
    org = Organization(
        id=uuid4(),
        name=f"WS Test Org {uuid4().hex[:6]}",
        is_active=True,
        created_by="test@example.com",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db_session.add(org)
    await db_session.flush()
    yield org


@pytest_asyncio.fixture
async def org_user(db_session: AsyncSession, org):
    user = User(
        id=uuid4(),
        email=f"orguser-{uuid4().hex[:6]}@example.com",
        name="Org User",
        organization_id=org.id,
        is_active=True,
        is_superuser=False,
        is_verified=True,
        is_registered=True,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db_session.add(user)
    await db_session.flush()
    yield user


@pytest_asyncio.fixture
async def superuser(db_session: AsyncSession):
    user = User(
        id=uuid4(),
        email=f"super-{uuid4().hex[:6]}@example.com",
        name="Super User",
        organization_id=None,
        is_active=True,
        is_superuser=True,
        is_verified=True,
        is_registered=True,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db_session.add(user)
    await db_session.flush()
    yield user


# ---------------------------------------------------------------------------
# list_visible_workspaces
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_returns_only_user_personal_for_org_user(
    db_session: AsyncSession, org_user: User
):
    other_user = User(
        id=uuid4(),
        email=f"other-{uuid4().hex[:6]}@example.com",
        name="Other",
        organization_id=org_user.organization_id,
        is_active=True,
        is_superuser=False,
        is_verified=True,
        is_registered=True,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db_session.add(other_user)
    await db_session.flush()

    await _make_personal_ws(db_session, org_user)
    await _make_personal_ws(db_session, other_user)

    visible = await list_visible_workspaces(db_session, _principal(org_user))
    visible_ids = {w.user_id for w in visible if w.scope == WorkspaceScope.PERSONAL}
    assert visible_ids == {org_user.id}


@pytest.mark.asyncio
async def test_list_includes_org_workspaces_in_users_org(
    db_session: AsyncSession, org_user: User, superuser: User, org: Organization
):
    org_ws = Workspace(
        id=uuid4(),
        name="Acme org workspace",
        scope=WorkspaceScope.ORG,
        organization_id=org.id,
        is_active=True,
        created_by=superuser.email,
    )
    other_org = Organization(
        id=uuid4(),
        name=f"Other org {uuid4().hex[:6]}",
        is_active=True,
        created_by="test@example.com",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db_session.add_all([org_ws, other_org])
    await db_session.flush()

    other_org_ws = Workspace(
        id=uuid4(),
        name="Other org workspace",
        scope=WorkspaceScope.ORG,
        organization_id=other_org.id,
        is_active=True,
        created_by=superuser.email,
    )
    db_session.add(other_org_ws)
    await db_session.flush()

    visible = await list_visible_workspaces(db_session, _principal(org_user))
    visible_ids = {w.id for w in visible}
    assert org_ws.id in visible_ids
    assert other_org_ws.id not in visible_ids


@pytest.mark.asyncio
async def test_list_includes_role_workspaces_only_for_role_holders(
    db_session: AsyncSession, org_user: User, superuser: User, org: Organization
):
    role = Role(
        id=uuid4(),
        name=f"Senior Tech {uuid4().hex[:4]}",
        description="senior tech",
        permissions={},
        created_by="test@example.com",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db_session.add(role)
    await db_session.flush()

    role_ws = Workspace(
        id=uuid4(),
        name="Senior tech workspace",
        scope=WorkspaceScope.ROLE,
        organization_id=org.id,
        role_id=role.id,
        is_active=True,
        created_by=superuser.email,
    )
    db_session.add(role_ws)
    await db_session.flush()

    # User does NOT have the role yet — should not see it.
    visible = await list_visible_workspaces(db_session, _principal(org_user))
    assert role_ws.id not in {w.id for w in visible}

    # Grant the role and recheck.
    db_session.add(
        UserRole(
            user_id=org_user.id,
            role_id=role.id,
            assigned_by=superuser.email,
            assigned_at=datetime.now(timezone.utc),
        )
    )
    await db_session.flush()

    visible = await list_visible_workspaces(db_session, _principal(org_user))
    assert role_ws.id in {w.id for w in visible}


@pytest.mark.asyncio
async def test_list_excludes_inactive_when_active_only(
    db_session: AsyncSession, org_user: User
):
    ws = await _make_personal_ws(db_session, org_user)
    ws.is_active = False
    await db_session.flush()

    visible_active = await list_visible_workspaces(
        db_session, _principal(org_user), active_only=True
    )
    visible_all = await list_visible_workspaces(
        db_session, _principal(org_user), active_only=False
    )
    assert ws.id not in {w.id for w in visible_active}
    assert ws.id in {w.id for w in visible_all}


@pytest.mark.asyncio
async def test_superuser_sees_all_workspaces(
    db_session: AsyncSession, org_user: User, superuser: User, org: Organization
):
    org_ws = Workspace(
        id=uuid4(),
        name="Org-only ws",
        scope=WorkspaceScope.ORG,
        organization_id=org.id,
        is_active=True,
        created_by=superuser.email,
    )
    db_session.add(org_ws)
    await db_session.flush()
    await _make_personal_ws(db_session, org_user)

    visible = await list_visible_workspaces(
        db_session, _principal(superuser, is_superuser=True)
    )
    ids = {w.id for w in visible}
    assert org_ws.id in ids
    assert any(w.scope == WorkspaceScope.PERSONAL and w.user_id == org_user.id for w in visible)


# ---------------------------------------------------------------------------
# can_access_workspace / can_manage_workspace
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_can_access_personal_only_for_owner(
    db_session: AsyncSession, org_user: User, superuser: User
):
    ws = await _make_personal_ws(db_session, org_user)
    assert await can_access_workspace(db_session, _principal(org_user), ws) is True

    other = User(
        id=uuid4(),
        email=f"other-{uuid4().hex[:6]}@example.com",
        organization_id=org_user.organization_id,
        is_active=True,
        is_superuser=False,
        is_verified=True,
        is_registered=True,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db_session.add(other)
    await db_session.flush()
    assert await can_access_workspace(db_session, _principal(other), ws) is False

    # Superuser bypasses.
    assert (
        await can_access_workspace(db_session, _principal(superuser, is_superuser=True), ws)
        is True
    )


@pytest.mark.asyncio
async def test_can_manage_org_workspace_for_org_members_and_admins(
    db_session: AsyncSession, org_user: User, superuser: User, org: Organization
):
    """Org users can manage workspaces in their own org; admins manage anything.

    Mirrors how agents/forms work today — org users don't need a separate admin
    role to create or edit role-based agents in their own org.
    """
    org_ws = Workspace(
        id=uuid4(),
        name="Org ws",
        scope=WorkspaceScope.ORG,
        organization_id=org.id,
        is_active=True,
        created_by=superuser.email,
    )
    db_session.add(org_ws)
    await db_session.flush()

    # Member of the workspace's org can manage it.
    assert await can_manage_workspace(_principal(org_user), org_ws) is True
    # Platform admin can manage anything.
    assert (
        await can_manage_workspace(_principal(superuser, is_superuser=True), org_ws)
        is True
    )


@pytest.mark.asyncio
async def test_can_manage_org_workspace_blocks_other_org_users(
    db_session: AsyncSession, superuser: User, org: Organization
):
    """A user from a different org cannot manage another org's workspace."""
    other_org = Organization(
        id=uuid4(),
        name=f"Other org {uuid4().hex[:6]}",
        is_active=True,
        created_by="test@example.com",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db_session.add(other_org)
    await db_session.flush()

    other_user = User(
        id=uuid4(),
        email=f"other-{uuid4().hex[:6]}@example.com",
        organization_id=other_org.id,
        is_active=True,
        is_superuser=False,
        is_verified=True,
        is_registered=True,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db_session.add(other_user)
    await db_session.flush()

    org_ws = Workspace(
        id=uuid4(),
        name="Org ws",
        scope=WorkspaceScope.ORG,
        organization_id=org.id,
        is_active=True,
        created_by=superuser.email,
    )
    db_session.add(org_ws)
    await db_session.flush()

    assert await can_manage_workspace(_principal(other_user), org_ws) is False


# ---------------------------------------------------------------------------
# effective_tool_ids
# ---------------------------------------------------------------------------


def test_effective_tool_ids_passthrough_when_workspace_unrestricted():
    ws = Workspace(
        id=uuid4(),
        name="unrestricted",
        scope=WorkspaceScope.PERSONAL,
        is_active=True,
        created_by="test",
    )
    assert effective_tool_ids(["a", "b"], ws) == ["a", "b"]
    assert effective_tool_ids(["a", "b"], None) == ["a", "b"]


def test_effective_tool_ids_intersects_when_workspace_restricts():
    ws = Workspace(
        id=uuid4(),
        name="restricted",
        scope=WorkspaceScope.ORG,
        is_active=True,
        created_by="test",
        enabled_tool_ids=["b", "c"],
    )
    assert effective_tool_ids(["a", "b", "c", "d"], ws) == ["b", "c"]


def test_effective_tool_ids_cannot_expand():
    """Workspace listing 'z' that the agent doesn't have must NOT add 'z' to the
    effective set — restriction-only rule."""
    ws = Workspace(
        id=uuid4(),
        name="restricted",
        scope=WorkspaceScope.ORG,
        is_active=True,
        created_by="test",
        enabled_tool_ids=["a", "z"],
    )
    assert effective_tool_ids(["a", "b"], ws) == ["a"]


def test_effective_tool_ids_empty_workspace_intersection_is_empty():
    ws = Workspace(
        id=uuid4(),
        name="locked-down",
        scope=WorkspaceScope.ORG,
        is_active=True,
        created_by="test",
        enabled_tool_ids=[],
    )
    assert effective_tool_ids(["a", "b"], ws) == []
