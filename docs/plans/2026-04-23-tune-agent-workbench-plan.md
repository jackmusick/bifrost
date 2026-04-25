# Tune Agent Workbench Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the chat-style tune page at `/agents/:id/tune` with a three-pane workbench (flagged runs / prompt editor / impact) so the "Generate proposal" CTA sits next to the runs it operates on, users can hand-edit the AI's proposed prompt, and the before/after diff is a real diff instead of a TODO.

**Architecture:** Pure client-side change. No backend or API changes. Keep the existing tuning hooks (`useTuningSession`, `useTuningDryRun`, `useApplyTuning`) unchanged; replace `AgentTunePage.tsx` with a new `AgentTuneWorkbench.tsx` organized as three panes inside a CSS grid. Reuse `RunReviewPanel` with `hideVerdictBar` for embedded transcripts. Add `react-diff-viewer-continued` for the side-by-side diff. The textarea (not the original proposal) is the source of truth for "Apply live".

**Tech Stack:** React + TypeScript (strict), vitest + React Testing Library, shadcn/ui primitives, Tailwind with the existing `@/components/agents/design-tokens`, `react-diff-viewer-continued` (new), react-router.

**Spec:** `docs/plans/2026-04-23-tune-agent-workbench-design.md`

---

## File Structure

**New files:**

- `client/src/pages/agents/AgentTuneWorkbench.tsx` — new page component. Owns state machine, renders three panes.
- `client/src/pages/agents/AgentTuneWorkbench.test.tsx` — vitest suite. Replaces `AgentTunePage.test.tsx`.
- `client/src/components/agents/PromptDiffViewer.tsx` — thin wrapper around `react-diff-viewer-continued` with our dark-theme styling.
- `client/src/components/agents/PromptDiffViewer.test.tsx` — vitest coverage for the wrapper.
- `client/src/components/agents/FlaggedRunCard.tsx` — expandable run row used in the left pane.
- `client/src/components/agents/FlaggedRunCard.test.tsx` — expand/collapse coverage.
- `client/src/components/agents/TuneHeader.tsx` — header with stat strip. Extracted so the page file stays focused.

**Deleted files:**

- `client/src/pages/agents/AgentTunePage.tsx` — replaced.
- `client/src/pages/agents/AgentTunePage.test.tsx` — replaced.

**Modified files:**

- `client/src/App.tsx` — swap `AgentTunePage` route to `AgentTuneWorkbench`.
- `client/package.json` — add `react-diff-viewer-continued`.

**Unchanged (but referenced):**

- `client/src/services/agentTuning.ts` — hooks reused as-is.
- `client/src/components/agents/RunReviewPanel.tsx` — reused with `hideVerdictBar={true}` for the embedded transcript view.
- `client/src/components/agents/StatCard.tsx` — reused for the stat strip.
- `client/src/components/agents/ChatBubble.tsx`, `ChatComposer` — kept in codebase (still used on run-detail by `FlagConversation`); just no longer imported by this page.

---

## Task 1: Add `react-diff-viewer-continued` dependency

**Files:**
- Modify: `client/package.json`

- [ ] **Step 1: Install the dependency**

Run from repo root:

```bash
cd client && npm install react-diff-viewer-continued@^4.0.0
```

Expected: `package.json` and `package-lock.json` updated with a new dep entry. No install errors.

- [ ] **Step 2: Verify it imports**

Run:

```bash
cd client && node -e "console.log(require.resolve('react-diff-viewer-continued'))"
```

Expected: absolute path under `node_modules/react-diff-viewer-continued/`.

- [ ] **Step 3: Commit**

```bash
git add client/package.json client/package-lock.json
git commit -m "chore(client): add react-diff-viewer-continued for tune page"
```

---

## Task 2: `PromptDiffViewer` component (TDD)

**Files:**
- Create: `client/src/components/agents/PromptDiffViewer.tsx`
- Create: `client/src/components/agents/PromptDiffViewer.test.tsx`

- [ ] **Step 1: Write the failing test**

Create `client/src/components/agents/PromptDiffViewer.test.tsx`:

```tsx
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";

import { PromptDiffViewer } from "./PromptDiffViewer";

describe("PromptDiffViewer", () => {
	it("renders before and after content", () => {
		render(
			<PromptDiffViewer
				before="You are a helpful agent."
				after="You are a helpful, concise agent."
			/>,
		);
		expect(screen.getByTestId("prompt-diff-viewer")).toBeInTheDocument();
		expect(
			screen.getByText(/you are a helpful agent\./i),
		).toBeInTheDocument();
		expect(
			screen.getByText(/you are a helpful, concise agent\./i),
		).toBeInTheDocument();
	});

	it("renders an empty-state hint when before and after are identical", () => {
		render(
			<PromptDiffViewer before="Same prompt." after="Same prompt." />,
		);
		expect(screen.getByTestId("prompt-diff-empty")).toHaveTextContent(
			/no changes/i,
		);
	});

	it("handles an empty before (fresh prompt)", () => {
		render(<PromptDiffViewer before="" after="Brand new prompt." />);
		expect(screen.getByTestId("prompt-diff-viewer")).toBeInTheDocument();
		expect(screen.getByText(/brand new prompt\./i)).toBeInTheDocument();
	});
});
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
cd client && npx vitest run src/components/agents/PromptDiffViewer.test.tsx
```

Expected: FAIL — `Cannot find module './PromptDiffViewer'` (module not yet created).

- [ ] **Step 3: Write minimal implementation**

Create `client/src/components/agents/PromptDiffViewer.tsx`:

```tsx
import ReactDiffViewer, { DiffMethod } from "react-diff-viewer-continued";

import { cn } from "@/lib/utils";
import { TONE_MUTED, TYPE_MUTED } from "./design-tokens";

export interface PromptDiffViewerProps {
	before: string;
	after: string;
	className?: string;
}

/**
 * Side-by-side diff of a current prompt vs a proposed prompt.
 *
 * Thin wrapper around react-diff-viewer-continued that applies our dark-theme
 * surface tokens and renders a friendly empty state when the two sides match.
 */
export function PromptDiffViewer({
	before,
	after,
	className,
}: PromptDiffViewerProps) {
	if (before === after) {
		return (
			<div
				data-testid="prompt-diff-empty"
				className={cn(
					"rounded-md border bg-muted/30 px-3 py-4 text-center",
					TYPE_MUTED,
					TONE_MUTED,
					className,
				)}
			>
				No changes — the proposed prompt matches the current one.
			</div>
		);
	}

	return (
		<div
			data-testid="prompt-diff-viewer"
			className={cn("overflow-hidden rounded-md border", className)}
		>
			<ReactDiffViewer
				oldValue={before}
				newValue={after}
				splitView
				compareMethod={DiffMethod.WORDS}
				useDarkTheme
				styles={{
					variables: {
						dark: {
							diffViewerBackground: "hsl(var(--card))",
							diffViewerColor: "hsl(var(--foreground))",
							gutterBackground: "hsl(var(--muted))",
							gutterColor: "hsl(var(--muted-foreground))",
						},
					},
					contentText: {
						fontFamily:
							"ui-monospace, SFMono-Regular, Menlo, monospace",
						fontSize: "12px",
						lineHeight: "1.5",
					},
				}}
			/>
		</div>
	);
}
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
cd client && npx vitest run src/components/agents/PromptDiffViewer.test.tsx
```

Expected: PASS (3 tests).

- [ ] **Step 5: Type check and lint**

Run:

```bash
cd client && npm run tsc && npm run lint
```

Expected: 0 errors.

- [ ] **Step 6: Commit**

```bash
git add client/src/components/agents/PromptDiffViewer.tsx client/src/components/agents/PromptDiffViewer.test.tsx
git commit -m "feat(agents): PromptDiffViewer with dark-theme side-by-side diff"
```

---

## Task 3: `FlaggedRunCard` component (TDD)

**Files:**
- Create: `client/src/components/agents/FlaggedRunCard.tsx`
- Create: `client/src/components/agents/FlaggedRunCard.test.tsx`

