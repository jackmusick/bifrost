/**
 * AgentDetailPage — single page handling both edit and create modes.
 *
 * Routes:
 *   /agents/:id  → edit mode (all 3 tabs active; Overview + Runs load data)
 *   /agents/new  → create mode (Overview + Runs disabled; Settings only)
 *
 * On successful create, navigates to /agents/:newId so the user lands
 * on the freshly-saved agent in edit mode.
 */

import { Link, useNavigate, useParams } from "react-router-dom";
import { ArrowLeft, Bot } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
	Tabs,
	TabsContent,
	TabsList,
	TabsTrigger,
} from "@/components/ui/tabs";
import {
	Tooltip,
	TooltipContent,
	TooltipProvider,
	TooltipTrigger,
} from "@/components/ui/tooltip";
import { AgentOverviewTab } from "@/components/agents/AgentOverviewTab";
import { AgentRunsTab } from "@/components/agents/AgentRunsTab";
import { AgentSettingsTab } from "@/components/agents/AgentSettingsTab";
import { useAgent } from "@/hooks/useAgents";

export function AgentDetailPage() {
	const { id } = useParams<{ id: string }>();
	const navigate = useNavigate();

	const isCreate = !id || id === "new";
	const agentId = isCreate ? undefined : id;
	const { data: agent, isLoading } = useAgent(agentId);

	function handleCreated(newId: string) {
		navigate(`/agents/${newId}`);
	}

	return (
		<div className="flex flex-col gap-5 max-w-7xl mx-auto">
			{/* Breadcrumb */}
			<Link
				to="/agents"
				className="inline-flex w-fit items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground"
			>
				<ArrowLeft className="h-3 w-3" /> All agents
			</Link>

			{/* Header */}
			<div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
				<div className="flex items-start gap-3 min-w-0">
					<Bot className="h-5 w-5 mt-1 shrink-0 text-muted-foreground" />
					<div className="min-w-0">
						<div className="flex flex-wrap items-center gap-2">
							<h1 className="text-2xl font-extrabold tracking-tight truncate">
								{isCreate
									? "New agent"
									: isLoading
										? "Loading…"
										: (agent?.name ?? "Unknown agent")}
							</h1>
							{!isCreate && agent ? (
								agent.is_active ? (
									<Badge
										variant="default"
										className="bg-emerald-500 text-white"
									>
										Active
									</Badge>
								) : (
									<Badge variant="secondary">Paused</Badge>
								)
							) : null}
						</div>
						{!isCreate && agent?.description ? (
							<p className="mt-1 text-sm text-muted-foreground truncate">
								{agent.description}
							</p>
						) : null}
					</div>
				</div>
				{!isCreate ? (
					<Button variant="outline" disabled>
						Test run
					</Button>
				) : null}
			</div>

			{/* Tabs */}
			<Tabs defaultValue={isCreate ? "settings" : "overview"}>
				<TabsList>
					<DisablableTrigger
						value="overview"
						disabled={isCreate}
						disabledTooltip="Available after first run"
					>
						Overview
					</DisablableTrigger>
					<DisablableTrigger
						value="runs"
						disabled={isCreate}
						disabledTooltip="Available after first run"
					>
						Runs
					</DisablableTrigger>
					<TabsTrigger value="settings">Settings</TabsTrigger>
				</TabsList>

				{/* Overview */}
				{!isCreate && agentId ? (
					<TabsContent value="overview" className="mt-4">
						<AgentOverviewTab agentId={agentId} />
					</TabsContent>
				) : null}

				{/* Runs */}
				{!isCreate && agentId ? (
					<TabsContent value="runs" className="mt-4">
						<AgentRunsTab agentId={agentId} />
					</TabsContent>
				) : null}

				{/* Settings */}
				<TabsContent value="settings" className="mt-4">
					{isCreate ? (
						<AgentSettingsTab
							mode="create"
							onCreated={handleCreated}
						/>
					) : isLoading ? (
						<Skeleton className="h-64 w-full" />
					) : (
						<AgentSettingsTab
							mode="edit"
							agent={agent ?? null}
						/>
					)}
				</TabsContent>
			</Tabs>
		</div>
	);
}

function DisablableTrigger({
	value,
	disabled,
	disabledTooltip,
	children,
}: {
	value: string;
	disabled: boolean;
	disabledTooltip: string;
	children: React.ReactNode;
}) {
	if (!disabled) {
		return <TabsTrigger value={value}>{children}</TabsTrigger>;
	}
	return (
		<TooltipProvider>
			<Tooltip>
				<TooltipTrigger asChild>
					{/* span wrapper because disabled buttons don't fire focus events */}
					<span tabIndex={0}>
						<TabsTrigger value={value} disabled>
							{children}
						</TabsTrigger>
					</span>
				</TooltipTrigger>
				<TooltipContent>{disabledTooltip}</TooltipContent>
			</Tooltip>
		</TooltipProvider>
	);
}

export default AgentDetailPage;
