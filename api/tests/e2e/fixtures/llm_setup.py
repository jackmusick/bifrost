"""
LLM Configuration E2E test fixtures.

Provides fixtures for testing LLM provider configuration endpoints.

Environment variables:
- ANTHROPIC_API_TEST_KEY: Anthropic API key for testing
- OPENAPI_API_TEST_KEY: OpenAI API key for testing
- GENERIC_AI_TEST_KEY: Custom OpenAI-compatible API key
- GENERIC_AI_BASE_URL: Custom endpoint URL (e.g., DeepSeek)
"""

import logging
import os
from collections.abc import Generator
from typing import Any

import pytest

logger = logging.getLogger(__name__)


@pytest.fixture(scope="session")
def llm_test_anthropic_key() -> str | None:
    """Get Anthropic test API key from environment."""
    return os.environ.get("ANTHROPIC_API_TEST_KEY")


@pytest.fixture(scope="session")
def llm_test_openai_key() -> str | None:
    """Get OpenAI test API key from environment."""
    return os.environ.get("OPENAPI_API_TEST_KEY")


@pytest.fixture(scope="session")
def llm_test_custom_config() -> dict[str, str] | None:
    """Get custom OpenAI-compatible provider config."""
    key = os.environ.get("GENERIC_AI_TEST_KEY")
    url = os.environ.get("GENERIC_AI_BASE_URL")

    if key and url:
        return {"api_key": key, "endpoint": url}
    return None


@pytest.fixture(scope="function")
def llm_config_cleanup(e2e_client, platform_admin) -> Generator[None, None, None]:
    """
    Ensure LLM config is cleaned up after test.

    This fixture ensures tests start with a clean state and
    cleans up any configuration created during the test.
    """
    # Clean up any existing config before test
    try:
        e2e_client.delete(
            "/api/admin/llm/config",
            headers=platform_admin.headers,
        )
    except Exception:
        pass  # Ignore if no config exists

    yield

    # Clean up after test
    try:
        e2e_client.delete(
            "/api/admin/llm/config",
            headers=platform_admin.headers,
        )
        logger.info("Cleaned up LLM config after test")
    except Exception:
        pass  # Ignore cleanup failures


@pytest.fixture(scope="function")
def llm_anthropic_configured(
    e2e_client,
    platform_admin,
    llm_test_anthropic_key,
) -> Generator[dict[str, Any], None, None]:
    """
    Configure Anthropic as the LLM provider for a test.

    Skips if ANTHROPIC_API_TEST_KEY is not set.

    Yields:
        dict with provider config details
    """
    if not llm_test_anthropic_key:
        pytest.skip("ANTHROPIC_API_TEST_KEY not configured")

    config = {
        "provider": "anthropic",
        "model": "claude-haiku-4-5-20251001",
        "api_key": llm_test_anthropic_key,
        "max_tokens": 1024,
    }

    response = e2e_client.post(
        "/api/admin/llm/config",
        json=config,
        headers=platform_admin.headers,
    )
    assert response.status_code == 200, (
        f"Failed to configure Anthropic: {response.text}"
    )

    logger.info("Configured Anthropic LLM provider")
    yield config

    # Cleanup
    try:
        e2e_client.delete(
            "/api/admin/llm/config",
            headers=platform_admin.headers,
        )
        logger.info("Cleaned up Anthropic config")
    except Exception as e:
        logger.warning(f"Failed to cleanup Anthropic config: {e}")


@pytest.fixture(scope="function")
def llm_openai_configured(
    e2e_client,
    platform_admin,
    llm_test_openai_key,
) -> Generator[dict[str, Any], None, None]:
    """
    Configure OpenAI as the LLM provider for a test.

    Skips if OPENAPI_API_TEST_KEY is not set.

    Yields:
        dict with provider config details
    """
    if not llm_test_openai_key:
        pytest.skip("OPENAPI_API_TEST_KEY not configured")

    config = {
        "provider": "openai",
        "model": "gpt-4o-mini",
        "api_key": llm_test_openai_key,
        "max_tokens": 1024,
    }

    response = e2e_client.post(
        "/api/admin/llm/config",
        json=config,
        headers=platform_admin.headers,
    )
    assert response.status_code == 200, f"Failed to configure OpenAI: {response.text}"

    logger.info("Configured OpenAI LLM provider")
    yield config

    # Cleanup
    try:
        e2e_client.delete(
            "/api/admin/llm/config",
            headers=platform_admin.headers,
        )
        logger.info("Cleaned up OpenAI config")
    except Exception as e:
        logger.warning(f"Failed to cleanup OpenAI config: {e}")
