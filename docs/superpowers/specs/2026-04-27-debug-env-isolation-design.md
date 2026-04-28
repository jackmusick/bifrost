# Per-worktree debug stacks + bifrost-debug skill

**Status:** draft
**Issue:** #136
**Date:** 2026-04-27

## Problem

`./debug.sh` boots a single `bifrost-dev` Compose project with fixed host port bindings (3000, 5672, 15672, 5678, 9000, 9001). Two worktrees can't run dev stacks in parallel — the `bifrost-issues` skill encodes this as a hard rule ("Only one `./debug.sh` across all worktrees"). When working on multiple feature branches simultaneously, the user constantly stops/starts the stack to switch context.

A second, related bug: `BIFROST_DEFAULT_USER_EMAIL` / `BIFROST_DEFAULT_USER_PASSWORD` create a User row but no Organization. The user-existence check (`UserRepository.user_exists()`, `users.py:90-101`) requires `organization_id IS NOT NULL`, so `has_users()` returns `false` even with the seed user present. The setup wizard renders, the user types the seed email, registration fails with "user already exists", and the seeded account is left in a dead-end state — can't log in (no org → no roles), can't complete setup.

## Goals

1. `./debug.sh up` works in any worktree without colliding with other worktrees.
2. Two boot modes auto-detected by environment:
   - **Mode A (Netbird):** `NETBIRD_SETUP_KEY` is present → boot a Netbird sidecar; reach the stack at `http://<worktree-hostname>` via the Netbird mesh. No host port bindings.
   - **Mode B (port allocation):** no key → pick a free port, expose only the client. Reach at `http://localhost:<port>`.
3. Default seed user (`dev@gobifrost.com` / `password`) is fully provisioned: real Org, `is_registered=True`, `mfa_enabled=False`. Login works on first boot, no wizard.
4. New `bifrost-debug` skill teaches Claude to bring up a stack on demand, runs it as a session-backgrounded process, hands the URL to the user. Doesn't auto-tear-down on session end (containers persist past Claude's lifecycle).
5. Existing `bifrost-issues` and `bifrost-testing` skills updated to reference the new flow.

## Non-goals

- HTTPS / Netbird reverse-proxy configuration. One-time manual setup in Netbird Admin (peer = the worktree hostname, target port = 80) — the script doesn't manage this.
- Auto-provisioning a Netbird PAT or rotating setup keys.
- Any changes to `bifrost-demo` or its setup script.
- SessionEnd hook lifecycle automation. The user explicitly didn't want this — the skill teaches Claude the lifecycle pattern instead.
- Migrating `docker-compose.dev.yml` away — it stays as-is for anyone who wants the legacy fixed-port behavior.

## Architecture

### Per-worktree Compose project name

Reuse `compute_project_name()` from `scripts/lib/test_helpers.sh`. Hashes the worktree's absolute root path (sha256, first 8 chars) — the same mechanism `test.sh` uses for test-stack isolation. Two worktrees → two distinct Compose projects → distinct volumes, networks, container names.

```bash
COMPOSE_PROJECT_NAME="bifrost-debug-<hash>"
```

### Mode detection

`debug.sh` resolves `NETBIRD_SETUP_KEY` in this order:

1. Process env (already exported by the caller).
2. `~/.config/bifrost/debug.env` — per-user, lives outside the repo, gitignored by location. User creates this manually once.
3. Repo `.env.debug` (the checked-in defaults file). Won't have a real key — only present if the user wants to override per-worktree.

If a key is found → Mode A. Otherwise → Mode B.

### Mode A: Netbird sidecar

Pattern lifted directly from `~/bifrost-demo/docker-compose.yml:254-269`:

```yaml
services:
  client:
    cap_add: [NET_ADMIN, SYS_ADMIN]
    devices: [/dev/net/tun]
    # No "ports:" — reachable only via Netbird

  netbird:
    image: netbirdio/netbird:latest
    network_mode: "service:client"
    cap_add: [NET_ADMIN, SYS_ADMIN]
    devices: [/dev/net/tun]
    environment:
      NB_SETUP_KEY: ${NETBIRD_SETUP_KEY}
      NB_HOSTNAME: ${NETBIRD_HOSTNAME}
    profiles: [netbird]
```

