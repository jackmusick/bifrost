"""
Pytest fixtures for Bifrost API testing infrastructure.

This module provides:
1. Database fixtures (PostgreSQL with SQLAlchemy async)
2. Message queue fixtures (RabbitMQ)
3. Cache fixtures (Redis)
4. Authentication/authorization fixtures
5. Common test data fixtures
"""

import os
import sys
from pathlib import Path
from typing import Any, AsyncGenerator
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.pool import NullPool

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Import fixture modules
pytest_plugins = [
    "tests.fixtures.auth",
    "tests.e2e.fixtures.setup",  # E2E session fixtures
    "tests.e2e.fixtures.github_setup",  # GitHub E2E fixtures
    "tests.e2e.fixtures.llm_setup",  # LLM E2E fixtures
    "tests.e2e.fixtures.knowledge_setup",  # Knowledge store E2E fixtures
]


# ==================== CONFIGURATION ====================

# Test database URL (prefer env provided by docker-compose; fall back to container hostnames)
TEST_DATABASE_URL = os.getenv(
    "BIFROST_DATABASE_URL",
    "postgresql+asyncpg://bifrost:bifrost_test@pgbouncer:5432/bifrost_test",
)

TEST_DATABASE_URL_SYNC = os.getenv(
    "BIFROST_DATABASE_URL_SYNC",
    "postgresql://bifrost:bifrost_test@pgbouncer:5432/bifrost_test",
)

TEST_RABBITMQ_URL = os.getenv(
    "BIFROST_RABBITMQ_URL",
    "amqp://bifrost:bifrost_test@rabbitmq:5672/",
)

TEST_REDIS_URL = os.getenv(
    "BIFROST_REDIS_URL",
    "redis://redis:6379/0",
)

TEST_API_URL = os.getenv("TEST_API_URL", "http://api:8000")


# ==================== SESSION FIXTURES (Start Once Per Test Run) ====================
# Note: pytest-asyncio handles event loop management automatically.
# Session-scoped async fixtures will share a loop; function-scoped ones get fresh loops.


@pytest.fixture(scope="session", autouse=True)
def setup_test_environment(tmp_path_factory):
    """Set up test environment variables once per session."""
    # Set environment variables for testing
    os.environ["BIFROST_ENVIRONMENT"] = "testing"
    os.environ["BIFROST_DATABASE_URL"] = TEST_DATABASE_URL
    os.environ["BIFROST_DATABASE_URL_SYNC"] = TEST_DATABASE_URL_SYNC
    os.environ["BIFROST_RABBITMQ_URL"] = TEST_RABBITMQ_URL
    os.environ["BIFROST_REDIS_URL"] = TEST_REDIS_URL
    os.environ["BIFROST_SECRET_KEY"] = "test-secret-key-for-e2e-testing-must-be-32-chars"

    # Set up workspace and temp locations for tests
    # These are now hardcoded paths - create them for test isolation
    test_workspace = Path("/tmp/bifrost/workspace")
    test_temp = Path("/tmp/bifrost/tmp")
    test_workspace.mkdir(parents=True, exist_ok=True)
    test_temp.mkdir(parents=True, exist_ok=True)
    os.environ["BIFROST_TEMP_LOCATION"] = str(test_temp)

    # Reset global database state to ensure it uses test settings
    # This is important because shared code (e.g., shared/metrics.py) uses
    # get_session_factory() which relies on global state
    from src.core.database import reset_db_state

    reset_db_state()

    yield

    # Clean up global database state after tests
    reset_db_state()


# ==================== DATABASE FIXTURES ====================


@pytest.fixture(scope="session")
def async_engine():
    """Create async SQLAlchemy engine for test session.

    Uses NullPool to avoid connection pooling issues with pytest-asyncio's
    function-scoped event loops. Each test gets fresh connections.
    """
    engine = create_async_engine(
        TEST_DATABASE_URL,
        echo=False,
        poolclass=NullPool,
    )
    yield engine
    # Cleanup handled by test.sh; NullPool ensures no lingering connections


@pytest.fixture(scope="session")
def async_session_factory(async_engine):
    """Create async session factory."""
    return async_sessionmaker(
        async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )


@pytest_asyncio.fixture
async def db_session(async_session_factory) -> AsyncGenerator[AsyncSession, None]:
    """
    Provide a database session for each test.

    Each test gets its own session that is rolled back after the test,
    ensuring test isolation.
    """
    async with async_session_factory() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def clean_db(db_session: AsyncSession) -> AsyncGenerator[AsyncSession, None]:
    """
    Provide a clean database for tests that need it.

    Truncates all tables before the test runs.
    Use sparingly as this is slower than transaction rollback.
    """
    # Get all table names
    result = await db_session.execute(
        text("""
            SELECT tablename FROM pg_tables
            WHERE schemaname = 'public'
            AND tablename != 'alembic_version'
        """)
    )
    tables = [row[0] for row in result.fetchall()]

    if tables:
        # Disable foreign key checks, truncate, re-enable
        await db_session.execute(text("SET session_replication_role = 'replica'"))
        for table in tables:
            await db_session.execute(text(f'TRUNCATE TABLE "{table}" CASCADE'))
        await db_session.execute(text("SET session_replication_role = 'origin'"))
        await db_session.commit()

    yield db_session


# ==================== MOCK FIXTURES ====================


@pytest.fixture
def mock_rabbitmq():
    """Mock RabbitMQ connection for unit tests."""
    mock = AsyncMock()
    mock.publish = AsyncMock(return_value=None)
    mock.consume = AsyncMock(return_value=None)
    return mock


@pytest.fixture
def mock_redis():
    """Mock Redis connection for unit tests."""
    mock = AsyncMock()
    mock.get = AsyncMock(return_value=None)
    mock.set = AsyncMock(return_value=True)
    mock.delete = AsyncMock(return_value=True)
    mock.expire = AsyncMock(return_value=True)
    return mock


# ==================== TEST DATA FIXTURES ====================


@pytest.fixture
def sample_user_data() -> dict[str, Any]:
    """Sample user data for testing."""
    return {
        "email": "test@example.com",
        "password": "SecurePassword123!",
        "name": "Test User",
    }


@pytest.fixture
def sample_org_data() -> dict[str, Any]:
    """Sample organization data for testing."""
    return {
        "name": "Test Organization",
        "domain": "example.com",
    }


@pytest.fixture
def sample_form_data() -> dict[str, Any]:
    """Sample form data for testing."""
    return {
        "name": "User Onboarding",
        "description": "Onboard new users",
        "linkedWorkflow": "user_onboarding",
        "formSchema": {
            "fields": [
                {
                    "type": "text",
                    "name": "email",
                    "label": "Email Address",
                    "required": True,
                },
                {
                    "type": "text",
                    "name": "name",
                    "label": "Full Name",
                    "required": True,
                },
            ]
        },
        "isPublic": False,
    }


@pytest.fixture
def sample_workflow_data() -> dict[str, Any]:
    """Sample workflow data for testing."""
    return {
        "name": "user_onboarding",
        "description": "User onboarding workflow",
        "steps": [
            {
                "id": "step1",
                "name": "Validate Input",
                "action": "validate",
            },
            {
                "id": "step2",
                "name": "Create User",
                "action": "create_user",
            },
        ],
    }


@pytest.fixture
def cleanup_workspace_files():
    """
    Fixture to track and clean up test files created in workspace.
    Yields paths to clean up, then removes them after test completes.
    """
    import shutil

    # Hardcoded workspace path
    workspace_path = Path("/tmp/bifrost/workspace")
    cleanup_paths = []

    def register_cleanup(path: str):
        """Register a path for cleanup."""
        cleanup_paths.append(path)

    yield register_cleanup

    # Cleanup after test
    for path_str in cleanup_paths:
        full_path = workspace_path / path_str
        if full_path.exists():
            if full_path.is_dir():
                shutil.rmtree(full_path)
            else:
                full_path.unlink()

    # Also clean up common test directories
    test_dirs = ["test_files", "test_folders", "test_listings", "forms"]
    for test_dir in test_dirs:
        dir_path = workspace_path / test_dir
        if dir_path.exists():
            # Only remove test files, not the whole directory structure
            for item in dir_path.glob("*"):
                if "test" in item.name.lower() or item.suffix == ".tmp":
                    if item.is_dir():
                        shutil.rmtree(item)
                    else:
                        item.unlink()


# ==================== MARKERS ====================


def pytest_configure(config):
    """Register custom pytest markers."""
    config.addinivalue_line("markers", "unit: Unit tests (fast, mocked dependencies)")
    config.addinivalue_line(
        "markers", "integration: Integration tests (real database, message queue)"
    )
    config.addinivalue_line(
        "markers", "e2e: End-to-end tests (full API with all services)"
    )
    config.addinivalue_line("markers", "slow: Tests that take >1 second")
