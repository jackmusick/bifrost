"""E2E: external-user isolation (EXT-1).

An EXTERNAL, non-bypass user sees only role-granted entities in their own
org:

- No global (NULL-org) tier: listings contain ZERO global entities, by-id
  access to global entities is denied — while a normal user in the same org
  still sees the global tier.
- No authenticated-tier entitlement: ``access_level="authenticated"``
  entities (even in their own org) do not grant; ``role_based`` + an
  explicitly assigned role does, and the form is executable.
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from tests.e2e.conftest import write_and_register
from tests.e2e.fixtures.setup import _register_and_authenticate_user
from tests.e2e.fixtures.users import E2EUser

pytestmark = pytest.mark.e2e

SUFFIX = uuid4().hex[:8]


@pytest.fixture(scope="module")
def ext_workflow(e2e_client, platform_admin):
    """A real (global) workflow so the role-granted form is executable."""
    content = '''"""E2E External Users Workflow"""
from bifrost import workflow

@workflow(
    name="e2e_external_users_workflow",
    description="Workflow used by external-user isolation E2E tests",
)
async def e2e_external_users_workflow(foo: str = "bar") -> dict:
    return {"ok": True, "foo": foo}
'''
    result = write_and_register(
        e2e_client,
        platform_admin.headers,
        "e2e_external_users_workflow.py",
        content,
        "e2e_external_users_workflow",
    )
    yield result
    e2e_client.delete(
        "/api/files/editor?path=e2e_external_users_workflow.py",
        headers=platform_admin.headers,
    )


@pytest.fixture(scope="module")
def portal_role(e2e_client, platform_admin):
    """Bespoke role held by the external user."""
    resp = e2e_client.post(
        "/api/roles",
        headers=platform_admin.headers,
        json={
            "name": f"E2E External Portal {SUFFIX}",
            "description": "external-user isolation e2e",
        },
    )
    assert resp.status_code == 201, resp.text
    role = resp.json()
    yield role
    e2e_client.delete(f"/api/roles/{role['id']}", headers=platform_admin.headers)


def _create_form(e2e_client, headers, *, name, workflow_id, org_id, access_level, role_ids=None):
    body = {
        "name": name,
        "description": "external-user isolation e2e",
        "workflow_id": workflow_id,
        "form_schema": {
            "fields": [
                {"name": "foo", "type": "text", "label": "Foo", "required": False},
            ]
        },
        "access_level": access_level,
        "organization_id": org_id,
    }
    if role_ids:
        body["role_ids"] = role_ids
    resp = e2e_client.post("/api/forms", headers=headers, json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()


@pytest.fixture(scope="module")
def global_auth_form(e2e_client, platform_admin, ext_workflow):
    """GLOBAL form at access_level=authenticated — the canary entity."""
    form = _create_form(
        e2e_client,
        platform_admin.headers,
        name=f"E2E Ext Global Auth Form {SUFFIX}",
        workflow_id=ext_workflow["id"],
        org_id=None,
        access_level="authenticated",
    )
    yield form
    e2e_client.delete(f"/api/forms/{form['id']}", headers=platform_admin.headers)


@pytest.fixture(scope="module")
def org_auth_form(e2e_client, platform_admin, ext_workflow, org1):
    """Org-scoped authenticated form — externals get no authenticated tier."""
    form = _create_form(
        e2e_client,
        platform_admin.headers,
        name=f"E2E Ext Org Auth Form {SUFFIX}",
        workflow_id=ext_workflow["id"],
        org_id=org1["id"],
        access_level="authenticated",
    )
    yield form
    e2e_client.delete(f"/api/forms/{form['id']}", headers=platform_admin.headers)


@pytest.fixture(scope="module")
def org_role_form(e2e_client, platform_admin, ext_workflow, org1, portal_role):
    """Org-scoped role_based form granted to the external user's role."""
    form = _create_form(
        e2e_client,
        platform_admin.headers,
        name=f"E2E Ext Org Role Form {SUFFIX}",
        workflow_id=ext_workflow["id"],
        org_id=org1["id"],
        access_level="role_based",
        role_ids=[portal_role["id"]],
    )
    yield form
    e2e_client.delete(f"/api/forms/{form['id']}", headers=platform_admin.headers)


@pytest.fixture(scope="module")
def global_auth_agent(e2e_client, platform_admin):
    """GLOBAL agent at access_level=authenticated — agents-listing canary."""
    resp = e2e_client.post(
        "/api/agents",
        headers=platform_admin.headers,
        json={
            "name": f"E2E Ext Global Agent {SUFFIX}",
            "system_prompt": "You are an e2e canary.",
            "access_level": "authenticated",
            "organization_id": None,
        },
    )
    assert resp.status_code == 201, resp.text
    agent = resp.json()
    yield agent
    e2e_client.delete(f"/api/agents/{agent['id']}", headers=platform_admin.headers)


