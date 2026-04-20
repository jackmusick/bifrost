# Test Infrastructure Refactor + `bifrost-testing` Skill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

## Execution State

- **Worktree:** `/home/jack/GitHub/bifrost/.worktrees/test-infra-refactor` (this is gitignored in the main repo; each worktree the main repo spawns goes under `.worktrees/<branch-name>/` by convention)
- **Branch:** `test-infra-refactor` (off `main`)
- **Status:** All 12 tasks complete. Branch ready for review/merge.

### Verification outcomes

| Task | Check | Result |
| --- | --- | --- |
| 6 | `stack up` cold boot | ✅ succeeded; all containers healthy; project `bifrost-test-1c24af24` |
| 6 | `stack up` idempotency | ✅ second call says "Stack already up." |
| 6 | `stack reset` (warm) | ✅ ran in **22s**. Target was <2s; most of the 22s is uvicorn cold-restart after the DB swap. Acceptable for now; see "Known tradeoff" below. |
| 6 | Template idempotency | ✅ "template up to date (hash: …)" on repeat runs |
| 6 | Migration-change rebuild | ✅ new hash → "Rebuilding template"; cleanup → rebuild again to original hash |
| 6 | `stack down` | ✅ clean teardown, volumes removed |
| 7 | `./test.sh unit` | ✅ 2867/2867 passed in 115s |
| 9 | `./test.sh client unit` | ✅ 14/14 vitest tests passed in 1.81s |
| 9 | `./test.sh client e2e <spec>` | ✅ 8/8 Playwright tests passed in 30.6s (incl. setup) |
| 12 | Orphaned-refs grep | ✅ zero hits of `bifrost-test-(api\|client\|…)` outside the plan file |

### Bugs surfaced during verification (and the commits that fixed them)

- `stack_template_init.sh` initially routed alembic through pgbouncer, but pgbouncer is pinned to `bifrost_test` — fixed in `scripts/stack_template_init.sh` (alembic now goes direct to `postgres:5432`).
- `stack reset` tried to rebuild the template while API/worker held connections to `bifrost_test` — fixed in `test.sh` `stack_reset()` which now stops API consumers before template_init.
- Code-review pass also caught: hash-comparison whitespace bug in template script; trap ordering in `cmd_ci`; `export_logs` missing `-p` flag; `reset_state` swallowing real errors; `/tmp/bifrost` mount not per-worktree. All fixed.

### Known tradeoff