`NETBIRD_HOSTNAME` is computed from the worktree directory name (sanitized: `[a-z0-9-]+`, lowercased, max 63 chars). Example: worktree at `.worktrees/136-debug-isolation` → hostname `bifrost-debug-136-debug-isolation`. Stable across reboots (same worktree → same hostname → same Netbird peer).

### Mode B: port allocation

`debug.sh` finds a free TCP port in the range 30000–39999 (avoids common service ports, gives plenty of headroom for parallel worktrees). The selected port is bound only to the `client` service; nothing else gets a host port binding.

Selection algorithm: try `30000 + (hash % 10000)` first (deterministic per worktree), fall back to a linear scan if taken. Stored in the script for the duration of the boot — printed in `status` output by reading the running container's published ports.

### Verb-style subcommands

```
./debug.sh up [--mode netbird|port]   # Boot. Default: auto-detect. Foreground (logs stream).
./debug.sh down                       # Tear down + remove volumes for THIS worktree.
./debug.sh status                     # Print: project name, mode, URL, login.
./debug.sh logs [service]             # docker compose logs -f, optionally filtered.
./debug.sh                            # = up (today's behavior preserved)
```

`up` stays foreground (matches today). The new `bifrost-debug` skill instructs Claude to run it via `Bash(run_in_background=true)` so the session-tied process lifecycle gives natural-ish cleanup. Human users running it interactively get logs streamed to their terminal, ctrl-C tears it down.

### Files

| File | Action |
|------|--------|
| `debug.sh` | Rewrite. Subcommand dispatcher + mode detection. ~200 lines. |
| `docker-compose.debug.yml` | New. Inherits dev compose, removes host ports, adds Netbird sidecar (profile `netbird`). |
| `.env.debug` | New, checked in. Defaults: dev user, MFA off, environment=development. |
| `~/.config/bifrost/debug.env` | Per-user, manual. Documented in skill. Holds `NETBIRD_SETUP_KEY`. |
| `api/src/main.py` | Modify `create_default_user()` to call `ensure_user_provisioned()`, set `is_registered=True`, `mfa_enabled=False`. |
| `.claude/skills/bifrost-debug/SKILL.md` | New skill. |
| `.claude/skills/bifrost-issues/SKILL.md` | Drop "only one debug.sh" warning (lines 17, 121-133). Replace with reference to new skill. |
| `.claude/skills/bifrost-testing/SKILL.md` | Where it implies `./debug.sh` for UI clicking, point at `bifrost-debug` skill. |

### Seed user fix detail

Current code (`api/src/main.py:218-254`):

```python
async def create_default_user() -> None:
    settings = get_settings()
    if not settings.default_user_email or not settings.default_user_password:
        return
    async with get_db_context() as db:
        user_repo = UserRepository(db)
        existing = await user_repo.get_by_email(settings.default_user_email)
        if existing:
            return
        hashed = get_password_hash(settings.default_user_password)
        await user_repo.create_user(
            email=settings.default_user_email,
            hashed_password=hashed,
            name="Admin",
            is_superuser=True,
        )
```

Problem: `create_user()` doesn't create or assign an Organization. The created User has `organization_id=None`. `has_users()` checks `organization_id IS NOT NULL`, so it returns false, the wizard appears, registration fails on duplicate email.

Fix: route through `ensure_user_provisioned()` (already used by `/auth/register`, `auth.py:1242`). It creates the user, the org, and the role assignments in one call. After provisioning, set the password, mark `is_registered=True`, and `mfa_enabled=False`.