Reuses `RunReviewPanel` with `hideVerdictBar={true}` for the expanded transcript. Fetches run detail on expand via `useAgentRun`.

- [ ] **Step 1: Write the failing test**

Create `client/src/components/agents/FlaggedRunCard.test.tsx`:

```tsx
import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderWithProviders, screen } from "@/test-utils";

import { FlaggedRunCard } from "./FlaggedRunCard";

const mockUseAgentRun = vi.fn();

vi.mock("@/services/agentRuns", () => ({
	useAgentRun: (id: string | undefined) => mockUseAgentRun(id),
}));

vi.mock("./RunReviewPanel", () => ({
	RunReviewPanel: () => (
		<div data-testid="run-review-panel">panel</div>
	),
}));

const baseRun = {
	id: "run-1",
	agent_id: "agent-1",
	agent_name: "Triage",
	status: "completed",
	asked: "Send a test event",
	did: "Sent webhook",
	verdict: "down",
	verdict_note: "Responded with a little more happiness",
	trigger_type: "manual",
	iterations_used: 1,
	tokens_used: 100,
	duration_ms: 500,
	started_at: "2026-04-20T00:00:00Z",
};

beforeEach(() => {
	mockUseAgentRun.mockReturnValue({ data: baseRun, isLoading: false });
});

describe("FlaggedRunCard", () => {
	it("renders collapsed by default with title and verdict note", () => {
		renderWithProviders(<FlaggedRunCard run={baseRun as never} />);
		expect(screen.getByText(/send a test event/i)).toBeInTheDocument();
		expect(
			screen.getByText(/responded with a little more happiness/i),
		).toBeInTheDocument();
		expect(screen.queryByTestId("run-review-panel")).toBeNull();
	});

	it("expands to show the transcript when the header is clicked", async () => {
		const { user } = renderWithProviders(
			<FlaggedRunCard run={baseRun as never} />,
		);
		await user.click(screen.getByTestId("flagged-run-toggle"));
		expect(screen.getByTestId("run-review-panel")).toBeInTheDocument();
	});

	it("collapses again on a second click", async () => {
		const { user } = renderWithProviders(
			<FlaggedRunCard run={baseRun as never} />,
		);
		const toggle = screen.getByTestId("flagged-run-toggle");
		await user.click(toggle);
		expect(screen.getByTestId("run-review-panel")).toBeInTheDocument();
		await user.click(toggle);
		expect(screen.queryByTestId("run-review-panel")).toBeNull();
	});
});
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
cd client && npx vitest run src/components/agents/FlaggedRunCard.test.tsx
```

Expected: FAIL — `Cannot find module './FlaggedRunCard'`.

- [ ] **Step 3: Write minimal implementation**

Create `client/src/components/agents/FlaggedRunCard.tsx`:

```tsx
import { useState } from "react";
import { ChevronDown, ThumbsDown } from "lucide-react";

import { cn } from "@/lib/utils";
import { Skeleton } from "@/components/ui/skeleton";
import { useAgentRun } from "@/services/agentRuns";
import type { components } from "@/lib/v1";

import { RunReviewPanel } from "./RunReviewPanel";
import { TONE_MUTED } from "./design-tokens";

type AgentRun = components["schemas"]["AgentRunResponse"];
type AgentRunDetail = components["schemas"]["AgentRunDetailResponse"];

export interface FlaggedRunCardProps {
	run: AgentRun;
}

export function FlaggedRunCard({ run }: FlaggedRunCardProps) {
	const [open, setOpen] = useState(false);
	const { data: detail, isLoading } = useAgentRun(
		open ? (run.id ?? undefined) : undefined,
	);

	const title = run.asked || run.did || "Run";

	return (
		<div className="rounded-md border bg-card">
			<button
				type="button"
				data-testid="flagged-run-toggle"
				onClick={() => setOpen((o) => !o)}
				className="flex w-full items-start gap-2 px-3 py-2 text-left text-xs hover:bg-accent/40"
				aria-expanded={open}
			>
				<div className="mt-0.5 grid h-5 w-5 shrink-0 place-items-center rounded-full bg-rose-500/15 text-rose-500">
					<ThumbsDown className="h-3 w-3" />
				</div>
				<div className="min-w-0 flex-1">
					<div className="truncate text-foreground">{title}</div>
					{run.verdict_note ? (
						<div
							className={cn(
								"truncate text-[11px] italic",
								TONE_MUTED,
							)}
							title={run.verdict_note ?? undefined}
						>
							&quot;{run.verdict_note}&quot;
						</div>
					) : null}
				</div>
				<ChevronDown
					className={cn(
						"mt-1 h-3 w-3 shrink-0 transition-transform",
						open ? "rotate-0" : "-rotate-90",
					)}
				/>
			</button>
			{open ? (
				<div className="border-t p-2">
					{isLoading || !detail ? (
						<Skeleton className="h-24 w-full" />
					) : (
						<RunReviewPanel
							run={detail as AgentRunDetail}
							variant="drawer"
							verdict={null}
							note=""
							onVerdict={() => {}}
							onNote={() => {}}
							hideVerdictBar
						/>
					)}
				</div>
			) : null}
		</div>
	);
}
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
cd client && npx vitest run src/components/agents/FlaggedRunCard.test.tsx
```

Expected: PASS (3 tests).

- [ ] **Step 5: Type check and lint**

Run:

```bash
cd client && npm run tsc && npm run lint
```

Expected: 0 errors.

- [ ] **Step 6: Commit**

```bash
git add client/src/components/agents/FlaggedRunCard.tsx client/src/components/agents/FlaggedRunCard.test.tsx
git commit -m "feat(agents): FlaggedRunCard with expandable transcript"
```

---

## Task 4: `TuneHeader` component (stat strip) (TDD)

**Files:**
- Create: `client/src/components/agents/TuneHeader.tsx`
- Create: `client/src/components/agents/TuneHeader.test.tsx`

Consistent with `FleetPage` and `AgentDetailPage`: `text-4xl font-extrabold tracking-tight` title + 4-card stat strip.

- [ ] **Step 1: Write the failing test**

Create `client/src/components/agents/TuneHeader.test.tsx`:

```tsx
import { describe, it, expect } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { render, screen } from "@testing-library/react";

import { TuneHeader } from "./TuneHeader";

function renderHeader(
	props: Partial<React.ComponentProps<typeof TuneHeader>> = {},
) {
	return render(
		<MemoryRouter>
			<TuneHeader
				agentId="agent-1"
				agentName="Test Parent Agent"
				flaggedCount={2}
				stats={{
					runs_7d: 47,
					success_rate: 0.92,
					avg_duration_ms: 1200,
					total_cost_7d: "0.42",
					last_run_at: "2026-04-22T00:00:00Z",
					runs_by_day: [],
					needs_review: 2,
					unreviewed: 2,
					agent_id: "agent-1",
				}}
				statsLoading={false}
				{...props}
			/>
		</MemoryRouter>,
	);
}

describe("TuneHeader", () => {
	it("renders the agent breadcrumb and page title", () => {
		renderHeader();
		expect(
			screen.getByRole("link", { name: /test parent agent/i }),
		).toHaveAttribute("href", "/agents/agent-1");
		expect(
			screen.getByRole("heading", { name: /tune agent/i }),
		).toBeInTheDocument();
	});

	it("renders the 4 stat cards with expected values", () => {
		renderHeader();
		expect(screen.getByText("Flagged runs")).toBeInTheDocument();
		expect(screen.getByText("2")).toBeInTheDocument();
		expect(screen.getByText("Runs (7d)")).toBeInTheDocument();
		expect(screen.getByText("47")).toBeInTheDocument();
		expect(screen.getByText("Success rate")).toBeInTheDocument();
		expect(screen.getByText("92%")).toBeInTheDocument();
		expect(screen.getByText("Last run")).toBeInTheDocument();
	});

	it("renders skeletons for the stat strip while stats are loading", () => {
		renderHeader({ stats: null, statsLoading: true });
		expect(screen.getAllByTestId("stat-skeleton")).toHaveLength(4);
	});
});
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
cd client && npx vitest run src/components/agents/TuneHeader.test.tsx
```

