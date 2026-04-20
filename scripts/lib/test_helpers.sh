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
