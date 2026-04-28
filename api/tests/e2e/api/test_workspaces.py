"""
Workspaces E2E Tests.

Covers /api/workspaces CRUD, conversation creation in workspaces, the general
pool (workspace_id IS NULL) listing filter, and move-to-workspace via PATCH.
"""
from __future__ import annotations

import logging
import uuid

import pytest

logger = logging.getLogger(__name__)


# Locally-scoped lightweight chat agent for the conversation tests.
@pytest.fixture
def workspace_test_chat_agent(e2e_client, platform_admin):
    response = e2e_client.post(
        "/api/agents",
        json={
            "name": f"WS chat agent {uuid.uuid4().hex[:6]}",
            "description": "Workspace tests",
            "system_prompt": "You are a helpful test assistant.",
            "channels": ["chat"],
            "access_level": "authenticated",
        },
        headers=platform_admin.headers,
    )
    assert response.status_code == 201, response.text
    agent = response.json()
    yield agent
    try:
        e2e_client.delete(
            f"/api/agents/{agent['id']}", headers=platform_admin.headers
        )
    except Exception as e:
        logger.debug(f"fixture cleanup error: {e}")


# =============================================================================
# Private (scope=personal) workspaces — explicit creation, no synthetic
# =============================================================================


class TestPrivateWorkspaces:
    def test_no_synthetic_listed_for_new_user(self, e2e_client, org1_user):
        # A user who hasn't created any workspaces sees an empty list.
        response = e2e_client.get(
            "/api/workspaces", headers=org1_user.headers
        )
        assert response.status_code == 200, response.text
        # Filter to only this user's personal workspaces (other test
        # workspaces from other tests/orgs may have been created earlier).
        my_personal = [
            w
            for w in response.json()
            if w["scope"] == "personal"
            and w["user_id"] == str(org1_user.user_id)
        ]
        assert my_personal == []

    def test_user_can_create_private_workspace(self, e2e_client, org1_user):
        name = f"My private {uuid.uuid4().hex[:6]}"
        response = e2e_client.post(
            "/api/workspaces",
            headers=org1_user.headers,
            json={"name": name, "scope": "personal"},
        )
        assert response.status_code == 201, response.text
        ws = response.json()
        assert ws["scope"] == "personal"
        assert ws["user_id"] == str(org1_user.user_id)
        assert ws["organization_id"] is None
        assert ws["role_id"] is None

    def test_user_can_create_multiple_private_workspaces(
        self, e2e_client, org1_user
    ):
        # Multiple are allowed — a user can have many private destinations.
        a = e2e_client.post(
            "/api/workspaces",
            headers=org1_user.headers,
            json={"name": f"Private A {uuid.uuid4().hex[:6]}", "scope": "personal"},
        ).json()
        b = e2e_client.post(
            "/api/workspaces",
            headers=org1_user.headers,
            json={"name": f"Private B {uuid.uuid4().hex[:6]}", "scope": "personal"},
        ).json()
        assert a["id"] != b["id"]

    def test_private_workspace_visibility_limited_to_owner(
        self, e2e_client, org1_user, org2_user
    ):
        marker = f"Private-{uuid.uuid4().hex[:6]}"
        e2e_client.post(
            "/api/workspaces",
            headers=org1_user.headers,
            json={"name": marker, "scope": "personal"},
        )
        for_org2 = e2e_client.get(
            "/api/workspaces", headers=org2_user.headers
        ).json()
        assert marker not in {w["name"] for w in for_org2}

    def test_user_can_soft_delete_their_private_workspace(
        self, e2e_client, org1_user
    ):
        ws = e2e_client.post(
            "/api/workspaces",
            headers=org1_user.headers,
            json={"name": f"Delete me {uuid.uuid4().hex[:6]}", "scope": "personal"},
        ).json()
        response = e2e_client.delete(
            f"/api/workspaces/{ws['id']}", headers=org1_user.headers
        )
        assert response.status_code == 204


# =============================================================================
# Org workspace creation
# =============================================================================


