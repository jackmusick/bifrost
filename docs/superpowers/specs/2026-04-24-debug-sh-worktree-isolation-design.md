# `./debug.sh` worktree isolation

## Background

`./test.sh` already runs cleanly from multiple git worktrees in parallel: each worktree gets its own Compose project name (`bifrost-test-<hash>`), its own named volumes, its own log directory, and no host-port collisions. `./debug.sh` does not. Today it hardcodes the project name `bifrost-dev`, binds fixed host ports (3000, 5432, 6379, 9000, 9001, 5672, 15672, 6432, 5678), and uses fixed `container_name:` values. A second worktree running `./debug.sh` conflicts on all three axes.

This design brings `./debug.sh` to parity with `./test.sh` for isolation, and solves access — the dev box is an SSH target, so "bind to localhost" is not useful. Access goes through Netbird, which the dev box is already on.

## Goals

- Run `./debug.sh` from any git worktree without collisions against other worktrees' dev stacks.
- Access each worktree's dev stack from any Netbird peer (laptop, phone) via a distinct, predictable URL.
- One prompt per new machine for a Netbird setup key. Zero prompts per new worktree.
- No passkey / MFA setup friction in worktree-scoped dev stacks.
- Production compose behavior (`docker-compose.yml` alone) stays identical.

## Non-goals

- Passkey / WebAuthn flow in dev worktrees. MFA is off by default in dev; flip `BIFROST_MFA_ENABLED=true` in `.env` locally if you need to exercise the enrollment flow.
- TLS on the Netbird endpoint. HTTP over wireguard is fine; Netbird's own reverse proxy can terminate TLS later if needed.
- Changes to `docker-compose.yml` (base / production compose).
- Changes to `./test.sh` or `docker-compose.test.yml`.
- A "classic mode" `./debug.sh` flag that keeps the current fixed-port behavior. Worktree mode is the one mode; the main clone is just one more worktree.

## Architecture

Each worktree running `./debug.sh` produces an isolated stack identified by a hash of its absolute repo root path:

- Compose project name: `bifrost-dev-<8char-hash>` (same `compute_project_name` helper `./test.sh` already uses)
- Named volumes scoped to that project (Compose handles this automatically)
- No host port bindings from the dev stack at all
- A Netbird sidecar container joins the mesh with hostname `bifrost-dev-<hash>`, producing FQDN `bifrost-dev-<hash>.netbird.cloud`
- The `client` container shares the Netbird container's network namespace (`network_mode: service:netbird`), so its `:80` surfaces on the peer's wireguard IP

From any Netbird peer: `http://bifrost-dev-<hash>.netbird.cloud` reaches that worktree's client, Vite proxies `/api/*` to the in-stack API, everything works the same as today.

### Why `network_mode: service:netbird`

`netbird` and `client` become one network namespace — same interfaces, same IPs, same localhost — while remaining separate containers (separate processes, separate filesystems). Netbird's `wt0` wireguard interface carries the peer IP; the client binds `:80` inside that namespace so the browser can reach it at `<peer-ip>:80` without an extra hop.

Tradeoff: the client loses its own docker-network identity — it can't simultaneously be on the `bifrost-dev` docker network and addressable as `client:80`. Verified against the dev stack: nothing calls `client` by service name at runtime (only `docker-compose.test.yml`'s Playwright and a `docs/ux/` script do, both scoped to the test stack). Safe for dev.

### Machine-scoped secrets file

`~/.bifrost/env` is a new, user-created file holding values that belong to *the machine*, not *the worktree*:

```
NETBIRD_SETUP_KEY=<reusable setup key from Netbird admin UI>
BIFROST_DEFAULT_USER_EMAIL=<admin email for dev stacks>
BIFROST_DEFAULT_USER_PASSWORD=<admin password for dev stacks>
```

