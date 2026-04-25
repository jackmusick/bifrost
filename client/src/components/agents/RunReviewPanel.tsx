/**
 * Shared run review panel.
 *
 * Used in three places:
 *   - variant="page": full agent run detail page (main column)
 *   - variant="flipbook": Review flipbook card (full-width inside card)
 *   - variant="drawer": runs sheet (compact side panel)
 *
 * Consistent UX across all three: same summary structure (asked / did / output),
 * same tool-call preview, same verdict capture bar.
 */

import { Link } from "react-router-dom";
import {
	User,
	Bot,
	Wrench,
	ThumbsUp,
	ThumbsDown,
	AlertCircle,
	ChevronRight,
	Loader2,
	RefreshCw,
} from "lucide-react";
import { toast } from "sonner";
import { useQueryClient } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";

import { cn } from "@/lib/utils";
import { formatDuration } from "@/lib/utils";
import { useAuth } from "@/contexts/AuthContext";
import { useRegenerateSummary } from "@/services/agentRuns";
import type { components } from "@/lib/v1";

import { DidNarrative } from "./DidNarrative";
import { isEmptyJson, JsonTree } from "./JsonTree";
import { SummaryPlaceholder } from "./SummaryPlaceholder";

export type Verdict = "up" | "down" | null;

type AgentRunDetail = components["schemas"]["AgentRunDetailResponse"];
type AgentRunStep = components["schemas"]["AgentRunStepResponse"];

export type RunReviewVariant = "page" | "flipbook" | "drawer";

export interface RunReviewPanelProps {
	run: AgentRunDetail;
	verdict: Verdict;
	note: string;
	onVerdict: (v: Verdict) => void;
	onNote: (n: string) => void;
	variant?: RunReviewVariant;
	hideVerdictBar?: boolean;
}

interface ToolCallContent {
	// Shape emitted by autonomous_agent_executor.py _record_step(..., "tool_call", ...)
	tool_name?: string;
	arguments?: unknown;
}

/** Pull tool calls out of run.steps.
 *
 * The executor records one `tool_call` step per invocation with
 * `content = { tool_name, arguments }` (see
 * api/src/services/execution/autonomous_agent_executor.py). Older code in
 * this component read `content.tool` / `content.args` which don't exist —
 * that's why every row rendered as `tool {}`.
 */
function extractToolCalls(steps: AgentRunStep[] | undefined): {
	tool: string;
	args: unknown;
	duration_ms: number | null;
}[] {
	if (!steps) return [];
	return steps
		.filter((s) => s.type === "tool_call")
		.map((s) => {
			const content = (s.content ?? {}) as ToolCallContent;
			return {
				tool: content.tool_name ?? "tool",
				args: content.arguments ?? {},
				duration_ms: s.duration_ms ?? null,
			};
		});
}

interface ToolCallRowProps {
	tool: string;
	args: unknown;
	duration_ms: number | null;
}

/** Tool-call row: tool name + (when args non-empty) chevron-disclosure +
 * duration. No inline args preview — that pushed long objects past the
 * card's right edge. Expanded form uses the shared JsonTree viewer.
 */
function ToolCallRow({ tool, args, duration_ms }: ToolCallRowProps) {
	const [open, setOpen] = useState(false);
	const empty = isEmptyJson(args);
	const expandable = !empty;

	return (
		<div className="overflow-hidden rounded border bg-card text-xs">
			<button
				type="button"
				onClick={() => expandable && setOpen((v) => !v)}
				disabled={!expandable}
				aria-expanded={expandable ? open : undefined}
				aria-label={
					expandable
						? open
							? "Hide arguments"
							: "Show arguments"
						: undefined
				}
				className={cn(
					"flex w-full items-center gap-2 px-2 py-1.5 text-left",
					expandable && "hover:bg-accent/40",
				)}
			>
				{expandable ? (
					<ChevronRight
						className={cn(
							"h-3 w-3 shrink-0 text-muted-foreground transition-transform",
							open && "rotate-90",
						)}
					/>
				) : (
					<span className="h-3 w-3 shrink-0" />
				)}
				<span className="min-w-0 flex-1 truncate font-mono font-medium">
					{tool}
				</span>
				<span className="shrink-0 text-[11px] text-muted-foreground">
					{duration_ms != null ? formatDuration(duration_ms) : ""}
				</span>
			</button>
			{expandable && open ? (
				<div className="max-h-[240px] overflow-y-auto border-t bg-muted/30 px-3 py-2">
					<JsonTree value={args} />
				</div>
			) : null}
		</div>
	);
}


