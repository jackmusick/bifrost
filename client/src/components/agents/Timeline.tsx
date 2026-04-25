/**
 * Timeline — per-step structured view of an agent run.
 *
 * Replaces the v2 "Raw step timeline" JSON dump. Each step renders an icon
 * by type, a friendly one-line label, and the duration on the right. Click
 * a row to expand its details (args/result for tool steps, message content
 * for LLM steps, raw JSON for everything else as the deepest layer).
 *
 * Brings back the v1 chronological-strip aesthetic so the train of thought
 * is scannable; the JSON is still there but it's one click deeper instead
 * of being the headline.
 */

import { useState } from "react";
import {
	AlertCircle,
	Bot,
	ChevronRight,
	CircleDot,
	Cpu,
	MessageSquare,
	Wrench,
} from "lucide-react";

import { cn } from "@/lib/utils";
import { formatDuration, formatNumber } from "@/lib/utils";
import type { components } from "@/lib/v1";

import { JsonTree, isEmptyJson } from "./JsonTree";

type AgentRunStepResponse = components["schemas"]["AgentRunStepResponse"];

type DetailRender =
	| { kind: "json"; value: unknown }
	| { kind: "text"; value: string };

interface StepViewModel {
	icon: typeof Wrench;
	iconClass: string;
	label: string;
	summary: string | null;
	primaryDetail: DetailRender | null;
	secondaryDetail: (DetailRender & { label: string }) | null;
}

function buildViewModel(step: AgentRunStepResponse): StepViewModel {
	const c = (step.content ?? {}) as Record<string, unknown>;
	const type = step.type ?? "step";

	switch (type) {
		case "tool_call": {
			const name = (c.tool_name as string) || "tool";
			const args = c.arguments;
			return {
				icon: Wrench,
				iconClass: "bg-blue-500/15 text-blue-600 dark:text-blue-400",
				label: `Called ${name}`,
				summary: null,
				primaryDetail: isEmptyJson(args)
					? null
					: { kind: "json", value: args },
				secondaryDetail: null,
			};
		}
		case "tool_result": {
			const name = (c.tool_name as string) || "tool";
			const result = (c.result as string | undefined) ?? "";
			return {
				icon: CircleDot,
				iconClass: "bg-emerald-500/15 text-emerald-600 dark:text-emerald-400",
				label: `Result from ${name}`,
				summary: result ? truncate(result, 100) : null,
				primaryDetail: result
					? { kind: "text", value: result }
					: null,
				secondaryDetail: null,
			};
		}
		case "tool_error": {
			const name = (c.tool_name as string) || "tool";
			const result = (c.result as string | undefined) ?? "";
			return {
				icon: AlertCircle,
				iconClass: "bg-rose-500/15 text-rose-600 dark:text-rose-400",
				label: `Error from ${name}`,
				summary: result ? truncate(result, 100) : null,
				primaryDetail: result
					? { kind: "text", value: result }
					: null,
				secondaryDetail: null,
			};
		}
		case "llm_request": {
			const model = (c.model as string | null) ?? null;
			const tools = (c.tools_count as number | undefined) ?? null;
			const messages = (c.messages_count as number | undefined) ?? null;
			const bits: string[] = [];
			if (model) bits.push(model);
			if (messages != null) bits.push(`${messages} msgs`);
			if (tools != null) bits.push(`${tools} tools`);
			return {
				icon: Cpu,
				iconClass: "bg-muted text-muted-foreground",
				label: "LLM request",
				summary: bits.length ? bits.join(" · ") : null,
				primaryDetail: { kind: "json", value: c },
				secondaryDetail: null,
			};
		}
		case "llm_response": {
			const text = (c.content as string | undefined) ?? "";
			const toolCalls = (c.tool_calls as Array<{
				name?: string;
			}> | undefined) ?? [];
			const callNames = toolCalls
				.map((tc) => tc.name)
				.filter(Boolean) as string[];
			// Label: when the LLM picked tools, name them directly.
			// "Decided to call get_ticket, send_email" beats the abstract
			// "LLM decided to call tools" by one click of comprehension.
			const label =
				callNames.length > 0
					? `Decided to call ${callNames.join(", ")}`
					: text
						? "Reasoned"
						: "LLM response";
			return {
				icon: Bot,
				iconClass: "bg-violet-500/15 text-violet-600 dark:text-violet-400",
				label,
				// If we put the names in the label, no summary needed; show the
				// reasoning text as summary when it's the standalone case.
				summary:
					callNames.length > 0
						? null
						: text
							? truncate(text, 120)
							: null,
				primaryDetail: text
					? { kind: "text", value: text }
					: null,
				secondaryDetail:
					callNames.length > 0
						? {
								kind: "json",
								label: "Tool calls",
								value: toolCalls,
							}
						: null,
			};
		}
		case "error":
		case "budget_warning":
		case "cancelled": {
			return {
				icon: AlertCircle,
				iconClass:
					type === "error"
						? "bg-rose-500/15 text-rose-600 dark:text-rose-400"
						: "bg-amber-500/15 text-amber-600 dark:text-amber-400",
				label:
					type === "cancelled"
						? "Cancelled"
						: type === "budget_warning"
							? "Budget warning"
							: "Error",
				summary: stringifyMaybeJson(c) ?? null,
				primaryDetail: { kind: "json", value: c },
				secondaryDetail: null,
			};
		}
		default: {
			return {
				icon: MessageSquare,
				iconClass: "bg-muted text-muted-foreground",
				label: type,
				summary: stringifyMaybeJson(c) ?? null,
				primaryDetail: { kind: "json", value: c },
				secondaryDetail: null,
			};
		}
	}
}