`setup.sh` reads it first, prompts for anything missing, writes newly-entered values back. Worktree-scoped `.env` gets the merged result plus freshly-generated per-worktree random secrets (`POSTGRES_PASSWORD`, `RABBITMQ_PASSWORD`, etc. — these stay per-worktree so stacks don't accidentally share data). Net effect: one prompt per new machine, zero per new worktree, moving to a new machine is one prompt.

The pattern mirrors `~/.ssh/` — a machine-scoped secret directory that every project on that machine can reference.

### MFA-off in dev

`docker-compose.dev.yml` sets `BIFROST_MFA_ENABLED: "${BIFROST_MFA_ENABLED:-false}"` on the `api` service. `BIFROST_MFA_ENABLED` is removed from `setup.sh` output and `.env.example` so the knob is invisible in the normal setup flow — the dev compose override is the source of truth.

`api/src/routers/auth.py:373` currently hard-requires MFA for password login regardless of the `settings.mfa_enabled` flag. It needs a new branch: if `settings.environment == "development"` and not `settings.mfa_enabled`, skip the MFA check and go straight to `_generate_login_tokens(user, db, response)`. Production paths are unaffected — non-development environments ignore the bypass entirely, even if someone flips `BIFROST_MFA_ENABLED=false` on a production host.

Default admin seeding (`BIFROST_DEFAULT_USER_EMAIL` / `BIFROST_DEFAULT_USER_PASSWORD` at `api/src/main.py:133`) already works; `setup.sh` populates these so the setup wizard is skipped on first boot.

## Files touched

| File | Change |
|------|--------|
| `debug.sh` | Derive `COMPOSE_PROJECT_NAME` via `compute_project_name`; gate on `.env` via `setup.sh` if missing; fail fast on missing `NETBIRD_SETUP_KEY`; compute peer FQDN and export as `BIFROST_PUBLIC_URL` / `BIFROST_WEBAUTHN_ORIGIN` / `BIFROST_WEBAUTHN_RP_ID`. |
| `setup.sh` | Read `~/.bifrost/env` if present; prompt only for missing fields (`NETBIRD_SETUP_KEY`, default admin creds); write newly-entered values back to `~/.bifrost/env`; emit merged result plus per-worktree secrets into `.env`. Remove `BIFROST_MFA_ENABLED` write. |
| `docker-compose.dev.yml` | Drop `name: bifrost-dev`; add `netbird` sidecar service; `network_mode: service:netbird` on `client`; `container_name: ""` overrides on all services that hardcode one in the base; `ports: []` overrides on all services that publish in the base; drop debug port 5678 block; `BIFROST_MFA_ENABLED: "${BIFROST_MFA_ENABLED:-false}"` on `api`. |
| `.env.example` | Drop `BIFROST_MFA_ENABLED`; document `NETBIRD_SETUP_KEY` and the `~/.bifrost/env` convention. |
| `api/src/routers/auth.py` | At line 373, add dev-mode MFA bypass branch (`settings.environment == "development" and not settings.mfa_enabled`). |
| `~/.bifrost/env` (new, user-managed) | Machine-scoped secrets. Created by `setup.sh`. Not in git, not in repo. |

## `debug.sh` flow

```
1. source scripts/lib/test_helpers.sh
2. COMPOSE_PROJECT_NAME=$(compute_project_name .)
3. [ ! -f .env ] && ./setup.sh
4. source .env
5. [ -z "$NETBIRD_SETUP_KEY" ] && die "Run ./setup.sh — NETBIRD_SETUP_KEY missing."
6. export BIFROST_PUBLIC_URL="http://bifrost-dev-<hash>.netbird.cloud"
7. export BIFROST_WEBAUTHN_ORIGIN="$BIFROST_PUBLIC_URL"
8. export BIFROST_WEBAUTHN_RP_ID="bifrost-dev-<hash>.netbird.cloud"
9. docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build
```

## `setup.sh` flow

```
1. [ -f ~/.bifrost/env ] && source ~/.bifrost/env
2. For each machine-scoped field (NETBIRD_SETUP_KEY, BIFROST_DEFAULT_USER_EMAIL, BIFROST_DEFAULT_USER_PASSWORD):
     if not set, prompt; append to ~/.bifrost/env
3. Generate per-worktree secrets (POSTGRES_PASSWORD, RABBITMQ_PASSWORD, MINIO_ROOT_PASSWORD, BIFROST_SECRET_KEY)
4. Copy .env.example → .env
5. Substitute both machine-scoped and worktree-scoped values into .env
6. Done
```

Default-admin creds default to a dev-safe pair (e.g. `admin@bifrost.local` / `bifrost-dev`) if the user just hits enter.

## Netbird sidecar service

```yaml
netbird:
  image: netbirdio/netbird:latest
  hostname: bifrost-dev-<hash>     # injected via env var from debug.sh
  cap_add: [NET_ADMIN, SYS_ADMIN]
  environment:
    NB_SETUP_KEY: ${NETBIRD_SETUP_KEY:?NETBIRD_SETUP_KEY is required}
    NB_HOSTNAME: bifrost-dev-<hash>
  volumes:
    - netbird_data:/etc/netbird
  restart: unless-stopped
```

`client` service gains `network_mode: "service:netbird"`. `client`'s own `ports:` becomes `[]` (nothing to publish; it's reachable via the peer IP). The `volumes:` and build config on `client` stay unchanged.

