"""
External-user isolation: gate tests + mechanical plumbing enforcement (EXT-1).

Three things live here:

1. ``resolve_external_claim`` — the token-mint helper that neutralizes the
   raw ``User.is_external`` flag for bypass principals
   (``is_platform_admin OR is_provider_org`` — the canonical C2 rule).
2. The authenticated-tier gates that live OUTSIDE ``OrgScopedRepository``:
   the agents-router tool-attach validation and the MCP agent access check.
3. A mechanical lint: every org-scoped repository construction that passes a
   principal-derived ``is_superuser`` must also pass ``is_external``.
   Forgetting the flag at a new call site silently re-grants the global
   tier to external users — this test makes that a red build instead.
"""

import ast
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from shared.external_access import resolve_external_claim

API_SRC = Path(__file__).resolve().parents[2] / "src"


# =============================================================================
# 1. resolve_external_claim (token mint)
# =============================================================================


def _user(is_external=True, is_superuser=False, organization_id=...):
    u = MagicMock(spec=["is_external", "is_superuser", "organization_id"])
    u.is_external = is_external
    u.is_superuser = is_superuser
    u.organization_id = uuid4() if organization_id is ... else organization_id
    return u


class TestResolveExternalClaim:
    async def test_non_external_user_is_false(self):
        db = AsyncMock()
        assert await resolve_external_claim(db, _user(is_external=False)) is False
        db.scalar.assert_not_awaited()

    async def test_platform_admin_is_neutralized(self):
        db = AsyncMock()
        assert (
            await resolve_external_claim(db, _user(is_superuser=True)) is False
        )
        db.scalar.assert_not_awaited()

    async def test_provider_org_member_is_neutralized(self):
        db = AsyncMock()
        db.scalar.return_value = True  # org.is_provider
        assert await resolve_external_claim(db, _user()) is False

    async def test_regular_org_external_is_true(self):
        db = AsyncMock()
        db.scalar.return_value = False
        assert await resolve_external_claim(db, _user()) is True

    async def test_orgless_external_is_false(self):
        db = AsyncMock()
        assert (
            await resolve_external_claim(db, _user(organization_id=None)) is False
        )
        db.scalar.assert_not_awaited()


# =============================================================================
# 2a. Agents router: _validate_user_tool_access
# =============================================================================


def _rows_result(values):
    result = MagicMock()
    result.scalars.return_value.all.return_value = values
    return result


def _scalar_result(value):
    result = MagicMock()
    result.scalar_one_or_none = MagicMock(return_value=value)
    return result


def _workflow(access_level: str):
    wf = MagicMock()
    wf.is_active = True
    wf.access_level = access_level
    wf.name = "wf"
    return wf


class TestValidateUserToolAccessExternal:
    async def test_authenticated_workflow_denied_for_external_without_role(self):
        from src.routers.agents import _validate_user_tool_access

        tool_id = str(uuid4())
        db = AsyncMock()
        db.execute.side_effect = [
            _rows_result([]),  # user's roles: none
            _scalar_result(_workflow("authenticated")),  # the workflow
            _rows_result([]),  # workflow's roles: none
        ]
        with pytest.raises(HTTPException) as exc:
            await _validate_user_tool_access(
                db, uuid4(), [tool_id], is_external=True
            )
        assert exc.value.status_code == 403

    async def test_authenticated_workflow_allowed_for_regular_user(self):
        from src.routers.agents import _validate_user_tool_access

        tool_id = str(uuid4())
        db = AsyncMock()
        db.execute.side_effect = [
            _rows_result([]),  # user's roles: none
            _scalar_result(_workflow("authenticated")),
        ]
        await _validate_user_tool_access(db, uuid4(), [tool_id])

    async def test_role_based_workflow_allowed_for_external_with_role(self):
        from src.routers.agents import _validate_user_tool_access

        role_id = uuid4()
        tool_id = str(uuid4())
        db = AsyncMock()
        db.execute.side_effect = [
            _rows_result([role_id]),  # user's roles
            _scalar_result(_workflow("role_based")),
            _rows_result([role_id]),  # workflow's roles
        ]
        await _validate_user_tool_access(db, uuid4(), [tool_id], is_external=True)


# =============================================================================
# 2b. MCP: _check_agent_access
# =============================================================================


class TestMCPAgentAccessExternal:
    def _agent(self, access_level, role_names=()):
        from src.models.enums import AgentAccessLevel

        agent = MagicMock()
        agent.access_level = AgentAccessLevel(access_level)
        agent.roles = [MagicMock(name=n) for n in role_names]
        for role, n in zip(agent.roles, role_names):
            role.name = n
        return agent

    def _check(self, agent, user_roles, is_superuser=False, is_external=False):
        from src.services.mcp_server.tool_access import MCPToolAccessService

        return MCPToolAccessService._check_agent_access(
            agent, user_roles, is_superuser, is_external
        )

    def test_authenticated_agent_denied_for_external(self):
        agent = self._agent("authenticated")
        assert self._check(agent, [], is_external=True) is False

    def test_authenticated_agent_allowed_for_regular_user(self):
        agent = self._agent("authenticated")
        assert self._check(agent, []) is True

    def test_authenticated_agent_allowed_for_external_superuser(self):
        agent = self._agent("authenticated")
        assert self._check(agent, [], is_superuser=True, is_external=True) is True

    def test_role_based_agent_allowed_for_external_with_role(self):
        agent = self._agent("role_based", role_names=("Portal User",))
        assert self._check(agent, ["Portal User"], is_external=True) is True


# =============================================================================
# 3. Mechanical plumbing lint
# =============================================================================


def _org_scoped_repo_class_names() -> set[str]:
    """Collect OrgScopedRepository subclass names from src/repositories/."""
    names: set[str] = set()
    for path in (API_SRC / "repositories").glob("*.py"):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                for base in node.bases:
                    base_src = ast.unparse(base)
                    if base_src.startswith("OrgScopedRepository"):
                        names.add(node.name)
    return names


def test_principal_derived_repo_constructions_pass_is_external():
    """Every org-scoped repo construction with a principal-derived
    ``is_superuser`` must also pass ``is_external``.

    A literal ``is_superuser=True``/``False`` means a fixed identity (engine
    sentinel / forced-regular path) and is exempt. Anything else is a real
    principal whose external-ness must travel with it — otherwise an external
    user regains the global tier at that call site.
    """
    repo_names = _org_scoped_repo_class_names()
    assert repo_names, "failed to discover OrgScopedRepository subclasses"

    violations: list[str] = []
    for path in API_SRC.rglob("*.py"):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            fn = node.func
            name = (
                fn.id
                if isinstance(fn, ast.Name)
                else fn.attr if isinstance(fn, ast.Attribute) else None
            )
            if name not in repo_names:
                continue
            kwargs = {kw.arg: kw.value for kw in node.keywords if kw.arg}
            su = kwargs.get("is_superuser")
            if su is None or isinstance(su, ast.Constant):
                continue  # no identity / fixed identity (sentinel) — exempt
            if "is_external" not in kwargs:
                violations.append(
                    f"{path.relative_to(API_SRC)}:{node.lineno} — {name}("
                    f"is_superuser={ast.unparse(su)}, ...) missing is_external"
                )

    assert not violations, (
        "Org-scoped repository constructed with a principal-derived "
        "is_superuser but no is_external. Pass the principal's "
        "is_external (e.g. is_external=ctx.user.is_external) so external "
        "users don't silently regain the global tier:\n  "
        + "\n  ".join(violations)
    )
