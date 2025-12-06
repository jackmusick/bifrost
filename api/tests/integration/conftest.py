"""
Pytest configuration for integration tests.

Integration tests use real PostgreSQL, RabbitMQ, and Redis services
provided by docker-compose.test.yml. All environment configuration
is handled by docker-compose - no local overrides needed.
"""

import os

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession


@pytest_asyncio.fixture
async def integration_db_session(db_session: AsyncSession) -> AsyncSession:
    """
    Provide a database session for integration tests.

    Wraps the base db_session fixture with integration-specific setup.
    """
    yield db_session


@pytest.fixture(scope="module")
def api_base_url():
    """
    Base URL for API integration tests.

    Default: http://localhost:18000 (docker-compose.test.yml offset port)
    Can be overridden with TEST_API_URL environment variable.
    """
    return os.getenv("TEST_API_URL", "http://localhost:18000")