```python
async def create_default_user() -> None:
    settings = get_settings()
    if not settings.default_user_email or not settings.default_user_password:
        return
    async with get_db_context() as db:
        user_repo = UserRepository(db)
        existing = await user_repo.get_by_email(settings.default_user_email)
        if existing:
            return  # already provisioned in a previous boot
        result = await ensure_user_provisioned(
            db=db,
            email=settings.default_user_email,
            name="Dev Admin",
        )
        user = result.user
        user.hashed_password = get_password_hash(settings.default_user_password)
        user.is_registered = True
        user.mfa_enabled = False
        await db.commit()
```

`BIFROST_MFA_ENABLED=false` in `.env.debug` belt-and-suspenders the global setting too, so even if a future user is created via the wizard in dev, MFA isn't required.

### Skill: bifrost-debug

Activates when user wants to click around the UI, test a feature, or otherwise needs the dev stack running. Triggers: "open the app", "test in the browser", "spin up debug", "/bifrost-debug", "let me click around".

Teaches Claude:

1. Run `./debug.sh status` first. If `Status: UP`, hand the user the URL and stop. Don't re-boot.
2. If down, run `./debug.sh up` via `Bash(run_in_background=true)`. Tail the background output via BashOutput until you see the line `Open: http://...`. Hand it to the user.
3. Login is `dev@gobifrost.com / password`. MFA is off. No wizard.
4. **Don't restart containers for code changes** (CLAUDE.md hot-reload rule).
5. **The stack outlives the session.** Closing this Claude session does NOT tear down the stack — the containers keep running. To tear down: `./debug.sh down`. (This is the explicit decision: simpler than session-lifecycle automation, and the user can run a second Claude session against an already-up stack.)
6. Two worktrees can run debug stacks in parallel. Each one gets its own URL. The skill prints both worktree's URLs if asked "where's debug running?" by listing all `bifrost-debug-*` Compose projects.

### bifrost-issues skill update

- Line 17 (Core Principles #6): delete "Only one `./debug.sh` across all worktrees…"
- Lines 121–133 (Step 4 "Dev stack coordination"): replace the entire section with: "If you need to click around the UI in this worktree, the `bifrost-debug` skill knows how to bring up an isolated stack. Most worktrees don't need it — the test stack (`./test.sh stack up`) is already per-worktree, and type generation can extract OpenAPI from the test-stack API container."

### bifrost-testing skill update

Minor: any reference suggesting "use `./debug.sh` for UI verification" gets replaced with a reference to `bifrost-debug`.

## Acceptance criteria

(Direct from the issue.)

1. Two worktrees can run `./debug.sh up` simultaneously without port/container conflicts.
2. Mode A: stack URL reachable via the worktree-derived Netbird peer hostname; login as `dev@gobifrost.com / password` works without setup wizard or MFA prompt.
3. Mode B: same login, URL is `http://localhost:<auto-port>`, browser-reachable.
4. `bifrost-issues` skill no longer warns about cross-worktree debug.sh conflicts.
5. `./debug.sh status` prints a structured snapshot (project, mode, URL, login).

## Open questions

None at this point — design is approved in conversation. Implementation flow is set.

## Risks / things to watch

- **Netbird DNS propagation:** new peer hostname may take a few seconds to register. The script should print the URL when the stack is up regardless; user retries the URL if it doesn't resolve immediately. Not worth blocking on.
- **Port-allocation collision:** `30000 + (hash % 10000)` could deterministically land on a port already used by something else (rare). Linear-scan fallback handles this.
- **Existing dev stack:** users currently running `docker compose -f docker-compose.dev.yml up` keep working — that path is untouched. Migration is opt-in: switch to `./debug.sh up` when ready.
- **`is_registered` default:** verify the User model defaults `is_registered=False` so existing seeded-user behavior remains unaffected if users haven't migrated. (Confirmed in conversation; field is set explicitly in the new `create_default_user` path.)

## Out-of-scope but follow-up

The user asked during this session to also update their ccstatusline to show the running debug URL when one exists. That's a separate, additive change that depends on `./debug.sh status` working — captured in TaskList, scoped after the core implementation lands.
