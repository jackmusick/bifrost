/**
 * Admin-only affordance to trigger a bulk summary backfill.
 *
 * Three states, all in one component:
 *   1. Idle: button. Click → fetch dry-run (eligible + est. cost).
 *   2. Confirm: modal with "N runs, ~$X.XX. Continue?"
 *   3. Progress: card that subscribes to summary-backfill:{jobId} WS channel.
 *
 * If a backfill is already running (`useSummaryBackfillJobs({ active: true })`
 * returns a hit on mount), the button is replaced with the progress card
 * attached to that existing job.
 */

import { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import {
	AlertTriangle,
	CheckCircle,
	Loader2,
	RefreshCw,
	X,
	XCircle,
} from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
	AlertDialog,
	AlertDialogAction,
	AlertDialogCancel,
	AlertDialogContent,
	AlertDialogDescription,
	AlertDialogFooter,
	AlertDialogHeader,
	AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Progress } from "@/components/ui/progress";
import {
	useBackfillEligible,
	useBackfillSummaries,
	useCancelBackfillJob,
	useSummaryBackfillJob,
	useSummaryBackfillJobs,
} from "@/services/agentRuns";
import { webSocketService } from "@/services/websocket";

const DISMISSED_KEY = "bifrost:dismissed-backfills";

function readDismissed(): Set<string> {
	try {
		const raw = sessionStorage.getItem(DISMISSED_KEY);
		if (!raw) return new Set();
		const parsed = JSON.parse(raw);
		return new Set(Array.isArray(parsed) ? parsed : []);
	} catch {
		return new Set();
	}
}

function writeDismissed(ids: Set<string>) {
	try {
		sessionStorage.setItem(DISMISSED_KEY, JSON.stringify(Array.from(ids)));
	} catch {
		// sessionStorage can throw in private mode; a dismissed card just
		// reappears on next mount — acceptable.
	}
}

export interface SummaryBackfillButtonProps {
	/** Limit backfill to a single agent. Omit for platform-wide. */
	agentId?: string;
	/** Layout hint. */
	size?: "sm" | "default";
}

type Phase = "idle" | "confirm" | "progress";

