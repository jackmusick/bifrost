#!/usr/bin/env bash
# Bifrost test runner — verb-style subcommand interface.
#
# Stack lifecycle (long-lived, per worktree):
#   ./test.sh stack up                  Boot the stack.
#   ./test.sh stack down                Tear it down + remove volumes.
#   ./test.sh stack reset               Fast state reset (DB clone, redis flush, minio wipe).
#   ./test.sh stack status              Print project name and running services.
#
# Backend tests (stack must be up):
#   ./test.sh                           Unit tests only (fast default).
#   ./test.sh unit                      Same as above.
#   ./test.sh e2e                       Backend e2e tests.
#   ./test.sh all                       Unit + e2e (mirrors CI).
#   ./test.sh tests/path/... [args]     Pass through to pytest.
#
# Client tests:
#   ./test.sh client unit               Vitest on the host (no stack).
#   ./test.sh client e2e                Playwright in the stack's client container.
#   ./test.sh client e2e --screenshots  Capture a screenshot for every test (UX review).
#   ./test.sh client e2e e2e/auth.unauth.spec.ts   Pass through to playwright.
#
# CI escape hatch:
#   ./test.sh ci                        Full isolated run: up, all tests, down.
#
# Global flags (apply to most subcommands):
#   --no-reset    Skip state reset before running tests.
#   --coverage    Enable coverage reporting (backend only).
#   --wait        On failure, pause before cleanup.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# shellcheck source=scripts/lib/test_helpers.sh
source "$SCRIPT_DIR/scripts/lib/test_helpers.sh"

COMPOSE_FILE="docker-compose.test.yml"
export COMPOSE_PROJECT_NAME
COMPOSE_PROJECT_NAME="$(compute_project_name .)"

LOG_DIR="/tmp/bifrost-$COMPOSE_PROJECT_NAME"
mkdir -p "$LOG_DIR"
export LOG_DIR

# Load .env.test for optional secrets (GitHub PAT, LLM keys, etc.)
if [ -f ".env.test" ]; then
    set -a
    # shellcheck disable=SC1091
    source .env.test
    set +a
fi

# =============================================================================
# Common helpers
# =============================================================================

print_project() {
    echo "Worktree: $(git rev-parse --show-toplevel)"
    echo "Project:  $COMPOSE_PROJECT_NAME"
}

require_stack_up() {
    if ! stack_is_up "$COMPOSE_PROJECT_NAME" "$COMPOSE_FILE"; then
        echo "ERROR: stack not running for this worktree. Run:" >&2
        echo "  ./test.sh stack up" >&2
        exit 1
    fi
}

reset_state() {
    echo "Resetting state..."

    docker compose -f "$COMPOSE_FILE" stop api worker scheduler pgbouncer 2>/dev/null || true

    docker compose -f "$COMPOSE_FILE" exec -T postgres psql -U bifrost -d postgres -c \
        "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = 'bifrost_test' AND pid <> pg_backend_pid();" \
        > /dev/null 2>&1 || true
    docker compose -f "$COMPOSE_FILE" exec -T postgres psql -U bifrost -d postgres -c \
        "DROP DATABASE IF EXISTS bifrost_test;" > /dev/null
    docker compose -f "$COMPOSE_FILE" exec -T postgres psql -U bifrost -d postgres -c \
        "CREATE DATABASE bifrost_test TEMPLATE bifrost_test_template;" > /dev/null

    docker compose -f "$COMPOSE_FILE" exec -T redis redis-cli FLUSHDB > /dev/null
    docker compose -f "$COMPOSE_FILE" run --rm --no-deps minio-init > /dev/null 2>&1 || true

    rm -f client/e2e/.auth/credentials.json \
          client/e2e/.auth/platform_admin.json \
          client/e2e/.auth/org1_user.json \
          client/e2e/.auth/org2_user.json 2>/dev/null || true

    docker compose -f "$COMPOSE_FILE" start pgbouncer > /dev/null
    wait_for_service "$COMPOSE_FILE" pgbouncer pg_isready -h localhost -p 5432 -U bifrost
    docker compose -f "$COMPOSE_FILE" --profile e2e start api worker scheduler > /dev/null 2>&1 || true
    wait_for_service "$COMPOSE_FILE" api curl -sf http://localhost:8000/health

    echo "State reset complete."
}

# =============================================================================
# stack up|down|reset|status
# =============================================================================

cmd_stack() {
    local subcmd="${1:-status}"
    shift || true

    case "$subcmd" in
        up) stack_up "$@" ;;
        down) stack_down ;;
        reset) stack_reset ;;
        status) stack_status ;;
        *)
            echo "Unknown stack subcommand: $subcmd" >&2
            echo "Valid: up, down, reset, status" >&2
            exit 2
            ;;
    esac
}

