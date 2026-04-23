# Tune Agent — Workbench Redesign

**Status:** Approved, ready for implementation plan
**Date:** 2026-04-23
**Scope:** Client-side redesign of `/agents/:id/tune` — no backend changes
**Related:** `docs/plans/2026-04-21-agent-management-m1.md` (M1 plan, adds polish items this spec supersedes)

## Problem

The current `AgentTunePage.tsx` is a chat UI: a single scroll of system/user/assistant bubbles with proposal and dry-run results rendered as nested slots inside assistant bubbles (`ChatBubble` + `ChatBubbleSlot`, introduced in Phase-7b). A "Flagged runs" sidebar lists the runs the tuner will consider; a "Current prompt" card sits below it.

Three issues:

1. **"Propose change" has no visual relationship to the flagged runs it operates on.** The button sits at the bottom of the chat composer, ~700px from the sidebar listing the flagged runs. The only hint that the two are related is the page subtitle ("against 2 flagged runs"). The button itself says "Propose change" with no indication of the input set.
2. **The empty state is dead space.** Before the first "Propose change" click, the main column is a mostly-empty card with one system-prose bubble. A 1400×800 dark canvas conveys nothing about what the tuner is about to do and offers no preview of the runs it will reason over.
3. **The chat metaphor is wrong for this task.** Tuning a prompt is a review-and-edit loop, not a conversation. The proposed prompt is the primary artifact. Today the diff is buried inside an assistant bubble; the "before" side says `(current prompt — see sidebar)` because the API only returns `proposed_prompt` (`AgentTunePage.tsx:463` — TODO: real diff library). Users can't hand-edit the proposal.

Separately, on run detail (`AgentRunDetailPage.tsx:300-318`), per-run chat with the tuner via `FlagConversation` already exists. That's where back-and-forth belongs — scoped to one run at a time.

## Design

Replace the chat UI with a three-pane workbench. Diagnosis (the flagged runs) and prescription (the prompt edit) both live on the page, with dry-run impact as a first-class third pane.

### Layout

```
┌────────────────────────────────────────────────────────────────────────┐
│ ← Test Parent Agent                                                    │
│ ✦ Tune agent                                        [Current version] │
│ Refine the prompt against 2 flagged runs. Dry-run before going live.  │
│ ┌──────────┬──────────┬──────────┬──────────┐                          │
│ │Flagged   │Runs (7d) │Success   │Last tuned│                          │
│ │   2      │   47     │  92%     │ 3d ago   │                          │
│ └──────────┴──────────┴──────────┴──────────┘                          │
├──────────────────┬──────────────────────────┬──────────────────────────┤
│ FLAGGED RUNS     │ PROMPT EDITOR            │ IMPACT                   │
│ ─────────────    │ ─────────────            │ ─────────────            │
│ 👎 Send a test…  │ Current (collapsed)     │ ┌─ Dry-run ───────────┐  │
│   "a little…"   │ ▸ "You help users…"     │ │ Run the proposed    │  │
│   [expand ▸]    │                          │ │ prompt against 2    │  │
│ ──────────────   │ Proposed                 │ │ flagged runs.       │  │
│ 👎 Summarize…    │ ┌──────────────────────┐ │ │                     │  │
│   "Done better" │ │ ⚡ Generate proposal │ │ │ [Run dry-run]       │  │
│   [expand ▸]    │ │    from 2 runs       │ │ └─────────────────────┘  │
│                  │ └──────────────────────┘ │                          │
│ [⚡ Generate     │                          │ (After dry-run:)         │
│   proposal      │ (After generation:)      │ ┌─ Dry-run results ──┐  │
│   from 2 runs]  │ [editable textarea]      │ │ 1/2 would change   │  │
│                  │                          │ │ ✓ Send test event  │  │
│                  │ Diff: before ┃ after     │ │   "Would respond…" │  │
│                  │                          │ │ ⚠ Summarize event  │  │
│                  │ [Discard] [Apply live]   │ │   "Still wrong"    │  │
│                  │                          │ └─────────────────────┘  │
└──────────────────┴──────────────────────────┴──────────────────────────┘
```

Responsive behavior:

- `lg` and up: three columns (`320px_1fr_360px`).
- `md`: two columns — flagged runs collapse into a horizontal strip above editor; impact moves below.
- `sm`: single column, stacked.

### Pane 1 — Flagged runs (left)

Primary pane when no proposal exists. Each run renders as an expandable row:

- **Collapsed:** verdict icon (thumbs-down), truncated `asked`/`did` title, italicized `verdict_note`, caret toggle.
- **Expanded:** embedded transcript (reuse `RunReviewPanel` with a new `variant="tune-inline"` that renders a condensed chat view — no verdict controls, no metadata chips, just the conversation and verdict note).

**Primary button** lives in this pane's footer: **"⚡ Generate proposal from N runs"** — N = `flagged.length`, capped at 10 (matches the service-layer cap). This is the structural fix: the button is adjacent to the runs it operates on.

Secondary action: "Re-generate" (once a proposal exists).

Per-run checkboxes are NOT included in M1 — the backend's `/tuning-session` and `/dry-run` endpoints don't accept a `run_ids` parameter (confirmed against `ConsolidatedDryRunRequest` in `v1.d.ts:10273` — body is `{proposed_prompt}` only). Adding per-run selection requires a backend change and is called out in "Deferred to M2" below. The UI still benefits from the expandable transcript rows because diagnosis (seeing the failing transcripts) is the main reason users come here.

### Pane 2 — Prompt editor (center)

Two stacked regions:

**Current** — read-only, collapsed by default. One-click expand shows the full system prompt in a monospace block. Replaces the sidebar "Current prompt" card.

**Proposed** — three states:

1. **Empty** — large CTA button `⚡ Generate proposal from N runs` (mirrors the left pane button so the user can click either). One-line hint beneath: "I'll read the flagged runs and suggest one consolidated prompt change."
2. **Generating** — skeleton of the textarea with a shimmer, plus the same loading-bubble copy from today ("Building proposal…").
3. **Has proposal** — editable `<textarea>` pre-filled with `proposal.proposed_prompt`. Below the textarea: a collapsible **Diff** section using `react-diff-viewer-continued` (side-by-side, line-level highlighting). Kills the `TODO` at `AgentTunePage.tsx:463`. Footer actions: `[Discard]` (clears proposal, returns to empty state) · `[Apply live]` (primary; calls `useApplyTuning` with whatever is currently in the textarea — NOT the original `proposed_prompt`, so hand-edits are respected).

The textarea is the source of truth for apply. The diff re-renders live as the user edits. API for `useApplyTuning` already accepts arbitrary `new_prompt` — no backend change needed.

One-line summary from `proposal.summary` renders above the diff as dim italic text (same role as today).

### Pane 3 — Impact (right)

Replaces the dry-run assistant bubble. Two states:

1. **Before dry-run** — card with short copy ("Simulate the proposed prompt against the selected flagged runs to see if it changes behavior before going live."), primary button `Run dry-run` (disabled until a proposal exists). `Apply live` is NOT gated on dry-run — users can skip it — but the UI nudges.
2. **After dry-run** — header count ("1 of 2 would change behavior"), then per-run result cards (same content as today's `DryRunBubble`: run ID prefix, badge, reasoning, confidence). Re-running dry-run replaces the results in place (no scrollback).

### Header

Breadcrumb back to agent (unchanged). Title `✦ Tune agent` uses `text-4xl font-extrabold tracking-tight` — matches the rest of the app per the header-consistency decision from 2026-04-23. Subtitle unchanged copy.

**Stat strip** — four `StatCard`s matching `FleetPage`/`AgentDetailPage`:

- Flagged runs (this agent) · big number
- Runs (7d) · from `useAgentStats`
- Success rate (7d) · from `useAgentStats`
- Last tuned · relative time (NEW field: if unavailable from `useAgent`, show "—"; add `last_tuned_at` to agent stats in a follow-up if desired — not blocking)

The stat strip gives the page the same "entered with context" feel as the other agent pages.

"Back to review" button moves from the top-right to the stat-strip right edge, smaller.

## State machine

```
NoProposal
  ├── generate() → Generating
  │   ├── success → HasProposal (proposal, edits=proposal.proposed_prompt)
  │   └── error → NoProposal (toast)
  │
HasProposal (edits: string)
  ├── edit textarea → HasProposal (edits updated)
  ├── discard() → NoProposal
  ├── regenerate() → Generating (keeps NoProposal semantics)
  ├── dryRun() → HasProposal + DryRunning
  │   ├── success → HasProposal + HasDryRun(results)
  │   └── error → HasProposal (toast)
  └── apply(edits) → Applying
      ├── success → navigate to /agents/:id (toast, invalidate queries)
      └── error → HasProposal (toast)
```

Apply sends `edits` (the textarea contents), not `proposal.proposed_prompt`. This is the one behavior change vs today.

## Components to build / change

**New:**

- `AgentTuneWorkbench.tsx` — the new page. Replaces `AgentTunePage.tsx` contents.
- `FlaggedRunCard.tsx` (or inline section in the page) — expandable run row with transcript.
- `PromptDiffViewer.tsx` — thin wrapper around `react-diff-viewer-continued` with our styling tokens.
- `StatCard` — already exists (`components/agents/StatCard.tsx`), reused.

**Modified:**

- `RunReviewPanel.tsx` — add `variant="tune-inline"` (condensed, no verdict controls). Adjacent to existing `"page"`, `"flipbook"`, `"drawer"` variants.
- `services/agentTuning.ts` — no changes. The existing hooks already match the M1 call signatures.

**Removed from this page (kept in the codebase for run-detail):**

- `ChatBubble` / `ChatBubbleSlot` usage (the primitives stay; they're still used by `FlagConversation` on run detail).
- `ChatComposer` from this page.
- `ProposalBubble`, `DryRunBubble`, `TuneMessage` (all internal to `AgentTunePage`).
- The `ChatMessage` union type and `messages` state (replaced by the state machine above).

## Dependencies

- `react-diff-viewer-continued` — add to `client/package.json`. Standard React diff library, dark-mode compatible, ~30kb.

## What we're intentionally NOT doing

- **Per-run selection** (include/exclude a flagged run from the proposal) — backend-blocked. `ConsolidatedDryRunRequest` at `v1.d.ts:10273` accepts only `proposed_prompt`; `/tuning-session` takes no body at all. Requires backend work on both endpoints. M2.
- **"Would regress" detection** in dry-run — needs backend work on `ConsolidatedDryRunResponse` (three-way outcome instead of `would_still_decide_same` bool). M2.
- **Version history / rollback** — no UI for prior prompt versions. The "Current version" chip in the mockup is copy-only for now.
- **Multi-proposal comparison** — user can regenerate and the new proposal replaces the old. No side-by-side of two AI proposals.
- **Streaming proposal generation** — still one-shot; spinner while pending.
- **Saving draft edits** — if the user hand-edits then navigates away, the edits are lost. M2 could persist to local state or server.

## Open questions (resolved)

1. **Per-run selection** — deferred to M2; backend doesn't support it today.
2. **Hand-edit of proposed prompt** — yes, textarea is editable; apply sends the textarea contents.
3. **Regression detection** — not in M1, backend-blocked.

## Testing

- `AgentTuneWorkbench.test.tsx` — replaces `AgentTunePage.test.tsx`:
  - Renders header + stat strip + three panes.
  - "Generate proposal" is disabled when there are 0 flagged runs, enabled otherwise.
  - Generating a proposal fills the textarea and shows the diff.
  - Editing the textarea updates the diff live.
  - Apply calls `useApplyTuning` with textarea contents, not the original proposal.
  - Dry-run renders results in the right pane, replacing prior results on re-run.
  - Discard returns to empty state.
- `PromptDiffViewer.test.tsx` — renders before/after, handles empty/identical cases.
- `FlaggedRunCard.test.tsx` (if extracted) — expand/collapse.

Playwright: extend existing tune-page spec to cover generate → edit → dry-run → apply flow end-to-end.

## Migration

No data migration. This is a pure client change. The existing `AgentTunePage.tsx` is deleted; its route (`/agents/:id/tune`) now renders `AgentTuneWorkbench`. No URL changes. No analytics events lost (none were wired).