class TestCreateOrgWorkspace:
    def test_org_user_can_create_org_workspace_in_own_org(
        self, e2e_client, org1_user
    ):
        response = e2e_client.post(
            "/api/workspaces",
            headers=org1_user.headers,
            json={
                "name": f"Marketing {uuid.uuid4().hex[:6]}",
                "scope": "org",
            },
        )
        assert response.status_code == 201, response.text
        ws = response.json()
        # Server pins org_id to the user's org regardless of payload.
        assert ws["organization_id"] == str(org1_user.organization_id)

    def test_org_user_cannot_target_another_org(
        self, e2e_client, org1_user, org2
    ):
        # Even if they pass another org's id, the server overrides to their own org.
        response = e2e_client.post(
            "/api/workspaces",
            headers=org1_user.headers,
            json={
                "name": f"Smuggling {uuid.uuid4().hex[:6]}",
                "scope": "org",
                "organization_id": org2["id"],
            },
        )
        assert response.status_code == 201, response.text
        ws = response.json()
        assert ws["organization_id"] == str(org1_user.organization_id)
        assert ws["organization_id"] != org2["id"]

    def test_admin_can_create_org_workspace(self, e2e_client, platform_admin, org1):
        response = e2e_client.post(
            "/api/workspaces",
            headers=platform_admin.headers,
            json={
                "name": f"Marketing {uuid.uuid4().hex[:6]}",
                "description": "Customer outreach",
                "scope": "org",
                "organization_id": org1["id"],
            },
        )
        assert response.status_code == 201, response.text
        ws = response.json()
        assert ws["scope"] == "org"
        assert ws["organization_id"] == org1["id"]
        assert ws["is_active"] is True


# =============================================================================
# Cross-org isolation: org1_user sees org1's workspace, not org2's
# =============================================================================


class TestWorkspaceVisibility:
    def test_org_workspace_visible_to_org_users_only(
        self, e2e_client, platform_admin, org1, org2, org1_user, org2_user
    ):
        marker = f"VisibilityTest-{uuid.uuid4().hex[:6]}"
        response = e2e_client.post(
            "/api/workspaces",
            headers=platform_admin.headers,
            json={"name": marker, "scope": "org", "organization_id": org1["id"]},
        )
        assert response.status_code == 201, response.text

        org1_visible = e2e_client.get(
            "/api/workspaces", headers=org1_user.headers
        ).json()
        assert marker in {w["name"] for w in org1_visible}

        org2_visible = e2e_client.get(
            "/api/workspaces", headers=org2_user.headers
        ).json()
        assert marker not in {w["name"] for w in org2_visible}


# =============================================================================
# Update + soft-delete
# =============================================================================


class TestWorkspaceLifecycle:
    @pytest.fixture
    def admin_org_workspace(self, e2e_client, platform_admin, org1):
        response = e2e_client.post(
            "/api/workspaces",
            headers=platform_admin.headers,
            json={
                "name": f"Lifecycle ws {uuid.uuid4().hex[:6]}",
                "scope": "org",
                "organization_id": org1["id"],
            },
        )
        assert response.status_code == 201, response.text
        return response.json()

    def test_admin_can_patch_workspace(
        self, e2e_client, platform_admin, admin_org_workspace
    ):
        response = e2e_client.patch(
            f"/api/workspaces/{admin_org_workspace['id']}",
            headers=platform_admin.headers,
            json={
                "description": "Updated description",
                "instructions": "Be concise.",
                "enabled_tool_ids": [],
            },
        )
        assert response.status_code == 200, response.text
        ws = response.json()
        assert ws["description"] == "Updated description"
        assert ws["instructions"] == "Be concise."
        assert ws["enabled_tool_ids"] == []

    def test_org_user_can_patch_their_orgs_workspace(
        self, e2e_client, org1_user, admin_org_workspace
    ):
        response = e2e_client.patch(
            f"/api/workspaces/{admin_org_workspace['id']}",
            headers=org1_user.headers,
            json={"description": "Updated by org user"},
        )
        assert response.status_code == 200, response.text
        assert response.json()["description"] == "Updated by org user"

    def test_org_user_cannot_patch_other_orgs_workspace(
        self, e2e_client, org2_user, admin_org_workspace
    ):
        # admin_org_workspace lives in org1; org2_user must not touch it.
        response = e2e_client.patch(
            f"/api/workspaces/{admin_org_workspace['id']}",
            headers=org2_user.headers,
            json={"description": "should fail"},
        )
        assert response.status_code == 403, response.text

    def test_admin_can_soft_delete_org_workspace(
        self, e2e_client, platform_admin, admin_org_workspace
    ):
        response = e2e_client.delete(
            f"/api/workspaces/{admin_org_workspace['id']}",
            headers=platform_admin.headers,
        )
        assert response.status_code == 204

        # Default list (active_only=True) excludes it
        listed = e2e_client.get(
            "/api/workspaces", headers=platform_admin.headers
        ).json()
        assert admin_org_workspace["id"] not in {w["id"] for w in listed}

        # active_only=false brings it back
        listed_all = e2e_client.get(
            "/api/workspaces?active_only=false", headers=platform_admin.headers
        ).json()
        assert admin_org_workspace["id"] in {w["id"] for w in listed_all}


# =============================================================================
# Conversations + workspace lifecycle
# =============================================================================


