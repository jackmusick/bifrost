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