function stringifyMaybeJson(v: unknown): string | null {
	if (v === null || v === undefined) return null;
	if (typeof v === "string") return v;
	try {
		const s = JSON.stringify(v);
		return s === "{}" ? null : s;
	} catch {
		return String(v);
	}
}

function truncate(s: string, n: number): string {
	if (s.length <= n) return s;
	return s.slice(0, n - 1) + "…";
}

export interface TimelineProps {
	steps: AgentRunStepResponse[] | null | undefined;
}

export function Timeline({ steps }: TimelineProps) {
	if (!steps || !steps.length) {
		return (
			<p className="text-xs text-muted-foreground">No steps recorded.</p>
		);
	}
	return (
		<ol className="flex flex-col gap-1.5">
			{steps.map((step, i) => (
				<TimelineRow key={step.id ?? i} step={step} index={i + 1} />
			))}
		</ol>
	);
}

function TimelineRow({
	step,
	index,
}: {
	step: AgentRunStepResponse;
	index: number;
}) {
	const [open, setOpen] = useState(false);
	const vm = buildViewModel(step);
	const hasDetail = !!vm.primaryDetail || !!vm.secondaryDetail;
	const Icon = vm.icon;
	return (
		<li className="rounded border bg-card">
			<button
				type="button"
				onClick={() => hasDetail && setOpen((v) => !v)}
				disabled={!hasDetail}
				aria-expanded={open}
				aria-label={hasDetail ? `Toggle details for step ${index}` : undefined}
				className={cn(
					"flex w-full items-start gap-2 px-3 py-2 text-left text-xs",
					hasDetail && "hover:bg-accent/40",
				)}
			>
				<div
					className={cn(
						"mt-0.5 grid h-5 w-5 shrink-0 place-items-center rounded-full",
						vm.iconClass,
					)}
				>
					<Icon className="h-3 w-3" />
				</div>
				<div className="min-w-0 flex-1">
					<div className="flex items-baseline gap-2">
						<span className="font-medium">{vm.label}</span>
						{vm.summary ? (
							<span className="truncate text-muted-foreground">
								{vm.summary}
							</span>
						) : null}
					</div>
				</div>
				<span className="ml-auto flex shrink-0 items-center gap-2 text-[11px] text-muted-foreground">
					{step.tokens_used ? (
						<span title="Tokens used">
							{formatNumber(step.tokens_used)} tok
						</span>
					) : null}
					{step.duration_ms != null ? (
						<span>{formatDuration(step.duration_ms)}</span>
					) : null}
					<span className="font-mono">#{index}</span>
					{hasDetail ? (
						<ChevronRight
							className={cn(
								"h-3 w-3 transition-transform",
								open && "rotate-90",
							)}
						/>
					) : null}
				</span>
			</button>
			{open && hasDetail ? (
				<div className="border-t px-3 py-2">
					{vm.primaryDetail ? (
						<DetailBlock detail={vm.primaryDetail} />
					) : null}
					{vm.secondaryDetail ? (
						<div className="mt-2">
							<div className="mb-1 text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
								{vm.secondaryDetail.label}
							</div>
							<DetailBlock detail={vm.secondaryDetail} />
						</div>
					) : null}
				</div>
			) : null}
		</li>
	);
}

function DetailBlock({ detail }: { detail: DetailRender }) {
	if (detail.kind === "json") {
		return (
			<div className="max-h-[280px] overflow-y-auto rounded bg-muted/30 px-2 py-1.5">
				<JsonTree value={detail.value} />
			</div>
		);
	}
	// Tool results / LLM response text are strings — but tool results often
	// look like JSON. Best-effort parse so the tree view kicks in.
	const parsed = tryParseJson(detail.value);
	if (parsed !== UNPARSEABLE) {
		return (
			<div className="max-h-[280px] overflow-y-auto rounded bg-muted/30 px-2 py-1.5">
				<JsonTree value={parsed} />
			</div>
		);
	}
	return (
		<pre className="max-h-[280px] overflow-y-auto rounded bg-muted/30 px-2 py-1.5 font-mono text-[11px] whitespace-pre-wrap break-words">
			{detail.value}
		</pre>
	);
}

const UNPARSEABLE = Symbol("unparseable");
function tryParseJson(value: string): unknown {
	const trimmed = value.trim();
	if (
		!(
			(trimmed.startsWith("{") && trimmed.endsWith("}")) ||
			(trimmed.startsWith("[") && trimmed.endsWith("]"))
		)
	) {
		return UNPARSEABLE;
	}
	try {
		return JSON.parse(trimmed);
	} catch {
		return UNPARSEABLE;
	}
}
