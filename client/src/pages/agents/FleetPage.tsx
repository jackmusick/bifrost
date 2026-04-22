/**
 * FleetPage — fleet-wide view of all agents.
 *
 * Replaces the legacy `Agents` page with the design from the M1 mockup:
 * fleet stats strip, search + grid/table toggle, per-agent cards with
 * lightweight stats. Per-agent stats are fetched via `useAgentStats(id)`
 * (N+1 queries — acceptable for v1; documented as TODO for follow-up).
 *
 * Replaces: `client/src/pages/Agents.tsx` (kept until T33 swaps the route).
 */

import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
	Bot,
	LayoutGrid,
	List,
	MessageSquare,
	Phone,
	Hash,
	Plus,
	Power,
	Search,
	Clock,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
	Card,
	CardContent,
	CardHeader,
	CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import {
	DataTable,
	DataTableBody,
	DataTableCell,
	DataTableHead,
	DataTableHeader,
	DataTableRow,
} from "@/components/ui/data-table";
import {
	ToggleGroup,
	ToggleGroupItem,
} from "@/components/ui/toggle-group";

import { FleetStats } from "@/components/agents/FleetStats";
import { QueueBanner } from "@/components/agents/QueueBanner";
import { useAgents, type AgentSummary } from "@/hooks/useAgents";
import { useAgentStats, useFleetStats } from "@/services/agents";
import {
	cn,
	formatCost,
	formatDuration,
	formatNumber,
	formatRelativeTime,
} from "@/lib/utils";

type ViewMode = "grid" | "table";

export function FleetPage() {
	const [view, setView] = useState<ViewMode>("grid");
	const [query, setQuery] = useState("");

	const { data: agents, isLoading: agentsLoading } = useAgents();
	const { data: fleetStats, isLoading: fleetLoading } = useFleetStats();

	const filtered = useMemo(() => {
		const q = query.trim().toLowerCase();
		if (!q) return agents ?? [];
		return (agents ?? []).filter((a) => {
			const name = (a.name ?? "").toLowerCase();
			const desc = (a.description ?? "").toLowerCase();
			return name.includes(q) || desc.includes(q);
		});
	}, [agents, query]);

	const totalAgents = agents?.length ?? 0;
	const activeCount = useMemo(
		() => (agents ?? []).filter((a) => a.is_active).length,
		[agents],
	);

	return (
		<div className="flex flex-col gap-5 max-w-7xl mx-auto">
			{/* Header */}
			<div className="flex items-start justify-between gap-3">
				<div>
					<h1 className="text-3xl font-extrabold tracking-tight">
						Agents
					</h1>
					<p className="mt-1 text-sm text-muted-foreground">
						{totalAgents} total · {activeCount} active · last 7 days
					</p>
				</div>
				<Button asChild>
					<Link to="/agents/new">
						<Plus className="h-4 w-4" /> New agent
					</Link>
				</Button>
			</div>

			{/* Tuning queue banner — only shows when fleet has flagged runs */}
			{fleetStats && fleetStats.needs_review > 0 ? (
				<QueueBanner
					count={fleetStats.needs_review}
					actionLabel="Review now"
					actionHref="/agents"
				/>
			) : null}

			{/* Fleet stats */}
			{fleetLoading || !fleetStats ? (
				<div className="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
					{[...Array(5)].map((_, i) => (
						<Skeleton key={i} className="h-24 w-full" />
					))}
				</div>
			) : (
				<FleetStats stats={fleetStats} />
			)}

			{/* Search + view toggle */}
			<div className="flex items-center justify-between gap-3">
				<div className="relative flex-1 max-w-md">
					<Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
					<Input
						aria-label="Search agents"
						placeholder="Search agents…"
						value={query}
						onChange={(e) => setQuery(e.target.value)}
						className="pl-8"
					/>
				</div>
				<ToggleGroup
					type="single"
					value={view}
					onValueChange={(v: string) =>
						v && setView(v as ViewMode)
					}
				>
					<ToggleGroupItem value="grid" aria-label="Grid view" size="sm">
						<LayoutGrid className="h-4 w-4" />
					</ToggleGroupItem>
					<ToggleGroupItem
						value="table"
						aria-label="Table view"
						size="sm"
					>
						<List className="h-4 w-4" />
					</ToggleGroupItem>
				</ToggleGroup>
			</div>

			{/* Content */}
			{agentsLoading ? (
				view === "grid" ? (
					<div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
						{[...Array(6)].map((_, i) => (
							<Skeleton key={i} className="h-48 w-full" />
						))}
					</div>
				) : (
					<div className="space-y-2">
						{[...Array(3)].map((_, i) => (
							<Skeleton key={i} className="h-12 w-full" />
						))}
					</div>
				)
			) : filtered.length === 0 ? (
				<EmptyState hasQuery={query.trim().length > 0} />
			) : view === "grid" ? (
				<div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
					{filtered.map((agent) => (
						<AgentGridCard key={agent.id} agent={agent} />
					))}
				</div>
			) : (
				<AgentTable agents={filtered} />
			)}
		</div>
	);
}