Expected: FAIL — module not found.

- [ ] **Step 3: Write minimal implementation**

Create `client/src/components/agents/TuneHeader.tsx`:

```tsx
import { ArrowLeft, FileText, Sparkles } from "lucide-react";
import { Link } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { cn, formatNumber, formatRelativeTime } from "@/lib/utils";
import type { components } from "@/lib/v1";

import { GAP_CARD, TONE_MUTED, TYPE_BODY } from "./design-tokens";
import { StatCard } from "./StatCard";

type AgentStats = components["schemas"]["AgentStatsResponse"];

export interface TuneHeaderProps {
	agentId: string | undefined;
	agentName: string | undefined;
	flaggedCount: number;
	stats: AgentStats | null;
	statsLoading: boolean;
}

export function TuneHeader({
	agentId,
	agentName,
	flaggedCount,
	stats,
	statsLoading,
}: TuneHeaderProps) {
	return (
		<div className="flex flex-col gap-4">
			<Link
				to={agentId ? `/agents/${agentId}` : "/agents"}
				className="inline-flex w-fit items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground"
			>
				<ArrowLeft className="h-3 w-3" />
				{agentName ?? "Back to agent"}
			</Link>

			<div className="flex flex-wrap items-start justify-between gap-3">
				<div>
					<h1 className="flex items-center gap-2 text-4xl font-extrabold tracking-tight">
						<Sparkles className="h-7 w-7" />
						Tune agent
					</h1>
					<p className={cn("mt-2", TYPE_BODY, TONE_MUTED)}>
						Refine {agentName ?? "this agent"}
						&apos;s prompt against {flaggedCount} flagged run
						{flaggedCount === 1 ? "" : "s"}. Changes are dry-run
						before going live.
					</p>
				</div>
				<Button asChild variant="outline" size="sm">
					<Link to={agentId ? `/agents/${agentId}/review` : "/agents"}>
						<FileText className="h-4 w-4" />
						Back to review
					</Link>
				</Button>
			</div>

			<div className={cn("grid grid-cols-2 lg:grid-cols-4", GAP_CARD)}>
				{statsLoading || !stats ? (
					<>
						{[0, 1, 2, 3].map((i) => (
							<Skeleton
								key={i}
								data-testid="stat-skeleton"
								className="h-24 w-full"
							/>
						))}
					</>
				) : (
					<>
						<StatCard
							label="Flagged runs"
							value={formatNumber(flaggedCount)}
							alert={flaggedCount > 0}
						/>
						<StatCard
							label="Runs (7d)"
							value={formatNumber(stats.runs_7d)}
						/>
						<StatCard
							label="Success rate"
							value={`${Math.round(
								(stats.success_rate ?? 0) * 100,
							)}%`}
						/>
						<StatCard
							label="Last run"
							value={
								stats.last_run_at
									? formatRelativeTime(stats.last_run_at)
									: "—"
							}
						/>
					</>
				)}
			</div>
		</div>
	);
}
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
cd client && npx vitest run src/components/agents/TuneHeader.test.tsx
```

Expected: PASS (3 tests).

- [ ] **Step 5: Type check and lint**

Run:

```bash
cd client && npm run tsc && npm run lint
```

Expected: 0 errors.

- [ ] **Step 6: Commit**

```bash
git add client/src/components/agents/TuneHeader.tsx client/src/components/agents/TuneHeader.test.tsx
git commit -m "feat(agents): TuneHeader with stat strip matching other pages"
```

---

## Task 5: `AgentTuneWorkbench` skeleton — header + empty three-pane layout (TDD)

**Files:**
- Create: `client/src/pages/agents/AgentTuneWorkbench.tsx`
- Create: `client/src/pages/agents/AgentTuneWorkbench.test.tsx`

This task lands just the structural shell — header, three empty panes with the "Generate proposal" button in the left pane, and the pane containers. State machine and mutations come in later tasks.

- [ ] **Step 1: Write the failing test**

Create `client/src/pages/agents/AgentTuneWorkbench.test.tsx`:

```tsx
import { describe, it, expect, vi, beforeEach } from "vitest";
import { Routes, Route } from "react-router-dom";

import { renderWithProviders, screen } from "@/test-utils";

const mockUseAgent = vi.fn();
const mockUseAgentRuns = vi.fn();
const mockUseAgentStats = vi.fn();
const mockTuningSession = vi.fn();
const mockTuningDryRun = vi.fn();
const mockApplyTuning = vi.fn();

vi.mock("@/hooks/useAgents", () => ({
	useAgent: (id: string | undefined) => mockUseAgent(id),
}));

vi.mock("@/services/agentRuns", () => ({
	useAgentRuns: (params: unknown) => mockUseAgentRuns(params),
	useAgentRun: () => ({ data: null, isLoading: false }),
}));

vi.mock("@/services/agents", () => ({
	useAgentStats: (id: string | undefined) => mockUseAgentStats(id),
}));

vi.mock("@/services/agentTuning", () => ({
	useTuningSession: () => ({
		mutate: mockTuningSession,
		isPending: false,
	}),
	useTuningDryRun: () => ({
		mutate: mockTuningDryRun,
		isPending: false,
	}),
	useApplyTuning: () => ({ mutate: mockApplyTuning, isPending: false }),
}));

vi.mock("sonner", () => ({
	toast: { success: vi.fn(), error: vi.fn() },
}));

const baseAgent = {
	id: "agent-1",
	name: "Test Parent Agent",
	system_prompt: "You are a helpful triage agent.",
};

const baseStats = {
	agent_id: "agent-1",
	runs_7d: 47,
	success_rate: 0.92,
	avg_duration_ms: 1200,
	total_cost_7d: "0.42",
	last_run_at: "2026-04-22T00:00:00Z",
	runs_by_day: [],
	needs_review: 2,
	unreviewed: 2,
};

function makeRun(id: string) {
	return {
		id,
		agent_id: "agent-1",
		agent_name: "Triage",
		trigger_type: "manual",
		status: "completed",
		iterations_used: 1,
		tokens_used: 100,
		duration_ms: 500,
		asked: `asked-${id}`,
		did: `did-${id}`,
		input: {},
		output: {},
		verdict: "down",
		verdict_note: `note-${id}`,
		created_at: "2026-04-20T00:00:00Z",
		started_at: "2026-04-20T00:00:00Z",
		metadata: {},
	};
}

beforeEach(() => {
	mockUseAgent.mockReturnValue({ data: baseAgent });
	mockUseAgentRuns.mockReturnValue({
		data: { items: [makeRun("a"), makeRun("b")], total: 2, next_cursor: null },
		isLoading: false,
	});
	mockUseAgentStats.mockReturnValue({ data: baseStats, isLoading: false });
	mockTuningSession.mockReset();
	mockTuningDryRun.mockReset();
	mockApplyTuning.mockReset();
});

async function renderPage() {
	const { AgentTuneWorkbench } = await import("./AgentTuneWorkbench");
	return renderWithProviders(
		<Routes>
			<Route path="/agents/:id/tune" element={<AgentTuneWorkbench />} />
			<Route path="/agents/:id" element={<div>agent page</div>} />
		</Routes>,
		{ initialEntries: ["/agents/agent-1/tune"] },
	);
}

describe("AgentTuneWorkbench — shell", () => {
	it("renders the header, stat strip, and three panes", async () => {
		await renderPage();

		expect(
			screen.getByRole("heading", { name: /tune agent/i }),
		).toBeInTheDocument();
		expect(screen.getByText("Flagged runs")).toBeInTheDocument();
		expect(screen.getByText("Runs (7d)")).toBeInTheDocument();
		expect(screen.getByText("47")).toBeInTheDocument();

		expect(screen.getByTestId("tune-pane-flagged")).toBeInTheDocument();
		expect(screen.getByTestId("tune-pane-editor")).toBeInTheDocument();
		expect(screen.getByTestId("tune-pane-impact")).toBeInTheDocument();
	});

	it("lists flagged runs in the left pane", async () => {
		await renderPage();
		const pane = screen.getByTestId("tune-pane-flagged");
		expect(pane).toHaveTextContent("asked-a");
		expect(pane).toHaveTextContent("asked-b");
	});

	it("disables Generate proposal when there are no flagged runs", async () => {
		mockUseAgentRuns.mockReturnValue({
			data: { items: [], total: 0, next_cursor: null },
			isLoading: false,
		});
		await renderPage();
		expect(screen.getByTestId("generate-proposal-button")).toBeDisabled();
	});

	it("enables Generate proposal when there are flagged runs", async () => {
		await renderPage();
		expect(screen.getByTestId("generate-proposal-button")).toBeEnabled();
	});

	it("renders the empty-state CTA in the editor pane when no proposal exists", async () => {
		await renderPage();
		expect(
			screen.getByTestId("editor-empty-generate-button"),
		).toBeInTheDocument();
	});

	it("renders a before-dry-run card in the impact pane with the button disabled", async () => {
		await renderPage();
		const pane = screen.getByTestId("tune-pane-impact");
		expect(pane).toHaveTextContent(/simulate the proposed prompt/i);
		expect(screen.getByTestId("dryrun-button")).toBeDisabled();
	});
});
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
cd client && npx vitest run src/pages/agents/AgentTuneWorkbench.test.tsx
```

