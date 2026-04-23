# Agent Management M1 — UAT Handoff

**Branch:** `worktree-agent-management-m1`
**Plan:** `docs/plans/2026-04-21-agent-management-m1.md`
**Commits on branch vs `main`:** 40

## What was built (T1–T43)

### Backend

- 5 alembic migrations:
  - `20260421a_run_summaries_metadata_confidence.py` — `asked`, `did`, `confidence`, `metadata`, `summary_status`, `summary_error` on `agent_runs`
  - `20260421b_run_verdicts_and_history.py` — `verdict`, `verdict_at`, `verdict_by`, and `agent_run_verdict_history` table
  - `20260421c_flag_conversations.py` — `agent_run_flag_conversations` table
  - `20260421d_agent_prompt_history.py` — `agent_prompt_history` table
  - `20260421e_run_tsvector_search.py` — `search_tsv` generated column + GIN index on `agent_runs`
- Verdict endpoints (POST/DELETE) with audit history (`agent_run_verdict_history`)
- Pause semantics — inactive agent webhook calls return HTTP 200 + `{"status": "paused", ...}`
- Runs search + verdict + metadata filters (`?search=`, `?verdict=`, `?metadata_key=/value=`)
- LLM config: optional `summarization_model` and `tuning_model` overrides in `LlmConfig`
- Worker queues: `agent-summarization`, `agent-tuning-chat` wired into RabbitMQ + scheduler
- Summarization service (post-run, populates `asked`, `did`, `confidence`, `metadata`)
- Per-agent + fleet stats endpoints (`GET /api/agents/:id/stats`, `GET /api/agents/fleet-stats`)
- Per-flag tuning conversation endpoints (`POST /api/agent-runs/:id/flag-conversation/message`)
- Dry-run endpoint (`POST /api/agent-runs/:id/dry-run`)
- Consolidated tuning session (propose / dry-run / apply) via `POST /api/agents/:id/tuning/*`
- Admin regenerate-summary endpoint (`POST /api/agent-runs/:id/regenerate-summary`, admin-only)
- Budget field visibility gating — admin-only writes for `max_iterations`, `max_token_budget`,
  `llm_max_tokens` (enforced in router + hidden in Settings tab for non-admins)

### Frontend

- New pages under `/agents/*`:
  - `/agents` — `FleetPage` (replaces legacy `Agents.tsx`)
  - `/agents/new` — create mode (Settings-only active tab)
  - `/agents/:id` — `AgentDetailPage` with Overview / Runs / Settings tabs
  - `/agents/:id/review` — `AgentReviewPage` flipbook review queue for flagged runs
  - `/agents/:id/tune` — `AgentTunePage` consolidated tuning chat
  - `/agents/:agentId/runs/:runId` — `AgentRunDetailPage` with sidebar metadata + regen summary
- Components (all under `client/src/components/agents/`):
  - `ChatComposer`, `VerdictToggle`, `RunReviewPanel`, `RunCard`, `RunReviewSheet`,
    `FlagConversation`, `QueueBanner`, `NeedsReviewCard`, `FleetStats`, `AgentGridCard`,
    `AgentTableRow`
- Service hooks (`client/src/services/agents.ts`, `agent-runs.ts`, `agent-stats.ts`,
  `agent-tuning.ts`) with `$api.useQuery()` / `$api.useMutation()` wrappers
- 5 Playwright specs (see below)

### Tests

- ~25 new backend unit tests (summarization, verdict history, model selection, pause semantics,
  filter parsing, etc.)
- ~10 new backend e2e tests (verdict round-trip, regenerate-summary auth/race, tuning session,
  budget visibility, fleet-stats shape)
- ~80 new frontend vitest tests covering service hooks, components, and page-level behavior
- 5 new Playwright specs under `client/e2e/`:
  - `agents-fleet.admin.spec.ts` — fleet page happy path (search, grid/table toggle)
  - `agents-detail-runs.admin.spec.ts` — agent detail tabs + create mode
  - `agents-review-verdict.admin.spec.ts` — review flipbook
  - `agents-tuning.admin.spec.ts` — tuning page
  - `agents-owner-budget-hidden.user.spec.ts` — non-admin cannot see budget fields