@pytest.fixture(scope="module")
def external_user(e2e_client, platform_admin, org1, portal_role) -> E2EUser:
    """External (portal/guest) user in org1, holding only the bespoke role."""
    user = E2EUser(
        email=f"e2e-external-{SUFFIX}@gobifrost.dev",
        password="ExternalPass123!",
        name=f"E2E External {SUFFIX}",
        organization_id=UUID(org1["id"]),
    )
    resp = e2e_client.post(
        "/api/users",
        headers=platform_admin.headers,
        json={
            "email": user.email,
            "name": user.name,
            "organization_id": org1["id"],
            "is_superuser": False,
            "is_external": True,
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["is_external"] is True, "is_external must round-trip on create"
    user.user_id = UUID(body["id"])

    assign = e2e_client.post(
        f"/api/roles/{portal_role['id']}/users",
        headers=platform_admin.headers,
        json={"user_ids": [str(user.user_id)]},
    )
    assert assign.status_code == 204, assign.text

    user = _register_and_authenticate_user(e2e_client, user, skip_registration=False)
    user.organization_id = UUID(org1["id"])
    return user


def _form_ids(e2e_client, user) -> set[str]:
    resp = e2e_client.get("/api/forms", headers=user.headers)
    assert resp.status_code == 200, resp.text
    return {f["id"] for f in resp.json()}


def _global_entities(items: list[dict]) -> list[dict]:
    return [i for i in items if i.get("organization_id") is None]


class TestExternalUserGlobalTier:
    def test_external_listings_contain_zero_global_entities(
        self,
        e2e_client,
        external_user,
        global_auth_form,
        global_auth_agent,
    ):
        # Forms: not just the canary — ZERO global entries of any kind.
        resp = e2e_client.get("/api/forms", headers=external_user.headers)
        assert resp.status_code == 200, resp.text
        forms = resp.json()
        assert _global_entities(forms) == [], (
            "external user's form listing must contain zero global forms"
        )
        assert global_auth_form["id"] not in {f["id"] for f in forms}

        # Agents.
        resp = e2e_client.get("/api/agents", headers=external_user.headers)
        assert resp.status_code == 200, resp.text
        agents = resp.json()
        agent_items = agents if isinstance(agents, list) else agents.get("agents", [])
        assert _global_entities(agent_items) == [], (
            "external user's agent listing must contain zero global agents"
        )
        assert global_auth_agent["id"] not in {a["id"] for a in agent_items}

    def test_normal_org_user_still_sees_global_tier(
        self,
        e2e_client,
        org1_user,
        global_auth_form,
        global_auth_agent,
    ):
        assert global_auth_form["id"] in _form_ids(e2e_client, org1_user), (
            "normal org user must still see the global authenticated form"
        )
        resp = e2e_client.get("/api/agents", headers=org1_user.headers)
        assert resp.status_code == 200, resp.text
        agents = resp.json()
        agent_items = agents if isinstance(agents, list) else agents.get("agents", [])
        assert global_auth_agent["id"] in {a["id"] for a in agent_items}

    def test_external_user_denied_global_form_by_id(
        self, e2e_client, external_user, global_auth_form
    ):
        resp = e2e_client.get(
            f"/api/forms/{global_auth_form['id']}", headers=external_user.headers
        )
        assert resp.status_code in (403, 404), (
            f"global form must not be reachable by id for externals: {resp.status_code}"
        )

    def test_external_user_cannot_execute_global_authenticated_form(
        self, e2e_client, external_user, global_auth_form
    ):
        resp = e2e_client.post(
            f"/api/forms/{global_auth_form['id']}/execute",
            headers=external_user.headers,
            json={"form_data": {"foo": "x"}},
        )
        assert resp.status_code in (403, 404), (
            f"global authenticated form must not execute for externals: {resp.status_code}"
        )


class TestExternalUserAuthenticatedTier:
    def test_org_authenticated_form_not_visible_to_external(
        self, e2e_client, external_user, org_auth_form
    ):
        assert org_auth_form["id"] not in _form_ids(e2e_client, external_user), (
            "authenticated-tier org form must not grant to an external user"
        )
        resp = e2e_client.get(
            f"/api/forms/{org_auth_form['id']}", headers=external_user.headers
        )
        assert resp.status_code in (403, 404)

    def test_org_authenticated_form_visible_to_normal_user(
        self, e2e_client, org1_user, org_auth_form
    ):
        assert org_auth_form["id"] in _form_ids(e2e_client, org1_user)


class TestExternalUserRoleGrant:
    def test_role_granted_form_is_listed(
        self, e2e_client, external_user, org_role_form
    ):
        assert org_role_form["id"] in _form_ids(e2e_client, external_user), (
            "role_based form granted to the external user's role must be listed"
        )

    def test_role_granted_form_is_executable(
        self, e2e_client, external_user, org_role_form
    ):
        resp = e2e_client.post(
            f"/api/forms/{org_role_form['id']}/execute",
            headers=external_user.headers,
            json={"form_data": {"foo": "external"}},
        )
        assert resp.status_code == 200, (
            f"role-granted form must execute for the external user: "
            f"{resp.status_code} {resp.text}"
        )


class TestExternalFlagLifecycle:
    def test_flag_updatable_via_user_update(
        self, e2e_client, platform_admin, org1
    ):
        suffix = uuid4().hex[:8]
        resp = e2e_client.post(
            "/api/users",
            headers=platform_admin.headers,
            json={
                "email": f"e2e-ext-toggle-{suffix}@gobifrost.dev",
                "name": "Toggle Test",
                "organization_id": org1["id"],
                "is_superuser": False,
            },
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["is_external"] is False
        user_id = body["id"]

        try:
            resp = e2e_client.patch(
                f"/api/users/{user_id}",
                headers=platform_admin.headers,
                json={"is_external": True},
            )
            assert resp.status_code == 200, resp.text
            assert resp.json()["is_external"] is True

            resp = e2e_client.patch(
                f"/api/users/{user_id}",
                headers=platform_admin.headers,
                json={"is_external": False},
            )
            assert resp.status_code == 200, resp.text
            assert resp.json()["is_external"] is False
        finally:
            e2e_client.delete(
                f"/api/users/{user_id}", headers=platform_admin.headers
            )
