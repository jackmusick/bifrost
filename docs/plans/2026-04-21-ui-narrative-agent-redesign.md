# UI Narrative: Agent Management Redesign

> A design-system artifact, not an implementation plan. Captures the principles, iteration history, and reusable patterns that emerged from the agent management mockup — intended to seed a broader Bifrost UI overhaul.

**Date:** 2026-04-21
**Mockup source:** `/tmp/agent-mockup/` (Vite + React, standalone)
**Pairs with:** the separate implementation plan for Milestone 1 (agent detail, runs, verdict capture)

---

## What this document is for

We spent an evening iterating on the agent management experience in an isolated mockup — no build system, no shadcn, no CLAUDE.md rules — just React + raw CSS on top of the existing visual tokens. The mockup went through five iterations, each driven by live feedback. What came out is not just "a nicer agent page." It's a coherent opinion about how *observability, review, and refinement* should feel across the whole product.

This document records:
1. **Principles** that emerged (use these as lenses, not laws)
2. **Patterns** we built (slide-over sheet, card rows, per-flag chat, queue banner, chat composer, verdict toggle)
3. **Decisions we made and why** (including ones we reversed)
4. **What the existing app should steal** — patterns that don't just belong to agent management

The goal is to hand this to someone doing a system-wide UI overhaul and have them think *"ah, this is the tone and structure we're reaching for."* Not prescriptive. Directional.

---

## Principles

### 1. A feature lives inside its subject, not beside it.

Before: agents were a flat list. Runs were a flat list. Chat was a separate thing. Settings was a modal dialog attached to an agent row. Users had to mentally reconstruct relationships.

After: agents are the subject. Everything about an agent lives inside that agent's detail page — runs, settings, metadata, chat, tuning, review. The fleet view is a directory; the detail page is the place you *work*.

**Test to apply elsewhere:** for every "management" screen that shows a list of things, ask — is there a "detail" for each thing that could host its own sub-features? Integrations, workflows, forms, tables all deserve the same treatment.

### 2. Answer "is this healthy?" in two seconds, not two clicks.

Cards aren't labels — they're vital signs. Each agent card in the fleet view shows runs (7d), success rate, average duration, spend, last activity, and a sparkline. Sparkline color encodes success rate thresholds (green ≥ 90%, yellow ≥ 75%, red below). You can scan the fleet and know which agent needs attention without opening anything.

**Test to apply elsewhere:** for every list of "things the user runs or owns," what is the one question they're asking? Put the answer on the card. Don't wait for them to click in.

### 3. Single component, many entry points.

We built one `RunReviewPanel` that renders the same Asked / Did / Answered / Captured-data structure. It's used in three surfaces — run detail page (main column), inline slide-over sheet (drawer), and flipbook review card. Same structure, same sections, same verdict UX.

Result: improvements to review UX propagate everywhere at once. And the user's muscle memory transfers — they learn the pattern once, apply it forever.

**Test to apply elsewhere:** before building a second view of the same content, can you abstract the content into a variant-aware component? The variants should be about *size* and *surrounding chrome*, not about what data is shown.

### 4. The fast action should be faster than the slow one.

On a run card, 👍 and 👎 are one click without opening anything. Opening the detail sheet is also one click, but on a *different* target (the card itself, not the buttons). This gives two speeds: "I can judge this from the summary → flag, move on" versus "I need to see the whole story → open the sheet."

Originally flagging auto-opened the sheet. We reverted that — it conflated the fast path with the slow one. Now: you can triage 20 runs in 20 seconds *without ever opening a sheet*, and the ones that need deeper investigation remain one click away.

**Test to apply elsewhere:** for every important action, is there a fast path (1 click, no context switch) and a slow path (open drawer, open page, multi-step)? Separate them. Never force the slow path.

### 5. Every action leaves a visible trace.

When you flag a run, three things happen: the card turns red with a visible indicator, a toast pops up ("Added to tuning queue — 3 flagged"), and the queue banner at the top shows the growing count with a pulsing red dot. The user has immediate confirmation that flagging *did something* — and a visible representation of the work they've queued.

This replaces the anxiety pattern where users re-click because they're not sure their click "took." It also surfaces the queue as a first-class concept, not an invisible back-end state.

**Test to apply elsewhere:** every mutation should leave something visible. If it's a status change, the UI should reflect it before the user looks for confirmation. If it's something reversible, the reversal path should be visible. If it's something that grows (queue, basket, draft), show it growing.