class TestConversationWorkspace:
    def test_new_conversation_lands_in_general_pool_by_default(
        self, e2e_client, org1_user, workspace_test_chat_agent
    ):
        response = e2e_client.post(
            "/api/chat/conversations",
            headers=org1_user.headers,
            json={"agent_id": workspace_test_chat_agent["id"], "channel": "chat"},
        )
        assert response.status_code == 201, response.text
        data = response.json()
        # No workspace specified → workspace_id is null (general pool).
        assert data["workspace_id"] is None

    def test_new_conversation_lands_in_specified_workspace(
        self, e2e_client, org1_user, workspace_test_chat_agent
    ):
        ws = e2e_client.post(
            "/api/workspaces",
            headers=org1_user.headers,
            json={"name": f"Carrying {uuid.uuid4().hex[:6]}", "scope": "personal"},
        ).json()

        response = e2e_client.post(
            "/api/chat/conversations",
            headers=org1_user.headers,
            json={
                "agent_id": workspace_test_chat_agent["id"],
                "channel": "chat",
                "workspace_id": ws["id"],
            },
        )
        assert response.status_code == 201, response.text
        assert response.json()["workspace_id"] == ws["id"]

    def test_pool_general_filter_returns_only_unscoped_chats(
        self, e2e_client, org1_user, workspace_test_chat_agent
    ):
        ws = e2e_client.post(
            "/api/workspaces",
            headers=org1_user.headers,
            json={"name": f"Filter test {uuid.uuid4().hex[:6]}", "scope": "personal"},
        ).json()

        # One in general pool, one in workspace.
        general = e2e_client.post(
            "/api/chat/conversations",
            headers=org1_user.headers,
            json={"agent_id": workspace_test_chat_agent["id"], "channel": "chat"},
        ).json()
        in_ws = e2e_client.post(
            "/api/chat/conversations",
            headers=org1_user.headers,
            json={
                "agent_id": workspace_test_chat_agent["id"],
                "channel": "chat",
                "workspace_id": ws["id"],
            },
        ).json()

        general_only = e2e_client.get(
            "/api/chat/conversations?pool=general",
            headers=org1_user.headers,
        ).json()
        ids = {c["id"] for c in general_only}
        assert general["id"] in ids
        assert in_ws["id"] not in ids

        in_ws_only = e2e_client.get(
            f"/api/chat/conversations?workspace_id={ws['id']}",
            headers=org1_user.headers,
        ).json()
        ids = {c["id"] for c in in_ws_only}
        assert in_ws["id"] in ids
        assert general["id"] not in ids


class TestMoveConversation:
    def test_user_can_move_chat_into_workspace_and_back(
        self, e2e_client, org1_user, workspace_test_chat_agent
    ):
        # Create a chat in the general pool
        chat = e2e_client.post(
            "/api/chat/conversations",
            headers=org1_user.headers,
            json={"agent_id": workspace_test_chat_agent["id"], "channel": "chat"},
        ).json()
        assert chat["workspace_id"] is None

        # Create a private workspace
        ws = e2e_client.post(
            "/api/workspaces",
            headers=org1_user.headers,
            json={"name": f"Move target {uuid.uuid4().hex[:6]}", "scope": "personal"},
        ).json()

        # Move the chat into the workspace
        moved = e2e_client.patch(
            f"/api/chat/conversations/{chat['id']}",
            headers=org1_user.headers,
            json={"workspace_id": ws["id"]},
        )
        assert moved.status_code == 200, moved.text
        assert moved.json()["workspace_id"] == ws["id"]

        # Move back to general pool
        back = e2e_client.patch(
            f"/api/chat/conversations/{chat['id']}",
            headers=org1_user.headers,
            json={"workspace_id": None},
        )
        assert back.status_code == 200, back.text
        assert back.json()["workspace_id"] is None

    def test_cannot_move_into_inaccessible_workspace(
        self, e2e_client, platform_admin, org1, org2_user, workspace_test_chat_agent
    ):
        # Admin creates an org1 workspace.
        ws = e2e_client.post(
            "/api/workspaces",
            headers=platform_admin.headers,
            json={
                "name": f"Cross-org target {uuid.uuid4().hex[:6]}",
                "scope": "org",
                "organization_id": org1["id"],
            },
        ).json()

        # org2_user's chat — they shouldn't be able to move it into org1's workspace.
        chat = e2e_client.post(
            "/api/chat/conversations",
            headers=org2_user.headers,
            json={"agent_id": workspace_test_chat_agent["id"], "channel": "chat"},
        ).json()

        response = e2e_client.patch(
            f"/api/chat/conversations/{chat['id']}",
            headers=org2_user.headers,
            json={"workspace_id": ws["id"]},
        )
        assert response.status_code == 403, response.text
