#!/bin/bash
# Bifrost API - Test Runner
#
# This script runs tests in an isolated Docker environment using docker-compose.test.yml.
# All dependencies (PostgreSQL, RabbitMQ, Redis, API, Worker) are ephemeral and cleaned up after tests.
#
# Usage:
#   ./test.sh                          # Run ALL backend tests (unit, integration, e2e)
#   ./test.sh --coverage               # Run all tests with coverage report
#   ./test.sh --wait                   # Wait before cleanup (for debugging)
#   ./test.sh tests/unit/ -v           # Run only unit tests
#   ./test.sh tests/integration/ -v    # Run only integration tests
#   ./test.sh tests/e2e/ -v            # Run only E2E tests
#   ./test.sh tests/unit/test_foo.py::test_bar -v  # Run single test
#   ./test.sh --client                 # Run backend tests + Playwright E2E tests
#   ./test.sh --client-only            # Run only Playwright E2E tests (skip backend)
#   ./test.sh --client-dev             # Fast iteration: reset DB + run Playwright (keeps stack running)
#   ./test.sh --client-dev e2e/auth.unauth.spec.ts  # Run specific test file
#   ./test.sh --client-dev --grep "login"          # Run tests matching pattern
#   ./test.sh --local                  # Start API stack for LOCAL Playwright testing
#   ./test.sh --reset-db               # Reset database (keeps containers running)

set -e

# Get script directory (repo root)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# =============================================================================
# Configuration
# =============================================================================
COMPOSE_FILE="docker-compose.test.yml"
COMPOSE_LOCAL="docker-compose.local.yml"
COVERAGE=false
WAIT_MODE=false
CLIENT_TESTS=false
CLIENT_ONLY=false
CLIENT_DEV=false
LOCAL_MODE=false
RESET_DB=false
NO_RESET=false
PYTEST_ARGS=()
PLAYWRIGHT_ARGS=()

# Load .env.test if it exists (for GitHub PAT and other test secrets)
if [ -f ".env.test" ]; then
    echo "Loading test configuration from .env.test..."
    set -a  # automatically export all variables
    source .env.test
    set +a
