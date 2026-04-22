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
} from "lucide-react";
import type { ReactNode } from "react";

import { cn } from "@/lib/utils";
import { formatDuration } from "@/lib/utils";
import type { components } from "@/lib/v1";

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
	tool?: string;
	args?: unknown;
}

/** Pull tool calls out of run.steps with light defensive parsing. */
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
				tool: content.tool ?? "tool",
				args: content.args ?? {},
				duration_ms: s.duration_ms ?? null,
			};
		});
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
	const canVerdict = run.status === "completed" && !hideVerdictBar;
	const compact = variant === "drawer";
	const maxToolCalls = compact ? 3 : 4;
	const visibleTools = toolCalls.slice(0, maxToolCalls);
	const overflow = toolCalls.length - visibleTools.length;
	const inputText = renderPayload(run.input);
	const outputText = renderPayload(run.output);

	return (
		<div data-slot="run-review-panel">
			<div
				className={cn(
					"grid",
					compact ? "gap-3.5 px-4 py-3.5" : "gap-4 px-5 py-4",
				)}
			>
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
						{run.asked || inputText || (
							<span className="text-muted-foreground">(no input)</span>
						)}
					</div>
				</Section>

				{toolCalls.length > 0 ? (
					<Section
						icon={<Wrench size={13} />}
						iconClassName="bg-blue-500/15 text-blue-600 dark:text-blue-400"
						label={`What it did · ${toolCalls.length} tool call${toolCalls.length === 1 ? "" : "s"}`}
						compact={compact}
					>
						<div className="grid gap-1.5">
							{visibleTools.map((c, i) => (
								<div
									key={i}
									className="flex items-center gap-2 rounded border bg-card px-2 py-1.5 text-xs"
								>
									<span className="font-mono font-medium">{c.tool}</span>
									<span className="flex-1 truncate font-mono text-muted-foreground">
										{typeof c.args === "string"
											? c.args
											: JSON.stringify(c.args)}
									</span>
									<span className="shrink-0 text-[11px] text-muted-foreground">
										{c.duration_ms != null
											? formatDuration(c.duration_ms)
											: ""}
									</span>
								</div>
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
							{run.did || outputText || (
								<span className="text-muted-foreground">(no output)</span>
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