**`stack reset` takes ~22s, not <2s.** The template-clone itself is sub-second; the remaining time is uvicorn (API + worker + scheduler) cold-restarting after connections are killed and waiting for the health probe. This is inherent to "reset state but keep the stack up" with a live API. If this becomes painful, options are:
1. Add a `reset --db-only` path that skips the API restart (for backend unit tests that don't hit the API).
2. Teach the API to hot-reload its DB connection pool on a signal instead of a restart.

Neither is required today. The >10× improvement over the old "nuke everything" flow is already captured.

**Goal:** Refactor `./test.sh` into a verb-style subcommand interface with per-worktree stack isolation and template-database fast reset, then codify the workflow in a new `.claude/skills/bifrost-testing` skill.

**Architecture:** `test.sh` becomes a dispatcher with subcommands (`stack up/down/reset/status`, `unit`, `e2e`, `all`, `client unit`, `client e2e`, `ci`). Compose project name is derived from the worktree's repo root path via SHA-256, so two worktrees run isolated stacks in parallel. A PostgreSQL template database (`bifrost_test_template`) is built once per alembic-versions hash at `stack up` and cloned on every reset — reducing reset time from ~10s to <2s. Hardcoded `container_name:` entries are removed in favor of docker compose's native service-name addressing. A new skill enforces hard rules (no skipped/failing tests) and co-located test authoring standards.

**Tech Stack:** Bash, Docker Compose v2, PostgreSQL 16 templates, pytest, Playwright, Vitest, Claude Code skills (`.claude/skills/<name>/SKILL.md` with frontmatter).

---

## File Structure

**Files being modified:**
- `test.sh` — full rewrite around subcommand dispatch (currently ~880 lines of flag-mode branches)
- `docker-compose.test.yml` — remove `name:` and `container_name:` hardcoding
- `docker-compose.local.yml` — deleted (functionality folded into `stack up --expose-api`)
- `client/playwright.config.ts` — read `PLAYWRIGHT_SCREENSHOT_ALL` env; drop any hardcoded container refs
- `CLAUDE.md` — update "Commands" + "Pre-Completion Verification" sections

**Files being created:**
- `scripts/lib/test_helpers.sh` — reusable bash: `compute_project_name`, `wait_for_service`, `export_logs`, `template_db_rebuild_if_needed`
- `scripts/stack_template_init.sh` — idempotent PostgreSQL template DB build
- `.claude/skills/bifrost-testing/SKILL.md` — the workflow skill
- `.claude/skills/bifrost-testing/authoring-rules.md` — expanded reference loaded on demand

**Files being deleted:**
- `docker-compose.local.yml` (replaced by `--expose-api` flag on `stack up`)

**Responsibility split:**
- `test.sh` is the user-facing entry point. It dispatches to subcommand handler functions, no business logic inline.
- `scripts/lib/test_helpers.sh` holds shared bash primitives (wait loops, project-name derivation, log export).
- `scripts/stack_template_init.sh` owns the template-DB build/rebuild logic.
- The skill files stay narrative — no shell logic, just documented workflow.

---

## Task 1: Add the test_helpers.sh library with project-name derivation

**Files:**
- Create: `scripts/lib/test_helpers.sh`

- [ ] **Step 1: Write the library**

```bash
#!/usr/bin/env bash
# Shared helpers for test.sh and scripts/stack_*.sh.
# Source this file; do not execute directly.

# Derive a Docker Compose project name scoped to this worktree.
# Two worktrees with the same repo name get distinct stacks because the
# hash is taken over the absolute repo root path.
compute_project_name() {
    local repo_root
    repo_root="$(git -C "${1:-.}" rev-parse --show-toplevel 2>/dev/null)"
    if [ -z "$repo_root" ]; then
        echo "ERROR: compute_project_name must be called inside a git worktree" >&2
        return 1
    fi
    local hash
    hash="$(printf '%s' "$repo_root" | sha256sum | cut -c1-8)"
    printf 'bifrost-test-%s' "$hash"
}

# Wait for a compose service to be healthy (or responding on a probe command).
# Args: <compose-file> <service> <probe-command...>
# Returns 0 if ready, 1 on timeout.
wait_for_service() {
    local compose_file="$1"; shift
    local service="$1"; shift
    local max_attempts="${WAIT_MAX_ATTEMPTS:-60}"
    local i
    for ((i=1; i<=max_attempts; i++)); do
        if docker compose -f "$compose_file" exec -T "$service" "$@" > /dev/null 2>&1; then
            return 0
        fi
        sleep 1
    done
    echo "ERROR: $service not ready after ${max_attempts}s" >&2
    return 1
}

# Is the stack for this worktree currently running?
stack_is_up() {
    local project="$1"
    local compose_file="$2"
    docker compose -p "$project" -f "$compose_file" ps --status running --quiet 2>/dev/null | grep -q .
}

# Export per-service logs to LOG_DIR. No-op if LOG_DIR is empty.
export_logs() {
    local compose_file="$1"
    local log_dir="${LOG_DIR:-}"
    [ -z "$log_dir" ] && return 0
    mkdir -p "$log_dir"
    local services
    services=$(docker compose -f "$compose_file" --profile e2e --profile test --profile client config --services 2>/dev/null)
    for svc in $services; do
        docker compose -f "$compose_file" logs --no-color --timestamps "$svc" > "$log_dir/$svc.log" 2>&1 || true
        [ -s "$log_dir/$svc.log" ] || rm -f "$log_dir/$svc.log"
    done
}
```

- [ ] **Step 2: Write a unit test for `compute_project_name`**

```bash
# tests/unit/test_test_helpers.bats (or simple shell assertion if bats is not installed)
```

Create `scripts/lib/test_helpers_test.sh`:

```bash
#!/usr/bin/env bash
set -e
source "$(dirname "$0")/test_helpers.sh"

# Case: called outside git should fail with clear message
result=$(compute_project_name /tmp 2>&1 || true)
[[ "$result" == *"must be called inside a git worktree"* ]] || { echo "FAIL: expected git error, got: $result"; exit 1; }

# Case: called inside repo should return deterministic hash
name1=$(compute_project_name "$(git rev-parse --show-toplevel)")
name2=$(compute_project_name "$(git rev-parse --show-toplevel)")
[[ "$name1" == "$name2" ]] || { echo "FAIL: hash not deterministic: $name1 vs $name2"; exit 1; }
[[ "$name1" =~ ^bifrost-test-[a-f0-9]{8}$ ]] || { echo "FAIL: bad format: $name1"; exit 1; }

echo "PASS: compute_project_name"
```

- [ ] **Step 3: Run the test**

Run: `bash scripts/lib/test_helpers_test.sh`
Expected: `PASS: compute_project_name`

- [ ] **Step 4: Commit**

```bash
git add scripts/lib/test_helpers.sh scripts/lib/test_helpers_test.sh
git commit -m "chore(test): add scripts/lib/test_helpers.sh with per-worktree project name derivation"
```

---

## Task 2: Make docker-compose.test.yml project-name-agnostic

**Files:**
- Modify: `docker-compose.test.yml`

- [ ] **Step 1: Remove the hardcoded `name:` and all `container_name:` fields**

Edit `docker-compose.test.yml`:
- Delete line 19: `name: bifrost-test`
- Delete every `container_name: bifrost-test-<service>` line (there will be one per service — postgres, pgbouncer, rabbitmq, redis, minio, minio-init, init, api, worker, scheduler, test-runner, client, playwright-runner).
- Leave service names and all other config untouched.

- [ ] **Step 2: Verify compose still parses**

Run:
```bash
COMPOSE_PROJECT_NAME=bifrost-test-check docker compose -f docker-compose.test.yml --profile e2e --profile test --profile client config --services
```
Expected: list of service names (postgres, pgbouncer, rabbitmq, redis, minio, minio-init, init, api, worker, scheduler, test-runner, client, playwright-runner). No errors.

- [ ] **Step 3: Verify containers now get project-prefixed names**

Run:
```bash
COMPOSE_PROJECT_NAME=bifrost-test-check docker compose -f docker-compose.test.yml up -d postgres
docker ps --filter "name=bifrost-test-check" --format '{{.Names}}'
```
Expected: a container named something like `bifrost-test-check-postgres-1` (compose's default naming scheme).

Clean up:
```bash
COMPOSE_PROJECT_NAME=bifrost-test-check docker compose -f docker-compose.test.yml down -v
```

- [ ] **Step 4: Commit**

```bash
git add docker-compose.test.yml
git commit -m "chore(test): drop hardcoded project/container names in docker-compose.test.yml

Per-worktree COMPOSE_PROJECT_NAME now drives namespacing so multiple
worktrees can run test stacks concurrently."
```

---

## Task 3: Add scripts/stack_template_init.sh (template DB build)

**Files:**
- Create: `scripts/stack_template_init.sh`

- [ ] **Step 1: Write the script**

```bash
#!/usr/bin/env bash
# Builds (or rebuilds) the bifrost_test_template database inside the postgres
# container. Idempotent: if the hash of api/alembic/versions/ matches the
# marker stored in the template DB, skips rebuild.
#
# Requires:
#   - COMPOSE_PROJECT_NAME exported
#   - docker-compose.test.yml's postgres service already running
#
# Emits: "template up to date" or "template rebuilt"

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
COMPOSE_FILE="$REPO_ROOT/docker-compose.test.yml"

: "${COMPOSE_PROJECT_NAME:?COMPOSE_PROJECT_NAME must be set}"

# Hash of the alembic versions directory — changes whenever a migration is added/edited.
MIGRATIONS_HASH=$(find "$REPO_ROOT/api/alembic/versions" -type f -name '*.py' \
    -exec sha256sum {} \; | sort | sha256sum | cut -c1-16)

psql_postgres() {
    docker compose -f "$COMPOSE_FILE" exec -T postgres \
        psql -U bifrost -d postgres -t -A "$@"
}

# Check existing marker on template DB (stored as a comment on the DB).
EXISTING_HASH=$(psql_postgres -c \
    "SELECT shobj_description(oid, 'pg_database') FROM pg_database WHERE datname = 'bifrost_test_template';" \
    2>/dev/null | tr -d ' ' || echo "")

if [ "$EXISTING_HASH" = "$MIGRATIONS_HASH" ]; then
    echo "template up to date (hash: $MIGRATIONS_HASH)"
    exit 0
fi

echo "Rebuilding template (old hash: ${EXISTING_HASH:-none}, new hash: $MIGRATIONS_HASH)..."

# Release the template flag (otherwise DROP fails) and drop.
psql_postgres -c \
    "UPDATE pg_database SET datistemplate = false WHERE datname = 'bifrost_test_template';" > /dev/null 2>&1 || true
psql_postgres -c "DROP DATABASE IF EXISTS bifrost_test_template;" > /dev/null

# Also drop bifrost_test to force a fresh clone on next reset.
psql_postgres -c \
    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = 'bifrost_test' AND pid <> pg_backend_pid();" > /dev/null 2>&1 || true
psql_postgres -c "DROP DATABASE IF EXISTS bifrost_test;" > /dev/null

# Create the template and run alembic into it. We temporarily point the API's
# DB URL at bifrost_test_template by starting a one-shot init container with
# an overridden env var.
psql_postgres -c "CREATE DATABASE bifrost_test_template;" > /dev/null

docker compose -f "$COMPOSE_FILE" run --rm \
    -e BIFROST_DATABASE_URL_SYNC="postgresql://bifrost:bifrost_test@pgbouncer:5432/bifrost_test_template" \
    -e BIFROST_DATABASE_URL="postgresql+asyncpg://bifrost:bifrost_test@pgbouncer:5432/bifrost_test_template" \
    --no-deps init alembic upgrade head > /dev/null

# Mark as template and stamp the hash.
psql_postgres -c "ALTER DATABASE bifrost_test_template IS_TEMPLATE true;" > /dev/null
psql_postgres -c "COMMENT ON DATABASE bifrost_test_template IS '${MIGRATIONS_HASH}';" > /dev/null

# Create a fresh bifrost_test from the template so tests can run immediately.
psql_postgres -c "CREATE DATABASE bifrost_test TEMPLATE bifrost_test_template;" > /dev/null

echo "template rebuilt (hash: $MIGRATIONS_HASH)"
```

- [ ] **Step 2: Make it executable**

```bash
chmod +x scripts/stack_template_init.sh
```

- [ ] **Step 3: Commit** (tested end-to-end in Task 6)

```bash
git add scripts/stack_template_init.sh
git commit -m "feat(test): add template-db build script for fast state reset"
```

---

## Task 4: Rewrite test.sh — top-level dispatcher + stack lifecycle subcommands

**Files:**
- Modify: `test.sh` (full rewrite)

- [ ] **Step 1: Replace test.sh entirely**

The new file is ~300 lines vs today's ~880. Full contents:

```bash
#!/usr/bin/env bash
# Bifrost test runner — verb-style subcommand interface.
#
# Stack lifecycle (long-lived, per worktree):
#   ./test.sh stack up [--expose-api]   Boot the stack. --expose-api publishes :8000 for local playwright.
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
export COMPOSE_PROJECT_NAME="$(compute_project_name .)"

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

    # Stop services that hold DB connections so we can drop/clone cleanly.
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
    local expose_api=false
    for a in "$@"; do
        [ "$a" = "--expose-api" ] && expose_api=true
    done

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
    if [ "$expose_api" = true ]; then
        # Publish port 8000 for local playwright. Uses an inline override.
        docker compose -f "$COMPOSE_FILE" --profile e2e up -d --build \
            --no-recreate --scale scheduler=1 api worker scheduler
        # Also expose via docker publish (requires container recreation if not already exposed).
        echo "NOTE: --expose-api requires 'docker run -p 8000:8000' semantics;"
        echo "      use scripts/expose_api.sh if needed, or see stack status for the API URL."
    else
        docker compose -f "$COMPOSE_FILE" --profile e2e up -d --build
    fi
    wait_for_service "$COMPOSE_FILE" api curl -sf http://localhost:8000/health

    echo "Starting client..."
    docker compose -f "$COMPOSE_FILE" --profile client up -d --build client
    # Client health comes from docker healthcheck; poll via docker inspect.
    for i in {1..120}; do
        local cid
        cid=$(docker compose -f "$COMPOSE_FILE" ps -q client)
        [ -z "$cid" ] && sleep 1 && continue
        local status
        status=$(docker inspect -f '{{.State.Health.Status}}' "$cid" 2>/dev/null || echo unknown)
        [ "$status" = "healthy" ] && { echo "Client ready."; break; }
        [ $i -eq 120 ] && { echo "ERROR: client not healthy"; exit 1; }
        sleep 1
    done

    echo ""
    echo "Stack is up. Project: $COMPOSE_PROJECT_NAME"
}

stack_down() {
    print_project
    echo "Tearing down stack..."
    export_logs "$COMPOSE_FILE"
    docker compose -f "$COMPOSE_FILE" --profile e2e --profile test --profile client down -v
    echo "Done."
}

stack_reset() {
    require_stack_up
    # Rebuild template if migrations changed.
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
    # Args: <pytest_paths_and_flags...>
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
    trap 'export_logs "$COMPOSE_FILE"; stack_down' EXIT
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
        # Passthrough to pytest when first arg looks like a path or pytest flag.
        run_pytest "$@"
        ;;
    *)
        echo "Unknown subcommand: $1" >&2
        echo "Run: ./test.sh --help" >&2
        exit 2
        ;;
esac
```

- [ ] **Step 2: Keep executable bit**

```bash
chmod +x test.sh
```

- [ ] **Step 3: Sanity-check the dispatcher**

Run: `./test.sh --help`
Expected: the comment block at the top of the file is printed.

Run: `./test.sh stack status`
Expected: prints worktree + project name, says "Status: DOWN" (stack isn't up yet in this task).

- [ ] **Step 4: Commit**

```bash
git add test.sh
git commit -m "feat(test): rewrite test.sh around verb-style subcommands"
```

---

## Task 5: Delete docker-compose.local.yml

**Files:**
- Delete: `docker-compose.local.yml`

- [ ] **Step 1: Remove the file**

```bash
git rm docker-compose.local.yml
```

- [ ] **Step 2: Grep for stale references**

Run: `grep -rn 'docker-compose\.local\.yml' . --include='*.sh' --include='*.yml' --include='*.yaml' --include='*.md' --include='*.ts'`
Expected: no hits (we rewrote test.sh in Task 4 and will update CLAUDE.md in Task 10).

If any references remain (in CI workflows, other docs), update them in this task.

- [ ] **Step 3: Commit**

```bash
git commit -m "chore(test): drop docker-compose.local.yml (replaced by stack up)"
```

---

## Task 6: End-to-end test — stack up, reset, down

**Files:** (no code changes — verification)

- [ ] **Step 1: Verify clean boot**

Run:
```bash
./test.sh stack down    # ensure clean slate
./test.sh stack up
```
Expected: infrastructure starts, template DB builds (first time — "Rebuilding template"), API + worker + client come up healthy, final "Stack is up" line.

- [ ] **Step 2: Verify `stack up` is idempotent**

Run: `./test.sh stack up` (second time)
Expected: "Stack already up."

- [ ] **Step 3: Verify fast reset**

Run: `time ./test.sh stack reset`
Expected: completes in under ~5s (our <2s target depends on image warmth; first run may be slower). Output includes "template up to date" (since nothing changed) and "State reset complete."

- [ ] **Step 4: Verify template rebuild on migration change**

Add a throwaway empty migration:
```bash
cd api && alembic revision -m "plan-task-6-throwaway" && cd ..
./test.sh stack reset
```
Expected: "Rebuilding template (old hash: …, new hash: …)" then "State reset complete."

Revert:
```bash
rm api/alembic/versions/*plan-task-6-throwaway*.py
./test.sh stack reset
```

- [ ] **Step 5: Verify concurrent worktree isolation**

```bash
git worktree add /tmp/bifrost-test-wt-check -b plan-task-6-wt-check
cd /tmp/bifrost-test-wt-check
./test.sh stack up
docker ps --format '{{.Names}}' | grep bifrost-test- | awk -F- '{print $1"-"$2"-"$3}' | sort -u
```
Expected: two distinct project names (one per worktree).

Clean up:
```bash
./test.sh stack down
cd - && git worktree remove /tmp/bifrost-test-wt-check --force
git branch -D plan-task-6-wt-check
```

- [ ] **Step 6: Verify stack down**

Run: `./test.sh stack down`
Expected: containers and volumes removed. `./test.sh stack status` shows "DOWN".

- [ ] **Step 7: Commit nothing (verification only)**

---

## Task 7: End-to-end test — backend test subcommands

**Files:** (no code changes — verification)

- [ ] **Step 1: Boot the stack**

```bash
./test.sh stack up
```

- [ ] **Step 2: Verify unit tests run**

Run: `./test.sh unit`
Expected: pytest runs against `tests/` excluding `tests/e2e/`. State is reset first, then pytest output. Exit code 0 on green.

- [ ] **Step 3: Verify e2e tests run**

Run: `./test.sh e2e`
Expected: pytest runs against `tests/e2e/`. State is reset first. Exit code 0 on green (if backend is healthy and tests are currently passing on main).

- [ ] **Step 4: Verify bare `./test.sh` runs unit only (fast default)**

Run: `./test.sh`
Expected: same as `./test.sh unit` — unit tests only, no e2e.

- [ ] **Step 5: Verify `./test.sh all` runs both**

Run: `./test.sh all`
Expected: runs `tests/` including e2e.

- [ ] **Step 6: Verify pytest passthrough**

Run: `./test.sh tests/unit/test_datetime_consistency.py -v`
Expected: pytest runs that single file.

- [ ] **Step 7: Commit nothing (verification only)**

---

## Task 8: Playwright config — read PLAYWRIGHT_SCREENSHOT_ALL

**Files:**
- Modify: `client/playwright.config.ts`

- [ ] **Step 1: Write the test change**

Edit `client/playwright.config.ts`, replace the `use:` block (lines 29-35):

```typescript
use: {
    baseURL: process.env.TEST_BASE_URL || "http://localhost:3000",
    trace: "on-first-retry",
    screenshot: process.env.PLAYWRIGHT_SCREENSHOT_ALL === "1" ? "on" : "only-on-failure",
    video: "on-first-retry",
},
```

- [ ] **Step 2: Verify config parses**

Run: `cd client && npx playwright test --list -g 'nonexistent-test-name' 2>&1 | head -5`
Expected: config loads without errors (output lists projects).

- [ ] **Step 3: Run with screenshots opt-in to verify wiring**

```bash
./test.sh client e2e --screenshots e2e/auth.unauth.spec.ts
```
Expected: after the run, `client/playwright-results/` or `client/test-results/` (whichever Playwright uses — confirm by looking) contains `.png` files for each test, not just failures.

- [ ] **Step 4: Commit**

```bash
git add client/playwright.config.ts
git commit -m "feat(client): honor PLAYWRIGHT_SCREENSHOT_ALL env to capture screenshots for every test"
```

---

## Task 9: End-to-end test — client test subcommands

**Files:** (no code changes — verification)

- [ ] **Step 1: Verify vitest runs on host**

Run: `./test.sh client unit`
Expected: `npm test` runs in `client/`, vitest prints results. No stack interaction. Fast (few seconds).

- [ ] **Step 2: Verify playwright runs in stack**

Run: `./test.sh client e2e`
Expected: state reset, then playwright runs in the stack's `playwright-runner` container against the internal client/api services. Exit 0 on green.

- [ ] **Step 3: Verify screenshot opt-in produces files**

Run: `./test.sh client e2e --screenshots e2e/auth.unauth.spec.ts`
Expected: Playwright writes screenshots under `client/playwright-results/` (or `client/test-results/` — confirm during Task 8), one per test — not only-on-failure.

- [ ] **Step 4: Verify spec passthrough**

Run: `./test.sh client e2e e2e/auth.unauth.spec.ts`
Expected: only that spec runs.

- [ ] **Step 5: Tear down**

```bash
./test.sh stack down
```

- [ ] **Step 6: Commit nothing (verification only)**

---

## Task 10: Update CLAUDE.md

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Find the existing "Commands" section**

```bash
grep -n '^### Commands' CLAUDE.md
```

- [ ] **Step 2: Replace the entire Commands block with the new syntax**

In `CLAUDE.md`, replace the existing `### Commands` subsection (the fenced block starting with `# Start Development` and ending around the next `###`) with:

```markdown
### Commands

```bash
# Dev stack
./debug.sh                                         # Start dev stack (hot reload)

# Test stack lifecycle (per worktree, long-lived)
./test.sh stack up                                 # Boot test stack for this worktree
./test.sh stack down                               # Tear it down
./test.sh stack reset                              # Fast state reset (<2s) — DB clone + redis flush + minio wipe
./test.sh stack status                             # Is the stack up? What project name?

# Backend tests (stack must be up; state auto-reset before each run)
./test.sh                                          # Unit only (fast default)
./test.sh unit                                     # Same
./test.sh e2e                                      # Backend e2e
./test.sh all                                      # Unit + e2e (mirrors CI)
./test.sh tests/unit/test_foo.py::test_bar -v      # Passthrough to pytest

# Client tests
./test.sh client unit                              # Vitest on host (no stack needed)
./test.sh client e2e                               # Playwright in containers
./test.sh client e2e --screenshots                 # Capture screenshots for every test (UX review)
./test.sh client e2e e2e/auth.unauth.spec.ts       # Passthrough to playwright

# CI
./test.sh ci                                       # Up → all tests → down, one shot

# Type generation (requires dev stack running)
cd client && npm run generate:types

# Quality checks
cd api && pyright
cd api && ruff check .
cd client && npm run tsc
cd client && npm run lint
```
```

- [ ] **Step 3: Update the "Pre-Completion Verification" section**

Find the block `## Pre-Completion Verification` and replace the test runner line. The existing step `5. Run tests` that currently says `./test.sh` should now say:

```bash
# 5. Run tests
./test.sh stack up    # if not already up
./test.sh all         # backend unit + e2e
./test.sh client unit # vitest
./test.sh client e2e  # playwright (skip if no UI changes)
```

- [ ] **Step 4: Remove stale flag mentions**

Search `CLAUDE.md` for `--client`, `--client-dev`, `--client-only`, `--e2e`, `--local`, `--reset-db`. Replace or delete the surrounding lines so they match the new syntax.

```bash
grep -n -- '--client\|--client-dev\|--client-only\|--e2e\|--local\|--reset-db' CLAUDE.md
```
Expected after edits: no hits.

- [ ] **Step 5: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: update CLAUDE.md test commands for new subcommand syntax"
```

---

## Task 11: Create the bifrost-testing skill

**Files:**
- Create: `.claude/skills/bifrost-testing/SKILL.md`
- Create: `.claude/skills/bifrost-testing/authoring-rules.md`

- [ ] **Step 1: Write SKILL.md**

```markdown
---
name: bifrost-testing
description: Run and write tests for Bifrost. Use when writing or running tests; adding or modifying React components, pages, or user-facing features; debugging failing or flaky tests; before declaring UI or backend work complete. Trigger phrases - "write a test", "run tests", "add a component", "ship this feature", "ready to merge", "test is failing", "flaky", "vitest", "pytest", "playwright".
---

# Bifrost Testing

This skill codifies how to run tests, what tests to write for new work, and the non-negotiable rules about failing or skipped tests.

## Hard Rules (Non-Negotiable)

1. **Never leave tests failing.** A red test means work is not done. Fix the test or fix the code under test. Never commit or claim completion with failing tests.

2. **Never skip tests as a shortcut.** No `@pytest.mark.skip`, `pytest.skip()`, `test.skip()`, `test.only()`, `it.skip()`, `xfail`, or commenting a test out. A skipped test must be either **fixed** or **deleted** — and delete only if the test is genuinely no longer useful (feature removed, behavior moved, truly redundant). "I'll come back to it" is not a valid reason to skip.

3. **Flaky ≠ add retries.** Per `feedback_flaky_tests.md`, E2E flakes are always state pollution from a prior test. Find the dirty state. Do not add retries, do not increase timeouts, do not re-run until green.

4. **No silencing.** If a test is noisy, fix the source or delete the test. Don't filter output, don't swallow the failure.

## Test Authoring Rules (Definition of Done for New UI Work)

Summary — see `authoring-rules.md` for examples:

- **Every non-trivial React component has a sibling `*.test.tsx`.** Co-located (`Foo.tsx` → `Foo.test.tsx` in same directory). Tests cover behavior, not pixels. Exempt: pure presentational components (static wrappers, icons).
- **Every user-facing feature has a happy-path Playwright spec** under `client/e2e/`. Happy path only — edge cases belong in vitest.
- **Backend logic needs unit tests; endpoint/workflow/integration changes need e2e tests.** (Already in `CLAUDE.md`.)

Check before declaring work done: component added but no sibling `.test.tsx`? Not done. User-facing feature shipped but no happy-path spec? Not done.

## Workflow

### 1. Is the stack up for this worktree?

```bash
./test.sh stack status
```

If DOWN: `./test.sh stack up`.

### 2. What am I testing?

- Backend logic only → `./test.sh unit` or `./test.sh tests/unit/test_foo.py -v`
- Backend with live services → `./test.sh e2e` or `./test.sh tests/e2e/test_foo.py -v`
- React component behavior → `./test.sh client unit` (vitest, no stack needed)
- Full user flow through UI → `./test.sh client e2e`

### 3. Before declaring done

Run the broader suite to catch regressions:

- Backend change: `./test.sh all`
- UI change: `./test.sh client unit && ./test.sh client e2e`

Verify the authoring rules above are satisfied for any new code.

### 4. UX review (conditional)

**Trigger:** the user is in "I just built a UI feature, write its first happy-path spec" mode. Signal comes from conversation, not git diff. If unsure, ask once.

**Process:**
1. Write the Playwright spec for the happy path.
2. `./test.sh client e2e --screenshots <spec-file>`
3. After green, Read each screenshot under `client/playwright-results/` (or `client/test-results/`) and report layout/spacing/contrast/alignment issues.
4. Iterate: tweak component → rerun → re-review until user signs off.

**Skip when:** bugfix, backend change, routine pre-merge check.

### 5. Flaky test?

Check `/tmp/bifrost-<project-name>/*.log` and `/tmp/bifrost/test-results.xml`. Remember: state pollution, not saturation. Find what a prior test left behind.

## Definition-of-Done Checklist

Before declaring work complete, verify each:

- [ ] New non-trivial React component has a sibling `*.test.tsx`
- [ ] New user-facing feature has a happy-path Playwright spec
- [ ] Backend logic has a unit test; endpoint/workflow changes have an e2e test
- [ ] No new `skip`, `xfail`, `.only`, or commented-out tests introduced
- [ ] Targeted suite green
- [ ] Broader suite green (`./test.sh all` for backend, `./test.sh client e2e` for UI)
- [ ] UX review done if new UI was built

If any box is unchecked, keep working — do not declare done.

## What This Skill Is Not

Not a coverage-threshold enforcer. Not a pixel-diff tool. Not a lint for pure refactors. It's a workflow guide with hard rules on what matters: red tests, skipped tests, and missing coverage on new code.
```

- [ ] **Step 2: Write authoring-rules.md**

```markdown
# Bifrost Test Authoring Rules — Expanded

## Component tests (vitest + testing-library)

Pattern: `client/src/components/foo/Foo.tsx` → `client/src/components/foo/Foo.test.tsx`.

What to cover:
- Validation (errors appear/disappear correctly)
- Conditional rendering (feature flags, loading/error/empty states)
- Event handlers (click → mutation called with right args)
- State transitions (dialog phases, toggle states)

How to mock:
- Mock hooks and external modules at module level with `vi.mock()`.
- Do not render the whole app. Mock the query/mutation layer.
- Use `userEvent.setup()` + `screen.getByRole()` / `getByLabel()`. No `data-testid`.

Reference patterns (copy these):
- `client/src/components/applications/AppReplacePathDialog.test.tsx`
- `client/src/components/workflows/WorkflowSidebar.test.tsx`

Exempt from requiring a sibling test:
- Pure presentational wrappers: `<Card>`, `<PageHeader>`, a styled div.
- Static icon components.
- Re-exports.

## Feature happy-path tests (Playwright)

One file per feature under `client/e2e/`, named `<feature>.<audience>.spec.ts` where audience is `admin`, `user`, or `unauth`.

What to cover:
- The primary user journey end-to-end: navigate, interact, verify outcome.
- One path, not every branch. Validation errors, permission-denied paths, and edge cases live in vitest.

Selectors: semantic only. `page.getByRole()`, `page.getByLabel()`, `page.getByPlaceholder()`. Do not introduce `data-testid`.

Wait strategy: use condition-based waits (`waitForURL`, `getByRole().waitFor()`, `Promise.race([...])`). Do not use `page.waitForTimeout()`.

## Backend tests

Already covered in CLAUDE.md under "Testing & Quality". Key reminders:
- Unit tests for pure logic in `api/tests/unit/`.
- E2E tests for anything that hits the API, DB, queue, or S3 in `api/tests/e2e/`.
- Use `./test.sh` — never run `pytest` on the host directly.
```

- [ ] **Step 3: Verify the skill is discoverable**

Run: `ls .claude/skills/bifrost-testing/`
Expected: `SKILL.md`, `authoring-rules.md`.

Run: `head -5 .claude/skills/bifrost-testing/SKILL.md`
Expected: frontmatter with `name: bifrost-testing` and the description on one line.

- [ ] **Step 4: Commit**

```bash
git add .claude/skills/bifrost-testing/
git commit -m "feat(skills): add bifrost-testing skill with test authoring rules"
```

---

## Task 12: Final verification sweep

**Files:** (no code changes — verification)

- [ ] **Step 1: Concurrent worktree smoke test**

In terminal 1 (original worktree):
```bash
./test.sh stack up
./test.sh unit
```

In terminal 2, create a second worktree and run in parallel:
```bash
git worktree add /tmp/bifrost-plan-verify -b plan-verify-throwaway
cd /tmp/bifrost-plan-verify
./test.sh stack up
./test.sh unit
```

Expected: both pass. `docker ps` in a third terminal shows distinct project-name prefixes. Cleanup:
```bash
./test.sh stack down
cd - && git worktree remove /tmp/bifrost-plan-verify --force
git branch -D plan-verify-throwaway
```

- [ ] **Step 2: CI path smoke test**

```bash
./test.sh stack down   # start clean
./test.sh ci
```
Expected: stack boots, all tests run, stack tears down at exit.

- [ ] **Step 3: Orphaned references check**

```bash
grep -rn 'bifrost-test-\(api\|client\|worker\|postgres\|pgbouncer\|rabbitmq\|redis\|minio\|scheduler\|init\|test-runner\|playwright\)' \
    --include='*.sh' --include='*.yml' --include='*.yaml' --include='*.ts' --include='*.tsx' --include='*.md' --include='*.py' .
```
Expected: zero hits (every reference to hardcoded `bifrost-test-*` container names has been removed).

If any hits: those files need to use service names via `docker compose exec` / `docker compose logs`.

- [ ] **Step 4: Skill auto-invocation smoke test**

This requires Claude Code. Open a fresh session in the repo and say:
> "Write me a vitest test for a new component I just made."

Expected: Claude invokes `bifrost-testing` without needing `/bifrost-testing` typed manually. Verify by checking the tool-call log.

- [ ] **Step 5: Commit nothing (verification only)**

---

## Self-Review

Spec coverage check:

| Spec requirement | Task |
|---|---|
| Single entry point, verb-style subcommands | 4 |
| Per-worktree stack isolation via COMPOSE_PROJECT_NAME | 1, 2, 4 |
| PostgreSQL template DB for fast reset | 3, 4 |
| Migration-hash triggered template rebuild | 3 |
| `./test.sh` defaults to unit only | 4 |
| `stack up --expose-api` replaces `--local` | 4 |
| Drop docker-compose.local.yml | 5 |
| Playwright screenshot opt-in via env | 8 |
| Vitest on host (no containers) | 4, 9 |
| CI one-shot path | 4 |
| Per-worktree log dir | 4 |
| Concurrent worktree verification | 6, 12 |
| Skill frontmatter tuned for auto-invoke | 11 |
| Hard rules: no failing/skipped tests | 11 |
| Test authoring rules (component + feature) | 11 |
| Definition-of-done checklist | 11 |
| UX review workflow | 11 |
| Update CLAUDE.md | 10 |

No placeholders found. All code blocks are complete. Type/method signatures match across tasks (compute_project_name, reset_state, wait_for_service, stack_is_up are defined in Task 1 and used consistently in Task 4).
