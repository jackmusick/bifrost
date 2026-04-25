/**
 * Card surfacing one flagged run on the agent detail Overview tab.
 *
 * Like RunCard but emphasises the verdict reason — used in a side column to
 * draw the user toward the runs that explicitly need their attention.
 */

import { ThumbsDown, ChevronRight, Clock } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { formatRelativeTime } from "@/lib/utils";
import type { components } from "@/lib/v1";

type AgentRun = components["schemas"]["AgentRunResponse"];

export interface NeedsReviewCardProps {
	run: AgentRun;
	onOpen?: () => void;
	className?: string;
}

export function NeedsReviewCard({
	run,
	onOpen,
	className,
}: NeedsReviewCardProps) {
	const startedAt = run.started_at ?? run.created_at;
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
				"flex items-start gap-3 rounded-lg border border-rose-500/30 bg-rose-500/5 p-3 transition-colors",
				onOpen && "cursor-pointer hover:bg-rose-500/10",
				className,
			)}
			data-slot="needs-review-card"
		>
			<div className="grid h-7 w-7 shrink-0 place-items-center rounded-full bg-rose-500/15 text-rose-600 dark:text-rose-400">
				<ThumbsDown size={14} />
			</div>
			<div className="flex min-w-0 flex-1 flex-col gap-1">
				<div className="flex items-center gap-2">
					<Badge
						variant="destructive"
						className="bg-rose-500/15 text-rose-700 dark:text-rose-300"
					>
						Flagged
					</Badge>
					<div
						className="min-w-0 flex-1 truncate text-sm font-medium"
						title={run.asked ?? undefined}
					>
						{run.asked || (
							<span className="text-muted-foreground">—</span>
						)}
					</div>
				</div>
				{run.verdict_note ? (
					<div
						className="line-clamp-2 text-xs text-muted-foreground"
						title={run.verdict_note}
					>
						“{run.verdict_note}”
					</div>
				) : run.did ? (
					<div
						className="truncate text-xs text-muted-foreground"
						title={run.did}
					>
						{run.did}
					</div>
				) : null}
				<div className="flex items-center gap-1 text-[11px] text-muted-foreground">
					<Clock size={11} />
					{formatRelativeTime(startedAt)}
				</div>
			</div>
			{onOpen ? (
				<ChevronRight
					size={14}
					className="mt-1 shrink-0 text-muted-foreground"
				/>
			) : null}
		</div>
	);
}
