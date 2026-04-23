/**
 * AgentTuneWorkbench — three-pane tuning workbench.
 *
 * Left: flagged runs (expandable transcripts) + Generate proposal CTA.
 * Center: prompt editor (current read-only, proposed editable with diff).
 * Right: dry-run impact panel.
 *
 * State lives in this component; mutations wire up in follow-up tasks.
 */

import { useParams } from "react-router-dom";
import { Sparkles } from "lucide-react";

import { Button } from "@/components/ui/button";

import { FlaggedRunCard } from "@/components/agents/FlaggedRunCard";
import { TuneHeader } from "@/components/agents/TuneHeader";
import {
	TONE_MUTED,
	TYPE_MUTED,
} from "@/components/agents/design-tokens";

import { useAgent } from "@/hooks/useAgents";
import { useAgentRuns } from "@/services/agentRuns";
import { useAgentStats } from "@/services/agents";
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

	const flagged: AgentRun[] = (flaggedResp?.items ?? []) as AgentRun[];
	const canGenerate = flagged.length > 0;

	function handleGenerate() {
		// Wired up in Task 6.
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
				<div
					className="flex flex-col gap-3"
					data-testid="tune-pane-flagged"
				>
					<div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
						Flagged runs ({flagged.length})
					</div>
					{flaggedLoading ? (
						<div className={cn(TYPE_MUTED)}>Loading runs…</div>
					) : flagged.length === 0 ? (
						<div
							className={cn(
								"rounded-md border bg-muted/20 p-4 text-center",
								TYPE_MUTED,
								TONE_MUTED,
							)}
						>
							No flagged runs. Mark a run thumbs-down from the runs
							tab to tune against it.
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
						<Sparkles className="h-3.5 w-3.5" />
						Generate proposal from {flagged.length} run
						{flagged.length === 1 ? "" : "s"}
					</Button>
				</div>

				{/* Center: prompt editor */}
				<div
					className="flex flex-col gap-3"
					data-testid="tune-pane-editor"
				>
					<div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
						Prompt editor
					</div>
					<div className="rounded-md border bg-muted/20 p-6 text-center">
						<p className={cn("mb-3", TYPE_MUTED, TONE_MUTED)}>
							I&apos;ll read the flagged runs and suggest one
							consolidated prompt change.
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
				</div>

				{/* Right: impact */}
				<div
					className="flex flex-col gap-3"
					data-testid="tune-pane-impact"
				>
					<div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
						Impact
					</div>
					<div className="rounded-md border bg-muted/20 p-4">
						<p className={cn("mb-3", TYPE_MUTED, TONE_MUTED)}>
							Simulate the proposed prompt against the flagged
							runs to see if it changes behavior before going
							live.
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
