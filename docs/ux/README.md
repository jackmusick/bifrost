# Agent-management UX capture scripts

Seed + capture scripts backing the Phase 7 / 7b UX rebuild loop in
`docs/plans/2026-04-21-agent-management-m1.md`.

## Quick usage

Dev stack must be up. Replace the network name with your worktree's project
(e.g. `bifrost-test-86cbedfe_default`):

```bash
NETWORK=bifrost-test-<project>_default

# 1. Seed realistic fixtures (5 agents, ~45 runs, 1 flag conversation, 1 prompt
#    history). Idempotent — clears everything first via hard-delete.
docker run --rm \
  --network $NETWORK \
  -v $PWD/docs/ux/seed-realistic.mjs:/work/seed.mjs \
  -w /work \
  -e API_URL=http://api:8000 -e PG_HOST=postgres \
  mcr.microsoft.com/playwright:v1.59.1-jammy \
  sh -c 'npm init -y >/dev/null && npm i --silent jsonwebtoken pg && node seed.mjs'

# 2. Capture screenshots of every agent surface.
docker run --rm \
  --network $NETWORK \
  -v $PWD/docs/ux/grab-ours.mjs:/work/grab.mjs \
  -v /tmp/ux-out:/tmp/ux-out \
  -w /work \
  -e CLIENT_URL=http://client -e API_URL=http://api:8000 \
  mcr.microsoft.com/playwright:v1.59.1-jammy \
  sh -c 'npm init -y >/dev/null && npm i --silent playwright jsonwebtoken && node grab.mjs'

# 3. Copy to your Sync folder for user review.
cp /tmp/ux-out/*.png ~/Sync/Screenshots/agent-ux-compare/
```

## Scripts

- `seed-realistic.mjs` — wipes `agents` + related tables, POSTs 5 seed agents,
  then SQL-inserts 10–14 runs per active agent across the last 7 days (with
  mixed status, ~2–3 flagged per agent, populated asked/did/metadata/confidence),
  one flag conversation (user → assistant → proposal → dryrun), and one prompt
  history row.
- `grab-ours.mjs` — looks up the primary agent ("Ticket Triage") and one
  flagged run, then captures `fleet`, `new-agent`, `agent-detail-{overview,runs,settings}`,
  `review-flipbook`, `tune-chat`, and `run-detail` into `/tmp/ux-out/ours-*.png`.

## Token conventions (for anyone re-writing these)

- JWT test secret: `test-secret-key-for-e2e-testing-must-be-32-chars`
- localStorage key: `bifrost_access_token`
- Postgres creds in the test stack: user `bifrost` / password `bifrost_test` /
  database `bifrost_test`
- Agent-run metadata is `dict[str, str]` per `api/src/models/contracts/agent_runs.py` —
  stringify numbers before inserting.