Expected: FAIL — `Cannot find module './AgentTuneWorkbench'`.

- [ ] **Step 3: Write minimal implementation**

Create `client/src/pages/agents/AgentTuneWorkbench.tsx`:

```tsx
/**
 * AgentTuneWorkbench — three-pane tuning workbench.
 *
 * Left: flagged runs (expandable transcripts) + Generate proposal CTA.
 * Center: prompt editor (current read-only, proposed editable with diff).
 * Right: dry-run impact panel.
 *
 * State lives in this component; mutations wire up in follow-up tasks.
 */

import { useParams } from "react-router-dom";
import { Sparkles } from "lucide-react";

import { Button } from "@/components/ui/button";

import { FlaggedRunCard } from "@/components/agents/FlaggedRunCard";
import { TuneHeader } from "@/components/agents/TuneHeader";
import {
	TONE_MUTED,
	TYPE_MUTED,
} from "@/components/agents/design-tokens";

import { useAgent } from "@/hooks/useAgents";
import { useAgentRuns } from "@/services/agentRuns";
import { useAgentStats } from "@/services/agents";
import { cn } from "@/lib/utils";
import type { components } from "@/lib/v1";

type AgentRun = components["schemas"]["AgentRunResponse"];

export function AgentTuneWorkbench() {
	const { id: agentId } = useParams<{ id: string }>();

	const { data: agent } = useAgent(agentId);
	const { data: stats, isLoading: statsLoading } = useAgentStats(agentId);
	const { data: flaggedResp, isLoading: flaggedLoading } = useAgentRuns({
		agentId,
		verdict: "down",
	});

	const flagged: AgentRun[] = (flaggedResp?.items ?? []) as AgentRun[];
	const canGenerate = flagged.length > 0;

	function handleGenerate() {
		// Wired up in Task 6.
	}

	return (
		<div
			className="mx-auto flex max-w-[1400px] flex-col gap-6 p-6 lg:p-8"
			data-testid="agent-tune-workbench"
		>
			<TuneHeader
				agentId={agentId}
				agentName={agent?.name}
				flaggedCount={flagged.length}
				stats={stats ?? null}
				statsLoading={statsLoading}
			/>

			<div className="grid grid-cols-1 gap-4 lg:grid-cols-[320px_1fr_360px]">
				{/* Left: flagged runs */}
				<div
					className="flex flex-col gap-3"
					data-testid="tune-pane-flagged"
				>
					<div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
						Flagged runs ({flagged.length})
					</div>
					{flaggedLoading ? (
						<div className={cn(TYPE_MUTED)}>Loading runs…</div>
					) : flagged.length === 0 ? (
						<div
							className={cn(
								"rounded-md border bg-muted/20 p-4 text-center",
								TYPE_MUTED,
								TONE_MUTED,
							)}
						>
							No flagged runs. Mark a run thumbs-down from the runs
							tab to tune against it.
						</div>
					) : (
						<div className="flex flex-col gap-2">
							{flagged.map((r) => (
								<FlaggedRunCard key={r.id} run={r} />
							))}
						</div>
					)}
					<Button
						type="button"
						data-testid="generate-proposal-button"
						disabled={!canGenerate}
						onClick={handleGenerate}
					>
						<Sparkles className="h-3.5 w-3.5" />
						Generate proposal from {flagged.length} run
						{flagged.length === 1 ? "" : "s"}
					</Button>
				</div>

				{/* Center: prompt editor */}
				<div
					className="flex flex-col gap-3"
					data-testid="tune-pane-editor"
				>
					<div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
						Prompt editor
					</div>
					<div className="rounded-md border bg-muted/20 p-6 text-center">
						<p className={cn("mb-3", TYPE_MUTED, TONE_MUTED)}>
							I&apos;ll read the flagged runs and suggest one
							consolidated prompt change.
						</p>
						<Button
							type="button"
							data-testid="editor-empty-generate-button"
							disabled={!canGenerate}
							onClick={handleGenerate}
						>
							<Sparkles className="h-3.5 w-3.5" />
							Generate proposal
						</Button>
					</div>
				</div>

				{/* Right: impact */}
				<div
					className="flex flex-col gap-3"
					data-testid="tune-pane-impact"
				>
					<div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
						Impact
					</div>
					<div className="rounded-md border bg-muted/20 p-4">
						<p className={cn("mb-3", TYPE_MUTED, TONE_MUTED)}>
							Simulate the proposed prompt against the flagged
							runs to see if it changes behavior before going
							live.
						</p>
						<Button
							type="button"
							data-testid="dryrun-button"
							variant="outline"
							disabled
						>
							Run dry-run
						</Button>
					</div>
				</div>
			</div>
		</div>
	);
}

export default AgentTuneWorkbench;
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
cd client && npx vitest run src/pages/agents/AgentTuneWorkbench.test.tsx
```

Expected: PASS (6 tests).

- [ ] **Step 5: Type check and lint**

Run:

```bash
cd client && npm run tsc && npm run lint
```

Expected: 0 errors.

- [ ] **Step 6: Commit**

```bash
git add client/src/pages/agents/AgentTuneWorkbench.tsx client/src/pages/agents/AgentTuneWorkbench.test.tsx
git commit -m "feat(agents): AgentTuneWorkbench shell with three panes"
```

---

## Task 6: Wire up proposal generation and the HasProposal state (TDD)

**Files:**
- Modify: `client/src/pages/agents/AgentTuneWorkbench.tsx`
- Modify: `client/src/pages/agents/AgentTuneWorkbench.test.tsx`

Adds: local state for `proposal` and `edits`, `useTuningSession` mutation wired to both Generate buttons, the editable textarea in the center pane, the `Current (collapsed)` region, `PromptDiffViewer`, and the `[Discard]` / `[Apply live]` footer actions. `Apply live` still no-ops in this task — wired up in Task 7.

- [ ] **Step 1: Add failing tests**

Append to `client/src/pages/agents/AgentTuneWorkbench.test.tsx`:

