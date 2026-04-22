/**
 * AgentDetailPage — single page handling both edit and create modes.
 *
 * Routes:
 *   /agents/:id  → edit mode (all 3 tabs active; Overview + Runs load data)
 *   /agents/new  → create mode (Overview + Runs disabled; Settings only)
 *
 * Visual spec mirrors /tmp/agent-mockup/src/pages/AgentDetailPage.tsx: breadcrumb,
 * header with name + Active/Paused pill + description + action row, pill tabs with
 * run-count badge, plus per-tab body (Overview/Runs/Settings).
 */

import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
	ArrowLeft,
	Bot,
	MessageSquare,
	Pause,
	PlayCircle,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
	Tooltip,
	TooltipContent,
	TooltipProvider,
	TooltipTrigger,
} from "@/components/ui/tooltip";
import { AgentOverviewTab } from "@/components/agents/AgentOverviewTab";
import { AgentRunsTab } from "@/components/agents/AgentRunsTab";
import { AgentSettingsTab } from "@/components/agents/AgentSettingsTab";
import { PillTabs } from "@/components/agents/PillTabs";
import {
	PILL_ACTIVE,
	TONE_MUTED,
	TYPE_BODY,
	TYPE_PAGE_TITLE,
} from "@/components/agents/design-tokens";
import { cn } from "@/lib/utils";
import { useAgent } from "@/hooks/useAgents";
import { useAgentRuns } from "@/services/agentRuns";
import { useUpdateAgent } from "@/hooks/useAgents";

type Tab = "overview" | "runs" | "settings";

export function AgentDetailPage() {
	const { id } = useParams<{ id: string }>();
	const navigate = useNavigate();

	const isCreate = !id || id === "new";
	const agentId = isCreate ? undefined : id;
	const { data: agent, isLoading } = useAgent(agentId);
	const { data: runsList } = useAgentRuns({
		agentId: agentId ?? "",
		limit: 1,
	});
	const runCount = (runsList as { total?: number } | undefined)?.total ?? 0;

	const [tab, setTab] = useState<Tab>(isCreate ? "settings" : "overview");

	const updateAgent = useUpdateAgent();

	function handleCreated(newId: string) {
		navigate(`/agents/${newId}`);
	}

	const hasChat = (agent?.channels ?? []).includes("chat");
	const isActive = agent?.is_active ?? true;

	return (
		<div className="mx-auto flex max-w-[1400px] flex-col gap-5 p-7">
			{/* Breadcrumb */}
			<div
				className={cn(
					"flex items-center gap-1.5 text-[13px]",
					TONE_MUTED,
				)}
			>
				<Link
					to="/agents"
					className="inline-flex items-center gap-1 hover:text-foreground"
				>
					<ArrowLeft className="h-3 w-3" /> Agents
				</Link>
				{!isCreate && agent ? (
					<>
						<span>/</span>
						<span>{agent.name}</span>
					</>
				) : null}
			</div>

			{/* Header */}
			<div className="flex flex-wrap items-start justify-between gap-4">
				<div className="min-w-0 flex-1">
					<h1 className={cn("flex items-center gap-2.5", TYPE_PAGE_TITLE)}>
						<Bot className="h-[18px] w-[18px] shrink-0 text-muted-foreground" />
						<span className="truncate">
							{isCreate
								? "New agent"
								: isLoading
									? "Loading…"
									: (agent?.name ?? "Unknown agent")}
						</span>
						{!isCreate && agent ? (
							isActive ? (
								<span className={PILL_ACTIVE}>Active</span>
							) : (
								<Badge variant="secondary" className="text-[11px]">
									Paused
								</Badge>
							)
						) : null}
					</h1>
					{!isCreate && agent?.description ? (
						<p className={cn("mt-1 line-clamp-2", TYPE_BODY, TONE_MUTED)}>
							{agent.description}
						</p>
					) : null}
				</div>
				{!isCreate && agent ? (
					<div className="flex items-center gap-2">
						{hasChat ? (
							<TooltipProvider>
								<Tooltip>
									<TooltipTrigger asChild>
										<span>
											<Button
												variant="outline"
												size="sm"
												disabled={!isActive}
											>
												<MessageSquare className="h-3.5 w-3.5" />
												Start chat
											</Button>
										</span>
									</TooltipTrigger>
									<TooltipContent>
										{isActive
											? "Open a chat session with this agent"
											: "Agent is paused"}
									</TooltipContent>
								</Tooltip>
							</TooltipProvider>
						) : null}
						<Button variant="outline" size="sm" disabled>
							<PlayCircle className="h-3.5 w-3.5" />
							Test run
						</Button>
						<Button
							variant="outline"
							size="sm"
							onClick={() =>
								updateAgent.mutate({
									params: { path: { agent_id: agent.id ?? "" } },
									body: { is_active: !isActive, clear_roles: false },
								})
							}
						>
							{isActive ? (
								<>
									<Pause className="h-3.5 w-3.5" /> Pause
								</>
							) : (
								<>
									<PlayCircle className="h-3.5 w-3.5" /> Activate
								</>
							)}
						</Button>
					</div>
				) : null}
			</div>

			{/* Pill tabs */}
			<PillTabs
				items={[
					{
						value: "overview",
						label: "Overview",
						disabled: isCreate,
					},
					{
						value: "runs",
						label: "Runs",
						count: runCount,
						disabled: isCreate,
					},
					{ value: "settings", label: "Settings" },
				]}
				value={tab}
				onValueChange={(v) => setTab(v as Tab)}
			/>

			{/* Tab body */}
			{tab === "overview" && !isCreate && agentId ? (
				<AgentOverviewTab agentId={agentId} />
			) : null}
			{tab === "runs" && !isCreate && agentId ? (
				<AgentRunsTab agentId={agentId} />
			) : null}
			{tab === "settings" ? (
				isCreate ? (
					<AgentSettingsTab mode="create" onCreated={handleCreated} />
				) : isLoading ? (
					<Skeleton className="h-64 w-full" />
				) : (
					<AgentSettingsTab mode="edit" agent={agent ?? null} />
				)
			) : null}
		</div>
	);
}

export default AgentDetailPage;
