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
} from "lucide-react";
import { Button } from "@/components/ui/button";
import {
	Card,
	CardContent,
	CardDescription,
	CardHeader,
	CardTitle,
} from "@/components/ui/card";
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
import { useWorkflowsMetadata } from "@/hooks/useWorkflows";
import { useWorkflowKeys } from "@/hooks/useWorkflowKeys";
import { HttpTriggerDialog } from "@/components/workflows/HttpTriggerDialog";
import { SearchBox } from "@/components/search/SearchBox";
import { useSearch } from "@/hooks/useSearch";
import type { components } from "@/lib/v1";
type Workflow = components["schemas"]["WorkflowMetadata"];

export function Workflows() {
	const navigate = useNavigate();
	const { data, isLoading, refetch } = useWorkflowsMetadata();
	const { data: apiKeys } = useWorkflowKeys({ includeRevoked: false });
	const [webhookDialogOpen, setWebhookDialogOpen] = useState(false);
	const [selectedWorkflow, setSelectedWorkflow] = useState<Workflow | null>(
		null,
	);
	const [searchTerm, setSearchTerm] = useState("");
	const [viewMode, setViewMode] = useState<"grid" | "table">("grid");

	const workflows = useMemo(() => data?.workflows || [], [data]);

	// Apply search filter
	const filteredWorkflows = useSearch(workflows, searchTerm, [
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

	return (
		<div className="h-[calc(100vh-8rem)] flex flex-col space-y-6">
			<div className="flex items-center justify-between">
				<div>
					<h1 className="text-4xl font-extrabold tracking-tight">
						Workflows
					</h1>
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

			{/* Search Box */}
			<SearchBox
				value={searchTerm}
				onChange={setSearchTerm}
				placeholder="Search workflows by name, description, or category..."
				className="max-w-md"
			/>

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
										{workflow.is_tool && (
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
									<Button
										className="w-full"
										onClick={() =>
											handleExecute(workflow.name ?? "")
										}
									>
										<PlayCircle className="mr-2 h-4 w-4" />
										Execute Workflow
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
								<DataTableHead>Name</DataTableHead>
								<DataTableHead>Description</DataTableHead>
								<DataTableHead className="text-right">
									Parameters
								</DataTableHead>
								<DataTableHead>Status</DataTableHead>
								<DataTableHead className="text-right">
									Actions
								</DataTableHead>
							</DataTableRow>
						</DataTableHeader>
						<DataTableBody>
							{filteredWorkflows.map((workflow) => (
								<DataTableRow key={workflow.name}>
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
											{workflow.is_tool && (
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
										<Button
											size="sm"
											onClick={() =>
												handleExecute(
													workflow.name ?? "",
												)
											}
										>
											<PlayCircle className="h-4 w-4" />
										</Button>
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

			{/* HTTP Trigger Dialog */}
			{selectedWorkflow && (
				<HttpTriggerDialog
					workflow={selectedWorkflow}
					open={webhookDialogOpen}
					onOpenChange={setWebhookDialogOpen}
				/>
			)}
		</div>
	);
}
