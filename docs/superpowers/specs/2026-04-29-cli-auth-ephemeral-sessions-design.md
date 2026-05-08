# CLI Authentication: Ephemeral Sessions and Multi-Instance Support

**Status:** Draft
**Date:** 2026-04-29
**Author:** Jack Musick (with Claude)

## Problem

The Bifrost CLI authenticates against one instance at a time. Credentials live in a single global file (`~/.bifrost/credentials.json`) keyed by nothing — re-running `bifrost login` against a different URL clobbers the prior token. This makes two everyday workflows painful:

1. **Working with prod and a debug stack at the same time.** The user has a real prod token in `~/.bifrost/credentials.json` right now. Spinning up a local `./debug.sh` stack and pointing the CLI at it overwrites the prod token.
2. **Running multiple parallel debug stacks.** `./debug.sh` already isolates per worktree (separate Compose project, separate port). But there's no way to direct CLI commands in one folder at one stack and CLI commands in another folder at another stack — they all read the single global credential record.

The longer-term framing the user gave: a client asks for a POC. The user wants to drop into a fresh folder, spin up an isolated debug stack, and have Claude take it from there — without manual login choreography between every CLI call.

## Goals

- One CLI binary can target multiple Bifrost instances on the same machine simultaneously, switched by `cd`.
- A debug stack can be brought up and used by Claude without the interactive browser device-code dance.
- The current prod token survives the migration; no user action required to keep it working.
- Token storage for persistent sessions moves off plaintext-on-disk to OS-native credential storage where available, with a clean fallback for headless Linux.

## Non-Goals

- Named profiles (`--profile prod`, `--profile staging`). URLs are unique enough to key off.
- Remote-instance management (deploying instances, listing them). Out of scope; this is auth/addressing only.
- Replacing the device-code login flow. It stays as the human-facing prod login path.
- Changing how `debug.sh` itself spins up stacks. The skill that wraps it changes; the script doesn't.
- A `bifrost poc init` scaffolding command. The user explicitly deferred this — "definitely a [manual flow] for now, dev flow improvements come later."

## Design Overview

Two clearly-separated authentication paths:

| Path | Triggered by | Tokens stored where | Use case |
|------|-------------|---------------------|----------|
| **Persistent** | `bifrost login` (browser device-code) | OS keychain, keyed by `api_url`; JSON fallback if no keychain backend | Prod, long-lived staging |
| **Ephemeral** | `bifrost login --email X --password Y --ephemeral` | Nowhere — printed to stdout, captured into `.env` by the caller | Debug stacks, isolated POC work |

Addressing is by `BIFROST_API_URL` from the CWD `.env` (already auto-loaded by `python-dotenv`, which is already a CLI dependency). No `.bifrost/instance` file, no profile concept, no parent-directory walk-up beyond what dotenv already does.

The CLI's token resolution order at every call site that needs a token:

1. **`BIFROST_ACCESS_TOKEN` / `BIFROST_REFRESH_TOKEN`** env vars (ephemeral path).
2. **Keychain entry for the current `BIFROST_API_URL`** (persistent path).
3. **Legacy `~/.bifrost/credentials.json`** entry — if URL matches, lazy-migrated into keychain on read, then JSON entry removed.

If none yields a token, the existing "not logged in" error fires.

## Components

### 1. Credentials module rewrite (`api/bifrost/credentials.py`)

Today this module is a thin wrapper around a single-record JSON file. It needs to become a small abstraction over multiple backends:

- **`Credentials`** dataclass: `api_url`, `access_token`, `refresh_token`, `expires_at`. Same shape as today.
- **Backend protocol** with three implementations:
  - `KeyringBackend` — uses `keyring` library. Service name `"bifrost"`, username = `api_url`, secret = JSON-encoded `Credentials` payload.
  - `JsonBackend` — `~/.bifrost/credentials.json`, but the file is now a `dict[str, Credentials]` keyed by `api_url`. Same file path as today; the format change is what the migration handles.
  - `EnvBackend` — read-only, returns a `Credentials` object built from `BIFROST_API_URL` + `BIFROST_ACCESS_TOKEN` + `BIFROST_REFRESH_TOKEN` if all are set; otherwise returns `None`. Never writes.
