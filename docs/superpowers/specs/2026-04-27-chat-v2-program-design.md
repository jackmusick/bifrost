# Chat V2 — Program-Level Design

**Status:** Draft (program-level scope; sub-project specs forthcoming)
**Author:** Jack Musick + Claude
**Date:** 2026-04-27

## Goal

Bring the Bifrost chat experience to feature parity with Claude.ai, ChatGPT, and Copilot, so an org can credibly use Bifrost as their primary LLM chat interface. Differentiation is org-managed cost/model controls and first-class custom tooling owned by the org and the community — not a hassle of MCP-server installs, but built-in capabilities authored against the Bifrost SDK.

This is a program, not a single feature. It decomposes into five sub-projects, each of which gets its own design spec and implementation plan.

## Non-goals

- Replacing Claude.ai for end-users outside the org's MSP context (we're not a public consumer chat product).
- Voice input/output in v1 (deferred).
- Untrusted community-uploaded skill execution before the Code Execution sub-project lands (skills v1 only loads org-authored or workflow-backed skills).
- Windows-host PowerShell execution in v1 (Linux-hosted `pwsh-core` is the long-term path).
- Replacing the existing MCP server. MCP stays as the escape hatch for external integrations; the chat product is built on first-party tools, mirroring how Claude.ai itself ships.

## Sub-projects

The five sub-projects, in implementation order:

| # | Sub-project | Depends on | One-liner |
|---|---|---|---|
| 1 | Chat UX overhaul | — | Branching, edit/regenerate, projects, search, attachments, lossless compaction, instruction management. The visible foundation. |
| 2 | Code Execution | (1) | Sandboxed code execution via `sandbox-runtime` shelled from existing workers. Multi-runtime (Python, Node, eventually pwsh). Required by Skills and Artifacts to be meaningfully useful — most non-trivial skills shell out to language runtimes (`npm`, `pandoc`, `soffice`, `pdftoppm`) and most artifact binary formats need subprocess execution. |
| 3 | Skills | (1), (2) | Adopt the public Agent Skills spec verbatim. Org/role/personal/global scoping (mirroring forms/agents). Skills with scripts execute via the sandbox built in (2). |
| 4 | Artifacts | (1), (2) | Structured artifact content blocks, panel UI, edit-in-place. Text/markdown/HTML/SVG render in a sandboxed iframe. Binary formats (docx/pdf/xlsx) generated via skill scripts running in the sandbox. |
| 5 | Web Search | (1) | First-party search tool wired into the agent loop (Brave/Tavily/Exa or pluggable). Lives outside the sandbox; returns data the model can use directly. |

(3) and (4) — Skills and Artifacts — are paired in spec sequencing because they share UI surface and content-block plumbing, but each gets its own design doc. Both **require** (2) Code Execution to ship in their full form, which is why the original ordering (Skills before Code Execution) was inverted: Anthropic's own document-creation skills shell out to `npm`, `pandoc`, `soffice`, `pdftoppm`, and friends, and any non-trivial skill is similar. A "markdown-only knowledge skill" v1 without code execution is possible but yields a much weaker product.

## Key architectural decisions (program-wide)

These decisions cut across multiple sub-projects and are settled here so individual specs don't relitigate them.

### 1. First-party tools, not MCP-as-primary

The chat UI does NOT become an MCP client as its primary architecture. Claude.ai's headline features (artifacts, code execution, web search, skills) are first-party tools defined inside the product, called via the regular tool-use API. MCP is an extension surface for external integrations. We follow that pattern. Existing Bifrost MCP server keeps its current role unchanged.

### 2. Adopt Agent Skills spec verbatim