Peer expires on `docker compose down -v` (volume removal triggers fresh registration on next boot with a new peer record). Reusing the setup key is supported — Netbird setup keys are multi-use by design.

## Access model

- `http://bifrost-dev-<hash>.netbird.cloud` → client:80 → Vite → /api/* proxied to API
- Resolves from any Netbird peer (laptop, phone, other dev boxes)
- No SSH port forwarding, no /etc/hosts edits, no wildcard DNS on a separate domain
- Each worktree has its own URL; multiple worktrees are fully parallel-accessible

## Failure modes

| Failure | Handling |
|---------|----------|
| `.env` missing | `debug.sh` runs `./setup.sh` automatically. |
| `~/.bifrost/env` missing | `setup.sh` prompts for each machine-scoped value, creates the file. |
| `NETBIRD_SETUP_KEY` empty or absent after setup | `debug.sh` fails fast with "Run ./setup.sh" remediation text. |
| Two worktrees started simultaneously | Distinct project names, distinct volumes, distinct Netbird peers. No collision. |
| Netbird daemon on dev box is down | Netbird container join fails; `docker compose up` logs the error. User restarts netbird on host or in container. |
| Setup key revoked in Netbird admin | Join fails, same surface as above. User rotates the key, updates `~/.bifrost/env`. |

## Migration from the current `bifrost-dev` stack

The existing stack on the main clone uses project name `bifrost-dev` and hardcoded container names. After this change, `./debug.sh` on that same clone computes `bifrost-dev-<hash>` and spins up a fresh parallel stack. The old stack keeps running in the background until explicitly retired. Old named volumes (`bifrost-dev_postgres_data`, etc.) do not follow — the new stack starts with a fresh DB.

**One-shot cleanup before first new run:**

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml -p bifrost-dev down -v
```

This retires the old project and its volumes. Any data you want to keep from it should be exported first via `bifrost export` or equivalent. The new stack will run the setup wizard (or seed the default admin via the new `BIFROST_DEFAULT_USER_*` flow) on first boot.

## Testing

- Manual smoke: `./debug.sh` in main clone, verify Netbird peer registers, `https://bifrost-dev-<hash>.netbird.cloud` reachable from a second Netbird peer.
- Manual smoke: `git worktree add ../bifrost-feat feat-branch && cd ../bifrost-feat && ./debug.sh` — verify second peer registers with distinct hash, both clones run concurrently without collision.
- Unit test: `setup.sh` idempotency — running twice with an existing `~/.bifrost/env` produces the same output, prompts for nothing.
- Unit test on the MFA bypass branch in `auth.py`: with `environment=development` and `mfa_enabled=false`, login issues tokens directly; in any other environment, the bypass does not fire.
