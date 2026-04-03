# Unified Execution Details Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `ExecutionDetails` the single component for both full-page and slideout drawer views, with a responsive single-column embedded layout and a fixed page header.

**Architecture:** Extend `ExecutionDetails`'s existing `embedded` prop to render a mobile-friendly single-column layout. Gut `ExecutionDrawer` to be a thin Sheet wrapper around `<ExecutionDetails embedded />`. Extract compact metadata from `ExecutionSidebar` into a new `ExecutionMetadataBar` component. Add `href` support to `DataTableRow` for middle-click/new-tab.

**Tech Stack:** React, TypeScript, shadcn/ui (Sheet, Card, Collapsible), Zustand, WebSocket streaming

**Spec:** `docs/superpowers/specs/2026-04-03-unified-execution-details-design.md`

---

### Task 1: Create `ExecutionMetadataBar` — compact metadata for embedded header

The current `ExecutionSidebar` renders metadata in separate Card sections. We need a compact inline version for the embedded/slideout header: workflow name, status badge, and a 2x2 metadata grid (who, org, started, duration).

**Files:**
- Create: `client/src/components/execution/ExecutionMetadataBar.tsx`
- Modify: `client/src/components/execution/index.ts`

- [ ] **Step 1: Create `ExecutionMetadataBar` component**

```tsx
// client/src/components/execution/ExecutionMetadataBar.tsx
import { User, Building2, Clock, Timer } from "lucide-react";
import { ExecutionStatusBadge } from "./ExecutionStatusBadge";
import { formatDate } from "@/lib/utils";
import type { components } from "@/lib/v1";

type ExecutionStatus =
	| components["schemas"]["ExecutionStatus"]
	| "Cancelling"
	| "Cancelled";

interface ExecutionMetadataBarProps {
	workflowName: string;
	status: ExecutionStatus;
	executedByName?: string | null;
	orgName?: string | null;
	startedAt?: string | null;
	durationMs?: number | null;
	queuePosition?: number;
	waitReason?: string;
	availableMemoryMb?: number;
	requiredMemoryMb?: number;
}

function formatDuration(ms: number): string {
	if (ms < 1000) return `${ms}ms`;
	if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`;
	const minutes = Math.floor(ms / 60000);
	const seconds = ((ms % 60000) / 1000).toFixed(0);
	return `${minutes}m ${seconds}s`;
}

