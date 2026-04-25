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

# wait_for_service should time out promptly against a non-existent service
WAIT_MAX_ATTEMPTS=1 result=$(wait_for_service docker-compose.test.yml no-such-service true 2>&1 || true)
[[ "$result" == *"not ready after 1 attempts"* ]] || { echo "FAIL: wait_for_service timeout message, got: $result"; exit 1; }

# compute_project_name should yield different hashes for different paths
hash_a=$(compute_project_name "$(git rev-parse --show-toplevel)")
# Use a known-different git dir if available; fall back to an init'd temp repo.
tmp_dir=$(mktemp -d)
(cd "$tmp_dir" && git init -q)
hash_b=$(compute_project_name "$tmp_dir")
rm -rf "$tmp_dir"
[[ "$hash_a" != "$hash_b" ]] || { echo "FAIL: same hash for different worktrees: $hash_a"; exit 1; }

echo "PASS: all"