```tsx
import { waitFor } from "@/test-utils";

const sampleProposal = {
	summary: "Tighten routing rules for password resets.",
	proposed_prompt:
		"You are a helpful triage agent. Always route password resets to Support.",
	affected_run_ids: ["a", "b"],
};

describe("AgentTuneWorkbench — generate proposal", () => {
	beforeEach(() => {
		mockTuningSession.mockImplementation((_args, opts) => {
			opts?.onSuccess?.(sampleProposal);
		});
	});

	it("calls useTuningSession when the left-pane button is clicked", async () => {
		const { user } = await renderPage();
		await user.click(screen.getByTestId("generate-proposal-button"));
		await waitFor(() => {
			expect(mockTuningSession).toHaveBeenCalledWith(
				expect.objectContaining({
					params: { path: { agent_id: "agent-1" } },
				}),
				expect.any(Object),
			);
		});
	});

	it("calls useTuningSession when the empty-state editor button is clicked", async () => {
		const { user } = await renderPage();
		await user.click(
			screen.getByTestId("editor-empty-generate-button"),
		);
		await waitFor(() => {
			expect(mockTuningSession).toHaveBeenCalled();
		});
	});

	it("renders the editable textarea with the proposal after generate", async () => {
		const { user } = await renderPage();
		await user.click(screen.getByTestId("generate-proposal-button"));
		const textarea = await screen.findByTestId(
			"proposal-textarea",
		);
		expect(textarea).toHaveValue(sampleProposal.proposed_prompt);
	});

	it("renders the diff viewer after a proposal is generated", async () => {
		const { user } = await renderPage();
		await user.click(screen.getByTestId("generate-proposal-button"));
		expect(
			await screen.findByTestId("prompt-diff-viewer"),
		).toBeInTheDocument();
	});

	it("edits to the textarea update the diff viewer content", async () => {
		const { user } = await renderPage();
		await user.click(screen.getByTestId("generate-proposal-button"));
		const textarea = (await screen.findByTestId(
			"proposal-textarea",
		)) as HTMLTextAreaElement;
		await user.clear(textarea);
		await user.type(textarea, "Brand new prompt.");
		expect(textarea).toHaveValue("Brand new prompt.");
		expect(screen.getByText(/brand new prompt\./i)).toBeInTheDocument();
	});

	it("Discard returns to the empty state", async () => {
		const { user } = await renderPage();
		await user.click(screen.getByTestId("generate-proposal-button"));
		await screen.findByTestId("proposal-textarea");
		await user.click(screen.getByTestId("discard-button"));
		expect(screen.queryByTestId("proposal-textarea")).toBeNull();
		expect(
			screen.getByTestId("editor-empty-generate-button"),
		).toBeInTheDocument();
	});
});
```

- [ ] **Step 2: Run the new tests to verify they fail**

Run:

```bash
cd client && npx vitest run src/pages/agents/AgentTuneWorkbench.test.tsx -t "generate proposal"
```

Expected: the 6 new tests FAIL (textarea / diff viewer not rendered, discard button missing, mutations not wired).

- [ ] **Step 3: Update the page to wire the HasProposal state**

Replace the contents of `client/src/pages/agents/AgentTuneWorkbench.tsx` with:

```tsx
/**
 * AgentTuneWorkbench — three-pane tuning workbench.
 *
 * Left: flagged runs (expandable transcripts) + Generate proposal CTA.
 * Center: prompt editor (current read-only, proposed editable with diff).
 * Right: dry-run impact panel.
 */

import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { Check, ChevronDown, Loader2, Sparkles, X } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";

import { FlaggedRunCard } from "@/components/agents/FlaggedRunCard";
import { PromptDiffViewer } from "@/components/agents/PromptDiffViewer";
import { TuneHeader } from "@/components/agents/TuneHeader";
import {
	TONE_MUTED,
	TYPE_LABEL_UPPERCASE,
	TYPE_MUTED,
} from "@/components/agents/design-tokens";

import { useAgent } from "@/hooks/useAgents";
import { useAgentRuns } from "@/services/agentRuns";
import { useAgentStats } from "@/services/agents";
import {
	useTuningSession,
	type ConsolidatedProposal,
} from "@/services/agentTuning";
import { cn } from "@/lib/utils";
import type { components } from "@/lib/v1";

type AgentRun = components["schemas"]["AgentRunResponse"];

export function AgentTuneWorkbench() {
	const { id: agentId } = useParams<{ id: string }>();

	const { data: agent } = useAgent(agentId);
	const { data: stats, isLoading: statsLoading } = useAgentStats(agentId);
	const { data: flaggedResp, isLoading: flaggedLoading } = useAgentRuns({
		agentId,
		verdict: "down",
	});

	const tuningSession = useTuningSession();

	const flagged: AgentRun[] = (flaggedResp?.items ?? []) as AgentRun[];
	const canGenerate = flagged.length > 0 && !tuningSession.isPending;

	const [proposal, setProposal] = useState<ConsolidatedProposal | null>(null);
	const [edits, setEdits] = useState<string>("");
	const [currentOpen, setCurrentOpen] = useState(false);

	const currentPrompt =
		(agent as unknown as { system_prompt?: string })?.system_prompt ?? "";

	useEffect(() => {
		if (proposal) {
			setEdits(proposal.proposed_prompt);
		}
	}, [proposal]);

	function handleGenerate() {
		if (!agentId) return;
		tuningSession.mutate(
			{ params: { path: { agent_id: agentId } } },
			{
				onSuccess: (data) => {
					setProposal(data as ConsolidatedProposal);
				},
				onError: () => toast.error("Failed to generate proposal"),
			},
		);
	}

	function handleDiscard() {
		setProposal(null);
		setEdits("");
	}

	return (
		<div
			className="mx-auto flex max-w-[1400px] flex-col gap-6 p-6 lg:p-8"
			data-testid="agent-tune-workbench"
		>
			<TuneHeader
				agentId={agentId}
				agentName={agent?.name}
				flaggedCount={flagged.length}
				stats={stats ?? null}
				statsLoading={statsLoading}
			/>

			<div className="grid grid-cols-1 gap-4 lg:grid-cols-[320px_1fr_360px]">
				{/* Left: flagged runs */}
				<div
					className="flex flex-col gap-3"
					data-testid="tune-pane-flagged"
				>
					<div
						className={cn(TYPE_LABEL_UPPERCASE, "text-muted-foreground")}
					>
						Flagged runs ({flagged.length})
					</div>
					{flaggedLoading ? (
						<Skeleton className="h-24 w-full" />
					) : flagged.length === 0 ? (
						<div
							className={cn(
								"rounded-md border bg-muted/20 p-4 text-center",
								TYPE_MUTED,
								TONE_MUTED,
							)}
						>
							No flagged runs. Mark a run thumbs-down from the
							runs tab to tune against it.
						</div>
					) : (
						<div className="flex flex-col gap-2">
							{flagged.map((r) => (
								<FlaggedRunCard key={r.id} run={r} />
							))}
						</div>
					)}
					<Button
						type="button"
						data-testid="generate-proposal-button"
						disabled={!canGenerate}
						onClick={handleGenerate}
					>
						{tuningSession.isPending ? (
							<Loader2 className="h-3.5 w-3.5 animate-spin" />
						) : (
							<Sparkles className="h-3.5 w-3.5" />
						)}
						{proposal ? "Re-generate" : `Generate proposal from ${flagged.length} run${flagged.length === 1 ? "" : "s"}`}
					</Button>
				</div>

				{/* Center: prompt editor */}
				<div
					className="flex flex-col gap-3"
					data-testid="tune-pane-editor"
				>
					<div
						className={cn(TYPE_LABEL_UPPERCASE, "text-muted-foreground")}
					>
						Prompt editor
					</div>

					{/* Current prompt (collapsible) */}
					<div className="rounded-md border bg-card">
						<button
							type="button"
							data-testid="current-prompt-toggle"
							onClick={() => setCurrentOpen((o) => !o)}
							className="flex w-full items-center justify-between px-3 py-2 text-left text-xs"
							aria-expanded={currentOpen}
						>
							<span className="font-medium">Current prompt</span>
							<ChevronDown
								className={cn(
									"h-3 w-3 transition-transform",
									currentOpen ? "rotate-0" : "-rotate-90",
								)}
							/>
						</button>
						{currentOpen ? (
							<pre className="max-h-60 overflow-y-auto whitespace-pre-wrap border-t px-3 py-2 font-mono text-[11.5px] text-muted-foreground">
								{currentPrompt || "(no system prompt set)"}
							</pre>
						) : null}
					</div>

					{/* Proposed prompt */}
					{tuningSession.isPending ? (
						<div className="rounded-md border bg-card p-4">
							<div className={cn("mb-2 text-xs", TONE_MUTED)}>
								Building proposal…
							</div>
							<Skeleton className="h-32 w-full" />
						</div>
					) : !proposal ? (
						<div className="rounded-md border bg-muted/20 p-6 text-center">
							<p className={cn("mb-3", TYPE_MUTED, TONE_MUTED)}>
								I&apos;ll read the flagged runs and suggest one
								consolidated prompt change.
							</p>
							<Button
								type="button"
								data-testid="editor-empty-generate-button"
								disabled={!canGenerate}
								onClick={handleGenerate}
							>
								<Sparkles className="h-3.5 w-3.5" />
								Generate proposal
							</Button>
						</div>
					) : (
						<div className="flex flex-col gap-3">
							<div className="rounded-md border bg-card">
								<div className="border-b px-3 py-2 text-xs font-medium">
									Proposed prompt (editable)
								</div>
								<Textarea
									data-testid="proposal-textarea"
									value={edits}
									onChange={(e) => setEdits(e.target.value)}
									rows={12}
									className="resize-y border-0 font-mono text-[12px] focus-visible:ring-0"
								/>
							</div>
							{proposal.summary ? (
								<p
									className={cn(
										"italic",
										TYPE_MUTED,
										TONE_MUTED,
									)}
								>
									{proposal.summary}
								</p>
							) : null}
							<PromptDiffViewer
								before={currentPrompt}
								after={edits}
							/>
							<div className="flex items-center justify-end gap-2">
								<Button
									type="button"
									variant="outline"
									size="sm"
									data-testid="discard-button"
									onClick={handleDiscard}
								>
									<X className="h-3.5 w-3.5" />
									Discard
								</Button>
								<Button
									type="button"
									size="sm"
									data-testid="apply-button"
									disabled
								>
									<Check className="h-3.5 w-3.5" />
									Apply live
								</Button>
							</div>
						</div>
					)}
				</div>

				{/* Right: impact */}
				<div
					className="flex flex-col gap-3"
					data-testid="tune-pane-impact"
				>
					<div
						className={cn(TYPE_LABEL_UPPERCASE, "text-muted-foreground")}
					>
						Impact
					</div>
					<div className="rounded-md border bg-muted/20 p-4">
						<p className={cn("mb-3", TYPE_MUTED, TONE_MUTED)}>
							Simulate the proposed prompt against the flagged
							runs to see if it changes behavior before going
							live.
						</p>
						<Button
							type="button"
							data-testid="dryrun-button"
							variant="outline"
							disabled
						>
							Run dry-run
						</Button>
					</div>
				</div>
			</div>
		</div>
	);
}

export default AgentTuneWorkbench;
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
cd client && npx vitest run src/pages/agents/AgentTuneWorkbench.test.tsx
```

