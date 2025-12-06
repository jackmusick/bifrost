#!/bin/bash
# Bifrost API - Test Runner
#
# This script runs tests in an isolated Docker environment using docker-compose.test.yml.
# All dependencies (PostgreSQL, RabbitMQ, Redis) are ephemeral and cleaned up after tests.
#
# Usage:
#   ./test.sh                          # Run unit/integration tests (waits before cleanup)
#   ./test.sh --e2e                    # Run E2E tests (starts API + Jobs workers)
#   ./test.sh --coverage               # Run tests with coverage report
#   ./test.sh --ci                     # Skip interactive wait (for CI/CD pipelines)
#   ./test.sh tests/unit/ -v           # Run specific tests with pytest args
#   ./test.sh tests/integration/api/test_auth.py::test_login -v  # Run single test

set -e

# Get script directory (repo root)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# =============================================================================
# Configuration
# =============================================================================
COMPOSE_FILE="docker-compose.test.yml"
E2E_MODE=false
COVERAGE=false
CI_MODE=false
PYTEST_ARGS=()

# Parse command line arguments
for arg in "$@"; do
    if [ "$arg" = "--e2e" ]; then
        E2E_MODE=true
    elif [ "$arg" = "--coverage" ]; then
        COVERAGE=true
    elif [ "$arg" = "--ci" ]; then
        CI_MODE=true
    else
        PYTEST_ARGS+=("$arg")
    fi
done

# =============================================================================
# Cleanup function
# =============================================================================
cleanup() {
    echo ""
    echo "Cleaning up test environment..."
    if [ "$E2E_MODE" = true ]; then
        docker compose -f "$COMPOSE_FILE" --profile e2e --profile test down -v 2>/dev/null || true
    else
        docker compose -f "$COMPOSE_FILE" --profile test down -v 2>/dev/null || true
    fi
    echo "Cleanup complete"
}

# Trap to ensure cleanup on exit or Ctrl+C
trap cleanup EXIT INT TERM

# =============================================================================
# Start services
# =============================================================================
echo "============================================================"
echo "Bifrost API - Test Runner (Containerized)"
echo "============================================================"
echo ""

# Stop any existing test containers
echo "Stopping any existing test containers..."
docker compose -f "$COMPOSE_FILE" --profile e2e --profile test down -v 2>/dev/null || true

# Build the test runner image
echo "Building test runner image..."
docker compose -f "$COMPOSE_FILE" build test-runner

# Start infrastructure services
echo "Starting PostgreSQL, PgBouncer, RabbitMQ, and Redis..."
docker compose -f "$COMPOSE_FILE" up -d postgres rabbitmq redis

# Wait for PostgreSQL to be ready
echo "Waiting for PostgreSQL to be ready..."
for i in {1..60}; do
    if docker compose -f "$COMPOSE_FILE" exec -T postgres pg_isready -U bifrost -d bifrost_test > /dev/null 2>&1; then
        echo "PostgreSQL is ready!"
        break
    fi
    if [ $i -eq 60 ]; then
        echo "ERROR: PostgreSQL failed to start within 60 seconds"
        docker compose -f "$COMPOSE_FILE" logs postgres
        exit 1
    fi
    echo "  Waiting for PostgreSQL... (attempt $i/60)"
    sleep 1
done

# Wait for RabbitMQ to be ready
echo "Waiting for RabbitMQ to be ready..."
for i in {1..60}; do
    if docker compose -f "$COMPOSE_FILE" exec -T rabbitmq rabbitmq-diagnostics check_running > /dev/null 2>&1; then
        echo "RabbitMQ is ready!"
        break
    fi
    if [ $i -eq 60 ]; then
        echo "ERROR: RabbitMQ failed to start within 60 seconds"
        docker compose -f "$COMPOSE_FILE" logs rabbitmq
        exit 1
    fi
    echo "  Waiting for RabbitMQ... (attempt $i/60)"
    sleep 1
done

# Wait for Redis to be ready
echo "Waiting for Redis to be ready..."
for i in {1..30}; do
    if docker compose -f "$COMPOSE_FILE" exec -T redis redis-cli ping > /dev/null 2>&1; then
        echo "Redis is ready!"
        break
    fi
    if [ $i -eq 30 ]; then
        echo "ERROR: Redis failed to start within 30 seconds"
        docker compose -f "$COMPOSE_FILE" logs redis
        exit 1
    fi
    echo "  Waiting for Redis... (attempt $i/30)"
    sleep 1
