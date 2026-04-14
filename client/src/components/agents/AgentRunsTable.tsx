/**
 * Reusable Agent Runs table with filters.
 * Used in ExecutionHistory (agents tab) and future agent detail page.
 */

import { useState, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import {
	Bot,
	CheckCircle,
	XCircle,
	Loader2,
	Clock,
	AlertTriangle,
	Eye,
	Globe,
	Building2,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
	DataTable,
	DataTableBody,
	DataTableCell,
	DataTableHead,
	DataTableHeader,
	DataTableRow,
} from "@/components/ui/data-table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { SearchBox } from "@/components/search/SearchBox";
import { useSearch } from "@/hooks/useSearch";
import { DateRangePicker } from "@/components/ui/date-range-picker";
import { OrganizationSelect } from "@/components/forms/OrganizationSelect";
import { useOrganizations } from "@/hooks/useOrganizations";
import { useAgents } from "@/hooks/useAgents";
import { formatDate } from "@/lib/utils";
import { useAgentRuns, useAgentRunListStream, type AgentRun } from "@/services/agentRuns";
import {
	Select,
	SelectContent,
	SelectItem,
	SelectTrigger,
	SelectValue,
} from "@/components/ui/select";
import type { DateRange } from "react-day-picker";
import type { components } from "@/lib/v1";

type Organization = components["schemas"]["OrganizationPublic"];

function getStatusBadge(status: string) {
	switch (status) {
		case "completed":
			return (
				<Badge variant="default" className="bg-green-500">
					<CheckCircle className="mr-1 h-3 w-3" />
					Completed
				</Badge>
			);
		case "failed":
			return (
				<Badge variant="destructive">
					<XCircle className="mr-1 h-3 w-3" />
					Failed
				</Badge>
			);
		case "running":
			return (
				<Badge variant="secondary">
					<Loader2 className="mr-1 h-3 w-3 animate-spin" />
					Running
				</Badge>
			);
		case "queued":
			return (
				<Badge variant="outline">
					<Clock className="mr-1 h-3 w-3" />
					Queued
				</Badge>
			);
		case "budget_exceeded":
			return (
				<Badge
					variant="outline"
					className="border-yellow-500 text-yellow-600 dark:text-yellow-500"
				>
					<AlertTriangle className="mr-1 h-3 w-3" />
					Budget Exceeded
				</Badge>
			);
		default:
			return <Badge variant="outline">{status}</Badge>;
	}
}

function triggerBadge(trigger: string) {
	const labels: Record<string, string> = {
		event: "Event",
		schedule: "Schedule",
		api: "API/SDK",
		chat: "Chat",
	};
	return (
		<Badge variant="outline" className="text-xs">
			{labels[trigger] || trigger}
		</Badge>
	);
}

interface AgentRunsTableProps {
	isPlatformAdmin: boolean;
}

export function AgentRunsTable({ isPlatformAdmin }: AgentRunsTableProps) {
	const navigate = useNavigate();
	const [statusFilter, setStatusFilter] = useState<string>("all");
	const [searchTerm, setSearchTerm] = useState("");
	const [agentFilter, setAgentFilter] = useState<string>("all");
	const [dateRange, setDateRange] = useState<DateRange | undefined>();
	const [filterOrgId, setFilterOrgId] = useState<string | null | undefined>(undefined);

	const { data: agents } = useAgents();
	const { data: organizations } = useOrganizations({ enabled: isPlatformAdmin });

	const getOrgName = (orgId: string | null | undefined): string => {
		if (!orgId) return "Global";
		const org = organizations?.find((o: Organization) => o.id === orgId);
		return org?.name || orgId;
	};

	const dateFilters = useMemo(() => {
		if (!dateRange?.from) return {};
		const startDate = new Date(dateRange.from);
		startDate.setHours(0, 0, 0, 0);
		const endDate = new Date(dateRange.to || dateRange.from);
		endDate.setHours(23, 59, 59, 999);
		return {
			startDate: startDate.toISOString(),
			endDate: endDate.toISOString(),
		};
	}, [dateRange]);

	const {
		data,
		isLoading,
	} = useAgentRuns({
		status: statusFilter !== "all" ? statusFilter : undefined,
		agentId: agentFilter !== "all" ? agentFilter : undefined,
		orgId: filterOrgId || undefined,
		...dateFilters,
		limit: 200,
	});

	useAgentRunListStream();

	const runs = data?.items || [];

	const filteredRuns = useSearch(runs, searchTerm, [
		"agent_name",
		"id",
		"trigger_type",
		(run) => run.status,
	]);

	return (
		<>
			{/* Search and Filters */}
			<div className="flex items-center gap-4">
				<SearchBox
					value={searchTerm}
					onChange={setSearchTerm}
					placeholder="Search by agent name, run ID..."
					className="flex-1 max-w-2xl"
				/>
				<Select value={agentFilter} onValueChange={setAgentFilter}>
					<SelectTrigger className="w-48">
						<SelectValue placeholder="All agents" />
					</SelectTrigger>
					<SelectContent>
						<SelectItem value="all">All Agents</SelectItem>
						{(agents || []).map((agent: { id: string; name: string }) => (
							<SelectItem key={agent.id} value={agent.id}>
								{agent.name}
							</SelectItem>
						))}
					</SelectContent>
				</Select>
				<DateRangePicker
					dateRange={dateRange}
					onDateRangeChange={setDateRange}
				/>
				{isPlatformAdmin && (
					<div className="w-64">
						<OrganizationSelect
							value={filterOrgId}
							onChange={setFilterOrgId}
							showAll={true}
							showGlobal={true}
							placeholder="All organizations"
						/>
					</div>
				)}
			</div>

			{/* Status Tabs */}
			<Tabs
				defaultValue="all"
				onValueChange={setStatusFilter}
				className="flex flex-col flex-1 min-h-0"
			>
				<TabsList className="w-fit">
					<TabsTrigger value="all">All</TabsTrigger>
					<TabsTrigger value="completed">Completed</TabsTrigger>
					<TabsTrigger value="running">Running</TabsTrigger>
					<TabsTrigger value="failed">Failed</TabsTrigger>
					<TabsTrigger value="queued">Queued</TabsTrigger>
					<TabsTrigger value="budget_exceeded">Budget Exceeded</TabsTrigger>
				</TabsList>

				<TabsContent
					value={statusFilter}
					className="mt-4 flex-1 min-h-0"
				>
					{isLoading ? (
						<div className="flex items-center justify-center py-12">
							<Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
						</div>
					) : filteredRuns.length > 0 ? (
						<DataTable>
							<DataTableHeader>
								<DataTableRow>
									{isPlatformAdmin && (
										<DataTableHead>Organization</DataTableHead>
									)}
									<DataTableHead>Agent</DataTableHead>
									<DataTableHead>Status</DataTableHead>
									<DataTableHead>Trigger</DataTableHead>
									<DataTableHead>Iterations</DataTableHead>
									<DataTableHead>Tokens</DataTableHead>
									<DataTableHead>Started At</DataTableHead>
									<DataTableHead>Completed At</DataTableHead>
									<DataTableHead>Duration</DataTableHead>
									<DataTableHead className="text-right"></DataTableHead>
								</DataTableRow>
							</DataTableHeader>
							<DataTableBody>
								{filteredRuns.map((run: AgentRun) => {
									const isGlobalRun = !run.org_id;
									const duration =
										run.duration_ms != null
											? `${(run.duration_ms / 1000).toFixed(1)}s`
											: "-";

									return (
										<DataTableRow
											key={run.id}
											clickable
											href={`/agent-runs/${run.id}`}
											onClick={(e) => {
												if (e.metaKey || e.ctrlKey || e.button === 1) return;
												navigate(`/agent-runs/${run.id}`);
											}}
										>
											{isPlatformAdmin && (
												<DataTableCell>
													{isGlobalRun ? (
														<Badge
															variant="default"
															className="text-xs"
														>
															<Globe className="mr-1 h-3 w-3" />
															Global
														</Badge>
													) : (
														<Badge
															variant="outline"
															className="text-xs"
														>
															<Building2 className="mr-1 h-3 w-3" />
															{getOrgName(run.org_id)}
														</Badge>
													)}
												</DataTableCell>
											)}
											<DataTableCell className="font-medium">
												{run.agent_name || "Unknown"}
											</DataTableCell>
											<DataTableCell>
												{getStatusBadge(run.status)}
											</DataTableCell>
											<DataTableCell>
												{triggerBadge(run.trigger_type)}
											</DataTableCell>
											<DataTableCell>
												{run.iterations_used}
												{run.budget_max_iterations && (
													<span className="text-muted-foreground text-xs">
														/{run.budget_max_iterations}
													</span>
												)}
											</DataTableCell>
											<DataTableCell>
												{run.tokens_used.toLocaleString()}
											</DataTableCell>
											<DataTableCell className="text-sm">
												{run.started_at
													? formatDate(run.started_at)
													: "-"}
											</DataTableCell>
											<DataTableCell className="text-sm">
												{run.completed_at
													? formatDate(run.completed_at)
													: "-"}
											</DataTableCell>
											<DataTableCell className="text-sm text-muted-foreground">
												{duration}
											</DataTableCell>
											<DataTableCell className="text-right">
												<Button
													variant="ghost"
													size="icon"
													onClick={(e) => {
														e.stopPropagation();
														navigate(
															`/agent-runs/${run.id}`,
														);
													}}
													title="View Details"
												>
													<Eye className="h-4 w-4" />
												</Button>
											</DataTableCell>
										</DataTableRow>
									);
								})}
							</DataTableBody>
						</DataTable>
					) : (
						<div className="flex flex-col items-center justify-center py-12 text-center">
							<Bot className="h-12 w-12 text-muted-foreground" />
							<h3 className="mt-4 text-lg font-semibold">
								{searchTerm
									? "No agent runs match your search"
									: "No agent runs found"}
							</h3>
							<p className="mt-2 text-sm text-muted-foreground">
								{searchTerm
									? "Try adjusting your search term or clear the filter"
									: "Trigger an agent to see runs appear here"}
							</p>
						</div>
					)}
				</TabsContent>
			</Tabs>
		</>
	);
}
