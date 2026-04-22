/**
 * Compact card for one agent run, used in the agent detail Runs tab.
 *
 * Shows: status badge, asked text, did/error text, verdict badge,
 * timing metadata (when, duration, tokens), and inline verdict toggles.
 *
 * Adapted from the mockup's `RunCard` (AgentDetailPage.tsx) — replaces inline
 * styles with Tailwind + shadcn primitives.
 */

import { Clock, Hash, ThumbsUp, ThumbsDown } from "lucide-react";
import {
	CheckCircle,
	XCircle,
	Loader2,
	AlertTriangle,
} from "lucide-react";
import type { MouseEvent } from "react";

import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { formatDuration, formatNumber, formatRelativeTime } from "@/lib/utils";
import type { components } from "@/lib/v1";

import type { Verdict } from "./RunReviewPanel";

type AgentRun = components["schemas"]["AgentRunResponse"];

export interface RunCardProps {
	run: AgentRun;
	verdict?: Verdict;
	highlight?: string;
	onOpen?: () => void;
	onVerdict?: (v: Verdict) => void;
	conversationCount?: number;
}

function StatusBadge({ status }: { status: string }) {
	switch (status) {
		case "completed":
			return (
				<Badge variant="default" className="bg-emerald-500 text-white">
					<CheckCircle className="h-3 w-3" /> Completed
				</Badge>
			);
		case "failed":
			return (
				<Badge variant="destructive">
					<XCircle className="h-3 w-3" /> Failed
				</Badge>
			);
		case "running":
			return (
				<Badge variant="secondary">
					<Loader2 className="h-3 w-3 animate-spin" /> Running
				</Badge>
			);
		case "budget_exceeded":
			return (
				<Badge variant="warning">
					<AlertTriangle className="h-3 w-3" /> Budget exceeded
				</Badge>
			);
		default:
			return <Badge variant="outline">{status}</Badge>;
	}
}

export function RunCard({
	run,
	verdict = null,
	highlight,
	onOpen,
	onVerdict,
	conversationCount = 0,
}: RunCardProps) {
	const q = highlight?.trim().toLowerCase() ?? "";
	const metadataEntries = run.metadata ? Object.entries(run.metadata) : [];
	const ranked = q
		? [...metadataEntries].sort((a, b) => {
				const aHit =
					a[0].toLowerCase().includes(q) ||
					a[1].toLowerCase().includes(q)
						? -1
						: 0;
				const bHit =
					b[0].toLowerCase().includes(q) ||
					b[1].toLowerCase().includes(q)
						? -1
						: 0;
				return aHit - bHit;
			})
		: metadataEntries;
	const visibleChips = ranked.slice(0, 3);
	const overflow = metadataEntries.length - visibleChips.length;
	const startedAt = run.started_at ?? run.created_at;
	const canVerdict = run.status === "completed";

	function handleVerdict(target: Verdict, e: MouseEvent) {
		e.stopPropagation();
		if (!onVerdict) return;
		onVerdict(verdict === target ? null : target);
	}

	return (
		<div
			role={onOpen ? "button" : undefined}
			tabIndex={onOpen ? 0 : undefined}
			onClick={onOpen}
			onKeyDown={(e) => {
				if (onOpen && (e.key === "Enter" || e.key === " ")) {
					e.preventDefault();
					onOpen();
				}
			}}
			className={cn(
				"flex items-start gap-3 rounded-lg border bg-card p-3 transition-colors",
				onOpen && "cursor-pointer hover:bg-accent/50",
			)}
			data-slot="run-card"
		>
			<div className="flex min-w-0 flex-1 flex-col gap-1.5">
				<div className="flex flex-wrap items-center gap-2">
					<StatusBadge status={run.status} />
					<div
						className="min-w-0 flex-1 truncate text-sm"
						title={run.asked ?? undefined}
					>
						{run.asked || (
							<span className="text-muted-foreground">—</span>
						)}
					</div>
					{verdict === "up" ? (
						<span className="inline-flex items-center gap-1 rounded border border-emerald-500/30 bg-emerald-500/10 px-1.5 py-0.5 text-[11px] font-medium text-emerald-700 dark:text-emerald-300">
							<ThumbsUp size={11} /> Good
						</span>
					) : verdict === "down" ? (
						<span className="inline-flex items-center gap-1 rounded border border-rose-500/30 bg-rose-500/10 px-1.5 py-0.5 text-[11px] font-medium text-rose-700 dark:text-rose-300">
							<ThumbsDown size={11} /> Wrong
							{conversationCount > 0
								? ` · ${conversationCount} msg`
								: ""}
						</span>
					) : null}
				</div>
				<div
					className="truncate text-sm text-muted-foreground"
					title={run.did ?? undefined}
				>
					{run.did ||
						(run.error ? `error: ${run.error}` : "—")}
				</div>
				<div className="flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
					<span className="inline-flex items-center gap-1">
						<Clock size={11} />
						{formatRelativeTime(startedAt)}
					</span>
					{run.duration_ms != null ? (
						<>
							<span>·</span>
							<span>{formatDuration(run.duration_ms)}</span>
						</>
					) : null}
					<span>·</span>
					<span className="inline-flex items-center gap-1">
						<Hash size={11} />
						{formatNumber(run.tokens_used)}
					</span>
					{visibleChips.length > 0 ? <span>·</span> : null}
					<div className="inline-flex flex-wrap gap-1">
						{visibleChips.map(([k, v]) => {
							const isHit =
								q &&
								(k.toLowerCase().includes(q) ||
									v.toLowerCase().includes(q));
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
									<span className="text-muted-foreground">
										{k}
									</span>
									<span className="font-mono">{v}</span>
								</span>
							);
						})}
						{overflow > 0 ? (
							<span className="inline-flex items-center rounded border border-border bg-card px-1.5 py-0.5 text-[11px]">
								+{overflow}
							</span>
						) : null}
					</div>
				</div>
			</div>

			<div
				className="flex shrink-0 items-center"
				onClick={(e) => e.stopPropagation()}
			>
				{canVerdict && onVerdict ? (
					<div className="flex gap-1">
						<button
							type="button"
							aria-label="Mark as good"
							aria-pressed={verdict === "up"}
							title="Good"
							onClick={(e) => handleVerdict("up", e)}
							className={cn(
								"grid h-7 w-7 place-items-center rounded-full border transition-colors",
								verdict === "up"
									? "border-emerald-500 bg-emerald-500/15 text-emerald-600 dark:text-emerald-400"
									: "bg-background hover:bg-accent",
							)}
						>
							<ThumbsUp size={14} />
						</button>
						<button
							type="button"
							aria-label="Mark as wrong"
							aria-pressed={verdict === "down"}
							title="Wrong"
							onClick={(e) => handleVerdict("down", e)}
							className={cn(
								"grid h-7 w-7 place-items-center rounded-full border transition-colors",
								verdict === "down"
									? "border-rose-500 bg-rose-500/15 text-rose-600 dark:text-rose-400"
									: "bg-background hover:bg-accent",
							)}
						>
							<ThumbsDown size={14} />
						</button>
					</div>
				) : (
					<span className="text-[11px] text-muted-foreground">n/a</span>
				)}
			</div>
		</div>
	);
}
