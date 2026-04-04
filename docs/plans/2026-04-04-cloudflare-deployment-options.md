# Cloudflare Deployment Options for Bifrost

Date: 2026-04-04
Status: Draft proposal for upstream deployment documentation

## Goals

1. Provide a low-risk **Hybrid in 30 days** path teams can adopt without major rewrites.
2. Provide a clear **Cloudflare-native in 90 days** target for teams that want lower ops overhead and global edge capabilities.
3. Explicitly call out where Bifrost platform behavior is preserved vs adapted for Cloudflare primitives.

---

## Baseline: Current Bifrost Runtime Model

Bifrost currently runs as independent roles:

- `client` (React frontend)
- `api` (FastAPI)
- `worker` (RabbitMQ consumers for workflow execution, package installation, and agent runs)
- `scheduler` (APScheduler singleton)
- state systems: PostgreSQL, Redis, RabbitMQ, S3-compatible storage

This proposal preserves that separation and remaps components incrementally.

---

## Option A: Hybrid in 30 Days

### Target Architecture Diagram

```text
                       ┌──────────────────────────────────┐
Users / Browser ─────▶ │ Cloudflare Edge                 │
                       │ - DNS / TLS / WAF / CDN         │
                       │ - (Optional) Worker for routing │
                       └──────────────┬───────────────────┘
                                      │
                                      ▼
                         ┌─────────────────────────┐
                         │ Existing Bifrost API    │
                         │ (VM/K8s/Compose)        │
                         └───────┬─────────────────┘
                                 │
          ┌──────────────────────┼──────────────────────┐
          ▼                      ▼                      ▼
  ┌───────────────┐      ┌───────────────┐      ┌──────────────────┐
  │ PostgreSQL    │      │ Redis         │      │ RabbitMQ         │
  │ (managed/self)│      │ (managed/self)│      │ (managed/self)   │
  └───────────────┘      └───────────────┘      └──────────────────┘
                                                      │
                                                      ▼
                                               ┌───────────────┐
                                               │ Bifrost worker│
                                               │ (existing)    │
                                               └───────────────┘

                    ┌──────────────────────────────────────────┐
                    │ Cloudflare R2 (S3-compatible workspace) │
                    └──────────────────────────────────────────┘
```

### What changes vs current platform

- Keep API, worker, scheduler runtime model unchanged.
- Add Cloudflare as front-door and optionally route static/UI through it.
- Move object storage target from MinIO/S3 endpoint to R2 endpoint.
- Keep RabbitMQ semantics intact in this phase.

### 30-day backlog (epics)

#### Epic H1 — Edge entrypoint and networking (Week 1)

- Configure Cloudflare DNS, TLS, WAF policies.
- Enable websocket pass-through validation for `/ws` routes.
- Add origin health monitoring and fallback origin host.

**Deliverables**
- Edge runbook
- Traffic cutover checklist
- Rollback DNS/TLS playbook

#### Epic H2 — R2 workspace storage (Week 1-2)

- Create R2 bucket(s): `bifrost-workspace`, `bifrost-artifacts` (optional split).
- Configure BIFROST S3 vars to R2 endpoint + keys.
- Validate read/write + presigned URL behavior.

**Deliverables**
- IaC/templates for bucket + credentials
- Data migration script (if existing object data)
- Integrity verification report

#### Epic H3 — Observability and SLO guardrails (Week 2)

- Add synthetic checks for login, workflow execution, websocket update.
- Define SLOs: API p95, worker queue latency, execution success rate.
- Set alert routing + on-call ownership boundaries.

**Deliverables**
- Dashboards
- Alert policy JSON/YAML
- Incident severity matrix

#### Epic H4 — Progressive traffic cutover (Week 3)

- Canary 5% / 25% / 50% / 100% through Cloudflare.
- Measure websocket stability and auth/session behavior.
- Lock in caching and bypass rules for auth/API routes.

**Deliverables**
- Cutover evidence report
- Known-issues document

#### Epic H5 — Upstream deployment profile docs (Week 4)

- Publish `deployment profile: cloudflare-hybrid` docs.
- Provide env var templates and operational caveats.
- Include "not changed yet" list (RabbitMQ, scheduler, worker runtime).

**Deliverables**
- Upstream doc PR
- Quickstart checklist

### Risks and mitigations (Hybrid)