- **Public functions** (preserving current names where possible):
  - `get_credentials(api_url: str | None = None) -> Credentials | None` — resolves through the chain. If `api_url` is `None`, falls back to the env var or, if no env var, the *first* entry in the persistent store (back-compat for users who only have one).
  - `save_credentials(creds: Credentials) -> None` — writes to keychain if available, else JSON. Never writes to env.
  - `clear_credentials(api_url: str) -> None` — removes from whichever persistent backend has it.
  - `list_credentials() -> list[str]` — returns the URLs that have stored credentials. Used by the new `bifrost auth status` and `bifrost logout` UX.

Backend selection is done once per process at module import time:

```python
def _select_persistent_backend() -> Backend:
    try:
        import keyring
        backend = keyring.get_keyring()
        # `fail.Keyring` is what keyring returns when no backend works
        if backend.__class__.__name__ == "Keyring" and "fail" in type(backend).__module__:
            return JsonBackend()
        # Probe with a no-op read to surface NoKeyringError / SecretServiceError now
        keyring.get_password("bifrost", "__probe__")
        return KeyringBackend()
    except Exception:
        return JsonBackend()
```

The probe matters: on a Linux box where `keyring` imports fine but D-Bus / Secret Service is missing, the failure happens on first real use, not at `get_keyring()`. We want to fail-and-fall-back at startup, not on the first `bifrost watch` of the day.

### 2. Migration: legacy single-record JSON → multi-record store

When the credentials module loads and finds the **old single-record format** (top-level keys are `api_url`/`access_token`/etc., not a dict-of-URLs), it migrates lazily on the next read:

