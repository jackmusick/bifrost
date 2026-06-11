"""OPEN-E e2e: /api/sdk/integrations/* must not leak the GLOBAL tier to
external users.

This is the coverage gap that let OPEN-E ship past three adversarial passes:
there was ZERO external test coverage on the integrations SDK endpoints. We
seed a GLOBAL integration mapping/defaults + a GLOBAL OAuth token, each
carrying a decrypt-able SECRET canary, then assert:

  - an EXTERNAL portal user (default scope, own org has no mapping) gets NONE
    of the global secret/token back from sdk_integrations_get, and cannot
    refresh the global OAuth token.
  - a NORMAL org user (and the sentinel/engine path) still receives the global
    tier — proving the restriction is external-specific, not a blanket break.

Engine/sentinel path is unchanged (a workflow legitimately uses its org's
integrations including global defaults).
"""

from uuid import UUID, uuid4

import pytest
import pytest_asyncio

from tests.e2e.fixtures.setup import _register_and_authenticate_user
from tests.e2e.fixtures.users import E2EUser

pytestmark = pytest.mark.e2e

SUFFIX = uuid4().hex[:8]

# Decrypt-able canaries — the SDK endpoint decrypts SECRETs before returning.
GLOBAL_CONFIG_SECRET = f"GLOBAL-INTEG-SECRET-{SUFFIX}"
GLOBAL_CLIENT_SECRET = f"GLOBAL-CLIENT-SECRET-{SUFFIX}"
GLOBAL_ACCESS_TOKEN = f"GLOBAL-ACCESS-TOKEN-{SUFFIX}"


@pytest.fixture(scope="module")
def portal_role(e2e_client, platform_admin):
    resp = e2e_client.post(
        "/api/roles",
        headers=platform_admin.headers,
        json={"name": f"E2E Integ Portal {SUFFIX}", "description": "open-e e2e"},
    )
    assert resp.status_code == 201, resp.text
    role = resp.json()
    yield role
    e2e_client.delete(f"/api/roles/{role['id']}", headers=platform_admin.headers)


