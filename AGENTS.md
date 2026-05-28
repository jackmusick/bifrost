# Bifrost Agent Guide (MTG)

Tool-neutral guidance for AI coding agents in `MTG-Thomas/bifrost`. This fork tracks [upstream](https://github.com/jackmusick/bifrost); `CLAUDE.md` remains the detailed **platform** playbook for Persona B work.

**New teammates and workspace-only work:** start with MTG onboarding, not this file alone.

- [Develop at MTG (Windows)](https://github.com/MTG-Thomas/bifrost-ops/blob/main/docs/develop-at-mtg-windows.md) — Persona A (default) and Persona B overview (`MTG-Thomas/bifrost-ops`)
- [Bifrost workspace agent guide](https://github.com/MTG-Thomas/bifrost-workspace/blob/main/AGENTS.md) — automation authoring against `https://dev.bifrost.midtowntg.com` (`MTG-Thomas/bifrost-workspace`)

## Personas

| Persona | Repo | Runtime | Verification |
| --- | --- | --- | --- |
| **A — Workspace author** | `bifrost-workspace` | `https://dev.bifrost.midtowntg.com` | Scoped sync, dev execution, PR CI — **no local Docker** |
| **B — Platform engineer** | `bifrost` (this repo) | Shared Linux dev VM on `pve-t340` or CI | `./test.sh` on the VM; see [Proxmox shared dev roadmap](https://github.com/MTG-Thomas/bifrost-ops/blob/main/docs/proxmox-shared-dev-roadmap.md) |

Assume **Persona A** unless the task clearly changes `api/`, `client/`, migrations, or platform MCP/CLI surfaces.

## Read First (Persona B)

- Work from the current checkout state. Do not revert user or other-agent changes unless explicitly asked.
- Use `rg` for search, inspect nearby code before editing, and follow existing patterns.
- Keep changes narrow and reviewable. Avoid drive-by refactors, dead code, commented-out code, and unrequested fallback paths.
- Treat `.bifrost/` as export-only. Mutate platform entities through the CLI or MCP tools — not by hand-editing manifest YAML.
- New MCP tools must be thin HTTP wrappers around REST endpoints. Do not add direct ORM/repository access in MCP tools.

## Development Environment (Persona B only)

Platform work runs in **Docker on a Linux host** (shared `pve-t340` dev guest or CI). Do **not** ask Windows teammates to install Docker Desktop for routine work.

On the Linux dev host:

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

Do not start host-side FastAPI, Vite, pytest, Postgres, Redis, RabbitMQ, or MinIO **on Windows** for platform verification.

## Local Coordination (optional)

Multiple Codex threads on one machine may use the local coordinator (warning-only, not in git):

```powershell
# If installed on the operator machine:
& "$env:USERPROFILE\.codex\bin\codex-agent-coordinator.ps1" claim `
  --owner "<thread-or-role>" --repo "<repo-path>" --scope "<path>" --note "<short note>"
```

Release claims after meaningful work. Skip entirely if the operator does not use Codex.

## Code Boundaries

- Backend API is FastAPI/Python. Keep HTTP handlers thin and put business logic in the shared/service layer.
- Request and response contracts use Pydantic models in `api/shared/models.py`.
- Frontend API types are generated from OpenAPI. Do not hand-write endpoint response types.
- If API contracts change, run type generation from `client/` while the dev stack is running.
- Manifest, CLI, and MCP surfaces must stay in sync when DTOs change. Run the DTO parity test in `CLAUDE.md`.

## Testing And Verification (Persona B)

- Primary bar: `./test.sh` on the **shared Linux dev environment** or **GitHub Actions** on `MTG-Thomas/bifrost`.
- Do not treat a Windows laptop without the stack as the platform verification environment.

Match verification to the change (see `CLAUDE.md` for detail):

- Backend logic: `api/tests/unit/`
- Endpoint, queue, DB, or workflow behavior: `api/tests/e2e/`
- React components: sibling `*.test.tsx`
- Functional frontend modules under `client/src/lib/**` or `client/src/services/**`: sibling `*.test.ts`
- User-facing UI flows: Playwright in `client/e2e/`

Before calling significant platform work complete, run the relevant checks from `CLAUDE.md` and report anything skipped with the reason.

## Security And Sensitive Paths

Use extra care around auth, execution, multi-tenancy filters, migrations, secrets, manifest round-trips, and audit logging. Call out sensitive-path changes in summaries and PR descriptions.

Do not expose secret values in chat, logs, test fixtures, screenshots, or committed files.

## Useful References

- `CLAUDE.md` — upstream-style platform commands, manifest rules, verification checklist
- `CONTRIBUTING.md` — human-facing PR expectations
- [Develop at MTG (Windows)](https://github.com/MTG-Thomas/bifrost-ops/blob/main/docs/develop-at-mtg-windows.md) — team onboarding (Windows-first)
- [Proxmox shared dev roadmap](https://github.com/MTG-Thomas/bifrost-ops/blob/main/docs/proxmox-shared-dev-roadmap.md) — shared lab + Entra direction
- `.claude/skills/` — upstream maintainer workflows (release, issues); **ignore for MTG day-to-day**
- `api/tests/README.md` — test structure and fixture notes