- **Risk:** websocket regressions via proxy config.
  - **Mitigation:** explicit websocket route tests and no-cache/bypass rules for upgrade paths.
- **Risk:** presigned URL host/path mismatch with R2 public endpoint.
  - **Mitigation:** e2e upload/download tests in staging with real browser origin.
- **Risk:** security drift during accelerated edge rollout.
  - **Mitigation:** least-privilege API tokens, short-lived credentials, WAF baselines.

### Rollback plan (Hybrid)

- Keep current origin deployment untouched for full 30 days.
- Rollback switch sequence:
  1. Cloudflare DNS record back to prior origin path (or disable proxy for affected host).
  2. Restore prior object storage env vars (if R2 introduces blocker).
  3. Re-run smoke tests (auth, workflow enqueue/execute, websocket live updates).
- RTO target: < 30 minutes for edge-only rollback.

---

## Option B: Cloudflare-native in 90 Days

### Target Architecture Diagram

```text
                               ┌─────────────────────────────┐
Users / Browser ─────────────▶ │ Cloudflare Worker API Edge │
                               │ - Auth/API gateway          │
                               │ - WebSocket handling        │
                               └──────────────┬──────────────┘
                                              │
             ┌────────────────────────────────┼────────────────────────────────┐
             ▼                                ▼                                ▼
   ┌──────────────────┐             ┌──────────────────────┐          ┌──────────────────┐
   │ Durable Objects  │             │ Cloudflare Queues    │          │ Cloudflare R2    │
   │ (session/streams │             │ (job envelopes)      │          │ (workspace/files)│
   │ coordination)    │             └───────────┬──────────┘          └──────────────────┘
   └──────────────────┘                         │
                                                ▼
                                      ┌──────────────────────┐
                                      │ Queue Consumers      │
                                      │ (Workers/Workflows)  │
                                      └───────────┬──────────┘
                                                  │
                                                  ▼
                                         ┌───────────────────┐
                                         │ Workflows engine  │
                                         │ (durable orches.) │
                                         └─────────┬─────────┘
                                                   │
                      ┌────────────────────────────┼────────────────────────────┐
                      ▼                            ▼                            ▼
               ┌───────────────┐           ┌───────────────┐           ┌────────────────┐
               │ Postgres      │           │ Redis*        │           │ External APIs  │
               │ via Hyperdrive│           │ (optional)    │           │ / OAuth targets│
               └───────────────┘           └───────────────┘           └────────────────┘

* Redis remains optional transitional state for compatibility features.
```

### Platform adjustments required for Cloudflare-native

This is the key section for upstream clarity.

#### 1) Queue/broker model adjustment

**Current:** RabbitMQ consumers with queue semantics tied to existing worker process model.  
**Target:** Cloudflare Queues envelopes + consumer handlers.

**Required platform changes**
- Introduce queue abstraction interface (`enqueue_job`, `ack`, `retry`, `dlq`).
- Implement adapters:
  - `RabbitMQAdapter` (existing behavior)
  - `CloudflareQueuesAdapter` (new behavior)
- Add explicit idempotency keys and replay-safe job handlers.

#### 2) Scheduler model adjustment

**Current:** APScheduler singleton container.  
**Target:** Cron Triggers + Workflows scheduling/orchestration.

**Required platform changes**
- Extract scheduler task definitions into declarative schedule manifest.
- Add scheduler backend adapters:
  - `ApschedulerBackend` (existing)
  - `CloudflareCronBackend` (new)
- Ensure schedule execution lock semantics are preserved without singleton process assumptions.

#### 3) Worker execution adjustment

**Current:** long-running Python worker service with thread/process execution for jobs.  
**Target:** split workloads by execution class.

**Required platform changes**
- Tag jobs as `edge_io_bound`, `durable_orchestration`, `heavy_python`.
- Route:
  - `edge_io_bound` -> Worker consumer directly
  - `durable_orchestration` -> Workflows
  - `heavy_python` -> compatibility runner (containerized) until rewritten
- Add standardized execution contract (input/output envelope + status transitions).

#### 4) Realtime transport adjustment

**Current:** app-level websocket router and redis/pubsub-backed update patterns.  
**Target:** Worker websocket endpoints + Durable Object coordination where shared fanout needed.

**Required platform changes**
- Introduce `RealtimeGateway` abstraction.
- Implement `WebSocketGateway` and `DurableObjectGateway` paths.
- Preserve existing event payload contracts to minimize frontend churn.