### 6. Put the action where the attention is.

The verdict footer in the sheet is **sticky**. Scroll all you want — the 👍/👎 never disappears. The chat composer at the bottom of a tuning conversation is **sticky**. You never have to scroll to act.

**Test to apply elsewhere:** if there's a primary action in a scrollable context, pin it. Scrolling to find the button is a bug.

### 7. Textbox vs chat is a false dichotomy.

When we added verdict notes, we made them a textbox. The user asked: shouldn't this be a chat? Every flag is a conversation with the tuning agent, not a dead-end note.

We collapsed the distinction: the verdict textbox **is the first message** of a per-flag chat. Type a note, hit enter, the tuning assistant responds. If you stop there, it's a note. If you want depth, it's a conversation.

This generalizes: anywhere we're tempted to add a text box for "what's wrong / what do you want / explain please," we should consider whether that text box is actually the opening turn of a conversation. Most of the time, it is — and the "assistant" can be as simple as an echo that logs and thanks you.

**Test to apply elsewhere:** every free-text input for "tell me why" / "what should it have done" / "describe this" is a chat. Shape it like a chat. Even if the other end doesn't respond today, the affordance is the same.

### 8. Separate "diagnose" from "apply."

Per-flag chat: diagnose the failure, explore the fix, optionally sandbox-test against *just this run*. No live prompt changes.

Consolidated tune page: aggregates all per-flag conversations, proposes one unified change, dry-runs against all flagged runs together, applies once.

Why: fixing flag 1 in isolation invalidates flag 2's diagnosis — you'd be tuning against a moving prompt. The separation is philosophical, not decorative. You triage many, apply once.

**Test to apply elsewhere:** when you have "review one item" and "apply changes" in the same flow, they should be different surfaces. The review surface never mutates shared state. The apply surface consumes the aggregate of reviews and commits once.

### 9. Sliding over > shrinking beside.

We originally built the sheet as a right-column drawer that shrank the table when it opened. User correctly pushed back: this breaks column alignment, makes it hard to scan the list while reviewing an item, feels compressed.

We replaced it with a slide-over sheet: right-side panel, dim overlay (50% black), full-height, escape to close. The list behind is preserved, blurred in attention by the overlay. The sheet itself has sticky header, scrollable middle, sticky footer — three independent zones.

**Test to apply elsewhere:** details of a list item should overlay the list, not push it around. Dim the background to focus attention. Preserve the list's geometry so the user can mentally keep their place.

### 10. Consistency across surfaces is a force multiplier.

The chat composer (rounded pill with an embedded send button) is used in three places today: per-flag chat in the sheet, consolidated tune chat, and — in a future iteration — any agent-scoped chat. It should become the standard across Bifrost.

**Test to apply elsewhere:** if it looks like a chat input anywhere, it should look like *this* chat input everywhere. Likewise cards, tables, badges, status indicators. Every inconsistency taxes the user.

---

## Iteration history

Keeping this because the *reversals* are as informative as the decisions.

### Iteration 1 — first mockup

Built the three core screens: fleet dashboard, agent detail with tabs, run detail with Request/Activity/Result structure. Good enough to establish direction, not good enough to ship.

### Iteration 2 — feedback-driven fixes

User feedback called out:
- "Needs review" stat card should be clickable (was decorative)
- Verdicts were being applied to failed runs (conflating system failure with bad output)
- Dedicated chat feels wrong ("someone else is going to do this better" — correctly noted that a generic chat clone has no product value)
- Pause semantics needed to be real (not cosmetic): webhook returns 503, in-flight runs finish, chat UI disables
- Removed invented features ("Rotate delegated secrets" was something I guessed at — killed it)

**Lesson:** the first iteration lies. Invented affordances (like a fake button) survive unless explicitly audited.

### Iteration 3 — search + metadata + inline drawer

User asked: "how do I find things from the runs page?" Two options surfaced: arbitrary jsonb metadata on runs (ticket IDs, customer, severity), or full-text search. Answer: both.

Added:
- `metadata` jsonb column with realistic per-run key/value pairs
- Full-text search across asked/did/input/output/error/metadata values
- Metadata chips rendered on each row, with matching chips highlighted yellow when you search
- Inline drawer when you click a row (slide-from-right within the table area)

**Reversal:** the inline drawer shrank the table. User flagged this as wrong — "should be slide-in-over, like a hamburger menu where the background fades."

### Iteration 4 — card rows + slide-over + per-flag chat