Expected: PASS (all 12 tests — 6 from Task 5 + 6 from this task).

- [ ] **Step 5: Type check and lint**

Run:

```bash
cd client && npm run tsc && npm run lint
```

Expected: 0 errors.

- [ ] **Step 6: Commit**

```bash
git add client/src/pages/agents/AgentTuneWorkbench.tsx client/src/pages/agents/AgentTuneWorkbench.test.tsx
git commit -m "feat(agents): wire proposal generation, editable textarea, diff"
```

---

## Task 7: Wire up Apply live (TDD)

**Files:**
- Modify: `client/src/pages/agents/AgentTuneWorkbench.tsx`
- Modify: `client/src/pages/agents/AgentTuneWorkbench.test.tsx`

Apply calls `useApplyTuning` with **`edits`** (not `proposal.proposed_prompt`), invalidates queries, toasts, and navigates to `/agents/:id`.

- [ ] **Step 1: Add failing tests**

Append to `client/src/pages/agents/AgentTuneWorkbench.test.tsx`:

```tsx
import { useLocation } from "react-router-dom";

function LocationProbe() {
	const loc = useLocation();
	return <div data-testid="location">{loc.pathname}</div>;
}

async function renderPageWithProbe() {
	const { AgentTuneWorkbench } = await import("./AgentTuneWorkbench");
	return renderWithProviders(
		<Routes>
			<Route
				path="/agents/:id/tune"
				element={
					<>
						<AgentTuneWorkbench />
						<LocationProbe />
					</>
				}
			/>
			<Route
				path="/agents/:id"
				element={<LocationProbe />}
			/>
		</Routes>,
		{ initialEntries: ["/agents/agent-1/tune"] },
	);
}

describe("AgentTuneWorkbench — apply", () => {
	beforeEach(() => {
		mockTuningSession.mockImplementation((_args, opts) => {
			opts?.onSuccess?.(sampleProposal);
		});
		mockApplyTuning.mockImplementation((_args, opts) => {
			opts?.onSuccess?.({
				agent_id: "agent-1",
				history_id: "h-1",
				affected_run_ids: ["a", "b"],
			});
		});
	});

	it("apply sends the current textarea contents, not the original proposal", async () => {
		const { user } = await renderPageWithProbe();
		await user.click(screen.getByTestId("generate-proposal-button"));
		const textarea = (await screen.findByTestId(
			"proposal-textarea",
		)) as HTMLTextAreaElement;
		await user.clear(textarea);
		await user.type(textarea, "Hand-edited final prompt.");
		await user.click(screen.getByTestId("apply-button"));

		await waitFor(() => {
			expect(mockApplyTuning).toHaveBeenCalledWith(
				expect.objectContaining({
					params: { path: { agent_id: "agent-1" } },
					body: { new_prompt: "Hand-edited final prompt." },
				}),
				expect.any(Object),
			);
		});
	});

	it("apply navigates to /agents/:id on success", async () => {
		const { user } = await renderPageWithProbe();
		await user.click(screen.getByTestId("generate-proposal-button"));
		await screen.findByTestId("proposal-textarea");
		await user.click(screen.getByTestId("apply-button"));
		await waitFor(() => {
			expect(screen.getByTestId("location")).toHaveTextContent(
				"/agents/agent-1",
			);
		});
	});
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
cd client && npx vitest run src/pages/agents/AgentTuneWorkbench.test.tsx -t "apply"
```

Expected: FAIL — apply-button is disabled / onClick not wired.

- [ ] **Step 3: Wire up apply in the page**

In `client/src/pages/agents/AgentTuneWorkbench.tsx`:

Add to imports:

```tsx
import { useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";

import {
	useApplyTuning,
	useTuningSession,
	type ConsolidatedProposal,
} from "@/services/agentTuning";
```

Inside `AgentTuneWorkbench`, after `const tuningSession = useTuningSession();`, add:

```tsx
const applyTuning = useApplyTuning();
const navigate = useNavigate();
const queryClient = useQueryClient();

function handleApply() {
	if (!agentId) return;
	applyTuning.mutate(
		{
			params: { path: { agent_id: agentId } },
			body: { new_prompt: edits },
		},
		{
			onSuccess: () => {
				toast.success("Prompt updated");
				queryClient.invalidateQueries({
					queryKey: ["get", "/api/agents"],
				});
				queryClient.invalidateQueries({ queryKey: ["agent-runs"] });
				navigate(`/agents/${agentId}`);
			},
			onError: () => toast.error("Failed to apply tuning"),
		},
	);
}
```

Replace the apply button JSX:

```tsx
<Button
	type="button"
	size="sm"
	data-testid="apply-button"
	disabled={applyTuning.isPending || !edits.trim()}
	onClick={handleApply}
>
	{applyTuning.isPending ? (
		<Loader2 className="h-3.5 w-3.5 animate-spin" />
	) : (
		<Check className="h-3.5 w-3.5" />
	)}
	Apply live
</Button>
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
cd client && npx vitest run src/pages/agents/AgentTuneWorkbench.test.tsx
```

Expected: PASS (all 14 tests).

- [ ] **Step 5: Type check and lint**

Run:

```bash
cd client && npm run tsc && npm run lint
```

Expected: 0 errors.

- [ ] **Step 6: Commit**

```bash
git add client/src/pages/agents/AgentTuneWorkbench.tsx client/src/pages/agents/AgentTuneWorkbench.test.tsx
git commit -m "feat(agents): apply tuning sends textarea contents, not original"
```