stack_up() {
    print_project

    if stack_is_up "$COMPOSE_PROJECT_NAME" "$COMPOSE_FILE"; then
        echo "Stack already up."
        return 0
    fi

    echo "Booting infrastructure..."
    docker compose -f "$COMPOSE_FILE" up -d postgres rabbitmq redis minio

    wait_for_service "$COMPOSE_FILE" postgres pg_isready -U bifrost -d postgres
    wait_for_service "$COMPOSE_FILE" rabbitmq rabbitmq-diagnostics check_running
    wait_for_service "$COMPOSE_FILE" redis redis-cli ping

    docker compose -f "$COMPOSE_FILE" up -d pgbouncer minio-init
    wait_for_service "$COMPOSE_FILE" pgbouncer pg_isready -h localhost -p 5432 -U bifrost

    echo "Building template database..."
    "$SCRIPT_DIR/scripts/stack_template_init.sh"

    echo "Starting API + Worker + Scheduler..."
    docker compose -f "$COMPOSE_FILE" --profile e2e up -d --build
    wait_for_service "$COMPOSE_FILE" api curl -sf http://localhost:8000/health

    echo "Starting client..."
    docker compose -f "$COMPOSE_FILE" --profile client up -d --build client
    echo "Waiting for client to be healthy..."
    for i in {1..120}; do
        cid=$(docker compose -f "$COMPOSE_FILE" ps -q client 2>/dev/null)
        if [ -n "$cid" ]; then
            status=$(docker inspect -f '{{.State.Health.Status}}' "$cid" 2>/dev/null || echo unknown)
            if [ "$status" = "healthy" ]; then
                echo "Client ready."
                break
            fi
        fi
        if [ $i -eq 120 ]; then
            echo "ERROR: client not healthy after 120s" >&2
            exit 1
        fi
        sleep 1
    done

    echo ""
    echo "Stack is up. Project: $COMPOSE_PROJECT_NAME"
}

stack_down() {
    print_project
    echo "Tearing down stack..."
    export_logs "$COMPOSE_PROJECT_NAME" "$COMPOSE_FILE"
    docker compose -f "$COMPOSE_FILE" --profile e2e --profile test --profile client down -v
    echo "Done."
}

stack_reset() {
    require_stack_up
    "$SCRIPT_DIR/scripts/stack_template_init.sh"
    reset_state
}

stack_status() {
    print_project
    if stack_is_up "$COMPOSE_PROJECT_NAME" "$COMPOSE_FILE"; then
        echo "Status: UP"
        docker compose -f "$COMPOSE_FILE" ps
    else
        echo "Status: DOWN"
    fi
}

# =============================================================================
# Test subcommands
# =============================================================================

run_pytest() {
    require_stack_up
    reset_state
    docker compose -f "$COMPOSE_FILE" --profile test run --rm test-runner \
        pytest "$@" --junitxml=/tmp/bifrost/test-results.xml 2>&1 | tee "$LOG_DIR/test-runner.log"
    return "${PIPESTATUS[0]}"
}

cmd_unit() { run_pytest tests/ --ignore=tests/e2e/ -v "$@"; }
cmd_e2e()  { run_pytest tests/e2e/ -v "$@"; }
cmd_all()  { run_pytest tests/ -v "$@"; }

cmd_client() {
    local sub="${1:-}"
    shift || true
    case "$sub" in
        unit) client_unit "$@" ;;
        e2e) client_e2e "$@" ;;
        *)
            echo "Usage: ./test.sh client {unit|e2e} [args]" >&2
            exit 2
            ;;
    esac
}

client_unit() {
    echo "Running vitest on host..."
    (cd client && npm test "$@")
}

client_e2e() {
    require_stack_up
    local screenshots_all=false
    local passthrough=()
    for a in "$@"; do
        if [ "$a" = "--screenshots" ]; then screenshots_all=true
        else passthrough+=("$a")
        fi
    done

    reset_state

    local env_args=()
    if [ "$screenshots_all" = true ]; then
        env_args=(-e PLAYWRIGHT_SCREENSHOT_ALL=1)
    fi

    if [ ${#passthrough[@]} -gt 0 ]; then
        docker compose -f "$COMPOSE_FILE" --profile client run --rm "${env_args[@]}" \
            playwright-runner npx playwright test "${passthrough[@]}"
    else
        docker compose -f "$COMPOSE_FILE" --profile client run --rm "${env_args[@]}" \
            playwright-runner
    fi
}

cmd_ci() {
    print_project
    stack_up
    trap 'export_logs "$COMPOSE_PROJECT_NAME" "$COMPOSE_FILE"; stack_down' EXIT
    cmd_all
    client_unit
    client_e2e
}

# =============================================================================
# Dispatch
# =============================================================================

if [ $# -eq 0 ]; then
    cmd_unit
    exit $?
fi

case "$1" in
    stack) shift; cmd_stack "$@" ;;
    unit) shift; cmd_unit "$@" ;;
    e2e) shift; cmd_e2e "$@" ;;
    all) shift; cmd_all "$@" ;;
    client) shift; cmd_client "$@" ;;
    ci) cmd_ci ;;
    -h|--help|help)
        sed -n '2,35p' "$0"
        ;;
    tests/*|--*)
        run_pytest "$@"
        ;;
    *)
        echo "Unknown subcommand: $1" >&2
        echo "Run: ./test.sh --help" >&2
        exit 2
        ;;
esac