Restructured:
- **Card rows** replaced the table — uniform heights, consistent weight, one metadata chip row per card with overflow
- **Slide-over sheet** (`Sheet` component with dim overlay) replaced the shrinking drawer
- **Per-flag chat** replaced the "note textbox" — when you flag, you enter a conversation
- **Tune agent CTA** in the Runs header, badged with the flagged count
- **Verdict toggle** with pop animation
- `hideVerdictBar` prop on `RunReviewPanel` to suppress the internal verdict bar when the sheet's own footer owns that responsibility

**Key philosophical decision** in this iteration: per-flag chat is *diagnostic only* — it never applies changes. Only the consolidated tuning surface applies. This is what separates triage from tuning.

### Iteration 5 — scroll fix, composer redesign, queue visibility

User feedback:
- Scroll was broken (flex `min-height: 0` issue — the classic)
- Tabs looked white/squared — didn't belong in the dark aesthetic. Replaced with pill-segmented rounded tabs.
- Chat input was a boxy textarea with a separate button. Replaced with the standard rounded composite (pill-shaped, embedded circular send button on the right, focus ring on the whole pill).
- Queue wasn't visible — user expected clicking red to queue, not open a sheet. Two fixes:
  - Flagging no longer opens the sheet (fast path stays fast)
  - Added a persistent **queue banner** below the search row — pulsing red dot, "N flagged runs in tuning queue," Open tuning button
  - Added a **toast** on every verdict change for immediate confirmation

---

## Reusable patterns

These are the things that should graduate from the mockup into the shared component library.

### `RunReviewPanel` → generalize as `ItemReviewPanel`

A sections-based renderer for any "reviewable thing." Sections are slots (asked / did / answered / metadata / errors / whatever). Variants are `page`, `drawer`, `flipbook`. Variant controls padding, chrome, and whether it renders its own verdict bar.

Applicable beyond runs: workflow executions, form submissions, integration events, tool call traces, approval requests.

### `Sheet` component (slide-over with dim overlay)

Already conceptually in shadcn (`sheet.tsx`). Our mockup confirmed the pattern's value. Critical details:
- Dim overlay (~55% black) dismisses on click
- Escape key dismisses
- Slide-in-right animation (~220ms, ease-out cubic-bezier)
- Internal structure: `.sheet-header` (sticky), `.sheet-body` (scroll, `min-height: 0`), `.sheet-footer` (sticky)
- Body scrolls independently — don't let content push header or footer

### `ChatComposer` — the standard chat input

Rounded pill, textarea flows naturally, embedded circular send button on the right (becomes disabled state when empty). Focus ring lights up the whole pill, not just the input. Enter to send, shift+enter for newline.

Used everywhere we accept free-text for a conversational response. Currently three surfaces in the mockup. Should become the input for:
- Any agent chat
- Any AI-assist textbox in the product (tuning, debugging, workflow-building help)
- Feedback/support messages

### `RunCard` / `ItemCard` — uniform-weight card rows

Grid template: `1fr auto`. Left column: status + title + subtitle + meta row. Right column: inline actions (verdict, etc.).

Meta row is a `flex wrap` of small chips/stats — duration, tokens, cost, metadata key-values. Overflow shows as "+N" chip.

Click card anywhere except the action column → open detail. Click action column → fast path (verdict, pause, etc.).

### Queue banner

Persistent surface below filters/search, appears only when the queue has items. Pulsing indicator + count + description + primary action. This is the pattern for *any* "work you've implicitly queued by taking actions."

Applicable to: drafts, pending approvals, unread notifications, items flagged for review, imports ready to commit.

### Verdict toggle

Circular-square toggle buttons (30px) with animated pop on activation. Color-coded: green/red-soft when active, transparent when inactive. Neutral hover state between.

Applicable to: any binary judgment — approved/rejected, seen/unseen, important/not, relevant/not.

### Animated attention dot (`queue-banner-dot`)

CSS-only pulsing dot — a box-shadow that expands and fades. Signals "something's here that wants attention" without being obnoxious. 2-second cycle. Reusable anywhere a count matters.

### Tabs (pill segment style)

Rounded pill segments on a subtly-elevated background. Active tab is a slight elevation (lighter background + border). Count badge inside active tab inherits a more saturated color.

This replaces the "underline tabs" aesthetic that feels thin against the dark palette. The pill-segmented style sits comfortably in card headers, sheet headers, page headers.

### Stat cards (fleet dashboard)

