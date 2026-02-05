"""
E2E test configuration.

E2E tests run against the full API stack (API + Jobs workers) with real
PostgreSQL, RabbitMQ, and Redis services.

These tests require:
- docker-compose.test.yml services running (via ./test.sh)
- API service accessible at TEST_API_URL

Session-scoped fixtures provide shared state:
- platform_admin: First registered user (superuser)
- org1, org2: Test organizations
- org1_user, org2_user: Org users with tokens

Note: pytest_plugins moved to tests/conftest.py (root) as required by pytest.
"""

import os

import pytest
import httpx

# Re-export so existing ``from tests.e2e.conftest import poll_until`` still works.
from tests.helpers.polling import poll_until  # noqa: F401


# E2E test API URL (from docker-compose.test.yml)
# Default to api:8000 since tests run inside Docker network
E2E_API_URL = os.getenv("TEST_API_URL", "http://api:8000")


def pytest_configure(config):
    """Register e2e marker."""
    config.addinivalue_line(
        "markers",
        "e2e: End-to-end tests requiring full API stack (auto-skipped if API not available)"
    )


def _check_api_available() -> tuple[bool, str | None]:
    """
    Check if the API is properly running and accessible.

    Returns:
        tuple: (is_available: bool, reason: str)
    """
    try:
        response = httpx.get(f"{E2E_API_URL}/health", timeout=5.0)
        if response.status_code == 200:
            return True, None
        return False, f"API returned status {response.status_code}"
    except httpx.ConnectError:
        return False, f"Cannot connect to API at {E2E_API_URL}"
    except httpx.TimeoutException:
        return False, f"API request timed out at {E2E_API_URL}"
    except Exception as e:
        return False, f"Error checking API: {str(e)}"


def pytest_collection_modifyitems(config, items):
    """Skip e2e tests if API is not available."""
    is_available, reason = _check_api_available()

    if not is_available:
        skip_e2e = pytest.mark.skip(reason=f"E2E tests skipped: {reason}")
        for item in items:
            if "e2e" in item.nodeid:
                item.add_marker(skip_e2e)


@pytest.fixture(scope="session")
def e2e_api_url():
    """Base URL for E2E API tests."""
    return E2E_API_URL


@pytest.fixture(scope="session")
def e2e_client():
    """
    HTTP client for E2E tests.

    Provides a configured httpx client for making requests to the API.
    """
    with httpx.Client(base_url=E2E_API_URL, timeout=30.0) as client:
        yield client
