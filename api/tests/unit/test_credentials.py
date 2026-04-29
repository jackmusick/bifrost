"""Tests for bifrost.credentials backend abstraction and multi-record store."""

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from bifrost import credentials as creds_mod
from bifrost.credentials import Credentials, EnvBackend, JsonBackend


# ---------- Credentials dataclass ----------

class TestCredentialsDataclass:
    def test_round_trip_to_dict_and_back(self):
        c = Credentials(
            api_url="http://localhost:38421",
            access_token="at",
            refresh_token="rt",
            expires_at="2030-01-01T00:00:00+00:00",
        )
        d = c.to_dict()
        assert d == {
            "api_url": "http://localhost:38421",
            "access_token": "at",
            "refresh_token": "rt",
            "expires_at": "2030-01-01T00:00:00+00:00",
        }
        assert Credentials.from_dict(d) == c


# ---------- EnvBackend ----------

class TestEnvBackend:
    def test_returns_credentials_when_all_three_env_vars_set(self, monkeypatch):
        monkeypatch.setenv("BIFROST_API_URL", "http://localhost:38421")
        monkeypatch.setenv("BIFROST_ACCESS_TOKEN", "at")
        monkeypatch.setenv("BIFROST_REFRESH_TOKEN", "rt")
        backend = EnvBackend()
        result = backend.get("http://localhost:38421")
        assert result is not None
        assert result.access_token == "at"
        assert result.refresh_token == "rt"

    def test_returns_none_when_url_does_not_match(self, monkeypatch):
        monkeypatch.setenv("BIFROST_API_URL", "http://localhost:38421")
        monkeypatch.setenv("BIFROST_ACCESS_TOKEN", "at")
        monkeypatch.setenv("BIFROST_REFRESH_TOKEN", "rt")
        backend = EnvBackend()
        # Ask for a different URL than what's in BIFROST_API_URL
        assert backend.get("http://localhost:99999") is None

    def test_returns_none_when_access_token_missing(self, monkeypatch):
        monkeypatch.setenv("BIFROST_API_URL", "http://localhost:38421")
        monkeypatch.delenv("BIFROST_ACCESS_TOKEN", raising=False)
        monkeypatch.setenv("BIFROST_REFRESH_TOKEN", "rt")
        backend = EnvBackend()
        assert backend.get("http://localhost:38421") is None

    def test_returns_none_when_refresh_token_missing(self, monkeypatch):
        monkeypatch.setenv("BIFROST_API_URL", "http://localhost:38421")
        monkeypatch.setenv("BIFROST_ACCESS_TOKEN", "at")
        monkeypatch.delenv("BIFROST_REFRESH_TOKEN", raising=False)
        backend = EnvBackend()
        assert backend.get("http://localhost:38421") is None

    def test_save_is_noop(self, monkeypatch):
        backend = EnvBackend()
        # Should not raise; env backend is read-only
        backend.save(Credentials("http://x", "at", "rt", "2030-01-01T00:00:00+00:00"))
        assert os.environ.get("BIFROST_ACCESS_TOKEN") in (None, "")  # didn't pollute env


# ---------- JsonBackend (multi-record) ----------

class TestJsonBackendMultiRecord:
    @pytest.fixture
    def tmp_creds_path(self, tmp_path, monkeypatch):
        path = tmp_path / "credentials.json"
        monkeypatch.setattr(creds_mod, "get_credentials_path", lambda: path)
        return path

    def test_save_and_get_single_record(self, tmp_creds_path):
        backend = JsonBackend()
        c = Credentials("http://localhost:38421", "at", "rt", "2030-01-01T00:00:00+00:00")
        backend.save(c)
        assert backend.get("http://localhost:38421") == c

    def test_save_two_urls_independently(self, tmp_creds_path):
        backend = JsonBackend()
        c1 = Credentials("http://localhost:38421", "at1", "rt1", "2030-01-01T00:00:00+00:00")
        c2 = Credentials("https://prod.example.com", "at2", "rt2", "2030-01-01T00:00:00+00:00")
        backend.save(c1)
        backend.save(c2)
        assert backend.get("http://localhost:38421") == c1
        assert backend.get("https://prod.example.com") == c2

    def test_clear_one_url_leaves_others(self, tmp_creds_path):
        backend = JsonBackend()
        c1 = Credentials("http://a", "at1", "rt1", "2030-01-01T00:00:00+00:00")
        c2 = Credentials("http://b", "at2", "rt2", "2030-01-01T00:00:00+00:00")
        backend.save(c1)
        backend.save(c2)
        backend.clear("http://a")
        assert backend.get("http://a") is None
        assert backend.get("http://b") == c2

    def test_list_returns_all_urls(self, tmp_creds_path):
        backend = JsonBackend()
        backend.save(Credentials("http://a", "at1", "rt1", "2030-01-01T00:00:00+00:00"))
        backend.save(Credentials("http://b", "at2", "rt2", "2030-01-01T00:00:00+00:00"))
        assert sorted(backend.list_urls()) == ["http://a", "http://b"]

    def test_get_returns_none_when_file_missing(self, tmp_creds_path):
        backend = JsonBackend()
        assert backend.get("http://anything") is None

    def test_file_permissions_are_0600(self, tmp_creds_path):
        import platform
        if platform.system() == "Windows":
            pytest.skip("POSIX permissions not applicable on Windows")
        backend = JsonBackend()
        backend.save(Credentials("http://a", "at", "rt", "2030-01-01T00:00:00+00:00"))
        mode = tmp_creds_path.stat().st_mode & 0o777
        assert mode == 0o600