export function SummaryBackfillButton({
	agentId,
	size = "sm",
}: SummaryBackfillButtonProps) {
	const [phase, setPhase] = useState<Phase>("idle");
	const [preview, setPreview] = useState<{
		eligible: number;
		estimated_cost_usd: string;
		cost_basis: "history" | "fallback";
	} | null>(null);
	const [jobId, setJobId] = useState<string | null>(null);
	const [dismissed, setDismissed] = useState<Set<string>>(() => readDismissed());

	// On mount, re-attach to an already-running job if one exists for this scope.
	// Only "running" jobs surface here (server-side filter). Terminal jobs that
	// the user hasn't dismissed this session stay on screen via the progress
	// card's own mount state — they don't re-attach after full page reload.
	const { data: activeJobs } = useSummaryBackfillJobs(true);
	const existingJob = useMemo(
		() =>
			phase === "idle" && activeJobs
				? activeJobs.items.find(
						(j) =>
							(j.agent_id ?? null) === (agentId ?? null) &&
							!dismissed.has(j.id),
					)
				: undefined,
		[phase, activeJobs, agentId, dismissed],
	);
	const effectiveJobId = jobId ?? existingJob?.id ?? null;
	const effectivePhase: Phase =
		phase === "idle" && existingJob ? "progress" : phase;

	function dismissJob(id: string) {
		const next = new Set(dismissed);
		next.add(id);
		setDismissed(next);
		writeDismissed(next);
		setPhase("idle");
		setJobId(null);
	}

	const backfill = useBackfillSummaries();

	async function openConfirm() {
		backfill.mutate(
			{
				body: {
					agent_id: agentId,
					statuses: ["pending", "failed"],
					limit: 5000,
					dry_run: true,
				},
			},
			{
				onSuccess: (data) => {
					setPreview({
						eligible: data.eligible,
						estimated_cost_usd: String(data.estimated_cost_usd),
						cost_basis: data.cost_basis,
					});
					setPhase("confirm");
				},
				onError: () => {
					toast.error("Failed to compute backfill estimate");
				},
			},
		);
	}

	async function confirmAndSubmit() {
		backfill.mutate(
			{
				body: {
					agent_id: agentId,
					statuses: ["pending", "failed"],
					limit: 5000,
					dry_run: false,
				},
			},
			{
				onSuccess: (data) => {
					if (!data.job_id) {
						toast.info("Nothing to backfill");
						setPhase("idle");
						return;
					}
					setJobId(data.job_id);
					setPhase("progress");
					toast.success(`Queued ${data.queued} summaries`);
				},
				onError: () => {
					toast.error("Failed to start backfill");
				},
			},
		);
	}

	// Hide the button entirely when nothing is eligible. Avoids the dead-end
	// "Nothing to backfill" modal — no affordance is better than a no-op one.
	// Hook must live above the early returns below to satisfy the rules of hooks.
	const { data: eligible, isLoading: eligibleLoading } =
		useBackfillEligible(agentId);

	if (effectivePhase === "progress" && effectiveJobId) {
		return (
			<SummaryBackfillProgress
				jobId={effectiveJobId}
				agentId={agentId}
				onDismiss={() => dismissJob(effectiveJobId)}
			/>
		);
	}

	if (eligibleLoading) return null;
	if (eligible && eligible.eligible === 0) return null;

	return (
		<>
			<Button
				type="button"
				variant="outline"
				size={size}
				disabled={backfill.isPending}
				onClick={openConfirm}
				data-testid="summary-backfill-button"
			>
				{backfill.isPending && effectivePhase === "idle" ? (
					<Loader2 className="h-3.5 w-3.5 animate-spin" />
				) : (
					<RefreshCw className="h-3.5 w-3.5" />
				)}
				{agentId ? "Backfill pending summaries" : "Backfill summaries"}
			</Button>

			<AlertDialog
				open={effectivePhase === "confirm"}
				onOpenChange={(open) => {
					if (!open) setPhase("idle");
				}}
			>
				<AlertDialogContent>
					<AlertDialogHeader>
						<AlertDialogTitle>
							{preview?.eligible === 0
								? "Nothing to backfill"
								: `Regenerate ${preview?.eligible ?? 0} summaries?`}
						</AlertDialogTitle>
						<AlertDialogDescription>
							{preview?.eligible === 0 ? (
								"All eligible runs already have a completed summary."
							) : (
								<>
									This will re-run the summarization model on{" "}
									<strong>{preview?.eligible}</strong>{" "}
									{agentId ? "runs for this agent." : "runs platform-wide."}{" "}
									Estimated cost:{" "}
									<strong>
										${Number(preview?.estimated_cost_usd ?? 0).toFixed(2)}
									</strong>{" "}
									<span className="text-muted-foreground">
										(
										{preview?.cost_basis === "history"
											? "from recent summaries"
											: "flat estimate; no history"}
										)
									</span>
									.
								</>
							)}
						</AlertDialogDescription>
					</AlertDialogHeader>
					<AlertDialogFooter>
						<AlertDialogCancel>Cancel</AlertDialogCancel>
						{preview?.eligible && preview.eligible > 0 ? (
							<AlertDialogAction
								onClick={confirmAndSubmit}
								disabled={backfill.isPending}
							>
								{backfill.isPending ? (
									<Loader2 className="h-3.5 w-3.5 animate-spin" />
								) : null}
								Start backfill
							</AlertDialogAction>
						) : null}
					</AlertDialogFooter>
				</AlertDialogContent>
			</AlertDialog>
		</>
	);
}

// -----------------------------------------------------------------------------

interface SummaryBackfillProgressProps {
	jobId: string;
	agentId?: string;
	onDismiss: () => void;
}

