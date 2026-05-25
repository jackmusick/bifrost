"""Security contract tests for CLI-facing SDK models."""

import pytest
from pydantic import ValidationError

from src.models.contracts.cli import SDKIntegrationsRefreshTokenResponse


def test_refresh_token_response_contract_excludes_token_material():
    """The refresh endpoint response must contain status metadata only."""
    response = SDKIntegrationsRefreshTokenResponse(
        refreshed=True,
        expires_at="2026-03-02T00:00:00+00:00",
    )

    payload = response.model_dump()

    assert payload == {
        "refreshed": True,
        "expires_at": "2026-03-02T00:00:00+00:00",
    }
    assert "access_token" not in payload
    assert "refresh_token" not in payload
    assert "client_secret" not in payload


@pytest.mark.parametrize("field_name", ["access_token", "refresh_token", "client_secret"])
def test_refresh_token_response_rejects_accidental_secret_fields(field_name):
    """Accidental secret fields should fail validation instead of being ignored."""
    with pytest.raises(ValidationError):
        SDKIntegrationsRefreshTokenResponse(
            refreshed=True,
            expires_at=None,
            **{field_name: "secret-value"},
        )