## What was deferred (Plan 2 / Phase 6)

- T45: Judge agent (auto-flag suspect runs)
- T46: Streaming tuning responses (SSE)
- T47: Agent-scoped chat UI
- T48: Prompt versioning UI (viewer + diff + revert on top of `agent_prompt_history`)
- T49: Cross-agent flagged runs view
- T50: Confidence-based review queue ordering
- T51: Metadata schema discovery (auto-complete on the search bar's `metadata_key=` helper)
- T52: Chat-as-runs consolidation
- T53: Cost caps and rate limits on tuning

## Known limitations / TODOs in code

- `client/src/pages/agents/FleetPage.tsx:229, 375` — per-card `useAgentStats` is N+1 for the
  fleet grid / table. Marked `TODO(plan-2)` for a denormalized fleet-stats batch endpoint.
- `client/src/pages/agents/AgentTunePage.tsx:19, 450` — the diff view renders the full proposed
  prompt; a real diff library (e.g. `diff2html`) is left for follow-up. Current API carries
  `proposed_prompt` as a flat string.

## Manual UAT items

- [ ] Create an agent via `/agents/new`, verify save → navigation to `/agents/:id`
- [ ] Edit an agent via `/agents/:id` → Settings tab, verify save
- [ ] Pause an agent (set `is_active=false` in Settings) — verify webhook calls return 200 +
      `{"status":"paused"}` (covered by `test_agent_webhook_paused.py` but worth an end-to-end
      click through)
- [ ] Set verdict on a completed run (👍 or 👎) — verify a row lands in
      `agent_run_verdict_history`
- [ ] Send a flag-conversation message on a 👎 run — verify assistant reply renders (requires a
      working LLM config on the environment)
- [ ] Open a run's tuning page, propose change → dry-run → apply — verify `agent.system_prompt`
      updated and a new `agent_prompt_history` row appears
- [ ] As non-admin org user: verify Settings tab does NOT show budget fields (max_iterations,
      max_token_budget, llm_max_tokens)
- [ ] As non-admin org user: verify `PUT /api/agents/:id` with budget fields returns 403
- [ ] Regenerate a failed summary via `AgentRunDetailPage` as admin — verify summary status
      moves off `failed` and the worker produces a new summary

## Test stack notes

- Worktree: `/home/jack/GitHub/bifrost/.claude/worktrees/agent-management-m1`
- Test stack project: `bifrost-test-86cbedfe`
- JUnit XML at `/tmp/bifrost-bifrost-test-86cbedfe/test-results.xml`
- All tests pass except known pre-existing unrelated failures:
  - `tests/e2e/api/test_executions.py::TestCodeHotReload::test_package_available_after_installation`
    (package install isolation — pre-existing, documented in the plan)
  - `tests/unit/core/test_module_cache.py::TestModuleCacheSync::test_get_module_index_sync_empty`
    (Redis state lingering — pre-existing)
- Playwright flakes unrelated to agent work:
  - `client/e2e/executions.admin.spec.ts` — 2 tests expect seeded executions

## Quality gates

- Backend `pyright`: 28 errors, all in pre-existing files (`bifrost/tui/*`, `openai_client.py`,
  `conftest.py`) — not introduced by this branch.
- Backend `ruff check`: 9 errors, all in pre-existing files (`bifrost/__init__.py`,
  `app_bundler/__init__.py`, `test_agent_connection_pressure.py`, `test_template_process.py`,
  `test_agent_executor_session.py`) — not introduced by this branch.
- Frontend `npm run tsc`: clean.
- Frontend `npm run lint`: clean.
- Frontend vitest: **613/613 passing**.
- Backend unit + e2e: **1042/1043 passing** (the one failure is the pre-existing package-install
  isolation test above).
- Playwright: **63/66 passing**, 2 pre-existing exec-history flakes + 1 retried-clean flake,
  not in agent scope.
