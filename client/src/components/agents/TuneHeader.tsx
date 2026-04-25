import type { ReactNode } from "react";
import { ArrowLeft, Sparkles } from "lucide-react";
import { Link } from "react-router-dom";

import { Skeleton } from "@/components/ui/skeleton";
import { cn, formatNumber, formatRelativeTime } from "@/lib/utils";
import type { components } from "@/lib/v1";

import { GAP_CARD, TONE_MUTED, TYPE_BODY } from "./design-tokens";
import { StatCard } from "./StatCard";

type AgentStats = components["schemas"]["AgentStatsResponse"];

export interface TuneHeaderProps {
	agentId: string | undefined;
	agentName: string | undefined;
	flaggedCount: number;
	stats: AgentStats | null;
	statsLoading: boolean;
	/** Action slot rendered at the top-right of the header. */
	action?: ReactNode;
}

export function TuneHeader({
	agentId,
	agentName,
	flaggedCount,
	stats,
	statsLoading,
	action,
}: TuneHeaderProps) {
	return (
		<div className="flex flex-col gap-4">
			<div className="flex items-center gap-3">
				<Link
					to={agentId ? `/agents/${agentId}` : "/agents"}
					className="inline-flex w-fit items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground"
				>
					<ArrowLeft className="h-3 w-3" />
					{agentName ?? "Back to agent"}
				</Link>
				<span className="text-xs text-muted-foreground">·</span>
				<Link
					to={agentId ? `/agents/${agentId}/review` : "/agents"}
					className="text-xs text-muted-foreground hover:text-foreground"
				>
					Review flagged runs
				</Link>
			</div>

			<div className="flex flex-wrap items-start justify-between gap-3">
				<div>
					<h1 className="flex items-center gap-2 text-4xl font-extrabold tracking-tight">
						<Sparkles className="h-7 w-7" />
						Tune agent
					</h1>
					<p className={cn("mt-2", TYPE_BODY, TONE_MUTED)}>
						Refine {agentName ?? "this agent"}
						&apos;s prompt against {flaggedCount} flagged run
						{flaggedCount === 1 ? "" : "s"}. Changes are dry-run
						before going live.
					</p>
				</div>
				{action ? <div className="flex items-center gap-2">{action}</div> : null}
			</div>

			<div className={cn("grid grid-cols-2 lg:grid-cols-4", GAP_CARD)}>
				{statsLoading || !stats ? (
					<>
						{[0, 1, 2, 3].map((i) => (
							<Skeleton
								key={i}
								data-testid="stat-skeleton"
								className="h-24 w-full"
							/>
						))}
					</>
				) : (
					<>
						<StatCard
							label="Flagged runs"
							value={formatNumber(flaggedCount)}
							alert={flaggedCount > 0}
						/>
						<StatCard
							label="Runs (7d)"
							value={formatNumber(stats.runs_7d)}
						/>
						<StatCard
							label="Success rate"
							value={`${Math.round(
								(stats.success_rate ?? 0) * 100,
							)}%`}
						/>
						<StatCard
							label="Last run"
							value={
								stats.last_run_at
									? formatRelativeTime(stats.last_run_at)
									: "—"
							}
						/>
					</>
				)}
			</div>
		</div>
	);
}