/** Render input/output that may be a string OR a JSON object. */
function renderPayload(value: unknown): string {
	if (value === null || value === undefined) return "";
	if (typeof value === "string") return value;
	try {
		return JSON.stringify(value, null, 2);
	} catch {
		return String(value);
	}
}

export function RunReviewPanel({
	run,
	verdict,
	note,
	onVerdict,
	onNote,
	variant = "page",
	hideVerdictBar = false,
}: RunReviewPanelProps) {
	const toolCalls = extractToolCalls(run.steps);
	// "What it did" rendering decision tree:
	//   v3+ summary with prose `did`     → render DidNarrative (chips inline
	//                                       when [tool_name] markers present;
	//                                       graceful plain-prose otherwise).
	//   no `did` but has tool_call steps → fall back to the raw tool-call
	//                                       list (v1/v2 era, pre-summary).
	//   neither                          → hide the section entirely.
	const hasDidProse = !!run.did && run.did.trim().length > 0;
	const canVerdict = run.status === "completed" && !hideVerdictBar;
	const compact = variant === "drawer";
	const maxToolCalls = compact ? 3 : 4;
	const visibleTools = toolCalls.slice(0, maxToolCalls);
	const overflow = toolCalls.length - visibleTools.length;
	const inputText = renderPayload(run.input);
	const outputText = renderPayload(run.output);

	const { isPlatformAdmin } = useAuth();
	const queryClient = useQueryClient();
	const regenSummary = useRegenerateSummary();
	const summaryStatus = run.summary_status;
	const needsRegen = summaryStatus && summaryStatus !== "completed";

	function handleRegenerate() {
		regenSummary.mutate(
			{ params: { path: { run_id: run.id } } },
			{
				onSuccess: () => {
					toast.success("Summary regeneration queued");
					queryClient.invalidateQueries({
						queryKey: ["get", "/api/agent-runs/{run_id}"],
					});
					queryClient.invalidateQueries({ queryKey: ["agent-runs"] });
				},
				onError: () => {
					toast.error("Failed to regenerate summary");
				},
			},
		);
	}

	return (
		<div data-slot="run-review-panel" className="min-w-0">
			<div
				className={cn(
					"grid min-w-0",
					compact ? "gap-3.5 px-4 py-3.5" : "gap-4 px-5 py-4",
				)}
			>
				{needsRegen ? (
					<div
						className={cn(
							// fade-in so the banner doesn't pop when the
							// websocket flips summary_status to generating.
							"flex items-center justify-between gap-3 rounded-md border px-3 py-2 animate-in fade-in duration-200",
							summaryStatus === "failed"
								? "border-rose-500/30 bg-rose-500/10"
								: "bg-muted/40",
							compact ? "text-xs" : "text-[13px]",
						)}
					>
						<div className="flex items-center gap-2">
							{summaryStatus === "generating" || regenSummary.isPending ? (
								<Loader2 className="h-3.5 w-3.5 animate-spin" />
							) : (
								<RefreshCw className="h-3.5 w-3.5 text-muted-foreground" />
							)}
							<span>
								{summaryStatus === "failed"
									? "Summary failed"
									: summaryStatus === "generating"
										? "Summary in progress…"
										: "Summary pending"}
							</span>
						</div>
						{/* Hide the Regenerate button while generation is
						    in flight — it would just no-op (idempotent
						    short-circuit on the backend) and looks like the
						    user is being asked to act. */}
						{summaryStatus !== "generating" ? (
							<button
								type="button"
								disabled={!isPlatformAdmin || regenSummary.isPending}
								title={
									isPlatformAdmin
										? "Re-run summarization"
										: "Only platform admins can regenerate summaries"
								}
								onClick={handleRegenerate}
								className={cn(
									"inline-flex items-center gap-1.5 rounded-md border bg-background px-2.5 py-1 text-xs font-medium transition-colors",
									isPlatformAdmin && !regenSummary.isPending
										? "hover:bg-accent"
										: "cursor-not-allowed opacity-60",
								)}
								data-testid="regen-summary-panel-button"
							>
								Regenerate
							</button>
						) : null}
					</div>
				) : null}
				<Section
					icon={<User size={13} />}
					iconClassName="bg-muted text-muted-foreground"
					label="What was asked"
					compact={compact}
				>
					<div
						className={cn(
							"rounded-md border bg-muted/40 px-3 py-2 whitespace-pre-wrap break-words",
							compact ? "text-xs" : "text-sm",
						)}
					>
						{run.asked || (
							<SummaryPlaceholder status={run.summary_status} runStatus={run.status} />
						)}
					</div>
				</Section>

				{hasDidProse ? (
					<Section
						icon={<Wrench size={13} />}
						iconClassName="bg-blue-500/15 text-blue-600 dark:text-blue-400"
						label="What it did"
						compact={compact}
					>
						<div
							className={cn(
								"rounded-md border bg-muted/40 px-3 py-2",
								compact ? "text-xs" : "text-sm",
							)}
						>
							<DidNarrative
								text={run.did}
								steps={run.steps}
								compact={compact}
							/>
						</div>
					</Section>
				) : toolCalls.length > 0 ? (
					// No `did` summary at all (pre-summary or summary failed)
					// — fall back to the raw tool-call list so the user
					// still sees what the agent did.
					<Section
						icon={<Wrench size={13} />}
						iconClassName="bg-blue-500/15 text-blue-600 dark:text-blue-400"
						label={`What it did · ${toolCalls.length} tool call${toolCalls.length === 1 ? "" : "s"}`}
						compact={compact}
					>
						<div className="grid gap-1.5">
							{visibleTools.map((c, i) => (
								<ToolCallRow
									key={i}
									tool={c.tool}
									args={c.args}
									duration_ms={c.duration_ms}
								/>
							))}
							{overflow > 0 ? (
								<div className="text-xs text-muted-foreground">
									+{overflow} more —{" "}
									<Link
										to={`/agents/${run.agent_id}/runs/${run.id}`}
										className="text-primary hover:underline"
									>
										open full detail
									</Link>
								</div>
							) : null}
						</div>
					</Section>
				) : null}

				{run.status === "completed" ? (
					<Section
						icon={<Bot size={13} />}
						iconClassName="bg-emerald-500/15 text-emerald-600 dark:text-emerald-400"
						label="What the agent answered"
						compact={compact}
					>
						<div
							className={cn(
								"rounded-md border bg-muted/40 px-3 py-2 whitespace-pre-wrap break-words",
								compact ? "text-xs" : "text-sm",
							)}
						>
							{run.answered ||
								// Fall back to `did` for v1/v2 summaries (no
								// separate `answered` field). Shows the
								// generic-but-better-than-nothing one-liner.
								run.did ||
								(
									<SummaryPlaceholder status={run.summary_status} runStatus={run.status} />
								)}
						</div>
					</Section>
				) : (
					<Section
						icon={<AlertCircle size={13} />}
						iconClassName="bg-rose-500/15 text-rose-600 dark:text-rose-400"
						label={
							run.status === "budget_exceeded"
								? "Budget exceeded"
								: "Run failed"
						}
						compact={compact}
					>
						<div
							className={cn(
								"rounded-md border border-transparent bg-rose-500/10 px-3 py-2 whitespace-pre-wrap break-words",
								compact ? "text-xs" : "text-sm",
							)}
						>
							{run.error ?? "No error message captured."}
						</div>
					</Section>
				)}

				{run.metadata && Object.keys(run.metadata).length > 0 ? (
					<Section label="Captured data" compact={compact} plain>
						<MetadataChips metadata={run.metadata} />
					</Section>
				) : null}

				{run.summary_status === "failed" && run.summary_error ? (
					<Section label="Summary error" compact={compact} plain>
						<div
							className={cn(
								"rounded-md border border-rose-500/30 bg-rose-500/10 px-3 py-2 text-rose-700 dark:text-rose-300 whitespace-pre-wrap break-words",
								compact ? "text-xs" : "text-sm",
							)}
						>
							{run.summary_error}
						</div>
					</Section>
				) : null}

				{inputText || outputText ? (
					<Section label="Raw payloads" compact={compact} plain>
						<div className="grid gap-2">
							{inputText ? (
								<RawDisclosure label="Raw input" text={inputText} compact={compact} />
							) : null}
							{outputText ? (
								<RawDisclosure label="Raw output" text={outputText} compact={compact} />
							) : null}
						</div>
					</Section>
				) : null}
			</div>

			{canVerdict ? (
				<div
					className={cn(
						"flex items-center gap-2 bg-muted/40",
						variant === "drawer"
							? "border-t px-4 py-3 flex-col items-stretch"
							: "mx-5 mb-5 rounded-md border px-3 py-2.5",
						compact && "flex-col items-stretch gap-2",
					)}
					data-slot="verdict-bar"
				>
					<div className="flex items-center gap-2">
						<div className="text-sm text-muted-foreground">Verdict</div>
						<button
							type="button"
							aria-label="Mark as good"
							aria-pressed={verdict === "up"}
							onClick={() =>
								onVerdict(verdict === "up" ? null : "up")
							}
							className={cn(
								"inline-flex items-center gap-1.5 rounded-md border px-2.5 py-1 text-xs font-medium transition-colors",
								verdict === "up"
									? "border-emerald-500 bg-emerald-500/15 text-emerald-700 dark:text-emerald-300"
									: "bg-background hover:bg-accent",
							)}
						>
							<ThumbsUp size={14} /> Good
						</button>
						<button
							type="button"
							aria-label="Mark as wrong"
							aria-pressed={verdict === "down"}
							onClick={() =>
								onVerdict(verdict === "down" ? null : "down")
							}
							className={cn(
								"inline-flex items-center gap-1.5 rounded-md border px-2.5 py-1 text-xs font-medium transition-colors",
								verdict === "down"
									? "border-rose-500 bg-rose-500/15 text-rose-700 dark:text-rose-300"
									: "bg-background hover:bg-accent",
							)}
						>
							<ThumbsDown size={14} /> Wrong
						</button>
					</div>
					<div
						className={cn(
							"flex flex-1",
							compact ? "ml-0" : "ml-4 max-w-[500px]",
						)}
					>
						<input
							type="text"
							placeholder={
								verdict === "down"
									? "What should it have done?"
									: "Add a note (optional)"
							}
							value={note}
							onChange={(e) => onNote(e.target.value)}
							className="w-full rounded-md border bg-background px-2.5 py-1 text-sm outline-none focus:border-primary focus:ring-2 focus:ring-primary/20"
						/>
					</div>
				</div>
			) : null}
		</div>
	);
}

