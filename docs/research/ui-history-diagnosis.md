# History page — designer-eye diagnosis

Date: 2026-06-11 · Page: `client/src/pages/ExecutionHistory.tsx` · Before: `/tmp/ui-history/before.png`

## The page's job

For an MSP operator the History page answers, in priority order:

1. **Did my automations run?** (a glanceable feed of recent activity)
2. **What failed, and why?** (the exceptional rows must pop; the reason must be readable without hunting)
3. **Drill in** (one obvious path to the full execution record)

It is a *time-ordered feed of mostly-successful events*. The correct mental model is a
monitoring feed (like a CI run list or an alerting timeline), rendered as a dense table
for scannability — not a generic CRUD grid where every column has equal weight.

## Named causes of the "off" feeling

### 1. Inverted status hierarchy — success screams, failure whispers
Thirteen solid-green `Completed` pills dominate the viewport; bright green is the
loudest color on the page and it's attached to the *non-event*. Meanwhile the one thing
the operator came to find — **why** `offboard_user` failed — is hidden behind a 16px
hover-only info icon. A designer renders the common case quietly (outline badge, muted
check) and spends color on the exceptions (failed/timeout filled red, error text inline).

### 2. Two timestamp columns burn ~40% of the grid to say the same thing
"Started At" and "Completed At" each render a full two-line datetime that differs by
seconds; Duration is *also* a column, so Completed At is pure redundancy. The wrap to
two lines makes every row tall and ragged. One "Ran" column (relative time, absolute on
hover) plus a right-aligned Duration carries the same information in a quarter of the
space and reads instantly.

### 3. No temporal landmarks — a history page with no sense of time
A run history is a feed, but all rows render identically with no grouping. The eye has
to parse a full datetime per row to know "was this today?". Day separator rows
("Today", "Yesterday", date) give the timeline quality a history page needs while
keeping the table's scannability.

### 4. Repeated identical metadata as loud chrome
Every row carries an identical outlined "Provider" org badge — zero bits of
information rendered sixteen times (it only matters when orgs *differ*). Likewise the
per-row Eye button duplicates the row's own click affordance, and the centered
pagination footer renders "Previous 1 Next" even when there is only one page. All of it
is chrome that competes with data.

### 5. Filter-bar soup with no grouping or order
One row holds: an admin-only "Logs View" mode *switch* (leftmost — the position of
highest priority), a small search box, workflow combobox, date range, a "Show Local
Executions" checkbox, and an org select — all equal weight, mode toggles interleaved
with filters. Designers group: primary search first and widest; entity filters
together; the rare mode switch and debug toggles demoted to the end.

### 6. Missing/weak states
- **Error state: none.** If `GET /api/executions` fails the page silently shows the
  empty state ("Execute a workflow to see it appear here") — actively misleading.
- **Loading**: a centered spinner that collapses the layout, then the table pops in.
  Skeleton rows hold the layout.
- **Empty**: one generic message regardless of context. "No executions found — execute
  a workflow" is wrong when the real cause is the Pending tab / search term / date
  filter; a filtered-empty needs "nothing matches" + a clear-filters action.

### 7. The header line narrates instead of informing
"View and track workflow execution history" tells the operator what the page is
(they know — they clicked History). That line is the natural home for the rollup the
job actually needs: how many runs, how many failed.

## Candidates for a future light design system (not built here)

- **Page header pattern**: title + optional mode toggle + summary line + actions, with
  fixed slots, so every page stops hand-rolling its own.
- **Status badge philosophy**: quiet-success/loud-failure variants as a shared
  component (today `ExecutionStatusBadge` and inline `getStatusBadge` duplicate each
  other, both loud-green).
- **List vs table vs feed selection**: history/audit/event pages share the
  "time-grouped dense table" need (day separators, relative time + hover absolute).
- **Standard empty/loading/error triad** for list pages, with a filtered-empty variant
  that offers clear-filters.
- **Density & column budget**: relative time + tooltip as the default for timestamps in
  lists; absolute datetime only in detail views.