Label (uppercase, muted) + value (large, semibold) + delta/context (small, optionally colored green/red). Four in a row on the fleet page.

This pattern already exists in the app. We're just calling it out — apply it consistently wherever "top-line numbers for the last N days" belong.

---

## Color / spacing observations

Observations, not prescriptions:

- **Soft-background variants** of primary / green / red / yellow / blue work extraordinarily well for badges. `--green-soft`, `--red-soft`, etc. The contrast against the dark base is readable without screaming.
- **Gradients are rare but useful** — the tuning assistant's avatar uses a primary-to-purple gradient as a visual signature. Used sparingly to mark "this is the AI talking," not decoratively.
- **`--text-subtle` below `--text-muted` below `--text`** is a three-tier hierarchy that kept showing up. Labels, meta, body. Worth formalizing in the tokens.
- **Animation timing: 120ms for hover/focus, 150-250ms for state changes (pop, slide-in), 800ms for spin.** Nothing should take longer. The slide-in sheet at 220ms feels slow enough to track, fast enough to not be in the way.
- **Border radius: 6px for inputs/buttons, 8-10px for cards, 999px for badges/chips, 20px for chat composers.** The bigger the container, the bigger the radius — up to the point where it's "pill."
- **Shadows are minimal.** Only the sheet has a real shadow. Cards have a 1px inset highlight (white at 3% opacity) to lift slightly from the background. Flat design with subtle elevation, not skeuomorphism.

---

## What this design implies for the rest of the app

Patterns from this redesign that other Bifrost surfaces should adopt:

1. **Workflow list → workflow detail with tabs** (Overview / Runs / Settings / Dependencies). Same shape as agent detail.
2. **Form list → form detail with tabs** (Overview / Submissions / Settings). Submissions get the same review treatment as runs.
3. **Integration list → integration detail** (already exists partly). Should gain the same health-stat cards.
4. **Every list of "executable things" gets card-row treatment** with fast-path actions in the right column.
5. **Every detail page gets a Runs/Submissions/Activity tab with search + metadata filter + slide-over review**.
6. **Every free-text "explain why" input becomes a chat composer with an assistant echo, at minimum.**
7. **Every mutation that can be queued should show a queue banner** (drafts, pending invites, imports, exports, anything "about to commit").

---

## Non-goals for this document

- Not a shadcn port (though most of these patterns are shadcn-compatible)
- Not a specification of which pixels go where (that's the design system)
- Not an implementation plan (that's the separate agent management plan)
- Not a commitment to redesign the whole app (but should inform the overhaul when you do)

---

## References

- Mockup source: `/tmp/agent-mockup/`
- Mockup PLAN_NOTES.md: `/tmp/agent-mockup/PLAN_NOTES.md` — detailed data model, visibility matrix, pause semantics, verdict schema
- Conversation log that generated this: session on 2026-04-21

---

## Appendix: raw patterns catalog

Quick reference for someone porting these to the real app.

| Pattern | CSS class(es) in mockup | Notes |
|---|---|---|
| Slide-over sheet | `.sheet`, `.sheet-overlay`, `.sheet-header`, `.sheet-body`, `.sheet-footer` | Body needs `min-height: 0` inside flex |
| Chat composer | `.chat-composer`, `.chat-composer-send` | Rounded 20px pill, embedded 30px circular send |
| Pill tabs | `.tabs`, `.tab`, `.tab-count` | Segmented container with elevated active state |
| Run card | `.run-card`, `.run-card-body`, `.run-card-meta`, `.run-card-actions` | Grid 1fr auto, click-through except right column |
| Verdict toggle | `.verdict-toggle.up`, `.verdict-toggle.down` | 30px square, pop keyframe on activation |
| Queue banner | `.queue-banner`, `.queue-banner-dot` | Persistent, pulsing dot, primary action on right |
| Toast | `.toast` | Bottom-center, 2-second auto-dismiss, fade+slide-up |
| Stat card | `.stat-card`, `.stat-label`, `.stat-value`, `.stat-delta` | Label + big value + optional colored delta |
| Soft-variant badges | `.badge-green`, `.badge-red`, `.badge-yellow`, `.badge-blue` | Soft-bg + colored text, no border |
| Animations | `@keyframes pop`, `fade-in`, `slide-in-right`, `pulse`, `toast-in`, `spin` | All short (120-800ms), easings favor cubic-bezier(0.2, 0.8, 0.2, 1) for movement |