function SummaryBackfillProgress({
	jobId,
	agentId,
	onDismiss,
}: SummaryBackfillProgressProps) {
	const { data: initial } = useSummaryBackfillJob(jobId);
	const cancel = useCancelBackfillJob();
	const [live, setLive] = useState<{
		total: number;
		succeeded: number;
		failed: number;
		status: string;
		actual_cost_usd: string;
	} | null>(null);

	useEffect(() => {
		void webSocketService.connect([`summary-backfill:${jobId}`]);
		const unsubscribe = webSocketService.onSummaryBackfillUpdate(
			jobId,
			(update) => {
				setLive({
					total: update.total,
					succeeded: update.succeeded,
					failed: update.failed,
					status: update.status,
					actual_cost_usd: update.actual_cost_usd,
				});
			},
		);
		return unsubscribe;
	}, [jobId]);

	const snapshot = useMemo(
		() =>
			live ?? {
				total: initial?.total ?? 0,
				succeeded: initial?.succeeded ?? 0,
				failed: initial?.failed ?? 0,
				status: initial?.status ?? "running",
				actual_cost_usd: String(initial?.actual_cost_usd ?? "0"),
			},
		[live, initial],
	);

	const pct = useMemo(() => {
		if (!snapshot.total) return 0;
		return Math.min(
			100,
			Math.round(
				((snapshot.succeeded + snapshot.failed) / snapshot.total) * 100,
			),
		);
	}, [snapshot]);

	const isTerminal =
		snapshot.status === "complete" ||
		snapshot.status === "cancelled" ||
		snapshot.status === "failed";

	// Fire the completion toast exactly once per terminal transition. The card
	// intentionally does NOT auto-dismiss — the user clicks X to clear it so
	// failure counts stay visible.
	const toastedRef = useRef(false);
	useEffect(() => {
		if (!isTerminal || toastedRef.current) return;
		toastedRef.current = true;
		const cost = Number(snapshot.actual_cost_usd).toFixed(2);
		if (snapshot.status === "complete") {
			const msg =
				snapshot.failed > 0
					? `Backfilled ${snapshot.succeeded} of ${snapshot.total} — ${snapshot.failed} failed — $${cost}`
					: `Backfilled ${snapshot.succeeded} of ${snapshot.total} — $${cost}`;
			toast.success(msg);
		} else if (snapshot.status === "cancelled") {
			toast.info(
				`Backfill cancelled at ${snapshot.succeeded + snapshot.failed} of ${snapshot.total}`,
			);
		} else if (snapshot.status === "failed") {
			toast.error(
				`Backfill failed at ${snapshot.succeeded + snapshot.failed} of ${snapshot.total}`,
			);
		}
	}, [isTerminal, snapshot.status, snapshot.succeeded, snapshot.failed, snapshot.total, snapshot.actual_cost_usd]);

	function handleCancel() {
		cancel.mutate(
			{ params: { path: { job_id: jobId } } },
			{
				onError: () => {
					toast.error("Failed to cancel backfill");
				},
			},
		);
	}

	const statusIcon = !isTerminal ? (
		<Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin text-muted-foreground" />
	) : snapshot.status === "complete" ? (
		<CheckCircle className="h-3.5 w-3.5 shrink-0 text-emerald-500" />
	) : snapshot.status === "cancelled" ? (
		<XCircle className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
	) : (
		<AlertTriangle className="h-3.5 w-3.5 shrink-0 text-rose-500" />
	);

	const headerLabel = !isTerminal
		? "Backfilling summaries"
		: snapshot.status === "complete"
			? "Backfill complete"
			: snapshot.status === "cancelled"
				? "Backfill cancelled"
				: "Backfill failed";

	// When there are failures, link to the Runs tab with a `summary=failed`
	// filter so the admin can review the failed runs and retry them.
	const reviewHref = agentId
		? `/agents/${agentId}?tab=runs&summary=failed`
		: "/agents";

	return (
		<div
			className="inline-flex min-w-[280px] items-center gap-3 rounded-md border bg-card px-3 py-2 text-xs"
			data-testid="summary-backfill-progress"
			data-status={snapshot.status}
		>
			{statusIcon}
			<div className="flex min-w-0 flex-1 flex-col gap-1">
				<div className="flex items-center justify-between">
					<span className="font-medium">{headerLabel}</span>
					<span className="text-muted-foreground">
						{snapshot.succeeded + snapshot.failed} / {snapshot.total}
					</span>
				</div>
				<Progress value={pct} className="h-1.5" />
				{snapshot.failed > 0 ? (
					<Link
						to={reviewHref}
						className="inline-flex items-center text-[11px] text-rose-600 hover:underline dark:text-rose-400"
					>
						{snapshot.failed} failed — Review failed runs →
					</Link>
				) : null}
			</div>
			{isTerminal ? (
				<button
					type="button"
					aria-label="Dismiss"
					title="Dismiss"
					onClick={onDismiss}
					className="inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
					data-testid="summary-backfill-dismiss"
				>
					<X className="h-3.5 w-3.5" />
				</button>
			) : (
				<button
					type="button"
					aria-label="Cancel backfill"
					title="Cancel backfill"
					onClick={handleCancel}
					disabled={cancel.isPending}
					className="inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-accent hover:text-foreground disabled:opacity-50"
					data-testid="summary-backfill-cancel"
				>
					{cancel.isPending ? (
						<Loader2 className="h-3.5 w-3.5 animate-spin" />
					) : (
						<X className="h-3.5 w-3.5" />
					)}
				</button>
			)}
		</div>
	);
}