#### 5) Storage endpoint adjustment

**Current:** S3-compatible settings; MinIO/S3 usage pattern.  
**Target:** R2 as primary object store.

**Required platform changes**
- None at domain level if S3 API contract remains stable.
- Add endpoint-aware URL generation tests for browser uploads/downloads.

### 90-day backlog (epics)

#### Epic N1 — Runtime abstraction layer (Days 1-20)

- Add adapters/interfaces for queue, scheduler, realtime gateway.
- Ensure existing RabbitMQ/APScheduler path remains default.
- Add feature flags to switch per capability.

**Output**
- No behavior change in default mode
- New extension points documented

#### Epic N2 — Cloudflare queues + cron implementation (Days 21-40)

- Implement `CloudflareQueuesAdapter`.
- Implement `CloudflareCronBackend`.
- Add retry/backoff/dead-letter policy equivalents.

**Output**
- End-to-end job enqueue/consume in staging
- Backward-compatible queue payload schema

#### Epic N3 — Durable orchestration + realtime (Days 41-60)

- Move selected workflows to Workflows orchestration path.
- Add Durable Object-backed channel coordinator for high-fanout streams.
- Verify UI contracts remain unchanged.

**Output**
- Pilot set of production-safe workflows on native path
- Realtime reliability benchmarks

#### Epic N4 — Heavy Python compatibility runner (Days 41-70, parallel)

- Preserve container-based runner for CPU-heavy or library-constrained jobs.
- Add router that dispatches heavy workloads away from edge-native path.
- Publish workload classification guide.

**Output**
- No regression for complex workflow workloads
- Clear migration criteria for moving jobs native

#### Epic N5 — Upstream profile + operator docs (Days 71-90)

- Publish `deployment profile: cloudflare-native` docs.
- Provide compatibility matrix by feature and workload class.
- Include rollback and partial-adoption guidance.

**Output**
- Upstream-ready architecture option docs
- Operational runbooks and SLOs

### Risks and mitigations (Cloudflare-native)

- **Risk:** semantic mismatch between RabbitMQ behavior and Cloudflare Queues delivery model.
  - **Mitigation:** explicit idempotency layer + deterministic retry policy + DLQ instrumentation.
- **Risk:** job duration/resource constraints for edge execution.
  - **Mitigation:** workload classification + compatibility runner maintained during migration.
- **Risk:** realtime behavior drift during websocket/DO transition.
  - **Mitigation:** freeze event schema; contract tests for client-consumed realtime events.
- **Risk:** operational complexity during dual-runtime window.
  - **Mitigation:** single control-plane config with per-feature flags and staged cutovers.

### Rollback plan (Cloudflare-native)

Rollback must be capability-scoped, not all-or-nothing.

- **Queue rollback:** flip feature flag from `CloudflareQueuesAdapter` -> `RabbitMQAdapter`.
- **Scheduler rollback:** switch `CloudflareCronBackend` -> `ApschedulerBackend`.
- **Realtime rollback:** route gateway from DO/Worker path -> existing websocket path.
- **Execution rollback:** force all `heavy_python` and optionally all jobs to compatibility runner.

**Operational policy**
- Keep RabbitMQ + APScheduler infrastructure available until at least 2 full release cycles after native cutover.
- Keep data contracts versioned to allow replay in either backend.
- RTO target for single-capability rollback: < 60 minutes.

---

## Upstream Documentation Package (Recommended)

To provide this back upstream clearly, ship the following docs together:

1. `cloudflare-hybrid.md` (30-day path)
2. `cloudflare-native.md` (90-day target)
3. `cloudflare-compatibility-matrix.md` (feature-by-feature status)
4. `cloudflare-migration-runbook.md` (step-by-step with rollback)

Minimum compatibility matrix columns:

- Feature
- Current backend
- Cloudflare backend
- Behavior parity (full/partial)
- Known caveats
- Rollback switch

---

## Suggested Success Criteria

### Hybrid in 30 days

- 100% traffic served through Cloudflare edge without functional regressions.
- R2 used for workspace storage in production-like environment.
- No increase in failed workflow executions or websocket disconnect incidents.

### Cloudflare-native in 90 days

- >= 60% of eligible workflows handled by Cloudflare-native queue/orchestration path.
- 100% of critical features have documented parity/exception status.
- Capability-scoped rollback tested in staging and once in production game day.
