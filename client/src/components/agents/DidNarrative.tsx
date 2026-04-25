/**
 * DidNarrative — renders the summarizer's prose `did` field with bracketed
 * `[tool_name]` markers turned into clickable chips.
 *
 * The summarizer (prompt v3) produces sentences like:
 *
 *   "I called [ai_ticketing_get_ticket_details] to fetch the ticket, then
 *    delegated to [security_subagent] when the alert turned out to be EOL."
 *
 * Each `[name]` is matched against the run's `tool_call` steps; clicking
 * the chip pops a clean technical view of THAT specific call (args + result
 * + duration). Unmatched markers still render as a chip but with the
 * "no record" hint — defensive against the summarizer hallucinating a
 * tool name. Plain prose between chips is preserved as text.
 */

import { useMemo, type ReactNode } from "react";
import { Wrench } from "lucide-react";

import {
	Popover,
	PopoverContent,
	PopoverTrigger,
} from "@/components/ui/popover";
import { cn } from "@/lib/utils";
import { formatDuration } from "@/lib/utils";
import type { components } from "@/lib/v1";

import { JsonTree, isEmptyJson } from "./JsonTree";

type AgentRunStep = components["schemas"]["AgentRunStepResponse"];

export interface DidNarrativeProps {
	text: string | null | undefined;
	steps: AgentRunStep[] | null | undefined;
	/** When true (drawer/sheet variants), use compact spacing. */
	compact?: boolean;
	/** Renderer for non-prose fallback (e.g. SummaryPlaceholder). */
	fallback?: ReactNode;
}

interface ToolCallSummary {
	tool: string;
	args: unknown;
	result?: string;
	is_error?: boolean;
	duration_ms: number | null;
}

/** Pull a tool-name → first-call summary map out of run.steps.
 *
 * If the same tool runs multiple times, we only surface the first call —
 * the prose can mention a tool more than once and we don't currently track
 * which mention pairs with which call. Good enough for v1; revisit when
 * users complain.
 */
function indexCallsByTool(
	steps: AgentRunStep[] | null | undefined,
): Record<string, ToolCallSummary> {
	if (!steps) return {};
	const out: Record<string, ToolCallSummary> = {};
	for (let i = 0; i < steps.length; i++) {
		const s = steps[i];
		if (s.type !== "tool_call") continue;
		const content = (s.content ?? {}) as {
			tool_name?: string;
			arguments?: unknown;
		};
		const name = content.tool_name;
		if (!name || out[name]) continue;
		// Find the matching tool_result step (next step with same tool_name).
		let result: string | undefined;
		let is_error: boolean | undefined;
		for (let j = i + 1; j < steps.length; j++) {
			const r = steps[j];
			if (r.type !== "tool_result" && r.type !== "tool_error") continue;
			const rc = (r.content ?? {}) as {
				tool_name?: string;
				result?: string;
				is_error?: boolean;
			};
			if (rc.tool_name === name) {
				result = rc.result;
				is_error = rc.is_error || r.type === "tool_error";
				break;
			}
		}
		out[name] = {
			tool: name,
			args: content.arguments ?? {},
			result,
			is_error,
			duration_ms: s.duration_ms ?? null,
		};
	}
	return out;
}

const TOOL_MARKER = /\[([a-zA-Z_][a-zA-Z0-9_.-]*)\]/g;

/** Split a string on `[tool]` markers preserving order. */
function splitOnMarkers(text: string): Array<
	{ kind: "text"; value: string } | { kind: "tool"; name: string }
> {
	const parts: Array<
		{ kind: "text"; value: string } | { kind: "tool"; name: string }
	> = [];
	let cursor = 0;
	for (const match of text.matchAll(TOOL_MARKER)) {
		const start = match.index ?? 0;
		if (start > cursor) {
			parts.push({ kind: "text", value: text.slice(cursor, start) });
		}
		parts.push({ kind: "tool", name: match[1] });
		cursor = start + match[0].length;
	}
	if (cursor < text.length) {
		parts.push({ kind: "text", value: text.slice(cursor) });
	}
	return parts;
}

export function DidNarrative({
	text,
	steps,
	compact,
	fallback,
}: DidNarrativeProps) {
	const callIndex = useMemo(() => indexCallsByTool(steps), [steps]);
	const parts = useMemo(
		() => (text ? splitOnMarkers(text) : []),
		[text],
	);
	if (!text || !text.trim()) {
		return <>{fallback}</>;
	}
	return (
		<div
			className={cn(
				"whitespace-pre-wrap break-words leading-relaxed",
				compact ? "text-xs" : "text-sm",
			)}
		>
			{parts.map((p, i) =>
				p.kind === "text" ? (
					<span key={i}>{p.value}</span>
				) : (
					<ToolMentionChip
						key={i}
						name={p.name}
						call={callIndex[p.name]}
					/>
				),
			)}
		</div>
	);
}

