from types import SimpleNamespace

from src.services.manifest_import import (
    _is_setup_placeholder,
    _normalize_manifest_oauth_provider,
)


def test_is_setup_placeholder_detects_manifest_setup_values():
    assert _is_setup_placeholder("__NEEDS_SETUP__") is True
    assert _is_setup_placeholder("<your-client-id>") is True
    assert _is_setup_placeholder("https://<your-instance>.halopsa.com/auth/token") is True
    assert _is_setup_placeholder("https://login.microsoftonline.com/{entity_id}/oauth2/v2.0/token") is False
    assert _is_setup_placeholder("https://authentication.logmeininc.com/oauth/token") is False


def test_normalize_manifest_oauth_provider_preserves_runtime_values_when_manifest_has_placeholders():
    op_data = SimpleNamespace(
        provider_name="HaloPSA",
        display_name="HaloPSA",
        oauth_flow_type="client_credentials",
        client_id="<your-client-id>",
        authorization_url=None,
        token_url="https://<your-instance>.halopsa.com/auth/token",
        token_url_defaults=None,
        scopes=["all"],
        redirect_uri=None,
    )

    insert_values, update_values = _normalize_manifest_oauth_provider(op_data)

    assert insert_values["client_id"] == "__NEEDS_SETUP__"
    assert insert_values["token_url"] is None
    assert "client_id" not in update_values
    assert "token_url" not in update_values
    assert update_values["scopes"] == ["all"]


def test_normalize_manifest_oauth_provider_keeps_real_values():
    op_data = SimpleNamespace(
        provider_name="GoToConnect",
        display_name="GoToConnect",
        oauth_flow_type="authorization_code",
        client_id="real-client-id",
        authorization_url="https://authentication.logmeininc.com/oauth/authorize",
        token_url="https://authentication.logmeininc.com/oauth/token",
        token_url_defaults={},
        scopes=["voice-admin.v1.read"],
        redirect_uri="https://example.com/callback",
    )

    insert_values, update_values = _normalize_manifest_oauth_provider(op_data)

    assert insert_values["client_id"] == "real-client-id"
    assert insert_values["token_url"] == "https://authentication.logmeininc.com/oauth/token"
    assert update_values["client_id"] == "real-client-id"
    assert update_values["token_url"] == "https://authentication.logmeininc.com/oauth/token"
    assert update_values["redirect_uri"] == "https://example.com/callback"