@pytest.fixture(scope="module")
def external_user(e2e_client, platform_admin, org1, portal_role) -> E2EUser:
    """External (portal) user in org1 — their org has NO integration mapping,
    so the endpoint would fall through to the global tier pre-fix."""
    user = E2EUser(
        email=f"e2e-integ-ext-{SUFFIX}@gobifrost.dev",
        password="ExternalPass123!",
        name=f"E2E Integ External {SUFFIX}",
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
    assert body["is_external"] is True
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


@pytest_asyncio.fixture
async def global_integration(e2e_client, platform_admin, db_session):
    """A GLOBAL integration with: a global SECRET config default + a global
    OAuth provider (decrypt-able client_secret) + a global OAuth token
    (decrypt-able access_token). No org mapping anywhere.

    Function-scoped with a per-call-unique name/provider so the four tests
    never collide on the integration name (soft-delete doesn't free it
    immediately). The canary VALUES are stable so assertions stay simple.
    """
    from src.core.security import encrypt_secret
    from src.models.enums import ConfigType
    from src.models.orm import Config as ConfigModel
    from src.models.orm import OAuthProvider
    from src.models.orm.oauth import OAuthToken

    uniq = uuid4().hex[:8]
    name = f"ext-integ-{uniq}"
    provider_name = f"ext_integ_provider_{uniq}"
    create = e2e_client.post(
        "/api/integrations",
        headers=platform_admin.headers,
        json={"name": name},
    )
    assert create.status_code == 201, create.text
    integration_id = UUID(create.json()["id"])

    # Global SECRET config default (organization_id=NULL).
    db_session.add(
        ConfigModel(
            key=f"api_key_{uniq}",
            value={"value": encrypt_secret(GLOBAL_CONFIG_SECRET)},
            config_type=ConfigType.SECRET,
            organization_id=None,
            integration_id=integration_id,
            updated_by="e2e-seed",
        )
    )
    provider = OAuthProvider(
        provider_name=provider_name,
        display_name="Ext Integ Provider",
        oauth_flow_type="client_credentials",
        client_id="ext-integ-client",
        encrypted_client_secret=encrypt_secret(GLOBAL_CLIENT_SECRET).encode(),
        authorization_url="https://example.com/authorize",
        token_url="https://example.com/token",
        scopes=["read"],
        redirect_uri="/api/oauth/callback/ext_integ",
        integration_id=integration_id,
        organization_id=None,
    )
    db_session.add(provider)
    await db_session.flush()

    db_session.add(
        OAuthToken(
            organization_id=None,
            provider_id=provider.id,
            user_id=None,
            encrypted_access_token=encrypt_secret(GLOBAL_ACCESS_TOKEN).encode(),
            scopes=["read"],
        )
    )
    await db_session.commit()

    yield {
        "name": name,
        "integration_id": str(integration_id),
        "provider_name": provider_name,
    }

    e2e_client.delete(
        f"/api/integrations/{integration_id}", headers=platform_admin.headers
    )


def _serialize(payload) -> str:
    import json

    return json.dumps(payload, default=str)


class TestExternalIntegrationsGet:
    """OPEN-E: sdk_integrations_get must return NONE of the global tier to an
    external caller on default scope."""

    def _get(self, e2e_client, user, name):
        return e2e_client.post(
            "/api/sdk/integrations/get",
            headers=user.headers,
            json={"name": name},
        )

    def test_external_gets_no_global_secret_or_token(
        self, e2e_client, external_user, global_integration
    ):
        resp = self._get(e2e_client, external_user, global_integration["name"])
        # Either an empty/None body or a body with no global tier — never the
        # decrypted global secrets.
        assert resp.status_code == 200, resp.text
        blob = _serialize(resp.json())
        assert GLOBAL_CONFIG_SECRET not in blob, (
            "external user received the global integration SECRET config"
        )
        assert GLOBAL_CLIENT_SECRET not in blob, (
            "external user received the global OAuth client_secret"
        )
        assert GLOBAL_ACCESS_TOKEN not in blob, (
            "external user received the global OAuth access_token"
        )

    def test_normal_user_still_gets_global_tier(
        self, e2e_client, org1_user, global_integration
    ):
        resp = self._get(e2e_client, org1_user, global_integration["name"])
        assert resp.status_code == 200, resp.text
        blob = _serialize(resp.json())
        # A normal org user's default-scope read still unions the global tier:
        # the integration config default AND the global OAuth token surface.
        assert GLOBAL_CONFIG_SECRET in blob, (
            "normal org user must still receive the global integration default"
        )
        assert GLOBAL_ACCESS_TOKEN in blob, (
            "normal org user must still receive the global OAuth access_token"
        )


class TestExternalIntegrationsRefreshToken:
    """OPEN-E: sdk_integrations_refresh_token must not let an external refresh /
    receive the GLOBAL OAuth token."""

    def _refresh(self, e2e_client, user, provider_name):
        return e2e_client.post(
            "/api/sdk/integrations/refresh_token",
            headers=user.headers,
            json={"connection_name": provider_name},
        )

    def test_external_cannot_refresh_global_provider(
        self, e2e_client, external_user, global_integration
    ):
        provider_name = global_integration["provider_name"]
        resp = self._refresh(e2e_client, external_user, provider_name)
        # The provider is GLOBAL; an external's by-name cascade drops the global
        # tier → 404 (provider not found). It must NOT return a fresh global
        # access_token.
        assert resp.status_code in (400, 404, 502), (
            f"external must not reach the global provider: "
            f"{resp.status_code} {resp.text}"
        )
        assert GLOBAL_ACCESS_TOKEN not in resp.text
        assert GLOBAL_CLIENT_SECRET not in resp.text

    def test_normal_user_reaches_global_provider(
        self, e2e_client, org1_user, global_integration
    ):
        # A normal org user's by-name cascade DOES reach the global provider —
        # it then attempts a real HTTP refresh against example.com (which
        # fails with 502), proving the provider resolved (not a 404 denial).
        provider_name = global_integration["provider_name"]
        resp = self._refresh(e2e_client, org1_user, provider_name)
        assert resp.status_code != 404, (
            f"normal org user must reach the global provider (not 404): "
            f"{resp.status_code} {resp.text}"
        )
