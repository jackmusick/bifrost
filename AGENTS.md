# Bifrost Agent Guide

This is the tool-neutral guidance for AI coding agents working in this repo. `CLAUDE.md` remains the detailed Bifrost playbook, but agents that support `AGENTS.md` should start here.

## Read First

- Work from the current checkout state. Do not revert user or other-agent changes unless explicitly asked.
- Use `rg` for search, inspect nearby code before editing, and follow existing patterns.
- Keep changes narrow and reviewable. Avoid drive-by refactors, dead code, commented-out code, and unrequested fallback paths.
- Treat `.bifrost/` as export-only. Mutate platform entities through the CLI or MCP surfaces described in `docs/llm.txt`.
- New MCP tools must be thin HTTP wrappers around REST endpoints. Do not add direct ORM/repository access in MCP tools.

## Local Coordination

This machine may have several Codex threads working in the same repos. Before meaningful edits, claim your scope with:

Windows/PowerShell on this workstation:

```powershell
C:\Users\ThomasBray\.codex\bin\codex-agent-coordinator.ps1 claim --owner "<thread-or-role>" --repo "<repo-path>" --scope "<path-or-task>" --note "<short note>"
```

Portable command shape for other environments:

```bash
~/.codex/bin/codex-agent-coordinator claim --owner "<thread-or-role>" --repo "<repo-path>" --scope "<path-or-task>" --note "<short note>"
```

Check `status` and `conflicts` when working near active agents. Release the claim after meaningful work. The coordinator is warning-only local state under `%USERPROFILE%\.codex`; never add coordination files to the repo unless asked.

## Development Environment

Everything runs in Docker. Do not start host-side FastAPI, Vite, pytest, Postgres, Redis, RabbitMQ, or MinIO processes for normal development.

Use the repo scripts:

```bash
./debug.sh             # Boot the per-worktree dev stack
./debug.sh status      # Show URL, login, and mode
./debug.sh logs api    # Follow one service log
./test.sh stack up     # Boot the per-worktree test stack
./test.sh              # Backend unit tests
./test.sh all          # Backend unit + e2e
./test.sh client unit  # Vitest
./test.sh client e2e   # Playwright
```

Hot reload is expected. Do not restart containers for ordinary code changes. Use targeted restarts only when dependencies, migrations, or generated API types require them.

## Code Boundaries

- Backend API is FastAPI/Python. Keep HTTP handlers thin and put business logic in the shared/service layer used by existing code.
- Request and response contracts should use Pydantic models.
- Frontend API types are generated from OpenAPI. Do not hand-write endpoint response types.
- If API contracts change, run type generation from `client/` while the dev stack is running.
- Manifest, CLI, and MCP surfaces must stay in sync when DTOs change. Run the DTO parity test called out in `CLAUDE.md`.

## Testing And Verification

Use `./test.sh`; do not run raw host `pytest` for repo tests. The script manages the Dockerized test dependencies and writes result artifacts.

Match verification to the change:

- Backend logic: focused unit tests under `api/tests/unit/`.
- Endpoint, queue, DB, or workflow behavior: e2e tests under `api/tests/e2e/`.
- React components: sibling `*.test.tsx`.
- Functional frontend modules under `client/src/lib/**` or `client/src/services/**`: sibling `*.test.ts`.
- User-facing UI flows: Playwright happy-path coverage in `client/e2e/`.

Before calling significant work complete, run the relevant checks from `CLAUDE.md` and report anything skipped with the reason.

## Security And Sensitive Paths

Use extra care around auth, execution, multi-tenancy filters, migrations, secrets, manifest round-trips, and audit logging. Call out sensitive-path changes in summaries and PR descriptions.

Do not expose secret values in chat, logs, test fixtures, screenshots, or committed files. Prefer live shape/status validation over copying credentials.

## Useful References

- `CLAUDE.md` - detailed repo rules, commands, and Bifrost-specific invariants.
- `CONTRIBUTING.md` - human-facing PR and contribution expectations.
- `docs/llm.txt` - CLI and MCP command reference for LLMs.
- `.claude/skills/` - Claude-specific skills that document Bifrost setup, testing, release, security, and build workflows.
- `api/tests/README.md` - test structure and fixture notes.
