# Bifrost Agent Guide

This file is the repo-level, tool-agnostic guidance layer for AI coding agents working in `MTG-Thomas/bifrost`.

Use this file for stable repo rules. Use the repo-local skill packs in [`.codex/skills/`](.codex/skills) or the Claude-specific materials in [`.claude/`](.claude) for deeper workflow instructions.

## Scope

- This guide applies to the `bifrost` repo.
- It does not describe separate workspace/content repos except where this repo depends on them.

## Core Rules

- Treat Docker as the normal development environment.
- Prefer `./debug.sh` for local stack startup.
- Prefer `./test.sh` for backend validation instead of raw host `pytest`.
- If Docker-backed validation is unavailable, run narrower syntax/import checks and say the validation is partial.
- Keep local git as the source of truth for branches, rebases, and code review.

## Repo Model

- Prefer authored source under `features/`, `modules/`, `shared/`, `helpers/`, `workflows/`, `apps/`, `api/`, and `client/`.
- Treat `.bifrost/*.yaml` as generated or transitional workspace metadata, not the default source of truth.
- Reading `.bifrost/*.yaml` for discovery is acceptable.
- Editing `.bifrost/*.yaml` should be tactical and minimal when the current fork workflow still requires it.

## Workflow Split

### Userland changes

Usually includes:

- `features/`
- `modules/`
- `shared/`
- `helpers/`
- `workflows/`
- `apps/`
- unavoidable fork-local `.bifrost/` metadata changes

Preferred path:

- local git for source control
- direct Bifrost CLI sync flows such as `bifrost watch`, `bifrost push`, and `bifrost sync`

### Platform/runtime changes

Usually includes:

- `api/`
- `client/`
- `docker-compose*.yml`
- build/deployment assets

These require rebuild or rollout behavior, not workspace sync alone.

## Testing Rules

- Unit tests belong in `api/tests/unit/` and should isolate business logic with controlled inputs and mocks.
- E2E tests belong in `api/tests/e2e/` and should be used only when real services or cross-process behavior are required.
- Do not move a test to E2E just to hide brittle path, import, or mount assumptions.
- CI failures should be diagnosed from the actual GitHub Actions logs, not only from generic annotations.

## CLI Boundaries

- `bifrost api` is for the Bifrost platform API, not vendor APIs.
- Do not assume interactive CLI commands can be safely run by an agent non-interactively.
- If the current task depends on the CLI and credentials, verify that setup first.

## Skills

Repo-local Codex skills live in [`.codex/skills/`](.codex/skills).

Current pack:

- `bifrost-setup`
- `bifrost-build`
- `bifrost-integration-authoring`
- `bifrost-ci-debugging`
- `bifrost-app-authoring`
- `bifrost-test-authoring`

Use them when the task clearly matches their scope. Keep this file short; do not duplicate their detailed instructions here.

## Related Files

- [`.codex/skills/`](.codex/skills)
- [`.claude/skills/`](.claude/skills)
- [`CODEX_SESSION_NOTES.md`](CODEX_SESSION_NOTES.md)
- [`docs/plans/2026-03-27-manifest-transition-guidance.md`](docs/plans/2026-03-27-manifest-transition-guidance.md)
- [`docs/plans/2026-03-27-post-github-integration-workflow.md`](docs/plans/2026-03-27-post-github-integration-workflow.md)
