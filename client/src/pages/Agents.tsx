/**
 * Agents Page
 *
 * Platform admin page for managing AI agents.
 * Displays agent list with CRUD operations.
 */

import { useState } from "react";
import {
	Plus,
	RefreshCw,
	Bot,
	Pencil,
	Trash2,
	Globe,
	Building2,
	LayoutGrid,
	Table as TableIcon,
	MessageSquare,
	Copy,
	Check,
	Lock,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import {
	Card,
	CardContent,
	CardDescription,
	CardHeader,
	CardTitle,
} from "@/components/ui/card";
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
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import {
	DataTable,
	DataTableBody,
	DataTableCell,
	DataTableHead,
	DataTableHeader,
	DataTableRow,
} from "@/components/ui/data-table";
import { useAgents, useDeleteAgent, useUpdateAgent } from "@/hooks/useAgents";
import { useOrgScope } from "@/contexts/OrgScopeContext";
import { useAuth } from "@/contexts/AuthContext";
import { useOrganizations } from "@/hooks/useOrganizations";
import { SearchBox } from "@/components/search/SearchBox";
import { useSearch } from "@/hooks/useSearch";
import { AgentDialog } from "@/components/agents/AgentDialog";
import { OrganizationSelect } from "@/components/forms/OrganizationSelect";
import { toast } from "sonner";
import type { components } from "@/lib/v1";

// Extended type to include organization_id (supported by backend, pending type regeneration)
type AgentSummary = components["schemas"]["AgentSummary"] & {
	organization_id?: string | null;
};
type Organization = components["schemas"]["OrganizationPublic"];

export function Agents() {
	const { scope, isGlobalScope } = useOrgScope();
	const { isPlatformAdmin } = useAuth();
	const [filterOrgId, setFilterOrgId] = useState<string | null | undefined>(
		undefined,
	);
	const [searchTerm, setSearchTerm] = useState("");
	const [viewMode, setViewMode] = useState<"grid" | "table">("grid");
	const [isDeleteDialogOpen, setIsDeleteDialogOpen] = useState(false);
	const [isAgentDialogOpen, setIsAgentDialogOpen] = useState(false);
	const [selectedAgent, setSelectedAgent] = useState<AgentSummary | null>(
		null,
	);
	const [editAgentId, setEditAgentId] = useState<string | null>(null);
	const [copiedId, setCopiedId] = useState<string | null>(null);

	// Pass filterOrgId to backend for filtering (undefined = all, null = global only)
	// For platform admins, undefined means show all. For non-admins, backend handles filtering.
	const {
		data: agents,
		isLoading,
		refetch,
	} = useAgents(isPlatformAdmin ? filterOrgId : undefined);
	const deleteAgent = useDeleteAgent();
	const updateAgent = useUpdateAgent();

	// Fetch organizations for the org name lookup (platform admins only)
	const { data: organizations } = useOrganizations({
		enabled: isPlatformAdmin,
	});

	// Helper to get organization name from ID
	const getOrgName = (orgId: string | null | undefined): string => {
		if (!orgId) return "Global";
		const org = organizations?.find((o: Organization) => o.id === orgId);
		return org?.name || orgId;
	};

	// All authenticated users can manage agents (create private ones)
	const canManageAgents = true;

	// Use agents from API directly (backend handles org filtering)
	// Cast to extended type that includes organization_id (pending type regeneration)
	const scopeFilteredAgents = (agents ?? []) as AgentSummary[];

	// Search filtering
	const filteredAgents = useSearch(scopeFilteredAgents, searchTerm, [
		"name",
		"description",
		(agent) => agent.id ?? "",
	]);

	const handleCreate = () => {
		setEditAgentId(null);
		setIsAgentDialogOpen(true);
	};

	const handleEdit = (agentId: string) => {
		setEditAgentId(agentId);
		setIsAgentDialogOpen(true);
	};

	const handleDelete = (agent: AgentSummary) => {
		setSelectedAgent(agent);
		setIsDeleteDialogOpen(true);
	};

	const handleConfirmDelete = async () => {
		if (!selectedAgent || !selectedAgent.id) return;
		await deleteAgent.mutateAsync({
			params: { path: { agent_id: selectedAgent.id } },
		});
		setIsDeleteDialogOpen(false);
		setSelectedAgent(null);
	};

	const handleToggleActive = async (agent: AgentSummary) => {
		if (!agent.id) return;
		await updateAgent.mutateAsync({
			params: { path: { agent_id: agent.id } },
			body: { is_active: !agent.is_active, clear_roles: false },
		});
	};

	const handleCopyMcpUrl = (agentId: string) => {
		const url = `${window.location.origin}/mcp/${agentId}`;
		navigator.clipboard.writeText(url);
		setCopiedId(agentId);
		toast.success("MCP URL copied to clipboard");
		setTimeout(() => setCopiedId(null), 2000);
	};

	const handleDialogClose = () => {
		setIsAgentDialogOpen(false);
		setEditAgentId(null);
	};

	return (
		<div className="h-[calc(100vh-8rem)] flex flex-col space-y-6">
			{/* Header */}
			<div className="flex items-center justify-between">
				<div>
					<div className="flex items-center gap-3">
						<h1 className="text-4xl font-extrabold tracking-tight">
							Agents
						</h1>
						{isPlatformAdmin && (
							<Badge
								variant={isGlobalScope ? "default" : "outline"}
								className="text-sm"
							>
								{isGlobalScope ? (
									<>
										<Globe className="mr-1 h-3 w-3" />
										Global
									</>
								) : (
									<>
										<Building2 className="mr-1 h-3 w-3" />
										{scope.orgName}
									</>
								)}
							</Badge>
						)}
					</div>
					<p className="mt-2 text-muted-foreground">
						{canManageAgents
							? "Create and manage AI agents with custom prompts and tools"
							: "View available AI agents"}
					</p>
				</div>
				<div className="flex gap-2">
					{canManageAgents && (
						<ToggleGroup
							type="single"
							value={viewMode}
							onValueChange={(value: string) =>
								value && setViewMode(value as "grid" | "table")
							}
						>
							<ToggleGroupItem
								value="grid"
								aria-label="Grid view"
								size="sm"
							>
								<LayoutGrid className="h-4 w-4" />
							</ToggleGroupItem>
							<ToggleGroupItem
								value="table"
								aria-label="Table view"
								size="sm"
							>
								<TableIcon className="h-4 w-4" />
							</ToggleGroupItem>
						</ToggleGroup>
					)}
					<Button
						variant="outline"
						size="icon"
						onClick={() => refetch()}
						title="Refresh"
					>
						<RefreshCw className="h-4 w-4" />
					</Button>
					{canManageAgents && (
						<Button
							variant="outline"
							size="icon"
							onClick={handleCreate}
							title="Create Agent"
						>
							<Plus className="h-4 w-4" />
						</Button>
					)}
				</div>
			</div>

			{/* Search and Filters */}
			<div className="flex items-center gap-4">
				<SearchBox
					value={searchTerm}
					onChange={setSearchTerm}
					placeholder="Search agents by name or description..."
					className="max-w-md"
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

			{/* Content */}
			{isLoading ? (
				viewMode === "grid" || !canManageAgents ? (
					<div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 2xl:grid-cols-5">
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
			) : filteredAgents && filteredAgents.length > 0 ? (
				viewMode === "grid" || !canManageAgents ? (
					// Grid View
					<div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 2xl:grid-cols-5">
						{filteredAgents.map((agent) => (
							<Card
								key={agent.id}
								className="hover:border-primary transition-colors flex flex-col"
							>
								<CardHeader className="pb-3">
									<div className="flex items-start justify-between gap-3">
										<div className="flex-1 min-w-0">
											<div className="flex items-center gap-2">
												<Bot className="h-4 w-4 text-muted-foreground shrink-0" />
												<CardTitle className="text-base break-words">
													{agent.name}
												</CardTitle>
											</div>
											<CardDescription className="mt-1.5 text-sm break-words line-clamp-2">
												{agent.description || (
													<span className="italic text-muted-foreground/60">
														No description
													</span>
												)}
											</CardDescription>
										</div>
										{canManageAgents && (
											<div className="flex items-center gap-2 shrink-0">
												<Switch
													checked={agent.is_active}
													onCheckedChange={() =>
														handleToggleActive(
															agent,
														)
													}
													disabled={
														updateAgent.isPending
													}
												/>
											</div>
										)}
									</div>
								</CardHeader>
								<CardContent className="pt-0 mt-auto">
									{/* Private badge */}
									{(agent as any).access_level === "private" && (
										<div className="mb-2">
											<Badge variant="secondary" className="text-xs">
												<Lock className="mr-1 h-3 w-3" />
												Private
											</Badge>
										</div>
									)}
									{/* Organization badge (platform admins only) */}
									{isPlatformAdmin && (
										<div className="mb-2">
											{agent.organization_id ? (
												<Badge
													variant="outline"
													className="text-xs"
												>
													<Building2 className="mr-1 h-3 w-3" />
													{getOrgName(
														agent.organization_id,
													)}
												</Badge>
											) : (
												<Badge
													variant="default"
													className="text-xs"
												>
													<Globe className="mr-1 h-3 w-3" />
													Global
												</Badge>
											)}
										</div>
									)}

									{/* Channel badges */}
									<div className="flex flex-wrap gap-1 mb-3">
										{agent.channels?.map((channel) => (
											<Badge
												key={channel}
												variant="secondary"
												className="text-xs"
											>
												<MessageSquare className="h-3 w-3 mr-1" />
												{channel}
											</Badge>
										))}
									</div>

									{/* Actions */}
									{canManageAgents && (
										<div className="flex gap-2">
											<Button
												variant="outline"
												size="sm"
												className="flex-1"
												onClick={() =>
													agent.id && handleEdit(agent.id)
												}
											>
												<Pencil className="h-3 w-3 mr-1" />
												Edit
											</Button>
											<Button
												variant="outline"
												size="sm"
												onClick={() =>
													agent.id && handleCopyMcpUrl(agent.id)
												}
												title="Copy MCP URL"
											>
												{copiedId === agent.id ? (
													<Check className="h-3 w-3" />
												) : (
													<Copy className="h-3 w-3" />
												)}
											</Button>
											<Button
												variant="outline"
												size="sm"
												onClick={() =>
													handleDelete(agent)
												}
											>
												<Trash2 className="h-3 w-3" />
											</Button>
										</div>
									)}
								</CardContent>
							</Card>
						))}
					</div>
				) : (
					// Table View
					<div className="flex-1 min-h-0">
						<DataTable className="max-h-full">
							<DataTableHeader>
								<DataTableRow>
									{isPlatformAdmin && (
										<DataTableHead>
											Organization
										</DataTableHead>
									)}
									<DataTableHead>Name</DataTableHead>
									<DataTableHead>Description</DataTableHead>
									<DataTableHead>Channels</DataTableHead>
									<DataTableHead>Status</DataTableHead>
									<DataTableHead className="text-right" />
								</DataTableRow>
							</DataTableHeader>
							<DataTableBody>
								{filteredAgents.map((agent) => (
									<DataTableRow key={agent.id}>
										{isPlatformAdmin && (
											<DataTableCell>
												{agent.organization_id ? (
													<Badge
														variant="outline"
														className="text-xs"
													>
														<Building2 className="mr-1 h-3 w-3" />
														{getOrgName(
															agent.organization_id,
														)}
													</Badge>
												) : (
													<Badge
														variant="default"
														className="text-xs"
													>
														<Globe className="mr-1 h-3 w-3" />
														Global
													</Badge>
												)}
											</DataTableCell>
										)}
										<DataTableCell className="font-medium">
											<div className="flex items-center gap-2">
												<Bot className="h-4 w-4 text-muted-foreground" />
												{agent.name}
											</div>
										</DataTableCell>
										<DataTableCell className="max-w-xs truncate text-muted-foreground">
											{agent.description ||
												"No description"}
										</DataTableCell>
										<DataTableCell>
											<div className="flex flex-wrap gap-1">
												{agent.channels?.map(
													(channel) => (
														<Badge
															key={channel}
															variant="secondary"
															className="text-xs"
														>
															{channel}
														</Badge>
													),
												)}
											</div>
										</DataTableCell>
										<DataTableCell>
											<Switch
												checked={agent.is_active}
												onCheckedChange={() =>
													handleToggleActive(agent)
												}
												disabled={updateAgent.isPending}
											/>
										</DataTableCell>
										<DataTableCell className="text-right">
											<div className="flex justify-end gap-2">
												<Button
													variant="ghost"
													size="icon-sm"
													onClick={() =>
														agent.id && handleEdit(agent.id)
													}
												>
													<Pencil className="h-4 w-4" />
												</Button>
												<Button
													variant="ghost"
													size="icon-sm"
													onClick={() =>
														agent.id && handleCopyMcpUrl(agent.id)
													}
													title="Copy MCP URL"
												>
													{copiedId === agent.id ? (
														<Check className="h-4 w-4" />
													) : (
														<Copy className="h-4 w-4" />
													)}
												</Button>
												<Button
													variant="ghost"
													size="icon-sm"
													onClick={() =>
														handleDelete(agent)
													}
												>
													<Trash2 className="h-4 w-4" />
												</Button>
											</div>
										</DataTableCell>
									</DataTableRow>
								))}
							</DataTableBody>
						</DataTable>
					</div>
				)
			) : (
				// Empty State
				<Card>
					<CardContent className="flex flex-col items-center justify-center py-12 text-center">
						<Bot className="h-12 w-12 text-muted-foreground" />
						<h3 className="mt-4 text-lg font-semibold">
							{searchTerm
								? "No agents match your search"
								: "No agents found"}
						</h3>
						<p className="mt-2 text-sm text-muted-foreground">
							{searchTerm
								? "Try adjusting your search term or clear the filter"
								: canManageAgents
									? "Get started by creating your first AI agent"
									: "No agents are currently available"}
						</p>
						{canManageAgents && !searchTerm && (
							<Button
								variant="outline"
								size="icon"
								onClick={handleCreate}
								className="mt-4"
								title="Create Agent"
							>
								<Plus className="h-4 w-4" />
							</Button>
						)}
					</CardContent>
				</Card>
			)}

			{/* Delete Confirmation Dialog */}
			<AlertDialog
				open={isDeleteDialogOpen}
				onOpenChange={setIsDeleteDialogOpen}
			>
				<AlertDialogContent>
					<AlertDialogHeader>
						<AlertDialogTitle>Delete Agent?</AlertDialogTitle>
						<AlertDialogDescription>
							This will delete the agent "{selectedAgent?.name}".
							This action cannot be undone.
						</AlertDialogDescription>
					</AlertDialogHeader>
					<AlertDialogFooter>
						<AlertDialogCancel>Cancel</AlertDialogCancel>
						<AlertDialogAction
							onClick={handleConfirmDelete}
							className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
						>
							{deleteAgent.isPending
								? "Deleting..."
								: "Delete Agent"}
						</AlertDialogAction>
					</AlertDialogFooter>
				</AlertDialogContent>
			</AlertDialog>

			{/* Create/Edit Agent Dialog */}
			<AgentDialog
				open={isAgentDialogOpen}
				onOpenChange={handleDialogClose}
				agentId={editAgentId}
			/>
		</div>
	);
}

export default Agents;