fi

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
    elif [ "$arg" = "--client" ]; then
        # Run Playwright E2E tests after backend tests
        CLIENT_TESTS=true
    elif [ "$arg" = "--client-only" ]; then
        # Run only Playwright E2E tests (skip backend tests)
        CLIENT_TESTS=true
        CLIENT_ONLY=true
    elif [ "$arg" = "--client-dev" ]; then
        # Fast iteration mode: reset DB + run Playwright, keep stack running
        CLIENT_DEV=true
    elif [ "$arg" = "--local" ]; then
        # Start API stack for local Playwright testing (port exposed)
        LOCAL_MODE=true
    elif [ "$arg" = "--reset-db" ]; then
        # Reset database without restarting containers
        RESET_DB=true
    elif [ "$arg" = "--no-reset" ]; then
        # Skip database reset in client-dev mode
        NO_RESET=true
    elif [[ "$arg" == e2e/* ]] || [[ "$arg" == *".spec.ts"* ]] || [[ "$arg" == "--"* && "$CLIENT_DEV" = true ]]; then
        # Playwright-specific args (e2e files, spec files, or flags when in client-dev mode)
        PLAYWRIGHT_ARGS+=("$arg")
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
    for service in api worker postgres rabbitmq redis pgbouncer client playwright-runner; do
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
    docker compose -f "$COMPOSE_FILE" --profile e2e --profile test --profile client --profile zitadel down -v 2>/dev/null || true
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
# Local Mode - Start API stack with exposed port for local Playwright testing
# =============================================================================
if [ "$LOCAL_MODE" = true ]; then
    echo "============================================================"
    echo "Bifrost API - Local Playwright Testing Mode"
    echo "============================================================"
    echo ""
    echo "Starting API stack with port 8000 exposed to host..."
    echo ""

    # Stop any existing test containers
    echo "Stopping any existing test containers..."
    docker compose -f "$COMPOSE_FILE" -f "$COMPOSE_LOCAL" --profile e2e --profile test --profile client down -v 2>/dev/null || true

    # Start services with local override (exposes port 8000)
    echo "Starting infrastructure + API + Worker..."
    docker compose -f "$COMPOSE_FILE" -f "$COMPOSE_LOCAL" --profile e2e up -d --build

    # Wait for API to be healthy
    echo ""
    echo "Waiting for API to be ready..."
    for i in {1..120}; do
        if curl -sf http://localhost:8000/health > /dev/null 2>&1; then
            echo "API is ready at http://localhost:8000"
            break
        fi
        if [ $i -eq 120 ]; then
            echo "ERROR: API failed to start within 120 seconds"
            exit 1
        fi
        echo "  Waiting for API... (attempt $i/120)"
        sleep 1
    done

    echo ""
    echo "============================================================"
    echo "API stack is running with port 8000 exposed!"
    echo "============================================================"
    echo ""
    echo "Run Playwright tests locally:"
    echo "  cd client"
    echo "  npx playwright test              # Run all tests"
    echo "  npx playwright test --headed     # Watch tests run"
    echo "  npx playwright test --debug      # Step-through debugging"
    echo "  npx playwright test -g 'login'   # Run specific test"
    echo ""
    echo "Press Ctrl+C to stop the API stack and cleanup..."
    echo ""

    # Set up cleanup for local mode
    local_cleanup() {
        echo ""
        echo "Stopping API stack..."
        docker compose -f "$COMPOSE_FILE" -f "$COMPOSE_LOCAL" --profile e2e down -v 2>/dev/null || true
        echo "Cleanup complete"
        exit 0
    }
    trap local_cleanup EXIT INT TERM

    # Wait for user to stop
    while true; do
        sleep 1
    done
fi

# =============================================================================
# Reset Database Mode - Quick reset without restarting containers
# =============================================================================
if [ "$RESET_DB" = true ]; then
    # Disable cleanup trap for reset-db mode
    trap - EXIT

    echo "============================================================"
    echo "Bifrost API - Database Reset"
    echo "============================================================"
    echo ""

    # Check if postgres container is running
    if ! docker compose -f "$COMPOSE_FILE" ps postgres 2>/dev/null | grep -q "running"; then
        echo "ERROR: Postgres container not running."
        echo "Start the stack first with: ./test.sh --local"
        exit 1
    fi

    echo "Terminating database connections and recreating database..."
    docker compose -f "$COMPOSE_FILE" exec -T postgres \
        psql -U bifrost -d postgres -c "
            SELECT pg_terminate_backend(pid) FROM pg_stat_activity
            WHERE datname = 'bifrost_test' AND pid <> pg_backend_pid();
            DROP DATABASE IF EXISTS bifrost_test;
            CREATE DATABASE bifrost_test;
        " > /dev/null

    echo "Running database migrations..."
    docker compose -f "$COMPOSE_FILE" exec -T api alembic upgrade head

    echo "Clearing Playwright auth state..."
    rm -f client/e2e/.auth/credentials.json
    rm -f client/e2e/.auth/platform_admin.json
    rm -f client/e2e/.auth/org1_user.json
    rm -f client/e2e/.auth/org2_user.json

    echo ""
    echo "============================================================"
    echo "Database reset complete!"
    echo "============================================================"
    echo ""
    echo "Run your Playwright tests now - setup will recreate users:"
    echo "  cd client"
    echo "  TEST_API_URL=http://localhost:8000 TEST_BASE_URL=http://localhost:3000 npx playwright test"
    echo ""
    exit 0
fi

# =============================================================================
# Client Dev Mode - Fast iteration: start stack if needed, reset DB, run tests
# =============================================================================
if [ "$CLIENT_DEV" = true ]; then
    # Disable cleanup trap - we want to keep containers running
    trap - EXIT

    echo "============================================================"
    echo "Bifrost API - Client Dev Mode (Fast Iteration)"
    echo "============================================================"
    echo ""

    # Check if stack is already running
    STACK_RUNNING=false
    if docker compose -f "$COMPOSE_FILE" ps api 2>/dev/null | grep -q "running"; then
        STACK_RUNNING=true
        echo "Stack already running, skipping startup..."
    fi

    if [ "$STACK_RUNNING" = false ]; then
        echo "Starting test stack..."

        # Start infrastructure
        docker compose -f "$COMPOSE_FILE" up -d postgres rabbitmq redis minio

        # Wait for postgres
        echo "Waiting for PostgreSQL..."
        for i in {1..60}; do
            if docker compose -f "$COMPOSE_FILE" exec -T postgres pg_isready -U bifrost -d bifrost_test > /dev/null 2>&1; then
                break
            fi
            sleep 1
        done

        # Start PgBouncer and MinIO init
        docker compose -f "$COMPOSE_FILE" up -d pgbouncer minio-init

        # Wait for PgBouncer
        echo "Waiting for PgBouncer..."
        for i in {1..30}; do
            if docker compose -f "$COMPOSE_FILE" exec -T pgbouncer pg_isready -h localhost -p 5432 -U bifrost > /dev/null 2>&1; then
                break
            fi
            sleep 1
        done

        # Start API and Worker
        echo "Starting API and Worker..."
        docker compose -f "$COMPOSE_FILE" --profile e2e up -d --build api worker

        # Wait for API
        echo "Waiting for API..."
        for i in {1..120}; do
            if docker compose -f "$COMPOSE_FILE" exec -T api curl -sf http://localhost:8000/health > /dev/null 2>&1; then
                echo "API is ready!"
                break
            fi
            sleep 1
        done

        # Start client
        echo "Starting Client..."
        docker compose -f "$COMPOSE_FILE" --profile client up -d --build client

        # Wait for client
        echo "Waiting for Client..."
        for i in {1..120}; do
            HEALTH_STATUS=$(docker inspect -f '{{.State.Health.Status}}' bifrost-test-client 2>/dev/null || echo "unknown")
            if [ "$HEALTH_STATUS" = "healthy" ]; then
                echo "Client is ready!"
                break
            fi
            sleep 1
        done
    fi

    # Reset database unless --no-reset was passed
    if [ "$NO_RESET" = false ]; then
        echo ""
        echo "Stopping API and worker to release database connections..."
        docker compose -f "$COMPOSE_FILE" stop api worker 2>/dev/null || true
        sleep 1

        echo "Resetting database..."
        # Terminate any remaining connections, then drop and recreate
        docker compose -f "$COMPOSE_FILE" exec -T postgres \
            psql -U bifrost -d postgres -c \
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = 'bifrost_test' AND pid <> pg_backend_pid();" \
            > /dev/null 2>&1 || true
        docker compose -f "$COMPOSE_FILE" exec -T postgres \
            psql -U bifrost -d postgres -c "DROP DATABASE IF EXISTS bifrost_test;" > /dev/null
        docker compose -f "$COMPOSE_FILE" exec -T postgres \
            psql -U bifrost -d postgres -c "CREATE DATABASE bifrost_test;" > /dev/null

        # Restart API to run migrations and start server
        echo "Restarting API (runs migrations on startup)..."
        docker compose -f "$COMPOSE_FILE" start api worker

        # Wait for API to be ready
        echo "Waiting for API to be ready..."
        for i in {1..60}; do
            if docker compose -f "$COMPOSE_FILE" exec -T api curl -sf http://localhost:8000/health > /dev/null 2>&1; then
                echo "API is ready!"
                break
            fi
            sleep 2
        done

        # Clear auth state
        rm -f client/e2e/.auth/credentials.json
        rm -f client/e2e/.auth/platform_admin.json
        rm -f client/e2e/.auth/org1_user.json
        rm -f client/e2e/.auth/org2_user.json
    else
        echo ""
        echo "Skipping database reset (--no-reset)"
    fi

    # Run Playwright tests
    echo ""
    echo "============================================================"
    echo "Running Playwright E2E tests..."
    if [ ${#PLAYWRIGHT_ARGS[@]} -gt 0 ]; then
        echo "Args: ${PLAYWRIGHT_ARGS[*]}"
    fi
    echo "============================================================"
    echo ""

    set +e
    if [ ${#PLAYWRIGHT_ARGS[@]} -gt 0 ]; then
        docker compose -f "$COMPOSE_FILE" --profile client run --rm playwright-runner \
            npx playwright test "${PLAYWRIGHT_ARGS[@]}"
    else
        docker compose -f "$COMPOSE_FILE" --profile client run --rm playwright-runner
    fi
    PLAYWRIGHT_EXIT_CODE=$?
    set -e

    echo ""
    echo "============================================================"
    if [ $PLAYWRIGHT_EXIT_CODE -eq 0 ]; then
        echo "Tests PASSED!"
    else
        echo "Tests FAILED (exit code $PLAYWRIGHT_EXIT_CODE)"
    fi
    echo "============================================================"
    echo ""
    echo "Stack is still running. Run './test.sh --client-dev' again to reset and re-test."
    echo "Run './test.sh --reset-db' to just reset the database."
    echo "Run 'docker compose -f docker-compose.test.yml down -v' to stop everything."
    echo ""

    exit $PLAYWRIGHT_EXIT_CODE
fi

# =============================================================================
# Start services
# =============================================================================
echo "============================================================"
echo "Bifrost API - Test Runner (Containerized)"
echo "============================================================"
echo ""

# Stop any existing test containers
echo "Stopping any existing test containers..."
docker compose -f "$COMPOSE_FILE" --profile e2e --profile test --profile client down -v 2>/dev/null || true

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
# Run backend tests (skip if --client-only)
# =============================================================================
TEST_EXIT_CODE=0

if [ "$CLIENT_ONLY" = false ]; then
    echo ""
    echo "============================================================"
    echo "Running backend tests..."
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
        echo "Backend tests completed successfully!"
    else
        echo "Backend tests failed with exit code $TEST_EXIT_CODE"
    fi
    echo "============================================================"
else
    echo ""
    echo "============================================================"
    echo "Skipping backend tests (--client-only mode)"
    echo "============================================================"
fi

# =============================================================================
# Run Playwright E2E tests (if --client or --client-only)
# =============================================================================
PLAYWRIGHT_EXIT_CODE=0

if [ "$CLIENT_TESTS" = true ]; then
    echo ""
    echo "============================================================"
    echo "Starting client services for Playwright tests..."
    echo "============================================================"

    # Start client service
    docker compose -f "$COMPOSE_FILE" --profile client up -d --build client

    # Wait for client to be healthy (using Docker health check status)
    echo "Waiting for client to be ready..."
    for i in {1..120}; do
        # Check if container is running
        CONTAINER_STATUS=$(docker inspect -f '{{.State.Status}}' bifrost-test-client 2>/dev/null || echo "not_found")
        if [ "$CONTAINER_STATUS" = "exited" ] || [ "$CONTAINER_STATUS" = "dead" ]; then
            echo "ERROR: Client container crashed!"
            echo "Container logs:"
            docker logs bifrost-test-client --tail=50 2>&1 || true
            export_docker_logs
            exit 1
        fi

        # Check health status
        HEALTH_STATUS=$(docker inspect -f '{{.State.Health.Status}}' bifrost-test-client 2>/dev/null || echo "unknown")
        if [ "$HEALTH_STATUS" = "healthy" ]; then
            echo "Client is ready!"
            break
        fi

        if [ $i -eq 120 ]; then
            echo "ERROR: Client failed to start within 120 seconds"
            echo "Health status: $HEALTH_STATUS"
            echo "Container logs:"
            docker logs bifrost-test-client --tail=50 2>&1 || true
            export_docker_logs
            exit 1
        fi
        echo "  Waiting for client... (attempt $i/120, status: $HEALTH_STATUS)"
        sleep 1
    done

    echo ""
    echo "============================================================"
    echo "Running Playwright E2E tests..."
    echo "============================================================"
    echo ""

    # Run Playwright tests (disable ERR trap - we handle exit code manually)
    trap - ERR
    set +e
    docker compose -f "$COMPOSE_FILE" --profile client run --rm playwright-runner
    PLAYWRIGHT_EXIT_CODE=$?
    set -e

    echo ""
    echo "============================================================"
    if [ $PLAYWRIGHT_EXIT_CODE -eq 0 ]; then
        echo "Playwright tests completed successfully!"
    else
        echo "Playwright tests failed with exit code $PLAYWRIGHT_EXIT_CODE"
    fi
    echo "============================================================"
fi

# =============================================================================
# Final summary
# =============================================================================
echo ""
echo "============================================================"
echo "Test Summary"
echo "============================================================"
if [ "$CLIENT_ONLY" = false ]; then
    if [ $TEST_EXIT_CODE -eq 0 ]; then
        echo "  Backend tests: PASSED"
    else
        echo "  Backend tests: FAILED (exit code $TEST_EXIT_CODE)"
    fi
fi
if [ "$CLIENT_TESTS" = true ]; then
    if [ $PLAYWRIGHT_EXIT_CODE -eq 0 ]; then
        echo "  Playwright tests: PASSED"
    else
        echo "  Playwright tests: FAILED (exit code $PLAYWRIGHT_EXIT_CODE)"
    fi
fi
echo "============================================================"

# In wait mode, wait for user before cleanup
if [ "$WAIT_MODE" = true ]; then
    echo ""
    echo "Press Enter to cleanup and exit (or Ctrl+C to keep containers running)..."
    read -r
fi

# Exit with failure if any tests failed
if [ $TEST_EXIT_CODE -ne 0 ]; then
    exit $TEST_EXIT_CODE
fi
if [ $PLAYWRIGHT_EXIT_CODE -ne 0 ]; then
    exit $PLAYWRIGHT_EXIT_CODE
fi
exit 0