export function ExecutionMetadataBar({
	workflowName,
	status,
	executedByName,
	orgName,
	startedAt,
	durationMs,
	queuePosition,
	waitReason,
	availableMemoryMb,
	requiredMemoryMb,
}: ExecutionMetadataBarProps) {
	return (
		<div className="space-y-3">
			{/* Workflow name + status */}
			<div className="flex items-center justify-between gap-3 flex-wrap">
				<h3 className="text-lg font-semibold truncate">
					{workflowName}
				</h3>
				<ExecutionStatusBadge
					status={status}
					queuePosition={queuePosition}
					waitReason={waitReason}
					availableMemoryMb={availableMemoryMb}
					requiredMemoryMb={requiredMemoryMb}
				/>
			</div>
			{/* Compact metadata grid */}
			<div className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
				<div className="flex items-center gap-1.5 text-muted-foreground">
					<User className="h-3.5 w-3.5 flex-shrink-0" />
					<span className="truncate">{executedByName || "Unknown"}</span>
				</div>
				<div className="flex items-center gap-1.5 text-muted-foreground">
					<Building2 className="h-3.5 w-3.5 flex-shrink-0" />
					<span className="truncate">{orgName || "Global"}</span>
				</div>
				<div className="flex items-center gap-1.5 text-muted-foreground">
					<Clock className="h-3.5 w-3.5 flex-shrink-0" />
					<span className="truncate">
						{startedAt ? formatDate(startedAt) : "Not started"}
					</span>
				</div>
				<div className="flex items-center gap-1.5 text-muted-foreground">
					<Timer className="h-3.5 w-3.5 flex-shrink-0" />
					<span>
						{durationMs != null
							? formatDuration(durationMs)
							: "In progress..."}
					</span>
				</div>
			</div>
		</div>
	);
}
```

- [ ] **Step 2: Export from barrel**

Add to `client/src/components/execution/index.ts`:

```ts
export { ExecutionMetadataBar } from "./ExecutionMetadataBar";
```

- [ ] **Step 3: Verify types compile**

Run: `cd client && npm run tsc`
Expected: no errors

- [ ] **Step 4: Commit**

```bash
git add client/src/components/execution/ExecutionMetadataBar.tsx client/src/components/execution/index.ts
git commit -m "feat: add ExecutionMetadataBar compact metadata component"
```

---

### Task 2: Add `extrasOnly` mode to `ExecutionSidebar`

The embedded layout renders metadata, error, input, and logs inline. The sidebar's "extra" sections (AI usage, metrics, variables, execution context) go in a collapsible at the bottom. We need a way to render only those extras without the status card, workflow info, input params, and error sections.

**Files:**
- Modify: `client/src/components/execution/ExecutionSidebar.tsx`

- [ ] **Step 1: Add `extrasOnly` prop to `ExecutionSidebar`**

Add to `ExecutionSidebarProps` interface:

```ts
/** When true, only render AI usage, metrics, variables, and execution context — skip status, workflow info, input, and error sections */
extrasOnly?: boolean;
```

Add to the destructured props:

```ts
extrasOnly = false,
```

- [ ] **Step 2: Wrap the skippable sections**

In the component return, wrap the Status Card, Error Section, Workflow Information Card, and Input Parameters Card with `{!extrasOnly && (...)}`:

```tsx
return (
	<div className="space-y-6">
		{!extrasOnly && (
			<>
				{/* Status Card */}
				<Card>...</Card>

				{/* Error Section */}
				{errorMessage && (...)}

				{/* Workflow Information Card */}
				<Card>...</Card>

				{/* Input Parameters - All users */}
				<Card>...</Card>
			</>
		)}

		{/* Execution Context - Platform admins only */}
		{executionContext && (...)}

		{/* Runtime Variables - Platform admins only */}
		{isPlatformAdmin && isComplete && (...)}

		{/* Usage Card */}
		{isComplete && (...)}
	</div>
);
```

- [ ] **Step 3: Verify types compile**

Run: `cd client && npm run tsc`
Expected: no errors

- [ ] **Step 4: Commit**

```bash
git add client/src/components/execution/ExecutionSidebar.tsx
git commit -m "feat: add extrasOnly mode to ExecutionSidebar"
```

---

### Task 3: Add embedded single-column layout to `ExecutionDetails`

Extend the `embedded` prop to render a single-column layout with the ordering: metadata bar → error/result → input data → logs → collapsible extras. Hide page header, rerun/cancel/editor buttons. Keep WebSocket streaming active.

**Files:**
- Modify: `client/src/pages/ExecutionDetails.tsx`

- [ ] **Step 1: Add imports for new components**

At the top of `ExecutionDetails.tsx`, add imports:

```ts
import { ExecutionMetadataBar } from "@/components/execution";
import { PrettyInputDisplay } from "@/components/execution";
import {
	Collapsible,
	CollapsibleContent,
	CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { ChevronDown } from "lucide-react";
```

Note: `PrettyInputDisplay` is already exported from the execution barrel. Check if `Collapsible` and `ChevronDown` are already imported — if so, skip those.

- [ ] **Step 2: Add the embedded layout rendering**

In `ExecutionDetails`, after the existing `if (error || !execution)` block (~line 493) and before the full-page `return`, add an early return for embedded mode. This replaces the current embedded code path (which just renders the same 3-column layout without a header).

```tsx
// Embedded mode — single-column layout for slideout drawer
if (embedded) {
	return (
		<div className="h-full overflow-y-auto">
			<div className="p-4 space-y-4">
				{/* Compact metadata header */}
				<ExecutionMetadataBar
					workflowName={execution.workflow_name}
					status={executionStatus as ExecutionStatus}
					executedByName={execution.executed_by_name}
					orgName={execution.org_name}
					startedAt={execution.started_at}
					durationMs={execution.duration_ms}
					queuePosition={streamState?.queuePosition}
					waitReason={streamState?.waitReason}
					availableMemoryMb={streamState?.availableMemoryMb}
					requiredMemoryMb={streamState?.requiredMemoryMb}
				/>

				{/* Error message */}
				{execution.error_message && (
					<div className="p-3 bg-destructive/10 border border-destructive/20 rounded-lg">
						<div className="flex items-start gap-2">
							<XCircle className="h-4 w-4 text-destructive flex-shrink-0 mt-0.5" />
							<pre className="text-sm whitespace-pre-wrap font-mono text-destructive/90 overflow-x-auto">
								{execution.error_message}
							</pre>
						</div>
					</div>
				)}

				{/* Result */}
				{isComplete && execution.result != null && (
					<ExecutionResultPanel
						result={resultData?.result}
						resultType={resultData?.result_type}
						workflowName={execution.workflow_name}
						isLoading={isLoadingResult}
					/>
				)}

				{/* Input data */}
				{execution.input_data && (
					<div className="space-y-2">
						<h4 className="text-sm font-medium text-muted-foreground">Input Parameters</h4>
						<PrettyInputDisplay
							inputData={execution.input_data as Record<string, unknown>}
							showToggle={true}
							defaultView="pretty"
						/>
					</div>
				)}

				{/* Logs */}
				<ExecutionLogsPanel
					logs={mergedLogs as LogEntry[]}
					status={executionStatus}
					isConnected={isConnected}
					isLoading={isLoadingLogs}
					isPlatformAdmin={isPlatformAdmin}
					maxHeight="50vh"
					embedded
				/>

				{/* Collapsible sections */}
				{/* AI Usage */}
				{isComplete && execution.ai_usage && (execution.ai_usage as AIUsagePublicSimple[]).length > 0 && (
					<CollapsibleSection title="AI Usage" defaultOpen={false}>
						<ExecutionSidebar
							status={execution.status as ExecutionStatus}
							workflowName={execution.workflow_name}
							executedByName={execution.executed_by_name}
							orgName={execution.org_name}
							startedAt={execution.started_at}
							completedAt={execution.completed_at}
							inputData={execution.input_data}
							isComplete={isComplete}
							isPlatformAdmin={isPlatformAdmin}
							isLoading={isLoading}
							variablesData={variablesData}
							peakMemoryBytes={execution.peak_memory_bytes}
							cpuTotalSeconds={execution.cpu_total_seconds}
							durationMs={execution.duration_ms}
							aiUsage={execution.ai_usage}
							aiTotals={execution.ai_totals}
							errorMessage={execution.error_message}
							executionContext={execution.execution_context}
						/>
					</CollapsibleSection>
				)}
			</div>
		</div>
	);
}
```

Wait — rendering the full `ExecutionSidebar` inside a collapsible is clunky. The sidebar has its own cards with status, error, workflow info, input params (all already shown above). We only want the "extra" sections: AI usage, metrics, variables, execution context.

Instead, create a simpler approach: render just the specific collapsible sections inline.

**Revised Step 2:** The embedded return should render the collapsible extras directly:

```tsx
if (embedded) {
	const aiUsageList = execution.ai_usage as AIUsagePublicSimple[] | undefined;
	const hasAiUsage = aiUsageList && aiUsageList.length > 0;
	const hasMetrics = isPlatformAdmin && (execution.peak_memory_bytes || execution.cpu_total_seconds);
	const hasVariables = isPlatformAdmin && isComplete && variablesData && Object.keys(variablesData).length > 0;
	const hasExtras = hasAiUsage || hasMetrics || hasVariables;

	return (
		<div className="h-full overflow-y-auto">
			<div className="p-4 space-y-4">
				{/* Compact metadata header */}
				<ExecutionMetadataBar
					workflowName={execution.workflow_name}
					status={executionStatus as ExecutionStatus}
					executedByName={execution.executed_by_name}
					orgName={execution.org_name}
					startedAt={execution.started_at}
					durationMs={execution.duration_ms}
					queuePosition={streamState?.queuePosition}
					waitReason={streamState?.waitReason}
					availableMemoryMb={streamState?.availableMemoryMb}
					requiredMemoryMb={streamState?.requiredMemoryMb}
				/>

				{/* Error message */}
				{execution.error_message && (
					<div className="p-3 bg-destructive/10 border border-destructive/20 rounded-lg">
						<div className="flex items-start gap-2">
							<XCircle className="h-4 w-4 text-destructive flex-shrink-0 mt-0.5" />
							<pre className="text-sm whitespace-pre-wrap font-mono text-destructive/90 overflow-x-auto">
								{execution.error_message}
							</pre>
						</div>
					</div>
				)}

				{/* Result */}
				{isComplete && execution.result != null && (
					<ExecutionResultPanel
						result={resultData?.result}
						resultType={resultData?.result_type}
						workflowName={execution.workflow_name}
						isLoading={isLoadingResult}
					/>
				)}

				{/* Input data */}
				{execution.input_data && (
					<div className="space-y-2">
						<h4 className="text-sm font-medium text-muted-foreground">Input Parameters</h4>
						<PrettyInputDisplay
							inputData={execution.input_data as Record<string, unknown>}
							showToggle={true}
							defaultView="pretty"
						/>
					</div>
				)}

				{/* Logs */}
				<ExecutionLogsPanel
					logs={mergedLogs as LogEntry[]}
					status={executionStatus}
					isConnected={isConnected}
					isLoading={isLoadingLogs}
					isPlatformAdmin={isPlatformAdmin}
					maxHeight="50vh"
					embedded
				/>

				{/* Extra details — collapsible */}
				{isComplete && hasExtras && (
					<Collapsible>
						<CollapsibleTrigger className="flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground transition-colors w-full py-2 [&[data-state=open]>svg]:rotate-180">
							<ChevronDown className="h-4 w-4 transition-transform duration-200" />
							More details
						</CollapsibleTrigger>
						<CollapsibleContent className="space-y-4 pt-2">
							<ExecutionSidebar
								status={execution.status as ExecutionStatus}
								workflowName={execution.workflow_name}
								executedByName={execution.executed_by_name}
								orgName={execution.org_name}
								startedAt={execution.started_at}
								completedAt={execution.completed_at}
								inputData={execution.input_data}
								isComplete={isComplete}
								isPlatformAdmin={isPlatformAdmin}
								isLoading={isLoading}
								variablesData={variablesData}
								peakMemoryBytes={execution.peak_memory_bytes}
								cpuTotalSeconds={execution.cpu_total_seconds}
								durationMs={execution.duration_ms}
								aiUsage={execution.ai_usage}
								aiTotals={execution.ai_totals}
								errorMessage={execution.error_message}
								executionContext={execution.execution_context}
								extrasOnly
							/>
						</CollapsibleContent>
					</Collapsible>
				)}
			</div>
		</div>
	);
}
```

Note: we pass `extrasOnly` to the sidebar so it only renders AI usage, metrics, variables, and execution context — not the status card, workflow info, input params, or error that are already displayed above.

- [ ] **Step 3: Remove old embedded handling**

The current full-page return (starting ~line 495) has `className={embedded ? "h-full overflow-y-auto" : "h-full overflow-y-auto"}` — both branches are identical. Since embedded now early-returns above, simplify this to just `"h-full overflow-y-auto"`.

- [ ] **Step 4: Verify types compile**

Run: `cd client && npm run tsc`
Expected: no errors

- [ ] **Step 5: Verify lint passes**

Run: `cd client && npm run lint`
Expected: no errors

- [ ] **Step 6: Commit**

```bash
git add client/src/pages/ExecutionDetails.tsx
git commit -m "feat: add single-column embedded layout to ExecutionDetails"
```

---

### Task 4: Gut `ExecutionDrawer` to use `ExecutionDetails`

Replace all custom content in `ExecutionDrawer` with `<ExecutionDetails executionId={...} embedded />`. Keep the Sheet wrapper and sticky header with "Open in new tab" button.

**Files:**
- Modify: `client/src/pages/ExecutionHistory/components/ExecutionDrawer.tsx`

- [ ] **Step 1: Rewrite ExecutionDrawer**

Replace the entire file content:

```tsx
import {
	Sheet,
	SheetContent,
	SheetHeader,
	SheetTitle,
	SheetDescription,
} from "@/components/ui/sheet";
import { Button } from "@/components/ui/button";
import { ExternalLink } from "lucide-react";
import { ExecutionDetails } from "@/pages/ExecutionDetails";

interface ExecutionDrawerProps {
	executionId: string | null;
	open: boolean;
	onOpenChange: (open: boolean) => void;
}

export function ExecutionDrawer({
	executionId,
	open,
	onOpenChange,
}: ExecutionDrawerProps) {
	const handleOpenInNewTab = () => {
		if (executionId) {
			window.open(`/history/${executionId}`, "_blank");
		}
	};

	return (
		<Sheet open={open} onOpenChange={onOpenChange}>
			<SheetContent
				side="right"
				className="w-full sm:max-w-xl md:max-w-2xl overflow-y-auto p-0"
			>
				<div className="sticky top-0 bg-background z-10 px-6 pt-6 pb-4 border-b">
					<SheetHeader>
						<div className="flex items-center justify-between">
							<SheetTitle className="text-lg">
								Execution Details
							</SheetTitle>
							<Button
								variant="outline"
								size="sm"
								onClick={handleOpenInNewTab}
								disabled={!executionId}
							>
								<ExternalLink className="h-4 w-4 mr-2" />
								Open in new tab
							</Button>
						</div>
						<SheetDescription>
							View workflow execution details and logs
						</SheetDescription>
					</SheetHeader>
				</div>

				{executionId && (
					<ExecutionDetails
						executionId={executionId}
						embedded
					/>
				)}
			</SheetContent>
		</Sheet>
	);
}
```

This removes: `useExecution`, `useExecutionLogs`, `useAuth`, `formatDate`, `formatDuration`, `ExecutionLogsPanel`, `ExecutionResultPanel`, `ExecutionStatusBadge`, the custom metadata grid, error display, result/logs rendering — all ~150 lines of duplicated layout.

- [ ] **Step 2: Verify types compile**

Run: `cd client && npm run tsc`
Expected: no errors

- [ ] **Step 3: Verify lint passes**

Run: `cd client && npm run lint`
Expected: no errors

- [ ] **Step 4: Commit**

```bash
git add client/src/pages/ExecutionHistory/components/ExecutionDrawer.tsx
git commit -m "refactor: replace ExecutionDrawer content with embedded ExecutionDetails"
```

---

### Task 5: Fix the full-page header layout

Replace the cramped single-row header with a multi-row layout that breathes on mobile: workflow name on row 1, execution ID + status on row 2, action buttons on row 3 (flex-wrap).

**Files:**
- Modify: `client/src/pages/ExecutionDetails.tsx:502-568`

- [ ] **Step 1: Replace the header block**

Find the existing header (inside `{!embedded && !isEmbed && (` block, the `<div className="sticky top-0 ...">` element). Replace it with:

```tsx
{!embedded && !isEmbed && (
	<div className="sticky top-0 bg-background/80 backdrop-blur-sm border-b z-10">
		<div className="px-6 lg:px-8 py-4 space-y-3">
			{/* Row 1: Back + workflow name */}
			<div className="flex items-center gap-3">
				<Button
					variant="ghost"
					size="icon"
					className="flex-shrink-0"
					onClick={() => navigate("/history")}
				>
					<ArrowLeft className="h-4 w-4" />
				</Button>
				<h1 className="text-2xl font-bold tracking-tight truncate">
					{execution.workflow_name}
				</h1>
			</div>
			{/* Row 2: Execution ID + status */}
			<div className="flex items-center gap-3 flex-wrap pl-11">
				<span className="text-sm text-muted-foreground font-mono">
					{execution.execution_id}
				</span>
				<ExecutionStatusBadge
					status={executionStatus as string}
					queuePosition={streamState?.queuePosition}
					waitReason={streamState?.waitReason}
					availableMemoryMb={streamState?.availableMemoryMb}
					requiredMemoryMb={streamState?.requiredMemoryMb}
				/>
			</div>
			{/* Row 3: Action buttons */}
			<div className="flex gap-2 flex-wrap pl-11">
				{metadata?.workflows?.find(
					(w: WorkflowMetadata) =>
						w.name === execution.workflow_name,
				)?.source_file_path && (
					<Button
						variant="outline"
						size="sm"
						onClick={handleOpenInEditor}
						disabled={isOpeningInEditor}
					>
						{isOpeningInEditor ? (
							<Loader2 className="mr-2 h-4 w-4 animate-spin" />
						) : (
							<Code2 className="mr-2 h-4 w-4" />
						)}
						Open in Editor
					</Button>
				)}
				{isComplete && (
					<Button
						variant="outline"
						size="sm"
						onClick={() => setShowRerunDialog(true)}
						disabled={isRerunning}
					>
						{isRerunning ? (
							<Loader2 className="mr-2 h-4 w-4 animate-spin" />
						) : (
							<RefreshCw className="mr-2 h-4 w-4" />
						)}
						Rerun
					</Button>
				)}
				{(execution.status === "Running" ||
					execution.status === "Pending") && (
					<Button
						variant="outline"
						size="sm"
						onClick={() => setShowCancelDialog(true)}
					>
						<XCircle className="mr-2 h-4 w-4" />
						Cancel
					</Button>
				)}
			</div>
		</div>
	</div>
)}
```

Key changes:
- Title reduced from `text-4xl font-extrabold` to `text-2xl font-bold` — shows workflow name instead of generic "Execution Details"
- Execution ID on its own row in smaller mono text
- Buttons use `size="sm"` and `flex-wrap` for mobile
- `pl-11` aligns rows 2-3 with the text (past the back button)

- [ ] **Step 2: Import `ExecutionStatusBadge` if not already imported**

Check if `ExecutionStatusBadge` is already imported in `ExecutionDetails.tsx`. It's used in the sidebar but may not be directly imported — it might come through `ExecutionSidebar`. If not imported, add:

```ts
import { ExecutionStatusBadge } from "@/components/execution";
```

- [ ] **Step 3: Verify types compile**

Run: `cd client && npm run tsc`
Expected: no errors

- [ ] **Step 4: Verify lint passes**

Run: `cd client && npm run lint`
Expected: no errors

- [ ] **Step 5: Commit**

```bash
git add client/src/pages/ExecutionDetails.tsx
git commit -m "fix: improve execution details header layout for mobile"
```

---

### Task 6: Add `href` support to `DataTableRow` for middle-click/new-tab

Make table rows behave like links without changing the `<tr>` element (which can't be an `<a>` in valid HTML). When `href` is provided, render an invisible stretched anchor inside the first cell so the browser natively handles middle-click and right-click "Open in new tab".

**Files:**
- Modify: `client/src/components/ui/data-table.tsx:106-124`

- [ ] **Step 1: Update `DataTableRow` to accept `href`**

Replace the `DataTableRow` definition:

```tsx
interface DataTableRowProps extends React.HTMLAttributes<HTMLTableRowElement> {
	/** Makes the row appear clickable with cursor and hover state */
	clickable?: boolean;
	/** URL for middle-click / right-click "Open in new tab" support.
	 *  Left clicks still use onClick. The href creates a hidden link overlay. */
	href?: string;
}

const DataTableRow = React.forwardRef<HTMLTableRowElement, DataTableRowProps>(
	({ className, clickable, href, onClick, ...props }, ref) => (
		<tr
			ref={ref}
			className={cn(
				"border-b transition-colors hover:bg-muted/50 data-[state=selected]:bg-muted relative",
				(clickable || href) && "cursor-pointer",
				className,
			)}
			onClick={onClick}
			{...props}
		>
			{href && (
				<td className="absolute inset-0 p-0 border-0" aria-hidden>
					<a
						href={href}
						className="absolute inset-0"
						onClick={(e) => e.preventDefault()}
						tabIndex={-1}
					/>
				</td>
			)}
			{props.children}
		</tr>
	),
);
```

Wait — a `<td>` as a direct child of `<tr>` is semantically correct, but positioning it absolutely over the row is tricky. A simpler approach: handle modifier keys in the onClick handler.

**Revised approach — helper function + onClick enhancement:**

Instead of a hidden anchor, detect middle-click and Cmd/Ctrl+click in the row's onClick and use `window.open`. This is simpler and avoids DOM gymnastics.

Create a helper and update `DataTableRow`:

```tsx
interface DataTableRowProps extends React.HTMLAttributes<HTMLTableRowElement> {
	/** Makes the row appear clickable with cursor and hover state */
	clickable?: boolean;
	/** URL for middle-click / Cmd+click to open in new tab */
	href?: string;
}

const DataTableRow = React.forwardRef<HTMLTableRowElement, DataTableRowProps>(
	({ className, clickable, href, onClick, onMouseDown, ...props }, ref) => (
		<tr
			ref={ref}
			className={cn(
				"border-b transition-colors hover:bg-muted/50 data-[state=selected]:bg-muted",
				(clickable || href) && "cursor-pointer",
				className,
			)}
			onClick={(e) => {
				// Cmd/Ctrl+click opens in new tab
				if (href && (e.metaKey || e.ctrlKey)) {
					e.preventDefault();
					window.open(href, "_blank");
					return;
				}
				onClick?.(e);
			}}
			onMouseDown={(e) => {
				// Middle-click opens in new tab
				if (href && e.button === 1) {
					e.preventDefault();
					window.open(href, "_blank");
					return;
				}
				onMouseDown?.(e);
			}}
			{...props}
		/>
	),
);
```

This handles:
- **Left click**: calls the existing `onClick` handler (opens slideout)
- **Cmd/Ctrl + click**: opens `href` in new tab
- **Middle click**: opens `href` in new tab
- **Right click → "Open in new tab"**: unfortunately this won't work without an actual `<a>` tag. But Cmd+click and middle-click cover the primary use cases.

For right-click context menu support, we need the actual anchor approach. Let's use a visually-hidden anchor that the browser can discover:

**Final approach — hidden anchor inside row:**

```tsx
const DataTableRow = React.forwardRef<HTMLTableRowElement, DataTableRowProps>(
	({ className, clickable, href, onClick, children, ...props }, ref) => (
		<tr
			ref={ref}
			className={cn(
				"border-b transition-colors hover:bg-muted/50 data-[state=selected]:bg-muted",
				(clickable || href) && "cursor-pointer",
				className,
			)}
			onClick={onClick}
			{...props}
		>
			{children}
			{href && (
				<td className="p-0 border-0 w-0 overflow-hidden">
					<a
						href={href}
						className="sr-only"
						tabIndex={-1}
						aria-hidden
						onClick={(e) => e.preventDefault()}
					>
						Open
					</a>
				</td>
			)}
		</tr>
	),
);
```

Hmm — a `sr-only` anchor won't appear in the right-click context menu because it has no visual presence where you click.

**Simplest correct approach**: Use the modifier-key detection (Cmd+click, middle-click) and accept that right-click context menu won't have "Open in new tab". This is the pattern used by many apps (GitHub, Linear, etc. all use JS click handlers on rows). Let's go with that.

```tsx
interface DataTableRowProps extends React.HTMLAttributes<HTMLTableRowElement> {
	/** Makes the row appear clickable with cursor and hover state */
	clickable?: boolean;
	/** URL for Cmd/Ctrl+click and middle-click to open in new tab */
	href?: string;
}

const DataTableRow = React.forwardRef<HTMLTableRowElement, DataTableRowProps>(
	({ className, clickable, href, onClick, ...props }, ref) => {
		const handleClick = (e: React.MouseEvent<HTMLTableRowElement>) => {
			if (href && (e.metaKey || e.ctrlKey)) {
				e.preventDefault();
				window.open(href, "_blank");
				return;
			}
			onClick?.(e);
		};

		const handleMouseUp = (e: React.MouseEvent<HTMLTableRowElement>) => {
			if (href && e.button === 1) {
				e.preventDefault();
				window.open(href, "_blank");
				return;
			}
			props.onMouseUp?.(e);
		};

		return (
			<tr
				ref={ref}
				className={cn(
					"border-b transition-colors hover:bg-muted/50 data-[state=selected]:bg-muted",
					(clickable || href) && "cursor-pointer",
					className,
				)}
				onClick={handleClick}
				onMouseUp={handleMouseUp}
				{...props}
			/>
		);
	},
);
DataTableRow.displayName = "DataTableRow";
```

- [ ] **Step 2: Verify types compile**

Run: `cd client && npm run tsc`
Expected: no errors

- [ ] **Step 3: Commit**

```bash
git add client/src/components/ui/data-table.tsx
git commit -m "feat: add href support to DataTableRow for new-tab navigation"
```

---

### Task 7: Wire up execution history table — slideout + new-tab

Change the execution history table to open a slideout drawer on left click (instead of navigating to the full page), with `href` for Cmd+click/middle-click to new tab.

**Files:**
- Modify: `client/src/pages/ExecutionHistory.tsx`

- [ ] **Step 1: Add drawer state and import**

At the top of `ExecutionHistory.tsx`, add the import:

```ts
import { ExecutionDrawer } from "./ExecutionHistory/components/ExecutionDrawer";
```

Inside the `ExecutionHistory` component, add state for the drawer (near the other state declarations ~line 140):

```ts
const [drawerExecutionId, setDrawerExecutionId] = useState<string | null>(null);
const [drawerOpen, setDrawerOpen] = useState(false);
```

- [ ] **Step 2: Change `handleViewDetails` to open drawer**

Replace the existing `handleViewDetails` function (~line 285-287):

```ts
const handleViewDetails = (execution_id: string) => {
	setDrawerExecutionId(execution_id);
	setDrawerOpen(true);
};
```

- [ ] **Step 3: Add `href` to execution table rows**

On the `DataTableRow` for each execution (~line 752), add the `href` prop:

```tsx
<DataTableRow
	key={execution.execution_id}
	clickable
	href={`/history/${execution.execution_id}`}
	onClick={() =>
		handleViewDetails(
			execution.execution_id,
		)
	}
>
```

- [ ] **Step 4: Add the ExecutionDrawer component**

At the bottom of the component return, before the closing `</div>` of the page, add:

```tsx
<ExecutionDrawer
	executionId={drawerExecutionId}
	open={drawerOpen}
	onOpenChange={setDrawerOpen}
/>
```

- [ ] **Step 5: Verify types compile**

Run: `cd client && npm run tsc`
Expected: no errors

- [ ] **Step 6: Verify lint passes**

Run: `cd client && npm run lint`
Expected: no errors

- [ ] **Step 7: Commit**

```bash
git add client/src/pages/ExecutionHistory.tsx
git commit -m "feat: open execution slideout from history table, support new-tab"
```

---

### Task 8: Wire up logs table — `href` for new-tab

The logs table already opens a slideout via `onLogClick`. Add `href` to rows for Cmd+click/middle-click support.

**Files:**
- Modify: `client/src/pages/ExecutionHistory/components/LogsTable.tsx`

- [ ] **Step 1: Add `href` to log rows**

In `LogsTable`, each row is rendered with `key={log.id}`. The log entry has an `execution_id` field. Update the row:

```tsx
<DataTableRow
	key={log.id}
	clickable
	href={`/history/${log.execution_id}`}
	onClick={() => onLogClick(log)}
	className="cursor-pointer"
>
```

- [ ] **Step 2: Verify types compile**

Run: `cd client && npm run tsc`
Expected: no errors

- [ ] **Step 3: Commit**

```bash
git add client/src/pages/ExecutionHistory/components/LogsTable.tsx
git commit -m "feat: add href to logs table rows for new-tab navigation"
```

---

### Task 9: Final verification

- [ ] **Step 1: Run full type check**

Run: `cd client && npm run tsc`
Expected: no errors

- [ ] **Step 2: Run lint**

Run: `cd client && npm run lint`
Expected: no errors

- [ ] **Step 3: Manual test — logs slideout**

1. Open the app at `localhost:3000`
2. Go to execution history → Logs tab
3. Click a log row → slideout opens with embedded ExecutionDetails
4. Verify content order: metadata bar → error/result → input data → logs → collapsible extras
5. Verify "Open in new tab" button works
6. Cmd+click a row → opens full page in new tab

- [ ] **Step 4: Manual test — execution history slideout**

1. Go to execution history → Workflow Executions tab
2. Click an execution row → slideout opens (instead of navigating)
3. Middle-click a row → opens full page in new tab
4. Verify same content order in slideout

- [ ] **Step 5: Manual test — full page header**

1. Open an execution in full page view (via new tab)
2. Verify header shows: workflow name, execution ID + status, action buttons
3. Resize to mobile width — verify buttons wrap, nothing overflows

- [ ] **Step 6: Manual test — mobile viewport**

1. Open browser dev tools, set mobile viewport (375px wide)
2. Open a slideout — verify it's usable, scrollable, nothing overflows
3. Open full page — verify header and content are readable

- [ ] **Step 7: Commit all remaining changes**

```bash
git add -A
git commit -m "feat: unified execution details for slideout and full page"
```
