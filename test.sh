#!/bin/bash
# Bifrost API - Test Runner
#
# This script runs tests in an isolated Docker environment using docker-compose.test.yml.
# All dependencies (PostgreSQL, RabbitMQ, Redis, API, Worker) are ephemeral and cleaned up after tests.
#
# Usage:
#   ./test.sh                          # Run ALL tests (unit, integration, e2e)
#   ./test.sh --coverage               # Run all tests with coverage report
#   ./test.sh --wait                   # Wait before cleanup (for debugging)
#   ./test.sh tests/unit/ -v           # Run only unit tests
#   ./test.sh tests/integration/ -v    # Run only integration tests
#   ./test.sh tests/e2e/ -v            # Run only E2E tests
#   ./test.sh tests/unit/test_foo.py::test_bar -v  # Run single test

set -e

# Get script directory (repo root)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# =============================================================================
# Configuration
# =============================================================================
COMPOSE_FILE="docker-compose.test.yml"
COVERAGE=false
WAIT_MODE=false
PYTEST_ARGS=()

# Parse command line arguments
for arg in "$@"; do
    if [ "$arg" = "--coverage" ]; then
        COVERAGE=true
    elif [ "$arg" = "--wait" ]; then
        WAIT_MODE=true
    elif [ "$arg" = "--ci" ]; then
        # Legacy flag - now the default behavior, kept for backwards compatibility
        true
    elif [ "$arg" = "--e2e" ]; then
        # Legacy flag - E2E now runs by default, kept for backwards compatibility
        true
    else
        PYTEST_ARGS+=("$arg")
    fi
done

# =============================================================================
# Docker log export directory
# =============================================================================
LOG_DIR="/tmp/bifrost"
mkdir -p "$LOG_DIR"

# =============================================================================
# Function to export docker logs
# =============================================================================
export_docker_logs() {
    echo "Exporting docker logs to $LOG_DIR/docker-logs.txt..."
    {
        echo "============================================================"
        echo "Docker Compose Logs - $(date)"
        echo "============================================================"
        docker compose -f "$COMPOSE_FILE" logs --no-color 2>&1
    } > "$LOG_DIR/docker-logs.txt" 2>&1 || true

    # Also export individual service logs for easier debugging
    for service in api worker postgres rabbitmq redis pgbouncer; do
        docker compose -f "$COMPOSE_FILE" logs --no-color "$service" > "$LOG_DIR/$service.log" 2>&1 || true
    done

    echo "Docker logs exported to $LOG_DIR/"
}

# =============================================================================
# Cleanup function
# =============================================================================
cleanup() {
    echo ""
    # Export logs before cleanup
    export_docker_logs
    echo "Cleaning up test environment..."
    docker compose -f "$COMPOSE_FILE" --profile e2e --profile test down -v 2>/dev/null || true
    echo "Cleanup complete"
}

# =============================================================================
# Error handler - prompts before cleanup on any failure
# =============================================================================
error_handler() {
    local exit_code=$?
    local line_number=$1

    echo ""
    echo "============================================================"
    echo "ERROR: Script failed at line $line_number (exit code: $exit_code)"
    echo "============================================================"

    # Show recent container logs for debugging
    echo ""
    echo "Recent container logs:"
    echo "------------------------------------------------------------"
    docker compose -f "$COMPOSE_FILE" logs --tail=50 2>/dev/null || true
    echo "------------------------------------------------------------"

    # In wait mode, wait for user before cleanup
    if [ "$WAIT_MODE" = true ]; then
        echo ""
        echo "Press Enter to cleanup and exit (or Ctrl+C to keep containers running for debugging)..."
        read -r
    fi
}

# Trap errors to show logs and wait before cleanup
trap 'error_handler $LINENO' ERR
# Trap to ensure cleanup on exit or Ctrl+C
trap cleanup EXIT

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
        exit 1
    fi
    echo "  Waiting for PgBouncer... (attempt $i/30)"
    sleep 1
done

# =============================================================================
# Start API and Worker for E2E tests
# =============================================================================
echo ""
echo "Starting API and Worker for E2E tests..."
docker compose -f "$COMPOSE_FILE" --profile e2e up -d --build api worker

# Wait for API to be healthy
echo "Waiting for API to be ready..."
for i in {1..120}; do
    if docker compose -f "$COMPOSE_FILE" exec -T api curl -sf http://localhost:8000/health > /dev/null 2>&1; then
        echo "API is ready!"
        break
    fi
    if [ $i -eq 120 ]; then
        echo "ERROR: API failed to start within 120 seconds"
        exit 1
    fi
    echo "  Waiting for API... (attempt $i/120)"
    sleep 1
done

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
    # Default: run ALL tests (unit, integration, e2e)
    PYTEST_CMD+=("tests/" "-v")
else
    # Custom test paths provided
    PYTEST_CMD+=("${PYTEST_ARGS[@]}")
fi

# Run tests in container (disable ERR trap for tests - we handle exit code manually)
trap - ERR
set +e
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

# In wait mode, wait for user before cleanup
if [ "$WAIT_MODE" = true ]; then
    echo ""
    echo "Press Enter to cleanup and exit (or Ctrl+C to keep containers running)..."
    read -r
fi

exit $TEST_EXIT_CODE