interface ToolMentionChipProps {
	name: string;
	call?: ToolCallSummary;
}

function ToolMentionChip({ name, call }: ToolMentionChipProps) {
	const matched = !!call;
	return (
		<Popover>
			<PopoverTrigger asChild>
				<button
					type="button"
					className={cn(
						"mx-0.5 inline-flex items-center gap-1 rounded border px-1.5 py-0.5 align-baseline font-mono text-[11px] transition-colors",
						matched
							? "border-blue-500/30 bg-blue-500/10 text-blue-700 hover:bg-blue-500/20 dark:text-blue-300"
							: "border-muted-foreground/30 bg-muted/40 text-muted-foreground",
					)}
					aria-label={
						matched
							? `Show details for ${name}`
							: `${name} (no matching call recorded)`
					}
				>
					<Wrench className="h-2.5 w-2.5" />
					{name}
				</button>
			</PopoverTrigger>
			<PopoverContent
				side="top"
				align="start"
				className="w-[420px] max-w-[90vw] p-0"
			>
				<div className="border-b px-3 py-2">
					<div className="flex items-center gap-2 text-xs font-medium">
						<Wrench className="h-3 w-3" />
						<span className="font-mono">{name}</span>
						{call?.duration_ms != null ? (
							<span className="ml-auto text-muted-foreground">
								{formatDuration(call.duration_ms)}
							</span>
						) : null}
					</div>
				</div>
				<div className="grid gap-2 px-3 py-2 text-xs">
					{!matched ? (
						<p className="text-muted-foreground">
							No matching tool call recorded on this run.
						</p>
					) : (
						<>
							<ChipSection label="Arguments">
								<JsonBlock value={call!.args} />
							</ChipSection>
							{call!.result !== undefined ? (
								<ChipSection
									label={call!.is_error ? "Error" : "Result"}
								>
									<div
										className={cn(
											"max-h-[180px] overflow-y-auto rounded border bg-muted/30 px-2 py-1.5 text-[11px] whitespace-pre-wrap break-words",
											call!.is_error
												? "border-rose-500/30 text-rose-700 dark:text-rose-300"
												: "",
										)}
									>
										<ResultBlock value={call!.result} isError={call!.is_error} />
									</div>
								</ChipSection>
							) : null}
						</>
					)}
				</div>
			</PopoverContent>
		</Popover>
	);
}

function ChipSection({
	label,
	children,
}: {
	label: string;
	children: ReactNode;
}) {
	return (
		<div className="grid gap-1">
			<div className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
				{label}
			</div>
			{children}
		</div>
	);
}

function JsonBlock({ value }: { value: unknown }) {
	if (isEmptyJson(value)) {
		return <p className="text-muted-foreground">No arguments.</p>;
	}
	if (typeof value === "string") {
		return (
			<pre className="max-h-[180px] overflow-y-auto rounded border bg-muted/30 px-2 py-1.5 font-mono text-[11px] whitespace-pre-wrap break-words">
				{value}
			</pre>
		);
	}
	return (
		<div className="max-h-[180px] overflow-y-auto rounded border bg-muted/30 px-2 py-1.5">
			<JsonTree value={value} />
		</div>
	);
}

/** Tool results come from `_record_step(..., "tool_result", { result: "..."})`
 * — always a string, often a JSON-shaped one. Try to parse and pretty-print
 * with the JsonTree; fall back to raw text for plain strings. */
function ResultBlock({ value, isError }: { value: string; isError?: boolean }) {
	const parsed = !isError ? tryParseJsonish(value) : UNPARSEABLE_RB;
	if (parsed !== UNPARSEABLE_RB) {
		return <JsonTree value={parsed} />;
	}
	return (
		<pre className="font-mono whitespace-pre-wrap break-words">{value}</pre>
	);
}

const UNPARSEABLE_RB = Symbol("unparseable");
function tryParseJsonish(value: string): unknown {
	const trimmed = value.trim();
	if (
		!(
			(trimmed.startsWith("{") && trimmed.endsWith("}")) ||
			(trimmed.startsWith("[") && trimmed.endsWith("]"))
		)
	) {
		return UNPARSEABLE_RB;
	}
	try {
		return JSON.parse(trimmed);
	} catch {
		return UNPARSEABLE_RB;
	}
}