interface SectionProps {
	icon?: ReactNode;
	iconClassName?: string;
	label: string;
	children: ReactNode;
	compact?: boolean;
	plain?: boolean;
}

function Section({
	icon,
	iconClassName,
	label,
	children,
	compact,
	plain,
}: SectionProps) {
	return (
		<section>
			<div className="mb-2 flex items-center gap-2">
				{icon && !plain ? (
					<div
						className={cn(
							"grid place-items-center rounded-full",
							compact ? "h-[22px] w-[22px]" : "h-7 w-7",
							iconClassName,
						)}
					>
						{icon}
					</div>
				) : null}
				<div
					className={cn(
						"font-medium",
						compact ? "text-xs" : "text-[13px]",
						plain
							? "text-[11px] uppercase tracking-wider text-muted-foreground"
							: "text-foreground",
					)}
				>
					{label}
				</div>
			</div>
			{children}
		</section>
	);
}

interface RawDisclosureProps {
	label: string;
	text: string;
	compact?: boolean;
}

/** Collapsible raw input/output block. Opaque unless admin explicitly opens it. */
function RawDisclosure({ label, text, compact }: RawDisclosureProps) {
	const [open, setOpen] = useState(false);
	return (
		<div className="rounded-md border bg-card">
			<button
				type="button"
				onClick={() => setOpen((v) => !v)}
				className={cn(
					"flex w-full items-center gap-1.5 px-3 py-1.5 text-left text-muted-foreground hover:text-foreground",
					compact ? "text-xs" : "text-[13px]",
				)}
			>
				<ChevronRight
					className={cn(
						"h-3 w-3 transition-transform",
						open && "rotate-90",
					)}
				/>
				<span>{label}</span>
				<span className="ml-auto text-[11px]">
					{text.length.toLocaleString()} chars
				</span>
			</button>
			{open ? (
				<pre
					className={cn(
						"max-h-[240px] overflow-auto border-t bg-muted/30 px-3 py-2 font-mono whitespace-pre-wrap break-words",
						compact ? "text-[11px]" : "text-xs",
					)}
				>
					{text}
				</pre>
			) : null}
		</div>
	);
}

export interface MetadataChipsProps {
	metadata: Record<string, string>;
	highlight?: string;
}

export function MetadataChips({ metadata, highlight }: MetadataChipsProps) {
	const entries = Object.entries(metadata);
	if (!entries.length) return null;
	const q = highlight?.trim().toLowerCase() ?? "";
	return (
		<div className="flex flex-wrap gap-1.5">
			{entries.map(([k, v]) => {
				const isHit =
					q &&
					(k.toLowerCase().includes(q) || v.toLowerCase().includes(q));
				return (
					<span
						key={k}
						title={`${k}=${v}`}
						className={cn(
							"inline-flex items-center gap-1 rounded border px-1.5 py-0.5 text-[11px]",
							isHit
								? "border-transparent bg-yellow-500/15 text-yellow-700 dark:text-yellow-300"
								: "border-border bg-card text-foreground",
						)}
					>
						<span className="text-muted-foreground">{k}</span>
						<span className="font-mono">{v}</span>
					</span>
				);
			})}
		</div>
	);
}
