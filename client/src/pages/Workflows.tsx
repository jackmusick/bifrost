import { useState, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import {
	PlayCircle,
	Code,
	RefreshCw,
	Webhook,
	AlertTriangle,
	LayoutGrid,
	Table as TableIcon,
	Bot,
	Database,
	PanelLeft,
	Globe,
	Building2,
	Pencil,
} from "lucide-react";
import type { CategoryCount } from "@/components/workflows/WorkflowSidebar";
import { Button } from "@/components/ui/button";
import {
	Card,
	CardContent,
	CardDescription,
	CardHeader,
	CardTitle,
} from "@/components/ui/card";
import {
	Dialog,
	DialogContent,
	DialogDescription,
	DialogFooter,
	DialogHeader,
	DialogTitle,
} from "@/components/ui/dialog";
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
import { useWorkflowsFiltered, useUpdateWorkflow } from "@/hooks/useWorkflows";
import { useWorkflowKeys } from "@/hooks/useWorkflowKeys";
import { useOrgScope } from "@/contexts/OrgScopeContext";
import { useAuth } from "@/contexts/AuthContext";
import { useOrganizations } from "@/hooks/useOrganizations";
import { HttpTriggerDialog } from "@/components/workflows/HttpTriggerDialog";
import { WorkflowSidebar } from "@/components/workflows/WorkflowSidebar";
import { SearchBox } from "@/components/search/SearchBox";
import { useSearch } from "@/hooks/useSearch";
import { OrganizationSelect } from "@/components/forms/OrganizationSelect";
import { toast } from "sonner";
import type { components } from "@/lib/v1";
type Workflow = components["schemas"]["WorkflowMetadata"];
type Organization = components["schemas"]["OrganizationPublic"];

export function Workflows() {
	const navigate = useNavigate();
	const { scope, isGlobalScope } = useOrgScope();
	const { isPlatformAdmin } = useAuth();
	const { data: apiKeys } = useWorkflowKeys({ includeRevoked: false });
	const updateWorkflow = useUpdateWorkflow();

	// Filter state
	const [filterOrgId, setFilterOrgId] = useState<string | null | undefined>(
		undefined,
	);
	const [webhookDialogOpen, setWebhookDialogOpen] = useState(false);
	const [selectedWorkflow, setSelectedWorkflow] = useState<Workflow | null>(
		null,
	);
	const [searchTerm, setSearchTerm] = useState("");
	const [viewMode, setViewMode] = useState<"grid" | "table">("grid");
	const [typeFilter, setTypeFilter] = useState<string>("all");
	const [sidebarOpen, setSidebarOpen] = useState(true);

	// Edit org scope dialog state
	const [editOrgDialogOpen, setEditOrgDialogOpen] = useState(false);
	const [editingWorkflow, setEditingWorkflow] = useState<Workflow | null>(null);
	const [editOrgId, setEditOrgId] = useState<string | null | undefined>(undefined);
	const [isUpdating, setIsUpdating] = useState(false);

	// Entity filter state
	const [selectedCategory, setSelectedCategory] = useState<string | null>(null);
	const [selectedFormId, setSelectedFormId] = useState<string | null>(null);
	const [selectedAppId, setSelectedAppId] = useState<string | null>(null);
	const [selectedAgentId, setSelectedAgentId] = useState<string | null>(null);

	// Fetch organizations for org name lookup (platform admins only)
	const { data: organizations } = useOrganizations({
		enabled: isPlatformAdmin,
	});

	// Helper to get organization name from ID
	const getOrgName = (orgId: string | null | undefined): string => {
		if (!orgId) return "Global";
		const org = organizations?.find((o: Organization) => o.id === orgId);
		return org?.name || orgId;
	};

	// Fetch workflows with entity filters and org scope
	const { data, isLoading, refetch } = useWorkflowsFiltered({
		scope: isPlatformAdmin ? filterOrgId : undefined,
		type: typeFilter === "all" ? undefined : typeFilter,
		filterByForm: selectedFormId ?? undefined,
		filterByApp: selectedAppId ?? undefined,
		filterByAgent: selectedAgentId ?? undefined,
	});

	const workflows = useMemo(() => data || [], [data]);

	// Compute categories from workflows
	const categories = useMemo<CategoryCount[]>(() => {
		const categoryMap = new Map<string, number>();
		workflows.forEach((w) => {
			if (w.category) {
				categoryMap.set(w.category, (categoryMap.get(w.category) || 0) + 1);
			}
		});
		return Array.from(categoryMap.entries())
			.map(([name, count]) => ({ name, count }))
			.sort((a, b) => a.name.localeCompare(b.name));
	}, [workflows]);

	// Apply category filter first
	const categoryFilteredWorkflows = useMemo(() => {
		if (!selectedCategory) return workflows;
		return workflows.filter((w) => w.category === selectedCategory);
	}, [workflows, selectedCategory]);

	// Apply search filter (type filtering is now done server-side)
	const filteredWorkflows = useSearch(categoryFilteredWorkflows, searchTerm, [
		"name",
		"description",
		"category",
		(w) => w.parameters?.map((p) => p.name).join(" ") || "",
	]);

	// Create a map of workflows that have API keys
	const workflowsWithKeys = useMemo(() => {
		if (!apiKeys) return new Set<string>();

		const workflowSet = new Set<string>();
		apiKeys.forEach((key) => {
			if (key.workflow_name && !key.revoked) {
				workflowSet.add(key.workflow_name);
			}
		});
		return workflowSet;
	}, [apiKeys]);

	const hasGlobalKey = useMemo(() => {
		if (!apiKeys) return false;
		return apiKeys.some((key) => !key.workflow_name && !key.revoked);
	}, [apiKeys]);

	const handleExecute = (workflowName: string) => {
		navigate(`/workflows/${workflowName}/execute`);
	};

	const handleShowWebhook = (workflow: Workflow) => {
		setSelectedWorkflow(workflow);
		setWebhookDialogOpen(true);
	};

	const handleEditOrgScope = (workflow: Workflow) => {
		setEditingWorkflow(workflow);
		// Convert organization_id to the format expected by OrganizationSelect
		// null means global, string means specific org
		setEditOrgId(workflow.organization_id ?? null);
		setEditOrgDialogOpen(true);
	};

	const handleSaveOrgScope = async () => {
		if (!editingWorkflow?.id) return;

		setIsUpdating(true);
		try {
			// OrganizationSelect uses:
			// - undefined for "All" (show all)
			// - null for "Global"
			// - string for specific org
			// For saving, we convert undefined to null (global)
			const orgIdToSave = editOrgId === undefined ? null : editOrgId;
			await updateWorkflow.mutateAsync(editingWorkflow.id, orgIdToSave);
			toast.success(
				`Workflow "${editingWorkflow.name}" updated to ${orgIdToSave ? getOrgName(orgIdToSave) : "Global"} scope`,
			);
			setEditOrgDialogOpen(false);
			setEditingWorkflow(null);
		} catch (error) {
			toast.error(
				error instanceof Error ? error.message : "Failed to update workflow",
			);
		} finally {
			setIsUpdating(false);
		}
	};

	return (
		<div className="h-[calc(100vh-8rem)] flex flex-col space-y-6">
			<div className="flex items-center justify-between">
				<div>
					<div className="flex items-center gap-3">
						<h1 className="text-4xl font-extrabold tracking-tight">
							Workflows
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
						Execute workflows directly with custom parameters
					</p>
				</div>
				<div className="flex gap-2">
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
					<Button
						variant="outline"
						size="icon"
						onClick={() => refetch()}
					>
						<RefreshCw className="h-4 w-4" />
					</Button>
				</div>
			</div>

			{/* Search Box, Org Filter, and Type Filter */}
			<div className="flex flex-col sm:flex-row gap-4 items-start sm:items-center">
				<SearchBox
					value={searchTerm}
					onChange={setSearchTerm}
					placeholder="Search by name, description, or category..."
					className="w-64"
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
				<ToggleGroup
					type="single"
					value={typeFilter}
					onValueChange={(value: string) =>
						value && setTypeFilter(value)
					}
				>
					<ToggleGroupItem value="all" size="sm">
						All
					</ToggleGroupItem>
					<ToggleGroupItem value="workflow" size="sm">
						Workflows
					</ToggleGroupItem>
					<ToggleGroupItem value="tool" size="sm">
						Tools
					</ToggleGroupItem>
					<ToggleGroupItem value="data_provider" size="sm">
						Data Providers
					</ToggleGroupItem>
				</ToggleGroup>
			</div>

			{/* Main Content with Sidebar */}
			<div className="flex-1 flex gap-6 min-h-0">
				{/* Sidebar */}
				{sidebarOpen ? (
					<WorkflowSidebar
						categories={categories}
						categoriesLoading={isLoading}
						selectedCategory={selectedCategory}
						onCategorySelect={setSelectedCategory}
						selectedFormId={selectedFormId}
						selectedAppId={selectedAppId}
						selectedAgentId={selectedAgentId}
						onFormSelect={setSelectedFormId}
						onAppSelect={setSelectedAppId}
						onAgentSelect={setSelectedAgentId}
						scope={isPlatformAdmin ? filterOrgId ?? undefined : undefined}
						onClose={() => setSidebarOpen(false)}
						className="w-64 shrink-0"
					/>
				) : (
					<Button
						variant="outline"
						size="icon"
						onClick={() => setSidebarOpen(true)}
						className="shrink-0 h-9 w-9"
						title="Show filters"
					>
						<PanelLeft className="h-4 w-4" />
					</Button>
				)}

				{/* Content Area */}
				<div className="flex-1 min-w-0 overflow-auto">
					{isLoading ? (
						viewMode === "grid" ? (
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
					) : filteredWorkflows.length > 0 ? (
						viewMode === "grid" ? (
							<div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 2xl:grid-cols-5">
								{filteredWorkflows.map((workflow) => (
									<Card
										key={workflow.name}
										className="hover:border-primary transition-colors flex flex-col"
									>
										<CardHeader className="pb-3">
											<div className="flex items-start justify-between gap-3">
												<div className="flex-1 min-w-0">
													<CardTitle className="font-mono text-base break-all">
														{workflow.name}
													</CardTitle>
													{workflow.description && (
														<CardDescription className="mt-1.5 text-sm break-words">
															{workflow.description}
														</CardDescription>
													)}
												</div>
											</div>
											<div className="flex flex-wrap items-center gap-1 mt-2">
												{workflow.type === "tool" && (
													<Badge
														variant="secondary"
														className="bg-purple-100 text-purple-700 dark:bg-purple-900 dark:text-purple-300"
														title={
															workflow.tool_description ||
															"Available as AI tool"
														}
													>
														<Bot className="mr-1 h-3 w-3" />
														Tool
													</Badge>
												)}
												{workflow.type === "data_provider" && (
													<Badge
														variant="secondary"
														className="bg-blue-100 text-blue-700 dark:bg-blue-900 dark:text-blue-300"
														title="Provides data for forms and apps"
													>
														<Database className="mr-1 h-3 w-3" />
														Data Provider
													</Badge>
												)}
												{workflow.endpoint_enabled && (
													<Badge
														variant={
															workflow.public_endpoint
																? "destructive"
																: hasGlobalKey ||
																	  workflowsWithKeys.has(
																			workflow.name ??
																				"",
																	  )
																	? "default"
																	: "outline"
														}
														className={`cursor-pointer transition-colors ${
															workflow.public_endpoint
																? "bg-orange-600 hover:bg-orange-700 border-orange-600"
																: hasGlobalKey ||
																	  workflowsWithKeys.has(
																			workflow.name ??
																				"",
																	  )
																	? "bg-green-600 hover:bg-green-700"
																	: "text-muted-foreground hover:bg-accent"
														}`}
														onClick={(e) => {
															e.stopPropagation();
															handleShowWebhook(workflow);
														}}
														title={
															workflow.public_endpoint
																? "Public webhook endpoint - no authentication required"
																: hasGlobalKey ||
																	  workflowsWithKeys.has(
																			workflow.name ??
																				"",
																	  )
																	? "HTTP endpoint enabled with API key"
																	: "HTTP endpoint (no API key configured)"
														}
													>
														{workflow.public_endpoint ? (
															<AlertTriangle className="mr-1 h-3 w-3" />
														) : (
															<Webhook className="mr-1 h-3 w-3" />
														)}
														Endpoint
													</Badge>
												)}
												{workflow.disable_global_key && (
													<Badge
														variant="outline"
														className="bg-orange-600 text-white hover:bg-orange-700 border-orange-600"
														title="This workflow only accepts workflow-specific API keys (global keys are disabled)"
													>
														Global Opt-Out
													</Badge>
												)}
												{workflow.category && (
													<Badge variant="secondary">
														{workflow.category}
													</Badge>
												)}
											</div>
										</CardHeader>
										<CardContent className="pt-0 mt-auto">
											{/* Organization badge (platform admins only) */}
											{isPlatformAdmin && (
												<div className="mb-2 flex items-center justify-between">
													{workflow.organization_id ? (
														<Badge
															variant="outline"
															className="text-xs"
														>
															<Building2 className="mr-1 h-3 w-3" />
															{getOrgName(
																workflow.organization_id,
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
													<Button
														variant="ghost"
														size="icon-sm"
														onClick={() =>
															handleEditOrgScope(workflow)
														}
														title="Edit organization scope"
													>
														<Pencil className="h-3 w-3" />
													</Button>
												</div>
											)}
											<Button
												className="w-full"
												onClick={() =>
													handleExecute(workflow.name ?? "")
												}
											>
												<PlayCircle className="mr-2 h-4 w-4" />
												{workflow.type === "tool"
													? "Test Tool"
													: workflow.type === "data_provider"
														? "Preview Data"
														: "Execute Workflow"}
											</Button>
										</CardContent>
									</Card>
								))}
							</div>
						) : (
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
											<DataTableHead className="text-right">
												Parameters
											</DataTableHead>
											<DataTableHead>Status</DataTableHead>
											<DataTableHead className="text-right">
												<span className="sr-only">Actions</span>
											</DataTableHead>
										</DataTableRow>
									</DataTableHeader>
									<DataTableBody>
										{filteredWorkflows.map((workflow) => (
											<DataTableRow key={workflow.name}>
												{isPlatformAdmin && (
													<DataTableCell>
														{workflow.organization_id ? (
															<Badge
																variant="outline"
																className="text-xs"
															>
																<Building2 className="mr-1 h-3 w-3" />
																{getOrgName(
																	workflow.organization_id,
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
												<DataTableCell className="font-mono font-medium break-all max-w-xs">
													{workflow.name}
												</DataTableCell>
												<DataTableCell className="max-w-xs break-words text-muted-foreground">
													{workflow.description || (
														<span className="italic">
															No description
														</span>
													)}
												</DataTableCell>
												<DataTableCell className="text-right">
													{workflow.parameters?.length ?? 0}
												</DataTableCell>
												<DataTableCell>
													<div className="flex items-center gap-1">
														{workflow.type === "tool" && (
															<Badge
																variant="secondary"
																className="bg-purple-100 text-purple-700 dark:bg-purple-900 dark:text-purple-300 text-xs"
																title={
																	workflow.tool_description ||
																	"Available as AI tool"
																}
															>
																<Bot className="mr-1 h-2 w-2" />
																Tool
															</Badge>
														)}
														{workflow.type ===
															"data_provider" && (
															<Badge
																variant="secondary"
																className="bg-blue-100 text-blue-700 dark:bg-blue-900 dark:text-blue-300 text-xs"
																title="Provides data for forms and apps"
															>
																<Database className="mr-1 h-2 w-2" />
																Data Provider
															</Badge>
														)}
														{workflow.endpoint_enabled && (
															<Badge
																variant={
																	workflow.public_endpoint
																		? "destructive"
																		: hasGlobalKey ||
																			  workflowsWithKeys.has(
																					workflow.name ??
																						"",
																			  )
																			? "default"
																			: "outline"
																}
																className={`cursor-pointer transition-colors text-xs ${
																	workflow.public_endpoint
																		? "bg-orange-600 hover:bg-orange-700 border-orange-600"
																		: hasGlobalKey ||
																			  workflowsWithKeys.has(
																					workflow.name ??
																						"",
																			  )
																			? "bg-green-600 hover:bg-green-700"
																			: "text-muted-foreground hover:bg-accent"
																}`}
																onClick={() =>
																	handleShowWebhook(
																		workflow,
																	)
																}
															>
																{workflow.public_endpoint ? (
																	<AlertTriangle className="mr-1 h-2 w-2" />
																) : (
																	<Webhook className="mr-1 h-2 w-2" />
																)}
																Endpoint
															</Badge>
														)}
														{workflow.category && (
															<Badge
																variant="secondary"
																className="text-xs"
															>
																{workflow.category}
															</Badge>
														)}
													</div>
												</DataTableCell>
												<DataTableCell className="text-right">
													<div className="flex items-center justify-end gap-1">
														{isPlatformAdmin && (
															<Button
																variant="outline"
																size="sm"
																onClick={() =>
																	handleEditOrgScope(workflow)
																}
																title="Edit organization scope"
															>
																<Pencil className="h-4 w-4" />
															</Button>
														)}
														<Button
															variant="outline"
															size="sm"
															onClick={() =>
																handleExecute(
																	workflow.name ?? "",
																)
															}
														>
															<PlayCircle className="h-4 w-4" />
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
						<Card>
							<CardContent className="flex flex-col items-center justify-center py-12 text-center">
								<Code className="h-12 w-12 text-muted-foreground" />
								<h3 className="mt-4 text-lg font-semibold">
									{searchTerm
										? "No workflows match your search"
										: "No workflows available"}
								</h3>
								<p className="mt-2 text-sm text-muted-foreground">
									{searchTerm
										? "Try adjusting your search term or clear the filter"
										: "No workflows have been registered in the workflow engine"}
								</p>
							</CardContent>
						</Card>
					)}
				</div>
			</div>

			{/* HTTP Trigger Dialog */}
			{selectedWorkflow && (
				<HttpTriggerDialog
					workflow={selectedWorkflow}
					open={webhookDialogOpen}
					onOpenChange={setWebhookDialogOpen}
				/>
			)}

			{/* Edit Organization Scope Dialog */}
			<Dialog open={editOrgDialogOpen} onOpenChange={setEditOrgDialogOpen}>
				<DialogContent>
					<DialogHeader>
						<DialogTitle>Edit Workflow Organization Scope</DialogTitle>
						<DialogDescription>
							Change the organization scope for "{editingWorkflow?.name}".
							Global workflows are available to all organizations.
						</DialogDescription>
					</DialogHeader>
					<div className="py-4">
						<OrganizationSelect
							value={editOrgId}
							onChange={setEditOrgId}
							showAll={false}
							showGlobal={true}
							placeholder="Select organization..."
						/>
					</div>
					<DialogFooter>
						<Button
							variant="outline"
							onClick={() => setEditOrgDialogOpen(false)}
							disabled={isUpdating}
						>
							Cancel
						</Button>
						<Button onClick={handleSaveOrgScope} disabled={isUpdating}>
							{isUpdating ? "Saving..." : "Save"}
						</Button>
					</DialogFooter>
				</DialogContent>
			</Dialog>
		</div>
	);
}
