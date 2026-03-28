# Bifrost CI Failure Patterns

## Container Layout Drift

Symptoms:

- file not found under `/integrations/...`
- import succeeds locally but fails in CI

Typical cause:

- test runner mounts only `api/`, `shared/`, or selected repo paths
- unit test assumed host checkout visibility

Typical fix:

- make path discovery explicit
- mount required repo-root directories
- avoid fixed parent-depth root calculations

## `test.sh` vs Raw `pytest`

Symptoms:

- test passes with raw host pytest or ad hoc imports
- CI fails in Docker-backed test flow

Typical fix:

- align with `./test.sh`
- respect the repo's two-phase test execution

## False “CI Noise” Diagnosis

Symptoms:

- generic `exit code 1` annotation
- no one checks the actual job log

Typical fix:

- fetch the full log
- identify exact test/module failure before editing
