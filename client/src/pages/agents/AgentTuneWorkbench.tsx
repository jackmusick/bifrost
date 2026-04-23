/**
 * AgentTuneWorkbench — three-pane tuning workbench.
 *
 * Left: flagged runs (expandable transcripts) + Generate proposal CTA.
 * Center: prompt editor (current collapsible, proposed editable with diff).
 * Right: dry-run impact panel.
 *
 * State lives in this component; Apply live wires up in Task 7.
 */

import { useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
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
	TYPE_MUTED,
	TYPE_PANE_LABEL,
} from "@/components/agents/design-tokens";

import { useAgent } from "@/hooks/useAgents";
import { useAgentRuns } from "@/services/agentRuns";
import { useAgentStats } from "@/services/agents";
import {
	useApplyTuning,
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
	const applyTuning = useApplyTuning();
	const navigate = useNavigate();
	const queryClient = useQueryClient();

	const flagged: AgentRun[] = (flaggedResp?.items ?? []) as AgentRun[];
	const hasFlaggedRuns = flagged.length > 0;
	const canGenerate = hasFlaggedRuns && !tuningSession.isPending;

	const [proposal, setProposal] = useState<ConsolidatedProposal | null>(null);
	const [edits, setEdits] = useState<string>("");
	const [currentOpen, setCurrentOpen] = useState(false);

	const currentPrompt = agent?.system_prompt ?? "";

	function handleGenerate() {
		if (!agentId) return;
		tuningSession.mutate(
			{ params: { path: { agent_id: agentId } } },
			{
				onSuccess: (data) => {
					setProposal(data);
					setEdits(data.proposed_prompt);
				},
				onError: () => toast.error("Failed to generate proposal"),
			},
		);
	}

	function handleDiscard() {
		setProposal(null);
		setEdits("");
	}

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
				<div className="flex flex-col gap-3" data-testid="tune-pane-flagged">
					<div className={TYPE_PANE_LABEL}>Flagged runs ({flagged.length})</div>
					{flaggedLoading ? (
						<Skeleton className="h-24 w-full" />
					) : !hasFlaggedRuns ? (
						<div
							className={cn(
								"rounded-md border bg-muted/20 p-4 text-center",
								TYPE_MUTED,
								TONE_MUTED,
							)}
						>
							No flagged runs. Mark a run thumbs-down from the runs tab to tune
							against it.
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
						{proposal
							? "Re-generate"
							: `Generate proposal from ${flagged.length} run${flagged.length === 1 ? "" : "s"}`}
					</Button>
				</div>

				{/* Center: prompt editor */}
				<div className="flex flex-col gap-3" data-testid="tune-pane-editor">
					<div className={TYPE_PANE_LABEL}>Prompt editor</div>

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
								I&apos;ll read the flagged runs and suggest one consolidated
								prompt change.
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
								<p className={cn("italic", TYPE_MUTED, TONE_MUTED)}>
									{proposal.summary}
								</p>
							) : null}
							<PromptDiffViewer before={currentPrompt} after={edits} />
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
							</div>
						</div>
					)}
				</div>

				{/* Right: impact */}
				<div className="flex flex-col gap-3" data-testid="tune-pane-impact">
					<div className={TYPE_PANE_LABEL}>Impact</div>
					<div className="rounded-md border bg-muted/20 p-4">
						<p className={cn("mb-3", TYPE_MUTED, TONE_MUTED)}>
							Simulate the proposed prompt against the flagged runs to see if it
							changes behavior before going live.
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