---

## Task 8: Wire up dry-run impact pane (TDD)

**Files:**
- Modify: `client/src/pages/agents/AgentTuneWorkbench.tsx`
- Modify: `client/src/pages/agents/AgentTuneWorkbench.test.tsx`

Dry-run becomes clickable once a proposal exists, sends the current textarea contents, and replaces results in place on re-run.

- [ ] **Step 1: Add failing tests**

Append to `client/src/pages/agents/AgentTuneWorkbench.test.tsx`:

```tsx
const sampleDryRun = {
	results: [
		{
			run_id: "a",
			would_still_decide_same: false,
			reasoning: "Now routes to Support",
			confidence: 0.9,
		},
		{
			run_id: "b",
			would_still_decide_same: true,
			reasoning: "Still answers itself",
			confidence: 0.7,
		},
	],
};

describe("AgentTuneWorkbench — dry-run", () => {
	beforeEach(() => {
		mockTuningSession.mockImplementation((_args, opts) => {
			opts?.onSuccess?.(sampleProposal);
		});
		mockTuningDryRun.mockImplementation((_args, opts) => {
			opts?.onSuccess?.(sampleDryRun);
		});
	});

	it("enables the dry-run button once a proposal exists", async () => {
		const { user } = await renderPage();
		expect(screen.getByTestId("dryrun-button")).toBeDisabled();
		await user.click(screen.getByTestId("generate-proposal-button"));
		await screen.findByTestId("proposal-textarea");
		expect(screen.getByTestId("dryrun-button")).toBeEnabled();
	});

	it("dry-run sends the current textarea contents", async () => {
		const { user } = await renderPage();
		await user.click(screen.getByTestId("generate-proposal-button"));
		const textarea = (await screen.findByTestId(
			"proposal-textarea",
		)) as HTMLTextAreaElement;
		await user.clear(textarea);
		await user.type(textarea, "Edited proposed prompt.");
		await user.click(screen.getByTestId("dryrun-button"));
		await waitFor(() => {
			expect(mockTuningDryRun).toHaveBeenCalledWith(
				expect.objectContaining({
					params: { path: { agent_id: "agent-1" } },
					body: { proposed_prompt: "Edited proposed prompt." },
				}),
				expect.any(Object),
			);
		});
	});

	it("renders per-run dry-run results after the call succeeds", async () => {
		const { user } = await renderPage();
		await user.click(screen.getByTestId("generate-proposal-button"));
		await screen.findByTestId("proposal-textarea");
		await user.click(screen.getByTestId("dryrun-button"));
		await screen.findByTestId("dryrun-results");
		expect(screen.getByText(/1 of 2/i)).toBeInTheDocument();
		expect(screen.getByText(/now routes to support/i)).toBeInTheDocument();
		expect(screen.getByText(/still answers itself/i)).toBeInTheDocument();
	});

	it("re-running dry-run replaces the prior results", async () => {
		const { user } = await renderPage();
		await user.click(screen.getByTestId("generate-proposal-button"));
		await screen.findByTestId("proposal-textarea");
		await user.click(screen.getByTestId("dryrun-button"));
		await screen.findByTestId("dryrun-results");

		mockTuningDryRun.mockImplementation((_args, opts) => {
			opts?.onSuccess?.({
				results: [
					{
						run_id: "a",
						would_still_decide_same: false,
						reasoning: "Different outcome this time",
						confidence: 0.8,
					},
				],
			});
		});

		await user.click(screen.getByTestId("dryrun-button"));
		await waitFor(() => {
			expect(
				screen.queryByText(/still answers itself/i),
			).toBeNull();
			expect(
				screen.getByText(/different outcome this time/i),
			).toBeInTheDocument();
		});
	});
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
cd client && npx vitest run src/pages/agents/AgentTuneWorkbench.test.tsx -t "dry-run"
```

Expected: FAIL — dry-run button disabled, no results render.

- [ ] **Step 3: Wire up dry-run**

In `client/src/pages/agents/AgentTuneWorkbench.tsx`:

Update imports:

```tsx
import { Badge } from "@/components/ui/badge";

import {
	useApplyTuning,
	useTuningDryRun,
	useTuningSession,
	type ConsolidatedDryRunResponse,
	type ConsolidatedProposal,
} from "@/services/agentTuning";
```

Add state + mutation inside `AgentTuneWorkbench`, near `const applyTuning = useApplyTuning();`:

```tsx
const tuningDryRun = useTuningDryRun();
const [dryRun, setDryRun] = useState<ConsolidatedDryRunResponse | null>(null);

function handleDryRun() {
	if (!agentId || !edits.trim()) return;
	tuningDryRun.mutate(
		{
			params: { path: { agent_id: agentId } },
			body: { proposed_prompt: edits },
		},
		{
			onSuccess: (data) => {
				setDryRun(data as ConsolidatedDryRunResponse);
			},
			onError: () => toast.error("Dry-run failed"),
		},
	);
}
```

Extend `handleDiscard` to also clear dry-run:

```tsx
function handleDiscard() {
	setProposal(null);
	setEdits("");
	setDryRun(null);
}
```

Replace the impact pane JSX (the div marked `data-testid="tune-pane-impact"`) with:

```tsx
<div
	className="flex flex-col gap-3"
	data-testid="tune-pane-impact"
>
	<div
		className={cn(TYPE_LABEL_UPPERCASE, "text-muted-foreground")}
	>
		Impact
	</div>
	<div className="rounded-md border bg-muted/20 p-4">
		<p className={cn("mb-3", TYPE_MUTED, TONE_MUTED)}>
			Simulate the proposed prompt against the flagged runs
			to see if it changes behavior before going live.
		</p>
		<Button
			type="button"
			data-testid="dryrun-button"
			variant="outline"
			disabled={
				!proposal || !edits.trim() || tuningDryRun.isPending
			}
			onClick={handleDryRun}
		>
			{tuningDryRun.isPending ? (
				<Loader2 className="h-3.5 w-3.5 animate-spin" />
			) : null}
			Run dry-run
		</Button>
	</div>
	{dryRun ? (
		<div
			className="flex flex-col gap-2"
			data-testid="dryrun-results"
		>
			{(() => {
				const total = dryRun.results.length;
				const wouldChange = dryRun.results.filter(
					(r) => !r.would_still_decide_same,
				).length;
				return (
					<p className={cn("text-xs", TONE_MUTED)}>
						{wouldChange} of {total} would change
						behavior with the new prompt.
					</p>
				);
			})()}
			{dryRun.results.map((r) => (
				<div
					key={r.run_id}
					className="rounded-md border bg-card p-2 text-xs"
				>
					<div className="flex items-center justify-between gap-2">
						<span className="font-mono text-[11px] text-muted-foreground">
							{r.run_id.slice(0, 8)}…
						</span>
						<Badge
							variant="outline"
							className={cn(
								"text-[10.5px]",
								r.would_still_decide_same
									? "border-yellow-500/40 text-yellow-500"
									: "border-emerald-500/40 text-emerald-500",
							)}
						>
							{r.would_still_decide_same
								? "Still wrong"
								: "Would change"}
						</Badge>
					</div>
					<div className={cn("mt-1", TONE_MUTED)}>
						{r.reasoning}
					</div>
					<div className="mt-0.5 text-[10.5px] text-muted-foreground">
						confidence: {Math.round(r.confidence * 100)}%
					</div>
				</div>
			))}
		</div>
	) : null}
</div>
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
cd client && npx vitest run src/pages/agents/AgentTuneWorkbench.test.tsx
```

Expected: PASS (all 18 tests).

- [ ] **Step 5: Type check and lint**

Run:

```bash
cd client && npm run tsc && npm run lint
```

Expected: 0 errors.

- [ ] **Step 6: Commit**

```bash
git add client/src/pages/agents/AgentTuneWorkbench.tsx client/src/pages/agents/AgentTuneWorkbench.test.tsx
git commit -m "feat(agents): wire dry-run impact pane with per-run results"
```

---

## Task 9: Swap the route, delete legacy page