Skills v1 implements `anthropics/skills/spec/agent-skills-spec.md` as published. `SKILL.md` with YAML frontmatter (`name`, `description` required) plus markdown body, plus optional bundled scripts/resources. No format invention. Adoption by Microsoft, OpenAI, Atlassian, Figma, Cursor, GitHub, Notion, Stripe, Canva means cross-vendor portability for free. Loader is small (an afternoon's work); the work is in the registry, UI, and integration with the agent context loader.

The existing `bifrost-sdk-skills` docs (Feb 2026) describe a different concept (SDK/CLI scaffolding). That namespace collision is acknowledged; the Skills sub-project will rename or disambiguate during its design phase.

### 3. Code Execution = sandbox-as-child-process inside existing workers

Anthropic's `anthropic-experimental/sandbox-runtime` (Apache-2.0, bubblewrap-based, used by Claude Code) is just an executable. Workers shell out to it for sandbox executions:

```
simple_worker.py (existing, trusted, SDK-aware)
    └─ subprocess: sandbox-runtime --policy <p> python /work/main.py  ← untrusted, isolated
```

The fork remains the unit of measurement. Diagnostics, heartbeats, cancellation, queue tracking, RabbitMQ dispatch — all unchanged. New `execution_runtime` field distinguishes `workflow` (today's behavior) from `sandbox-python`, `sandbox-node`, eventually `sandbox-pwsh`.

This design replaces an earlier consideration of two separate pools with a shared `ExecutionRuntime` interface. The interface is unnecessary because the fork-as-unit model already gives us the unification we wanted.

**Privilege model:** the worker pod itself stays unprivileged — no `CAP_SYS_ADMIN`, no `privileged: true`, no root capabilities. But `bwrap`'s syscalls (`unshare(CLONE_NEWUSER)`, mount operations) are blocked by Docker's and K8s's default seccomp profile (`RuntimeDefault`). So the worker pod **does** require a relaxed seccomp profile — either `Unconfined` (simplest, broadest relaxation) or a custom profile (`bifrost-sandbox-seccomp.json`) that whitelists the specific bwrap-required syscalls. On Ubuntu 24.04 hosts, the pod also needs `apparmor: Unconfined`. These are real security relaxations vs. PSA "restricted" — meaningful enough to flag, but narrower than `privileged: true`.

The detailed empirical findings — what was tested, on what platforms, what the working bwrap recipe looks like, why we don't get a fresh PID namespace, the four security layers and which platforms gate which — live in the companion document `2026-04-27-chat-v2-sandbox-bwrap-findings.md`. Sub-project (4) starts from that recipe rather than re-deriving it.

Per-platform reality (verified, 2026-04 — full table in the findings doc):

| Platform | Pod-side knobs needed | Host-side knobs needed |
|---|---|---|
| DigitalOcean Managed K8s (Debian 12) | seccomp=Unconfined (or custom) | None |
| GKE (COS) | seccomp=Unconfined | None |
| EKS on Amazon Linux 2023 | seccomp=Unconfined | None |
| AKS on Azure Linux 3.0 | seccomp=Unconfined | None |
| Local Docker Compose on Debian 12 / Ubuntu 22.04 | seccomp=unconfined | None |
| **EKS on Bottlerocket** | seccomp=Unconfined | `user.max_user_namespaces > 0` in node user data |
| **AKS on Ubuntu 24.04** | seccomp=Unconfined + apparmor=Unconfined | `kernel.apparmor_restrict_unprivileged_userns=0` |
| Local Docker on Ubuntu 24.04 host | seccomp=unconfined + apparmor=unconfined | Same |

**Note on seccomp:** The "seccomp=Unconfined" requirement is universal — it's a Docker/K8s default issue, not a host issue. We will likely ship a custom seccomp profile (`bifrost-sandbox-seccomp.json`) that whitelists the specific bwrap-required syscalls so operators don't have to use full Unconfined. That profile is sub-project (4)'s responsibility to author.

To handle the failure cases, the worker runs a startup **preflight check** (`unshare -U true` from inside the pod) and one of two paths happens:

1. **Strong sandbox available** — proceed normally.
2. **Strong sandbox unavailable** — log a loud diagnostic with platform-specific remediation, and either (a) refuse to start sandbox executions (default, fail-closed), or (b) drop to `enableWeakerNestedSandbox` mode if the org has explicitly opted in to the weaker isolation. `sandbox-runtime` ships this weak mode upstream specifically for restrictive container environments; we surface it as an org-level config knob with a clear security-tradeoff acknowledgement.

This means there is no "CAP_SYS_ADMIN fallback" — that was incorrect in an earlier draft. The fallback is either operator-side host config (preferred) or the upstream weak-mode flag (opt-in, documented tradeoff).

**Multi-runtime:** different binaries (`python3`, `node`, `pwsh`) invoked through the same shell-out pattern, different `sandbox-runtime` policy files per runtime. Adding a new runtime = ship a new policy + ensure the binary is in the worker image. No protocol changes.

**Networking default:** no network from the sandbox. Web access is provided by a separate first-party `bifrost.fetch` / web-search tool that runs *outside* the sandbox and returns response data to the model, which the model can then pass back into a sandbox execution if needed.

**Filesystem default:** per-execution `/work` tmpfs. No per-conversation persistent volume. Cross-turn persistence happens via artifacts — the model must explicitly save things it wants to keep.

### 4. Sandbox does not get SDK access

The workflow process pool runs trusted code with full SDK access (DB, integrations, OAuth tokens, etc.) — that's the entire value proposition of workflows. The sandbox is the opposite: zero SDK, zero credentials, zero DB connectivity, zero trust. If a sandboxed program needs to call into Bifrost capabilities, the agent (running outside the sandbox) is the one that does it, then passes results back as data on the next sandbox invocation.

### 5. Artifacts have three rendering tiers

| Tier | Examples | Where it runs |
|---|---|---|
| Inert content | Markdown, JSON, CSV | Browser (just rendered) |
| Sandboxed render | HTML, React component, SVG | Browser iframe with `sandbox=""` + CSP |
| Server-generated binary | docx, pdf, xlsx, png from data | Code Execution sandbox running skill scripts |

The earlier draft separated "trusted workflow-backed binary generation" from "untrusted user-provided code" as different tiers shipping at different times. After investigating Anthropic's own docx/pdf/pptx/xlsx skills, this distinction collapsed: real document generation requires multi-runtime shelling out (`npm install -g docx`, `pandoc`, `soffice`, `pdftoppm`), which is exactly what the Code Execution sandbox provides. Trying to write all of that as Bifrost workflows in the trusted pool would mean re-implementing what Anthropic spent significant effort on, badly. So all binary artifact generation goes through the sandbox.

### 6. Chat UX features — scope

Chat UX is the broadest sub-project. The full feature list:

- Conversation branching/forking from any message
- Message editing (with re-run from edit point)
- Regenerate last assistant message (with optional model/temp override)
- Conversation folders / "projects" (Claude-style: scoped instructions, scoped tools/skills, scoped knowledge sources)
- Conversation search (full-text across history, scoped to user/org permissions)
- Attachments — images, PDFs, text files, CSVs (uploaded to S3, referenced by content blocks, optionally OCR'd or extracted)
- Lossless context compaction (summarize old turns into a briefing rather than truncating)
- Per-conversation system instructions (independent of the agent's global system prompt)
- Per-message model/parameter override
- Conversation rename, delete, export
- Multi-agent in single response (delegation that doesn't require @-switching mid-thread)

The Chat UX spec will further sub-divide this — not all of it ships in one PR — but it's all owned by sub-project (1).

### 7. Diagnostics treats every execution uniformly

Whether a fork ran a workflow, a sandboxed Python script, or a sandboxed Node script, it shows up in Diagnostics with the same shape: PID, runtime, status, duration, memory, logs, kill button. Filter by `execution_runtime`. Same heartbeat, same cancel button, same crash detection.

### 8. Skills + Artifacts share content-block plumbing

Both sub-projects (3) and (4) — Skills and Artifacts — need to introduce new structured content-block types into the message protocol. Doing them together means one round of wire-format change rather than two. They get separate design docs but a coordinated implementation milestone.

### 9. Skills scoping mirrors forms/agents

Skills follow the existing four-tier scoping model the platform already uses for forms, agents, workflows, and tools:

| Tier | Authored by | Visible to | Editable by |
|---|---|---|---|
| **Global** | Bifrost (ships with platform) | Everyone (subject to org-admin disable) | Bifrost upstream |
| **Org** | Org admins / contributors | Anyone in the org (subject to role gating) | Org admins |
| **Role** | Org admins | Members of specific role(s) | Org admins |
| **Personal** | Individual user | Only that user | That user |

This is strictly more flexible than Claude (no role tier) or Copilot (storage-location-based scoping conflated with access). For MSPs, the role tier matters: Senior Tech vs. Help Desk vs. Account Manager have meaningfully different runbooks, and skills should reflect that out of the box.

**Note on Anthropic's open-source skills as global tier candidates:** their `mcp-builder`, `frontend-design`, `webapp-testing`, `claude-api`, `skill-creator`, etc. are Apache-2.0 and can ship as global skills. Their docx/pdf/pptx/xlsx skills are *source-available, not open source* and explicitly prohibit derivative works — we cannot ship them. Bifrost's global document-generation skills will need to be authored fresh (likely informed by the open-source ones in spirit, but not derived from the proprietary ones).

The skill content format (`SKILL.md` + scripts) is the open Agent Skills spec, fully portable. The scoping/visibility/role metadata is Bifrost-specific and lives outside the SKILL.md file (in DB rows and the `.bifrost/skills.yaml` manifest entry), so community-shared skills remain compatible across tools.

## Cross-cutting concerns

### Permissions / org control

Every sub-project must respect the existing org/role model:

- Skills are scoped to org, with optional access-level / role gating per skill.
- Artifacts respect the same access controls as the conversation that created them.
- Code Execution is gated by org policy: orgs can disable sandbox execution entirely, or limit it to specific roles.
- Web Search is org-toggleable and the search provider is an org config (so an org can use their own enterprise search instead of Brave).

### Cost accounting

Per the goal of "manage costs across the organization," every sub-project must surface cost:

- Per-message cost (already partial today via `AIUsage` / `total_cost_7d`).
- Per-skill invocation cost (delta of LLM usage attributable to skill body being loaded).
- Per-sandbox-execution cost (CPU-seconds × pricing model TBD; or absorbed as part of org infra cost and not chargeback'd).
- Per-search cost (provider-specific).

The Cost Surface design is folded into each sub-project's spec rather than being its own project.

### Testing

Each sub-project ships:

- Unit tests for new shared/business logic.
- E2E tests for new endpoints.
- Vitest tests for new functional frontend modules (`client/src/lib/**`, `client/src/services/**`).
- Playwright happy-path for any user-facing flow.

Sandbox-related tests need a CI runner with `bwrap` available and unprivileged user namespaces enabled. GitHub Actions `ubuntu-22.04` runners satisfy this today (`ubuntu-24.04` runners hit the AppArmor restriction; pin to 22.04 or pre-load an AppArmor profile in CI setup).

Sub-project (4) must also include:
- A startup preflight check inside the worker pod (`unshare -U true`) that surfaces a clear, actionable diagnostic on failure with per-platform remediation links.
- Documentation pages per supported platform (DOKS, GKE, EKS-AL2023, EKS-Bottlerocket, AKS-AzureLinux, AKS-Ubuntu24, on-prem) covering whether sandbox works out of the box and what an operator has to do if not.
- Org-level config to opt in to `enableWeakerNestedSandbox` for operators on locked-down platforms, gated behind an explicit acknowledgement.

## Implementation roadmap

**Phase 1 (Chat UX foundation) — 4-6 weeks**

Sub-project (1). Lands the visible product. Without this, none of the other sub-projects have a UI surface to integrate with.

**Phase 2 (Code Execution) — 3-4 weeks**

Sub-project (2). Sandbox runtime, multi-runtime support (Python first, Node second), Diagnostics integration, preflight checks, per-platform deployment docs. Required before Skills and Artifacts can ship in their full form.

**Phase 3 (Skills + Artifacts) — 4-6 weeks**

Sub-projects (3) and (4) coordinated. Shares wire-format work. With (2) in place, skill scripts and binary artifact generation are real — Anthropic's open-source skills (Apache-2.0) work directly, Bifrost-authored document generation skills can shell out properly, community/role/org/personal scoping all work uniformly.

**Phase 4 (Web Search) — 1-2 weeks**

Sub-project (5). Smallest. Pure tool addition. Can be slotted at any point after Phase 1; no real dependencies on Phases 2-3.

**Total program estimate: 12-18 weeks of focused work.** Each phase delivers visible user value independently — Chat UX alone is shippable and useful even if (2)–(5) never lands. Phase 2 alone enables the existing workflow product to gain a "run this Python in a sandbox" capability separate from any Chat V2 surface.

**Earlier ordering correction:** an initial draft put Skills+Artifacts in Phase 2 with Code Execution in Phase 3. That assumed skill scripts and binary artifact generation could ship as trusted workflow-backed first, with sandbox-required versions deferred. Inspection of real-world skills (Anthropic's open-source set) showed this was wishful — most non-trivial skills shell out to language runtimes. Inverting the order means Code Execution lands first and Skills+Artifacts ship as a meaningful product when they arrive, rather than as v0.5 placeholders.

## What this spec does NOT do

- Pick a model provider abstraction. (The existing single-LLM-config story has to evolve to support per-message overrides; that's part of sub-project (1)'s detailed spec.)
- Specify the Skills registry data model. (Sub-project (2).)
- Specify the artifact content-block schema. (Sub-project (3).)
- Specify the sandbox policy file format details, runtime image build process, or Diagnostics UI changes. (Sub-project (4).)
- Pick a web search provider. (Sub-project (5).)

## Next steps

1. Commit this program-level spec.
2. Brainstorm and write the sub-project (1) Chat UX overhaul design doc.
3. After (1) is implemented, brainstorm (2) Code Execution.
4. After (2), brainstorm (3) Skills and (4) Artifacts together.
5. Slot (5) Web Search wherever there's bandwidth — it has no real dependencies beyond the chat surface existing.

## References

- `anthropics/skills/spec/agent-skills-spec.md` — Agent Skills format we're adopting
- `anthropic-experimental/sandbox-runtime` — Apache-2.0 sandbox tech we're building on
- `api/src/services/execution/README.md` — current execution engine architecture (the load-bearing reference for sub-project (4))
- `docs/superpowers/specs/2026-04-05-fork-based-process-pool-design.md` — process pool design we're extending, not replacing
- `docs/superpowers/specs/2026-04-27-chat-v2-sandbox-bwrap-findings.md` — empirical bwrap test results; the working sandbox recipe; per-platform security-layer matrix. Mandatory reading before sub-project (4) begins.
- `docs/plans/2026-02-04-bifrost-sdk-skills-design.md` — *different* "skills" concept (SDK scaffolding); name disambiguation is sub-project (2)'s problem