1. Parse the legacy record.
2. Write it to the selected persistent backend keyed by its own `api_url`.
3. Rewrite `~/.bifrost/credentials.json` to the new dict format. If keychain was the destination, the JSON file becomes `{}` (kept as a marker that migration happened so we don't try again on every CLI invocation; safer than deleting because permission errors are recoverable, vs. trying to recreate a deleted-then-re-needed file).
4. On the *next* read against the same URL, the chain finds it in the new location.

This is one-shot, transparent, and the prod token never goes missing — at worst we read it from JSON, write it to keychain, and the next call picks up from keychain.

### 3. New `bifrost login` flags

Today: `bifrost login [--url URL] [--no-browser]`. Adds:

- **`--email EMAIL --password PASSWORD --ephemeral`** — three flags, all required together. POSTs to `/auth/login` with `{email, password}`. Behavior:
  - On success (MFA disabled, or trusted device): prints tokens to stdout in a parseable shape (see "Output format" below). Does NOT save anywhere.
  - On `mfa_required` / `mfa_setup_required` response: errors out with a clear message: *"This instance has MFA enabled. Ephemeral password login only works for instances with `BIFROST_MFA_ENABLED=false`. Use `bifrost login` (no flags) for the browser flow."* Exit code 2.
  - Prints a warning every invocation, on stderr, before doing anything:
    > ⚠️  Password-grant login is for ephemeral, isolated development stacks only. Do not run a Bifrost instance with MFA disabled in production.
- **No `--ephemeral` without `--email/--password`.** No `--email/--password` without `--ephemeral`. Either you're using the browser flow or you're explicitly opting into the ephemeral one.
- **URL resolution for `--ephemeral`:** `--url` flag wins, else `BIFROST_API_URL` env var, else error. We do *not* fall through to the existing `BIFROST_DEV_URL` default of `http://localhost:8000` — that default is for the human convenience case, and silently logging into the wrong stack with hardcoded debug creds is exactly the kind of foot-gun the explicit error prevents.

**Output format for `--ephemeral`:**

Stdout, one variable per line, suitable for `eval` / `>> .env`:

```
BIFROST_API_URL=http://localhost:38421
BIFROST_ACCESS_TOKEN=eyJhbGciOiJI...
BIFROST_REFRESH_TOKEN=eyJhbGciOiJI...
```

This is what the calling skill captures and writes to `.env`. The caller decides whether to use it as `eval "$(...)"` (export to current shell), append to a `.env`, or pipe somewhere else. The CLI's job ends at "print three lines."

### 4. Token-refresh behavior in the ephemeral path

Persistent tokens get refreshed when they're near expiry — `refresh_tokens()` in `client.py:78` already handles this and re-saves through `save_credentials()`. For the ephemeral path:

- The CLI process reads `BIFROST_ACCESS_TOKEN` once at startup. If that token is expired, the CLI uses `BIFROST_REFRESH_TOKEN` to mint a new pair from `/auth/refresh` — but it has nowhere to *persist* the rotated tokens (the env vars in the parent shell are immutable from a child process).
- So: in-process the new tokens are used for the rest of that CLI invocation. The next CLI invocation will start over from the original env-var pair. If those have aged out past the refresh-token's lifetime too, the user re-runs `bifrost login --ephemeral …` to mint fresh ones.
- This is acceptable because "ephemeral" really means short-lived: the debug stack itself goes away on `./debug.sh down`.

### 5. `bifrost-debug` skill update

The skill currently brings up the stack and hands the URL to the user for browser login. After this change, when the skill brings up a stack it also:

1. Reads the URL from `./debug.sh status`.
2. Calls `bifrost login --email dev@gobifrost.com --password password --ephemeral --url <URL>` and captures stdout.
3. Writes (or appends to) `.env` in the worktree root with the three captured `BIFROST_*` lines, and notes them in `.gitignore` if not already.
4. Tells the user: *"Stack up at <URL>. CLI in this folder is now connected. Tokens are ephemeral; no browser login needed."*

On `./debug.sh down`, the skill should `rm` the three `BIFROST_*` lines from `.env` (or the whole file if it created it). Implementation note: simplest is to fence them with marker comments (`# BIFROST CLI ephemeral session`) and remove the fenced block. No other file should be touched.

### 6. Cross-platform keychain test plan

The spec is acceptance-gated on these tests passing on the listed platforms before merge:

| Platform | What to verify | How |
|----------|---------------|-----|
| **Linux desktop (xfce, dev's machine)** | `keyring` resolves to `SecretService`, persistent save+read+clear works, and `bifrost login` against a real instance round-trips. | Manual on dev's machine. `python -c "import keyring; print(keyring.get_keyring())"` should print `SecretService`. |
| **Linux headless** | Backend selection falls through to `JsonBackend` cleanly; no traceback on import; persistent save+read+clear works against the JSON file. | Unit test that monkeypatches `keyring.get_keyring()` to return `fail.Keyring`. Plus a manual run inside a Docker container (`docker run --rm -it python:3.11 ...`) to verify the real-world headless path. |
| **macOS (dev's secondary machine)** | `keyring` resolves to `macOS.Keyring`, persistent save+read+clear works, no permission prompts beyond the OS's first-use approval dialog. | Manual on dev's Mac. |
| **Windows** | `keyring` resolves to `Windows.WinVaultKeyring`, persistent save+read+clear works. | Deferred to first Windows user; we don't have a CI runner. Code path is exercised by `keyring`'s own test suite, so we trust the library here. |

The unit-test layer covers backend selection, migration logic, env-var precedence, and the multi-record JSON format. Cross-platform verification is per-platform manual smoke tests of the full save→read→clear cycle.

## Data Flow

### Persistent login (today's flow, post-migration)

```
$ cd ~/work/prod-monitoring     # .env: BIFROST_API_URL=https://prod.gobifrost.com
$ bifrost login                  # browser device-code flow
  → writes to keychain: ("bifrost", "https://prod.gobifrost.com") = {tokens...}
$ bifrost forms list             # reads keychain entry for $BIFROST_API_URL
```

### Ephemeral session (new flow)

```
# Skill brings up debug stack via ./debug.sh
$ cd ~/poc-acme                  # fresh folder
$ ./debug.sh up                  # boot stack, get URL http://localhost:38421
$ bifrost login --email dev@gobifrost.com --password password --ephemeral \
    --url http://localhost:38421
⚠️  Password-grant login is for ephemeral, isolated development stacks only.
   Do not run a Bifrost instance with MFA disabled in production.
BIFROST_API_URL=http://localhost:38421
BIFROST_ACCESS_TOKEN=eyJ...
BIFROST_REFRESH_TOKEN=eyJ...

# Skill captures and writes:
$ cat .env
# BIFROST CLI ephemeral session
BIFROST_API_URL=http://localhost:38421
BIFROST_ACCESS_TOKEN=eyJ...
BIFROST_REFRESH_TOKEN=eyJ...

$ bifrost forms list             # reads from env vars (precedence #1), keychain ignored
```

### Both at once

```
$ cd ~/work/prod-monitoring && bifrost forms list
# resolves: env vars not set → keychain entry for prod URL → token

$ cd ~/poc-acme && bifrost forms list
# resolves: env vars set (ephemeral) → use those, never touch keychain
```

No collision. The `.env` in the POC folder shadows whatever's in the keychain whenever you're inside that folder.

## Security Considerations

- **MFA-off instances are the only ones the ephemeral path works against.** The CLI refuses MFA-required responses by design. This is the correct enforcement point — the API will reject the password grant if MFA is required and there's no MFA token, and the CLI surfaces that as a clear error rather than trying to handle it.
- **The warning prints every invocation, not once.** Surfacing it on every `--ephemeral` login is mildly annoying by design — MFA-off in prod is the failure mode this whole feature could enable, so making the warning hard to forget is worth the noise.
- **Tokens in `.env` are no worse than tokens in `~/.bifrost/credentials.json`.** Both are mode-0600 files in the user's home tree. The `.env` file is gitignored by the skill. The honest position is that anyone with read access to the user's home directory can read either; the keychain path improves on this for the persistent token, the ephemeral path does not because env-var inheritance through `BIFROST_ACCESS_TOKEN` is the whole point of how it works.
- **Keychain entries persist across reboots and survive uninstalling the CLI.** That's the OS-native behavior. `bifrost logout` removes the relevant entry; `bifrost logout --all` removes all entries with service name `"bifrost"`.

## Testing

### Unit tests (`api/tests/unit/test_credentials.py`)

- New file. Cover:
  - Backend selection: keychain available → `KeyringBackend`; `fail.Keyring` → `JsonBackend`; import error → `JsonBackend`.
  - Migration: legacy single-record JSON migrates to selected backend on first read; the file is rewritten to the new format; subsequent reads come from the new location.
  - `EnvBackend` precedence: env vars set → returned; env vars partial → not returned (treated as not present); env vars absent → falls through to persistent backend.
  - Multi-record JSON: write two URLs, read each independently, clear one without affecting the other.
  - `list_credentials()` returns all stored URLs across the active persistent backend.

### CLI tests (`api/tests/unit/test_cli_login.py`)

- New file. Cover:
  - `bifrost login --email X --password Y --ephemeral` against a stub `/auth/login` that returns tokens directly → stdout matches the three-line format, nothing written to disk.
  - Same flags but stub returns `mfa_required: true` → exit code 2, error message on stderr, nothing written.
  - Warning prints to stderr on every `--ephemeral` invocation regardless of success.
  - `--ephemeral` without `--email`/`--password` → usage error.
  - `--email` without `--ephemeral` → usage error (so we don't accidentally enable password-grant for the persistent path).

### E2E test (`api/tests/e2e/platform/test_cli_ephemeral_login.py`)

- New file. One test: real test stack (MFA off), real `/auth/login`, real `bifrost login --email --password --ephemeral`, parse stdout, set the resulting env vars in a subprocess, run `bifrost api GET /api/integrations`, verify it succeeds. This validates the full round-trip including the API actually accepting the issued token.

### Cross-platform smoke tests (manual, before merge)

Per the table in §6: dev runs the keychain save/read/clear cycle on Linux desktop and macOS. Headless Linux is covered by the unit-test fail-keyring branch plus a Docker smoke run. Windows is deferred.

## Migration & Rollback

- **Migration:** Lazy, on first credentials read after upgrade. No data loss possible — the legacy record is read, written to the new location, *then* the file is rewritten. If anything fails between read and write, the original file is untouched.
- **Rollback:** If we need to back out, the JSON-fallback path means everything still works without the new code. A user who downgrades the CLI after migrating to keychain would lose access to the keychain-stored token (because old code only reads JSON), but the JSON file still exists in its new dict-format. Old code would read the dict and not find the expected top-level keys, treat it as "not logged in," and prompt for `bifrost login` — annoying but not destructive. Acceptable.

## Open Questions

None remaining as of writing. All key decisions confirmed in the brainstorm:

- Storage for persistent: keychain with JSON fallback. ✓
- Storage for ephemeral: nowhere (in-process / env vars only). ✓
- Addressing: `.env` in CWD via existing dotenv. ✓
- Scope: this project is auth/addressing only; no `bifrost poc init`, no remote-instance management. ✓
