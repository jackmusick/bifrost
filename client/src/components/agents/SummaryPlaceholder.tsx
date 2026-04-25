/**
 * Muted placeholder shown when a run's asked/did fields are empty.
 *
 * Keyed off BOTH the run's overall `status` and its `summary_status`:
 *   - A run that never reached `status='completed'` can't be summarized (the
 *     summarizer's idempotent guard short-circuits silently), so showing
 *     "Summary pending…" would be a lie. Surface the real lifecycle state
 *     instead.
 *   - Only when the run is genuinely completed does summary_status matter.
 *
 * Never falls back to raw run.input / run.output — those are opaque (often
 * HTML email bodies) and make the UI unreadable.
 */

import { cn } from "@/lib/utils";

export interface SummaryPlaceholderProps {
	/** The run's summary_status (pending/generating/completed/failed). */
	status: string | undefined | null;
	/** The run's overall status (queued/running/completed/failed/...). Optional
	 *  for backwards compat, but preferred — lets us tell users when a run
	 *  never actually finished. */
	runStatus?: string | undefined | null;
	muted?: boolean;
	className?: string;
}

export function SummaryPlaceholder({
	status,
	runStatus,
	muted = false,
	className,
}: SummaryPlaceholderProps) {
	// Prefer run-level lifecycle signals when the run never completed.
	// These cases make "Summary pending…" misleading — the summarizer will
	// never run on a non-completed AgentRun.
	let text: string;
	if (runStatus === "running" || runStatus === "queued") {
		text = "Run in progress…";
	} else if (runStatus === "failed") {
		text = "Run failed";
	} else if (runStatus === "budget_exceeded") {
		text = "Budget exceeded";
	} else if (runStatus === "cancelled") {
		text = "Run cancelled";
	} else if (status === "failed") {
		text = "Summary failed";
	} else if (status === "generating") {
		text = "Summarizing…";
	} else if (status === "completed") {
		text = "—";
	} else {
		// Run completed but summary_status is still pending.
		text = "Summary pending…";
	}
	return (
		<span
			className={cn(
				"italic",
				muted ? "text-muted-foreground/70" : "text-muted-foreground",
				className,
			)}
		>
			{text}
		</span>
	);
}
