"""Tests for `bifrost login --ephemeral` flag handling."""

import pytest

from bifrost import cli


def _stub_post(json_payload: dict, status_code: int = 200):
    """Build an httpx.AsyncClient stand-in whose .post() returns the given payload."""
    class StubResponse:
        def __init__(self, code, payload):
            self.status_code = code
            self._payload = payload

        def json(self):
            return self._payload

        def raise_for_status(self):
            if self.status_code >= 400:
                raise Exception(f"HTTP {self.status_code}")

    class StubClient:
        def __init__(self, *_a, **_kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_a):
            return False

        async def post(self, _url, json=None):
            return StubResponse(status_code, json_payload)

    return StubClient


class TestEphemeralLoginFlagParsing:
    def test_ephemeral_without_email_password_errors(self, capsys):
        rc = cli.handle_login(["--ephemeral", "--url", "http://localhost:38421"])
        assert rc != 0
        err = capsys.readouterr().err
        assert "--email" in err and "--password" in err

    def test_email_password_without_ephemeral_errors(self, capsys):
        rc = cli.handle_login(["--email", "x@y", "--password", "p"])
        assert rc != 0
        err = capsys.readouterr().err
        assert "--ephemeral" in err

    def test_ephemeral_without_url_or_env_errors(self, capsys, monkeypatch):
        monkeypatch.delenv("BIFROST_API_URL", raising=False)
        rc = cli.handle_login(["--ephemeral", "--email", "x@y", "--password", "p"])
        assert rc != 0
        err = capsys.readouterr().err
        assert "URL" in err or "url" in err


class TestEphemeralLoginSuccess:
    def test_prints_three_lines_and_warning(self, capsys, monkeypatch):
        stub = _stub_post({
            "access_token": "at_value",
            "refresh_token": "rt_value",
            "expires_in": 1800,
        })
        monkeypatch.setattr("httpx.AsyncClient", stub)

        rc = cli.handle_login([
            "--ephemeral",
            "--email", "dev@gobifrost.com",
            "--password", "password",
            "--url", "http://localhost:38421",
        ])
        assert rc == 0

        captured = capsys.readouterr()
        # Three env-var-style lines on stdout
        out_lines = [l for l in captured.out.splitlines() if l.strip()]
        assert "BIFROST_API_URL=http://localhost:38421" in out_lines
        assert "BIFROST_ACCESS_TOKEN=at_value" in out_lines
        assert "BIFROST_REFRESH_TOKEN=rt_value" in out_lines

        # Warning to stderr
        assert "MFA" in captured.err
        assert "ephemeral" in captured.err.lower()

    def test_does_not_write_to_disk(self, capsys, monkeypatch, tmp_path):
        stub = _stub_post({
            "access_token": "at",
            "refresh_token": "rt",
            "expires_in": 1800,
        })
        monkeypatch.setattr("httpx.AsyncClient", stub)
        # Redirect any save target into tmp_path
        monkeypatch.setattr(
            "bifrost.credentials.get_credentials_path",
            lambda: tmp_path / "credentials.json",
        )

        cli.handle_login([
            "--ephemeral",
            "--email", "dev@gobifrost.com",
            "--password", "password",
            "--url", "http://localhost:38421",
        ])

        assert not (tmp_path / "credentials.json").exists()


class TestEphemeralLoginMfaRefusal:
    def test_mfa_required_returns_exit_2(self, capsys, monkeypatch):
        stub = _stub_post({"mfa_required": True, "mfa_token": "mt", "expires_in": 300})
        monkeypatch.setattr("httpx.AsyncClient", stub)

        rc = cli.handle_login([
            "--ephemeral",
            "--email", "dev@gobifrost.com",
            "--password", "password",
            "--url", "http://localhost:38421",
        ])
        assert rc == 2
        err = capsys.readouterr().err
        assert "MFA" in err
        assert "BIFROST_MFA_ENABLED" in err or "browser" in err.lower()

    def test_mfa_setup_required_returns_exit_2(self, capsys, monkeypatch):
        stub = _stub_post({"mfa_setup_required": True, "mfa_token": "mt", "expires_in": 300})
        monkeypatch.setattr("httpx.AsyncClient", stub)

        rc = cli.handle_login([
            "--ephemeral",
            "--email", "dev@gobifrost.com",
            "--password", "password",
            "--url", "http://localhost:38421",
        ])
        assert rc == 2


class TestEphemeralLoginUsesBifrostApiUrl:
    def test_falls_back_to_env_var_for_url(self, capsys, monkeypatch):
        stub = _stub_post({
            "access_token": "at",
            "refresh_token": "rt",
            "expires_in": 1800,
        })
        monkeypatch.setattr("httpx.AsyncClient", stub)
        monkeypatch.setenv("BIFROST_API_URL", "http://localhost:38421")

        rc = cli.handle_login([
            "--ephemeral",
            "--email", "dev@gobifrost.com",
            "--password", "password",
        ])
        assert rc == 0
        out_lines = capsys.readouterr().out.splitlines()
        assert "BIFROST_API_URL=http://localhost:38421" in out_lines
