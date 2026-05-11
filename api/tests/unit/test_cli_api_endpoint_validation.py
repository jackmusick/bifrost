"""Regression coverage for authenticated ``bifrost api`` endpoint handling."""

from __future__ import annotations

import pytest

import bifrost.cli as cli


@pytest.mark.parametrize(
    "endpoint",
    [
        "/api/workflows",
        "/api/files/push?dry_run=true",
    ],
)
def test_api_endpoint_validator_accepts_absolute_paths(endpoint: str) -> None:
    assert cli._validate_api_endpoint(endpoint) is None


@pytest.mark.parametrize(
    "endpoint",
    [
        "api/workflows",
        "https://evil.example/collect",
        "http" + "://evil.example/collect",
        "//evil.example/collect",
        "/api/https://evil.example/collect",
    ],
)
def test_api_endpoint_validator_rejects_external_or_relative_urls(endpoint: str) -> None:
    assert cli._validate_api_endpoint(endpoint) is not None


def test_handle_api_rejects_external_url_before_auth(monkeypatch, capsys) -> None:
    def fail_get_instance(*args, **kwargs):  # pragma: no cover - should not run
        raise AssertionError("auth client should not be created for invalid endpoint")

    monkeypatch.setattr(cli.BifrostClient, "get_instance", fail_get_instance)

    exit_code = cli.handle_api(["GET", "https://evil.example/collect"])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "must not include a URL scheme or host" in captured.err