function EmptyState({ hasQuery }: { hasQuery: boolean }) {
	return (
		<Card>
			<CardContent className="flex flex-col items-center justify-center py-12 text-center">
				<Bot className="h-12 w-12 text-muted-foreground" />
				<h3 className="mt-4 text-lg font-semibold">
					{hasQuery ? "No agents match your search" : "No agents yet"}
				</h3>
				<p className="mt-1 text-sm text-muted-foreground">
					{hasQuery
						? "Try adjusting your search."
						: "Get started by creating your first AI agent."}
				</p>
				{!hasQuery ? (
					<Button asChild variant="outline" className="mt-4">
						<Link to="/agents/new">
							<Plus className="h-4 w-4" /> New agent
						</Link>
					</Button>
				) : null}
			</CardContent>
		</Card>
	);
}

function ChannelBadge({ channel }: { channel: string }) {
	const Icon =
		channel === "voice"
			? Phone
			: channel === "teams" || channel === "slack"
				? Hash
				: MessageSquare;
	return (
		<Badge variant="outline" className="text-[11px]">
			<Icon className="h-3 w-3" />
			{channel}
		</Badge>
	);
}

function AgentGridCard({ agent }: { agent: AgentSummary }) {
	// TODO(plan-2): replace per-card useAgentStats N+1 with a denormalized
	// list endpoint that returns fleet member stats in one round-trip.
	const { data: stats, isLoading } = useAgentStats(agent.id ?? undefined);
	const successRate = stats?.success_rate ?? 0;
	const successColor =
		successRate >= 0.9
			? "text-emerald-600 dark:text-emerald-400"
			: successRate >= 0.75
				? "text-yellow-600 dark:text-yellow-400"
				: "text-rose-600 dark:text-rose-400";

	return (
		<Card className="flex flex-col transition-colors hover:border-primary">
			<Link
				to={`/agents/${agent.id}`}
				className="flex h-full flex-col"
				data-testid={`agent-card-${agent.id}`}
			>
				<CardHeader className="pb-3">
					<div className="flex items-start justify-between gap-3">
						<div className="flex min-w-0 items-center gap-2">
							<Bot className="h-4 w-4 shrink-0 text-muted-foreground" />
							<CardTitle className="truncate text-base">
								{agent.name}
							</CardTitle>
							{!agent.is_active ? (
								<Badge variant="secondary" className="text-[11px]">
									Paused
								</Badge>
							) : null}
						</div>
						<div className="flex shrink-0 flex-wrap gap-1">
							{(agent.channels ?? [])
								.slice(0, 3)
								.map((c) => (
									<ChannelBadge key={c} channel={c} />
								))}
						</div>
					</div>
					{agent.description ? (
						<p className="mt-1.5 line-clamp-2 text-sm text-muted-foreground">
							{agent.description}
						</p>
					) : null}
				</CardHeader>
				<CardContent className="mt-auto flex flex-col gap-3 pt-0">
					{isLoading ? (
						<Skeleton className="h-12 w-full" />
					) : stats && stats.runs_7d > 0 ? (
						<>
							<div className="grid grid-cols-3 gap-2">
								<MiniStat
									label="Runs"
									value={formatNumber(stats.runs_7d)}
								/>
								<MiniStat
									label="Success"
									value={`${Math.round(stats.success_rate * 100)}%`}
									valueClass={successColor}
								/>
								<MiniStat
									label="Spend"
									value={formatCost(stats.total_cost_7d)}
								/>
							</div>
							<div className="flex items-center justify-between text-[11px] text-muted-foreground">
								<span className="inline-flex items-center gap-1">
									<Clock className="h-3 w-3" />
									{stats.last_run_at
										? `Last run ${formatRelativeTime(stats.last_run_at)}`
										: "—"}
								</span>
								<span>
									avg {formatDuration(stats.avg_duration_ms)}
								</span>
							</div>
						</>
					) : (
						<p className="text-xs text-muted-foreground">
							No runs yet ·{" "}
							{agent.is_active ? "waiting for traffic" : "paused"}
						</p>
					)}
				</CardContent>
			</Link>
		</Card>
	);
}

