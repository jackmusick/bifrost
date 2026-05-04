"""End-to-end test: bifrost password-grant login against the real test API.

Validates the password-grant CLI path (`bifrost login --email --password`):
the CLI is invoked as a real subprocess (no in-process shortcuts) that hits
the test stack's /auth/login endpoint and then uses the returned tokens, via
env vars, in a second subprocess invocation of `bifrost api`.

Two paths are exercised, gated on whether the test stack has global MFA
enabled (probed via /auth/status). Exactly one of the two tests is
meaningful in any given configuration; the other skips with a clear
reason. Together they cover both branches of the feature.
"""

from __future__ import annotations

import os
import subprocess
import sys

import httpx
import pytest


def _mfa_required_for_password(api_url: str) -> bool:
    """Probe the test stack to see if global MFA is enabled."""
    with httpx.Client(base_url=api_url, timeout=10.0) as client:
        resp = client.get("/auth/status")
        resp.raise_for_status()
        return bool(resp.json().get("mfa_required_for_password", False))


def _bifrost_cli() -> list[str]:
    """Command vector for invoking the bifrost CLI via the same Python."""
    return [sys.executable, "-m", "bifrost"]


def test_ephemeral_login_round_trip(e2e_api_url):
    """Full path: password-grant login, parse env-style output, use tokens via env vars in a child `bifrost api` call.

    Skips if the test stack has global MFA enabled (the default), since
    the password path by design refuses on instances with MFA on. Run with
    BIFROST_MFA_ENABLED=false on the API to exercise this end-to-end.
    """
    if _mfa_required_for_password(e2e_api_url):
        pytest.skip(
            "Test stack has global MFA enabled; password-grant refuses by design. "
            "Set BIFROST_MFA_ENABLED=false on the test stack's api service to "
            "exercise the round-trip."
        )

    # The seed user (BIFROST_DEFAULT_USER_EMAIL/PASSWORD) is the only user
    # we know exists with mfa_enabled=False on a stack configured for
    # password grant. If it isn't seeded, skip.
    email = os.environ.get("BIFROST_DEFAULT_USER_EMAIL", "dev@gobifrost.com")
    password = os.environ.get("BIFROST_DEFAULT_USER_PASSWORD", "password")

    # Step 1: password-grant login.
    result = subprocess.run(
        _bifrost_cli() + [
            "login",
            "--email", email,
            "--password", password,
            "--url", e2e_api_url,
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, (
        f"login failed: stdout={result.stdout!r} stderr={result.stderr!r}"
    )

    # Step 2: parse the three BIFROST_* lines.
    env_lines = {}
    for line in result.stdout.splitlines():
        if "=" in line and line.startswith("BIFROST_"):
            k, _, v = line.partition("=")
            env_lines[k] = v

    assert env_lines.get("BIFROST_API_URL", "").rstrip("/") == e2e_api_url.rstrip("/"), (
        f"BIFROST_API_URL not echoed correctly: {env_lines}"
    )
    assert env_lines.get("BIFROST_ACCESS_TOKEN"), f"missing access token: {env_lines}"
    assert env_lines.get("BIFROST_REFRESH_TOKEN"), f"missing refresh token: {env_lines}"

    # Step 3 & 4: use the tokens in a child `bifrost api` call.
    child_env = os.environ.copy()
    child_env.update(env_lines)
    result2 = subprocess.run(
        _bifrost_cli() + ["api", "GET", "/api/integrations"],
        env=child_env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result2.returncode == 0, (
        f"`bifrost api GET /api/integrations` failed: "
        f"stdout={result2.stdout!r} stderr={result2.stderr!r}"
    )


def test_ephemeral_login_refuses_mfa_required(e2e_api_url, platform_admin):
    """When the stack has MFA on, password-grant against an MFA-enrolled user must exit 2.

    Uses the platform_admin fixture (which has MFA enrolled) to provoke
    the mfa_required branch. Skips when the stack has global MFA off,
    since the CLI would receive direct tokens and never see mfa_required.
    """
    if not _mfa_required_for_password(e2e_api_url):
        pytest.skip(
            "Test stack has global MFA disabled; password-grant returns "
            "tokens directly and never reaches the refusal branch."
        )

    result = subprocess.run(
        _bifrost_cli() + [
            "login",
            "--email", platform_admin.email,
            "--password", platform_admin.password,
            "--url", e2e_api_url,
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode == 2, (
        f"Expected exit 2 (MFA refused), got {result.returncode}. "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    assert "MFA" in result.stderr, f"stderr missing MFA mention: {result.stderr!r}"


def test_ephemeral_env_vars_authenticate_bifrost_api_subprocess(
    e2e_api_url, platform_admin
):
    """Tokens injected via BIFROST_* env vars actually authenticate `bifrost api`.

    This is the half of the ephemeral round-trip that does NOT depend on
    global MFA being off: we obtain real tokens via the regular fixture
    (post-MFA), then prove that the EnvBackend correctly picks them up
    in a child `bifrost api GET ...` invocation. Combined with the
    refusal test (CLI -> /auth/login wire-up) and the round-trip test
    (full path on MFA-off stacks), this gives real-world coverage of
    every link in the chain.
    """
    child_env = os.environ.copy()
    child_env["BIFROST_API_URL"] = e2e_api_url
    child_env["BIFROST_ACCESS_TOKEN"] = platform_admin.access_token
    child_env["BIFROST_REFRESH_TOKEN"] = platform_admin.refresh_token

    result = subprocess.run(
        _bifrost_cli() + ["api", "GET", "/api/integrations"],
        env=child_env,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0, (
        f"`bifrost api GET /api/integrations` failed with env-var auth: "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
