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
# Strips all whitespace (including trailing newline from psql -t -A) so the
# equality check below works. If psql itself errors (postgres not running,
# auth failure), let the error propagate — don't silently rebuild.
EXISTING_HASH=$(psql_postgres -c \
    "SELECT COALESCE(shobj_description(oid, 'pg_database'), '') FROM pg_database WHERE datname = 'bifrost_test_template';" \
    | tr -d '[:space:]')

if [ "$EXISTING_HASH" = "$MIGRATIONS_HASH" ]; then
    echo "template up to date (hash: $MIGRATIONS_HASH)"
    exit 0
fi

echo "Rebuilding template (old hash: ${EXISTING_HASH:-none}, new hash: $MIGRATIONS_HASH)..."

# Release the template flag (otherwise DROP fails), kick out any connections,
# then drop.
psql_postgres -c \
    "UPDATE pg_database SET datistemplate = false WHERE datname = 'bifrost_test_template';" > /dev/null 2>&1 || true
psql_postgres -c \
    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = 'bifrost_test_template' AND pid <> pg_backend_pid();" > /dev/null 2>&1 || true
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
    -e BIFROST_DATABASE_URL_SYNC="postgresql://bifrost:bifrost_test@postgres:5432/bifrost_test_template" \
    -e BIFROST_DATABASE_URL="postgresql+asyncpg://bifrost:bifrost_test@postgres:5432/bifrost_test_template" \
    --no-deps init alembic upgrade head > /dev/null

# Mark as template and stamp the hash.
psql_postgres -c "ALTER DATABASE bifrost_test_template IS_TEMPLATE true;" > /dev/null
psql_postgres -c "COMMENT ON DATABASE bifrost_test_template IS '${MIGRATIONS_HASH}';" > /dev/null

# Create a fresh bifrost_test from the template so tests can run immediately.
psql_postgres -c "CREATE DATABASE bifrost_test TEMPLATE bifrost_test_template;" > /dev/null

echo "template rebuilt (hash: $MIGRATIONS_HASH)"