function MiniStat({
	label,
	value,
	valueClass,
}: {
	label: string;
	value: string;
	valueClass?: string;
}) {
	return (
		<div>
			<div className="text-[10.5px] text-muted-foreground">{label}</div>
			<div
				className={cn(
					"text-sm font-semibold tabular-nums",
					valueClass,
				)}
			>
				{value}
			</div>
		</div>
	);
}

function AgentTable({ agents }: { agents: AgentSummary[] }) {
	return (
		<div className="rounded-lg border">
			<DataTable>
				<DataTableHeader>
					<DataTableRow>
						<DataTableHead>Name</DataTableHead>
						<DataTableHead>Channels</DataTableHead>
						<DataTableHead className="w-0 whitespace-nowrap text-right">
							Runs (7d)
						</DataTableHead>
						<DataTableHead className="w-0 whitespace-nowrap text-right">
							Success
						</DataTableHead>
						<DataTableHead className="w-0 whitespace-nowrap text-right">
							Spend (7d)
						</DataTableHead>
						<DataTableHead className="w-0 whitespace-nowrap">
							Status
						</DataTableHead>
					</DataTableRow>
				</DataTableHeader>
				<DataTableBody>
					{agents.map((agent) => (
						<AgentTableRow key={agent.id} agent={agent} />
					))}
				</DataTableBody>
			</DataTable>
		</div>
	);
}

function AgentTableRow({ agent }: { agent: AgentSummary }) {
	// TODO(plan-2): see AgentGridCard — N+1 stats queries.
	const { data: stats } = useAgentStats(agent.id ?? undefined);
	const hasRuns = (stats?.runs_7d ?? 0) > 0;
	const navigateTo = `/agents/${agent.id}`;

	return (
		<DataTableRow
			className="cursor-pointer hover:bg-accent/40"
			onClick={() => {
				window.location.href = navigateTo;
			}}
		>
			<DataTableCell>
				<div className="flex items-center gap-2">
					<Bot className="h-4 w-4 text-muted-foreground" />
					<span className="font-medium">{agent.name}</span>
				</div>
				{agent.description ? (
					<div className="text-xs text-muted-foreground line-clamp-1">
						{agent.description}
					</div>
				) : null}
			</DataTableCell>
			<DataTableCell>
				<div className="flex flex-wrap gap-1">
					{(agent.channels ?? []).map((c) => (
						<ChannelBadge key={c} channel={c} />
					))}
				</div>
			</DataTableCell>
			<DataTableCell className="w-0 whitespace-nowrap text-right tabular-nums">
				{hasRuns ? formatNumber(stats!.runs_7d) : "—"}
			</DataTableCell>
			<DataTableCell className="w-0 whitespace-nowrap text-right tabular-nums">
				{hasRuns
					? `${Math.round(stats!.success_rate * 100)}%`
					: "—"}
			</DataTableCell>
			<DataTableCell className="w-0 whitespace-nowrap text-right tabular-nums">
				{hasRuns ? formatCost(stats!.total_cost_7d) : "—"}
			</DataTableCell>
			<DataTableCell className="w-0 whitespace-nowrap">
				{agent.is_active ? (
					<Badge variant="default" className="bg-emerald-500 text-white">
						<Power className="h-3 w-3" /> Active
					</Badge>
				) : (
					<Badge variant="secondary">Paused</Badge>
				)}
			</DataTableCell>
		</DataTableRow>
	);
}

export default FleetPage;