done

# Start PgBouncer (depends on PostgreSQL being healthy)
echo "Starting PgBouncer..."
docker compose -f "$COMPOSE_FILE" up -d pgbouncer

# Wait for PgBouncer to be ready
echo "Waiting for PgBouncer to be ready..."
for i in {1..30}; do
    if docker compose -f "$COMPOSE_FILE" exec -T pgbouncer pg_isready -h localhost -p 5432 -U bifrost > /dev/null 2>&1; then
        echo "PgBouncer is ready!"
        break
    fi
    if [ $i -eq 30 ]; then
        echo "ERROR: PgBouncer failed to start within 30 seconds"
        docker compose -f "$COMPOSE_FILE" logs pgbouncer
        exit 1
    fi
    echo "  Waiting for PgBouncer... (attempt $i/30)"
    sleep 1
done

# =============================================================================
# E2E Mode: Start API and Jobs workers
# =============================================================================
if [ "$E2E_MODE" = true ]; then
    echo ""
    echo "E2E Mode: Starting API, Discovery, and Worker..."
    docker compose -f "$COMPOSE_FILE" --profile e2e up -d api discovery worker

    # Wait for API to be healthy
    echo "Waiting for API to be ready..."
    for i in {1..120}; do
        if docker compose -f "$COMPOSE_FILE" exec -T api curl -sf http://localhost:8000/health > /dev/null 2>&1; then
            echo "API is ready!"
            break
        fi
        if [ $i -eq 120 ]; then
            echo "ERROR: API failed to start within 120 seconds"
            docker compose -f "$COMPOSE_FILE" logs api
            exit 1
        fi
        echo "  Waiting for API... (attempt $i/120)"
        sleep 1
    done

    # Wait for Discovery to sync initial index
    echo "Waiting for Discovery to sync..."
    sleep 3  # Give discovery time to build initial index and sync to DB
fi

# =============================================================================
# Run database migrations
# =============================================================================
echo ""
echo "Running database migrations..."
docker compose -f "$COMPOSE_FILE" --profile test run --rm -T test-runner alembic upgrade head

# =============================================================================
# Run tests
# =============================================================================
echo ""
echo "============================================================"
echo "Running tests..."
echo "============================================================"
echo ""

# Build pytest command
PYTEST_CMD=("pytest")

if [ "$COVERAGE" = true ]; then
    PYTEST_CMD+=("--cov=src" "--cov-report=term-missing" "--cov-report=xml:/app/coverage.xml")
fi

if [ ${#PYTEST_ARGS[@]} -eq 0 ]; then
    # Default: run all tests except E2E (unless in E2E mode)
    if [ "$E2E_MODE" = true ]; then
        # Override the default "-m not e2e" from pytest.ini addopts
        PYTEST_CMD+=("tests/e2e/" "-m" "e2e" "-v")
    else
        PYTEST_CMD+=("tests/" "--ignore=tests/e2e/" "-v")
    fi
else
    PYTEST_CMD+=("${PYTEST_ARGS[@]}")
fi

# Run tests in container
set +e  # Don't exit on test failure
docker compose -f "$COMPOSE_FILE" --profile test run --rm test-runner "${PYTEST_CMD[@]}"
TEST_EXIT_CODE=$?
set -e

# Copy coverage report if generated
if [ "$COVERAGE" = true ]; then
    echo ""
    echo "Copying coverage report..."
    docker compose -f "$COMPOSE_FILE" --profile test run --rm test-runner cat /app/coverage.xml > coverage.xml 2>/dev/null || true
fi

echo ""
echo "============================================================"
if [ $TEST_EXIT_CODE -eq 0 ]; then
    echo "Tests completed successfully!"
else
    echo "Tests failed with exit code $TEST_EXIT_CODE"
fi
echo "============================================================"

# In interactive mode, wait for user before cleanup
if [ "$CI_MODE" = false ]; then
    echo ""
    echo "Press Enter to cleanup and exit (or Ctrl+C to keep containers running)..."
    read -r
fi

exit $TEST_EXIT_CODE
