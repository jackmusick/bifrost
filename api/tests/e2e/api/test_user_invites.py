"""E2E tests for user invite endpoints (#227).

Verifies the invite-management endpoints on the users router and the
unauthenticated register-from-invite flow on the auth router.
"""

import pytest


@pytest.mark.e2e
class TestUserInviteFlags:
    """invite_status field on UserPublic."""

    def test_create_user_default_invite_status_never_invited(
        self, e2e_client, platform_admin, org1
    ):
        """A user created without invite=True has invite_status='never_invited'."""
        resp = e2e_client.post(
            "/api/users",
            headers=platform_admin.headers,
            json={
                "email": "inv-noinv@gobifrost.dev",
                "name": "No Invite",
                "organization_id": org1["id"],
                "is_superuser": False,
            },
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["invite_status"] == "never_invited"
        # Cleanup
        e2e_client.patch(
            f"/api/users/{body['id']}",
            headers=platform_admin.headers,
            json={"is_active": False},
        )
        e2e_client.delete(
            f"/api/users/{body['id']}", headers=platform_admin.headers
        )

    def test_listing_includes_invite_status(self, e2e_client, platform_admin):
        """List response includes invite_status on every user."""
        resp = e2e_client.get(
            "/api/users", headers=platform_admin.headers
        )
        assert resp.status_code == 200
        for u in resp.json():
            assert "invite_status" in u
            assert u["invite_status"] in {"active", "pending", "expired", "never_invited"}


@pytest.mark.e2e
class TestInviteEndpoints:
    """Endpoints under /api/users/{id}/invite."""

    def test_regenerate_returns_registration_url(
        self, e2e_client, platform_admin, org1
    ):
        """POST /invite/regenerate returns a token-bearing URL and does not send email."""
        create_resp = e2e_client.post(
            "/api/users",
            headers=platform_admin.headers,
            json={
                "email": "inv-regen@gobifrost.dev",
                "name": "Regen",
                "organization_id": org1["id"],
                "is_superuser": False,
            },
        )
        assert create_resp.status_code == 201
        user_id = create_resp.json()["id"]

        regen_resp = e2e_client.post(
            f"/api/users/{user_id}/invite/regenerate",
            headers=platform_admin.headers,
        )
        assert regen_resp.status_code == 200
        body = regen_resp.json()
        assert "accept-invite?token=" in body["registration_url"]
        assert body["email_sent"] is False

        # User should now show invite_status=pending
        list_resp = e2e_client.get(
            "/api/users",
            headers=platform_admin.headers,
        )
        target = next(u for u in list_resp.json() if u["id"] == user_id)
        assert target["invite_status"] == "pending"

        # Cleanup
        e2e_client.patch(
            f"/api/users/{user_id}",
            headers=platform_admin.headers,
            json={"is_active": False},
        )
        e2e_client.delete(
            f"/api/users/{user_id}", headers=platform_admin.headers
        )

    def test_revoke_invite_returns_to_never_invited(
        self, e2e_client, platform_admin, org1
    ):
        """DELETE /invite revokes the invite; status returns to never_invited."""
        create_resp = e2e_client.post(
            "/api/users",
            headers=platform_admin.headers,
            json={
                "email": "inv-rev@gobifrost.dev",
                "name": "Revoke",
                "organization_id": org1["id"],
                "is_superuser": False,
            },
        )
        user_id = create_resp.json()["id"]

        e2e_client.post(
            f"/api/users/{user_id}/invite/regenerate",
            headers=platform_admin.headers,
        )
        revoke_resp = e2e_client.delete(
            f"/api/users/{user_id}/invite",
            headers=platform_admin.headers,
        )
        assert revoke_resp.status_code == 204

        list_resp = e2e_client.get(
            "/api/users", headers=platform_admin.headers
        )
        target = next(u for u in list_resp.json() if u["id"] == user_id)
        assert target["invite_status"] == "never_invited"

        # Cleanup
        e2e_client.patch(
            f"/api/users/{user_id}",
            headers=platform_admin.headers,
            json={"is_active": False},
        )
        e2e_client.delete(
            f"/api/users/{user_id}", headers=platform_admin.headers
        )

    def test_regenerate_for_registered_user_409(
        self, e2e_client, platform_admin
    ):
        """Cannot generate invite for already-registered user."""
        # platform_admin is already registered.
        resp = e2e_client.post(
            f"/api/users/{platform_admin.user_id}/invite/regenerate",
            headers=platform_admin.headers,
        )
        assert resp.status_code == 409


@pytest.mark.e2e
class TestRegisterFromInvite:
    """POST /auth/register-from-invite consumes a single-use token."""

    def test_register_consumes_token_and_marks_user_registered(
        self, e2e_client, platform_admin, org1
    ):
        """Happy path: regenerate invite, then redeem the token."""
        create_resp = e2e_client.post(
            "/api/users",
            headers=platform_admin.headers,
            json={
                "email": "inv-reg@gobifrost.dev",
                "name": "RegFromInvite",
                "organization_id": org1["id"],
                "is_superuser": False,
            },
        )
        user_id = create_resp.json()["id"]

        regen = e2e_client.post(
            f"/api/users/{user_id}/invite/regenerate",
            headers=platform_admin.headers,
        )
        url: str = regen.json()["registration_url"]
        token = url.split("token=", 1)[1]

        register_resp = e2e_client.post(
            "/auth/register-from-invite",
            json={"token": token, "password": "supersecret-1234"},
        )
        assert register_resp.status_code == 200
        assert register_resp.json()["email"] == "inv-reg@gobifrost.dev"
        assert register_resp.json()["is_registered"] is True

        # Replay must fail
        replay = e2e_client.post(
            "/auth/register-from-invite",
            json={"token": token, "password": "x"},
        )
        assert replay.status_code == 400

        # Cleanup
        e2e_client.patch(
            f"/api/users/{user_id}",
            headers=platform_admin.headers,
            json={"is_active": False},
        )
        e2e_client.delete(
            f"/api/users/{user_id}", headers=platform_admin.headers
        )

    def test_register_unknown_token_400(self, e2e_client):
        """Unknown token returns 400, not 200/500."""
        resp = e2e_client.post(
            "/auth/register-from-invite",
            json={"token": "garbage-token", "password": "x"},
        )
        assert resp.status_code == 400


@pytest.mark.e2e
class TestInvitePermissions:
    """Invite-management endpoints require platform admin auth."""

    def test_regenerate_requires_superuser(
        self, e2e_client, org1_user, platform_admin
    ):
        # need a non-self user_id to attempt regen on
        target_id = platform_admin.user_id
        resp = e2e_client.post(
            f"/api/users/{target_id}/invite/regenerate",
            headers=org1_user.headers,
        )
        # CurrentSuperuser dependency should reject non-superuser
        assert resp.status_code in (401, 403)

    def test_revoke_requires_superuser(self, e2e_client, org1_user, platform_admin):
        target_id = platform_admin.user_id
        resp = e2e_client.delete(
            f"/api/users/{target_id}/invite",
            headers=org1_user.headers,
        )
        assert resp.status_code in (401, 403)