**Files:**
- Modify: `client/src/App.tsx`
- Delete: `client/src/pages/agents/AgentTunePage.tsx`
- Delete: `client/src/pages/agents/AgentTunePage.test.tsx`

- [ ] **Step 1: Find and update the route import in `App.tsx`**

Run:

```bash
grep -n "AgentTunePage" client/src/App.tsx
```

Identify the lazy import and route element for `AgentTunePage`.

Replace the `AgentTunePage` lazy import with `AgentTuneWorkbench`:

```tsx
const AgentTuneWorkbench = lazyWithReload(() =>
	import("@/pages/agents/AgentTuneWorkbench").then((m) => ({
		default: m.AgentTuneWorkbench,
	})),
);
```

Replace the route `element`:

```tsx
<Route
	path="agents/:id/tune"
	element={<AgentTuneWorkbench />}
/>
```

- [ ] **Step 2: Delete the legacy page + its tests**

Run:

```bash
git rm client/src/pages/agents/AgentTunePage.tsx client/src/pages/agents/AgentTunePage.test.tsx
```

- [ ] **Step 3: Confirm no remaining imports of `AgentTunePage`**

Run:

```bash
grep -rn "AgentTunePage" client/src/ || echo "no references"
```

Expected: `no references`.

- [ ] **Step 4: Run the full client unit suite**

Run:

```bash
./test.sh client unit
```

Expected: PASS. No unrelated test fails. New workbench tests included.

- [ ] **Step 5: Type check and lint**

Run:

```bash
cd client && npm run tsc && npm run lint
```

Expected: 0 errors.

- [ ] **Step 6: Commit**

```bash
git add client/src/App.tsx client/src/pages/agents/AgentTunePage.tsx client/src/pages/agents/AgentTunePage.test.tsx
git commit -m "feat(agents): route /agents/:id/tune to AgentTuneWorkbench"
```

---

## Task 10: E2E coverage — generate → edit → dry-run → apply

**Files:**
- Modify: `client/e2e/<existing-agents-spec>.spec.ts` (or add a new spec if none covers `/tune`)

Look for an existing Playwright spec that visits `/agents/:id/tune`:

```bash
grep -rln "/tune" client/e2e/ 2>/dev/null || echo "no spec"
```

- [ ] **Step 1: If no existing spec, create one**

If `grep` returned `no spec`, create `client/e2e/agents.tune.spec.ts`:

```ts
import { test, expect } from "@playwright/test";
import {
	loginAsPlatformAdmin,
	seedFlaggedAgentRun,
} from "./helpers";

test.describe("Agent tune workbench", () => {
	test("generate → hand-edit → apply updates the prompt", async ({
		page,
	}) => {
		await loginAsPlatformAdmin(page);
		const { agentId } = await seedFlaggedAgentRun(page);

		await page.goto(`/agents/${agentId}/tune`);

		await expect(
			page.getByRole("heading", { name: /tune agent/i }),
		).toBeVisible();
		await expect(page.getByTestId("tune-pane-flagged")).toBeVisible();
		await expect(page.getByTestId("tune-pane-editor")).toBeVisible();
		await expect(page.getByTestId("tune-pane-impact")).toBeVisible();

		await page.getByTestId("generate-proposal-button").click();

		const textarea = page.getByTestId("proposal-textarea");
		await expect(textarea).toBeVisible();

		await textarea.fill(
			"You are a helpful triage agent. E2E edited prompt.",
		);

		await page.getByTestId("apply-button").click();

		await expect(page).toHaveURL(
			new RegExp(`/agents/${agentId}$`),
		);
	});
});
```

Note: `seedFlaggedAgentRun` helper may already exist. If not, this task includes extending `client/e2e/helpers.ts` to seed an agent with one flagged run. Check first with `grep -n "seedFlaggedAgentRun\|self-seed" client/e2e/helpers.ts`. If missing, implement using the same pattern as other self-seeding helpers in that file (create agent via `POST /api/agents`, trigger a run, mark it `verdict=down` via `POST /api/agent-runs/:id/verdict`).

- [ ] **Step 2: If an existing spec covers `/tune`, extend it**

Update the existing test to use the new test-ids (`generate-proposal-button`, `proposal-textarea`, `apply-button`) instead of the legacy `propose-button` / `proposal-after`.

- [ ] **Step 3: Run the Playwright spec**

Run:

```bash
./test.sh client e2e client/e2e/agents.tune.spec.ts
```

(Substitute the actual filename if you extended an existing spec.)

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add client/e2e/
git commit -m "test(e2e): cover tune workbench generate → edit → apply flow"
```

---

## Task 11: Pre-completion verification

No new code. Just the full verification sequence from `CLAUDE.md`.

- [ ] **Step 1: Confirm dev stack is running**

Run:

```bash
docker ps --filter "name=bifrost-dev-api" --format "{{.Names}}" | grep -q "bifrost-dev-api" || ./debug.sh
```

Expected: dev stack up.

- [ ] **Step 2: Frontend type check and lint**

Run:

```bash
cd client && npm run tsc && npm run lint
```

Expected: 0 errors, 0 warnings we introduced.

- [ ] **Step 3: Full client unit suite**

Run:

```bash
./test.sh client unit
```

Expected: PASS.

- [ ] **Step 4: Smoke-test in a browser**

Run:

```bash
./debug.sh
```

Then open `http://localhost:3000/agents`, pick an agent that has flagged runs, click "Tune" from its detail page. Verify:

- Header shows `Tune agent` title and 4 stat cards.
- Left pane lists flagged runs; clicking one expands the transcript.
- Clicking "Generate proposal" shows the editable textarea in the center pane and a real before/after diff below.
- Editing the textarea updates the diff live.
- "Run dry-run" renders per-run result cards in the right pane.
- "Apply live" navigates back to `/agents/:id` and toasts success.

- [ ] **Step 5: Final commit (if any outstanding changes from smoke-test fixes)**

If no fixes were needed, skip.

---

## Self-Review

Running the self-review checklist against the spec:

**Spec coverage:**

- ✅ Three-pane workbench layout (Task 5).
- ✅ Header with stat strip matching other pages (Task 4).
- ✅ Flagged runs with expandable transcripts (Tasks 3, 5).
- ✅ "Generate proposal from N runs" adjacent to flagged runs (Tasks 5, 6).
- ✅ Current prompt collapsible (Task 6).
- ✅ Editable textarea for proposed prompt (Task 6).
- ✅ Real side-by-side diff with `react-diff-viewer-continued` (Tasks 1, 2, 6).
- ✅ Apply sends textarea contents, not original proposal (Task 7).
- ✅ Dry-run first-class pane, replaces prior results (Task 8).
- ✅ Route swap + legacy removal (Task 9).
- ✅ E2E + verification (Tasks 10, 11).
- ✅ Per-run selection intentionally NOT implemented (spec defers to M2; no task attempts it).
- ✅ `ChatBubble` / `ChatBubbleSlot` primitives kept in the codebase; only their usage on this page is removed (done implicitly by deleting `AgentTunePage.tsx`).

**Placeholder scan:** No "TBD", "TODO", "implement later", or "similar to Task N" references. Every code step has full code.

**Type consistency:**

- `ConsolidatedProposal` / `ConsolidatedDryRunResponse` — matches `services/agentTuning.ts` exports.
- `AgentRun` / `AgentRunDetail` — matches `components/schemas/AgentRunResponse` / `AgentRunDetailResponse`.
- Test-ids are consistent across tasks: `generate-proposal-button`, `editor-empty-generate-button`, `proposal-textarea`, `discard-button`, `apply-button`, `dryrun-button`, `dryrun-results`, `tune-pane-flagged/editor/impact`, `flagged-run-toggle`, `current-prompt-toggle`, `prompt-diff-viewer`, `prompt-diff-empty`, `stat-skeleton`.
- Handler names consistent: `handleGenerate`, `handleDiscard`, `handleApply`, `handleDryRun`.
- `edits` (textarea state) is the source of truth for both apply and dry-run bodies.

All checks pass.
