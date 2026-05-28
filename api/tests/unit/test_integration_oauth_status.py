"""Unit tests for integration-level OAuth status reconciliation."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from src.services.oauth_provider import resolve_integration_oauth_status


def _provider(*, status: str, status_message: str | None = None):
    return SimpleNamespace(status=status, status_message=status_message)


def _token(
    *,
    status: str = "completed",
    status_message: str | None = None,
    has_access_token: bool = True,
):
    return SimpleNamespace(
        status=status,
        status_message=status_message,
        encrypted_access_token=b"encrypted" if has_access_token else None,
    )


class TestResolveIntegrationOAuthStatus:
    def test_completed_token_overrides_stale_provider_failure(self):
        provider = _provider(status="failed", status_message="Token refresh failed: bad entity_id")
        token = _token(status="completed")

        status, message = resolve_integration_oauth_status(provider, token)

        assert status == "completed"
        assert message is None

    def test_failed_token_keeps_failure_message(self):
        provider = _provider(status="completed")
        token = _token(status="failed", status_message="Refresh token revoked")

        status, message = resolve_integration_oauth_status(provider, token)

        assert status == "failed"
        assert message == "Refresh token revoked"

    def test_in_progress_provider_status_without_token(self):
        provider = _provider(status="waiting_callback", status_message="Awaiting user authorization")

        status, message = resolve_integration_oauth_status(provider, None)

        assert status == "waiting_callback"
        assert message == "Awaiting user authorization"

    def test_provider_failure_without_token(self):
        provider = _provider(status="failed", status_message="No refresh token available")

        status, message = resolve_integration_oauth_status(provider, None)

        assert status == "failed"
        assert message == "No refresh token available"

    def test_legacy_token_without_status_is_connected(self):
        provider = _provider(status="failed", status_message="Old scheduler failure")
        token = _token(status="not_connected")

        status, message = resolve_integration_oauth_status(provider, token)

        assert status == "completed"
        assert message is None

    def test_no_token_defaults_to_not_connected(self):
        provider = _provider(status="not_connected")

        status, message = resolve_integration_oauth_status(provider, None)

        assert status == "not_connected"
        assert message is None


@pytest.mark.asyncio
async def test_persist_integration_oauth_recovery_clears_stale_provider_failure():
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, MagicMock, patch

    from src.services.oauth_provider import persist_integration_oauth_recovery

    provider = SimpleNamespace(
        status="failed",
        status_message="Token refresh failed: bad entity_id",
        last_token_refresh=None,
        scopes=["scope"],
    )
    token = SimpleNamespace(
        encrypted_access_token=b"old-token",
        encrypted_refresh_token=None,
        expires_at=None,
        scopes=[],
        status="failed",
        status_message="Token refresh failed: bad entity_id",
        last_refresh_at=None,
    )
    db = MagicMock()
    db.add = MagicMock()
    db.flush = AsyncMock()

    with patch(
        "src.services.oauth_scope_resolution.get_oauth_token_for_scope",
        new_callable=AsyncMock,
        return_value=token,
    ):
        result = await persist_integration_oauth_recovery(
            db,
            provider=provider,
            org_uuid=None,
            stored_token=token,
            encrypted_access_token=b"new-token",
            expires_at=datetime.now(timezone.utc),
        )

    assert result is token
    assert provider.status == "completed"
    assert provider.status_message is None
    assert token.status == "completed"
    assert token.status_message is None
    assert token.encrypted_access_token == b"new-token"
    db.flush.assert_awaited_once()
