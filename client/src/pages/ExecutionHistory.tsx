import { useState, useMemo, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import {
	CheckCircle,
	XCircle,
	Loader2,
	Clock,
	RefreshCw,
	History as HistoryIcon,
	Globe,
	Building2,
	Eraser,
	AlertCircle,
	Info,
	Eye,
	Terminal,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import {
	Card,
	CardContent,
	CardDescription,
	CardHeader,
	CardTitle,
} from "@/components/ui/card";
import {
	Table,
	TableBody,
	TableCell,
	TableHead,
	TableHeader,
	TableRow,
} from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import {
	Tooltip,
	TooltipContent,
	TooltipProvider,
	TooltipTrigger,
} from "@/components/ui/tooltip";

import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
	Dialog,
	DialogContent,
	DialogDescription,
	DialogFooter,
	DialogHeader,
	DialogTitle,
	DialogTrigger,
} from "@/components/ui/dialog";
import { useExecutions, cancelExecution } from "@/hooks/useExecutions";
import { useExecutionHistory } from "@/hooks/useExecutionStream";
import { useScopeStore } from "@/stores/scopeStore";
import { formatDate } from "@/lib/utils";
import { SearchBox } from "@/components/search/SearchBox";
import { useSearch } from "@/hooks/useSearch";
import { apiClient } from "@/lib/api-client";
import { toast } from "sonner";
import type { ExecutionFilters } from "@/lib/client-types";
import {
	Pagination,
	PaginationContent,
	PaginationItem,
	PaginationLink,
	PaginationNext,
	PaginationPrevious,
} from "@/components/ui/pagination";
import { DateRangePicker } from "@/components/ui/date-range-picker";
import type { DateRange } from "react-day-picker";
// import { useOrganizations } from '@/hooks/useOrganizations'
import type { components } from "@/lib/v1";
type ExecutionStatus =
	| components["schemas"]["ExecutionStatus"]
	| "Cancelling"
	| "Cancelled";

interface StuckExecution {
	execution_id: string;
	workflow_name: string;
	org_id?: string | null;
	form_id?: string | null;
	executed_by: string;
	executed_by_name: string;
	status: string;
	started_at?: string | null;
	completed_at?: string | null;
	error_message?: string | null;
	return_value?: Record<string, unknown> | null;
	output?: Record<string, unknown> | null;
	logs_count?: number;
	variables?: Record<string, unknown> | null;
}

export function ExecutionHistory() {
	const navigate = useNavigate();
	const [statusFilter, setStatusFilter] = useState<ExecutionStatus | "all">(
		"all",
	);
	const [searchTerm, setSearchTerm] = useState("");
	const [dateRange, setDateRange] = useState<DateRange | undefined>();
	const [cleanupDialogOpen, setCleanupDialogOpen] = useState(false);
	const [stuckExecutions, setStuckExecutions] = useState<StuckExecution[]>(
		[],
	);
	const [loadingStuck, setLoadingStuck] = useState(false);
	const [cleaningUp, setCleaningUp] = useState(false);
	const [showLocal, setShowLocal] = useState(false);
	const isGlobalScope = useScopeStore((state) => state.isGlobalScope);
	const orgId = useScopeStore((state) => state.scope.orgId);

	// Enable real-time updates for history page
	const scope = isGlobalScope ? "GLOBAL" : orgId || "GLOBAL";
	useExecutionHistory({ scope, enabled: true });
	// Pagination state - stack of continuation tokens for "back" navigation
	const [pageStack, setPageStack] = useState<(string | null)[]>([]);
	const [currentToken, setCurrentToken] = useState<string | undefined>(
		undefined,
	);
	// const { data: organization } = useOrganizations()
	// const organizations = organization ? [organization] : []

	// Build filters including date range and local executions toggle
	const filters = useMemo(() => {
		const baseFilters: Record<string, string | boolean> =
			statusFilter !== "all" ? { status: statusFilter as string } : {};

		// Add excludeLocal filter (inverse of showLocal)
		baseFilters.excludeLocal = !showLocal;

		if (dateRange?.from) {
			// Set start to beginning of day (00:00:00)
			const startDate = new Date(dateRange.from);
			startDate.setHours(0, 0, 0, 0);

			// Set end to end of day (23:59:59.999)
			// If no end date selected, use the same day as start
			const endDate = new Date(dateRange.to || dateRange.from);
			endDate.setHours(23, 59, 59, 999);

			return {
				...baseFilters,
				startDate: startDate.toISOString(),
				endDate: endDate.toISOString(),
			};
		}

		return baseFilters;
	}, [statusFilter, dateRange, showLocal]);

	const {
		data: response,
		isFetching,
		refetch,
	} = useExecutions(filters as ExecutionFilters, currentToken);

	// Memoize executions to prevent dependency issues
	const executions = useMemo(
		() => response?.executions || [],
		[response?.executions],
	);
	const nextToken = response?.continuation_token || null;
	const hasMore = nextToken !== null;

	// Find executions that are still running (for display purposes)
	const runningExecutionIds = useMemo(() => {
		if (!executions) return [];
		return executions
			.filter(
				(exec) =>
					exec.status === "Pending" || exec.status === "Running",
			)
			.map((exec) => exec.execution_id);
	}, [executions]);

	// Polling disabled - users can manually refresh to see status updates
	const isPolling = false;

	// Helper to get organization name from orgId (currently unused since orgId not available in Execution schema)
	// const getOrgName = (orgId?: string) => {
	//   if (!orgId || orgId === 'GLOBAL') return 'Global'
	//   const org = organizations?.find(o => o.id === orgId)
	//   return org?.name || orgId
	// }

	const getStatusBadge = (status: ExecutionStatus) => {
		switch (status) {
			case "Success":
				return (
					<Badge variant="default" className="bg-green-500">
						<CheckCircle className="mr-1 h-3 w-3" />
						Completed
					</Badge>
				);
			case "Failed":
				return (
					<Badge variant="destructive">
						<XCircle className="mr-1 h-3 w-3" />
						Failed
					</Badge>
				);
			case "Running":
				return (
					<Badge variant="secondary">
						<Loader2 className="mr-1 h-3 w-3 animate-spin" />
						Running
					</Badge>
				);
			case "Pending":
				return (
					<Badge variant="outline">
						<Clock className="mr-1 h-3 w-3" />
						Pending
					</Badge>
				);
			case "Cancelling":
				return (
					<Badge
						variant="secondary"
						className="bg-orange-500 text-white"
					>
						<Loader2 className="mr-1 h-3 w-3 animate-spin" />
						Cancelling
					</Badge>
				);
			case "Cancelled":
				return (
					<Badge
						variant="outline"
						className="border-gray-500 text-gray-600 dark:text-gray-400"
					>
						<XCircle className="mr-1 h-3 w-3" />
						Cancelled
					</Badge>
				);
			case "Timeout":
				return (
					<Badge variant="destructive">
						<XCircle className="mr-1 h-3 w-3" />
						Timeout
					</Badge>
				);
			case "CompletedWithErrors":
				return (
					<Badge
						variant="outline"
						className="border-yellow-500 text-yellow-600 dark:text-yellow-500"
					>
						<AlertCircle className="mr-1 h-3 w-3" />
						Completed with Errors
					</Badge>
				);
			default:
				return <Badge variant="outline">Unknown</Badge>;
		}
	};

	const handleViewDetails = (execution_id: string) => {
		navigate(`/history/${execution_id}`);
	};

	const handleCancelExecution = async (
		execution_id: string,
		workflow_name: string,
	) => {
		try {
			await cancelExecution(execution_id);
			toast.success(`Cancellation requested for ${workflow_name}`);
			// Refetch to show updated status
			refetch();
		} catch (error) {
			toast.error(`Failed to cancel execution: ${error}`);
		}
	};

	const handleOpenCleanup = async () => {
		setCleanupDialogOpen(true);
		setLoadingStuck(true);

		try {
			const response = await apiClient.GET(
				"/api/executions/cleanup/stuck",
			);
			if (response.data) {
				setStuckExecutions(response.data.executions || []);
			}
		} catch {
			toast.error("Failed to load stuck executions");
		} finally {
			setLoadingStuck(false);
		}
	};

	const handleTriggerCleanup = async () => {
		setCleaningUp(true);

		try {
			const response = await apiClient.POST(
				"/api/executions/cleanup/trigger",
				{},
			);
			if (response.data) {
				toast.success(
					`Cleaned up ${response.data.cleaned} stuck executions`,
				);
				setCleanupDialogOpen(false);
				// Refetch executions to show updated status
				refetch();
			}
		} catch {
			toast.error("Failed to trigger cleanup");
		} finally {
			setCleaningUp(false);
		}
	};

	// Apply search filter
	const searchFilteredExecutions = useSearch(executions || [], searchTerm, [
		"workflow_name",
		"executed_by_name",
		"execution_id",
		(exec) => exec.status,
	]);

	const filteredExecutions = searchFilteredExecutions;

	// Pagination handlers
	const handleNextPage = () => {
		if (nextToken) {
			// Push current state to stack for "back" navigation
			setPageStack([...pageStack, currentToken || null]);
			setCurrentToken(nextToken);
		}
	};

	const handlePreviousPage = () => {
		if (pageStack.length > 0) {
			// Pop from stack to go back
			const newStack = [...pageStack];
			const previousToken = newStack.pop();
			setPageStack(newStack);
			setCurrentToken(previousToken || undefined);
		}
	};

	// Reset pagination when filters change
	useEffect(() => {
		setPageStack([]);
		setCurrentToken(undefined);
	}, [statusFilter, dateRange, showLocal]);

	return (
		<div className="flex flex-col h-[calc(100vh-8rem)] space-y-6">
			<div className="flex-shrink-0">
				<div className="flex items-center justify-between">
					<div>
						<h1 className="text-4xl font-extrabold tracking-tight">
							Execution History
						</h1>
						<p className="mt-2 text-muted-foreground">
							View and track workflow execution history
						</p>
					</div>
				</div>
			</div>

			<Card className="flex-1 flex flex-col overflow-hidden">
				<CardHeader className="flex-shrink-0">
					<div className="flex items-center justify-between">
						<div>
							<CardTitle>All Executions</CardTitle>
							<CardDescription>
								{executions.length > 0 && (
									<span>
										Showing {executions.length} execution
										{executions.length !== 1 ? "s" : ""} on
										this page
										{hasMore && " (more available)"}
									</span>
								)}
								{executions.length === 0 &&
									"Recent workflow executions and their status"}
								{isPolling && (
									<span className="ml-2 inline-flex items-center text-blue-600">
										<Loader2 className="mr-1 h-3 w-3 animate-spin" />
										Auto-refreshing{" "}
										{runningExecutionIds.length} running
										execution
										{runningExecutionIds.length !== 1
											? "s"
											: ""}
									</span>
								)}
							</CardDescription>
						</div>
						<div className="flex items-center gap-2">
							<Dialog
								open={cleanupDialogOpen}
								onOpenChange={setCleanupDialogOpen}
							>
								<DialogTrigger asChild>
									<Button
										variant="outline"
										size="icon"
										onClick={handleOpenCleanup}
										title="Cleanup Stuck Executions"
									>
										<Eraser className="h-4 w-4" />
									</Button>
								</DialogTrigger>
								<DialogContent className="max-w-3xl">
									<DialogHeader>
										<DialogTitle>
											Cleanup Stuck Executions
										</DialogTitle>
										<DialogDescription>
											Stuck executions are workflows that
											have been in Pending status for 10+
											minutes or Running status for 30+
											minutes.
										</DialogDescription>
									</DialogHeader>

									{loadingStuck ? (
										<div className="flex items-center justify-center py-12">
											<Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
										</div>
									) : stuckExecutions.length === 0 ? (
										<div className="flex flex-col items-center justify-center py-12 text-center">
											<CheckCircle className="h-12 w-12 text-green-500 mb-4" />
											<h3 className="text-lg font-semibold">
												No Stuck Executions
											</h3>
											<p className="mt-2 text-sm text-muted-foreground">
												All executions are running
												normally
											</p>
										</div>
									) : (
										<div className="border rounded-lg">
											<Table>
												<TableHeader>
													<TableRow>
														<TableHead>
															Workflow
														</TableHead>
														<TableHead>
															Status
														</TableHead>
														<TableHead>
															Executed By
														</TableHead>
														<TableHead>
															Started At
														</TableHead>
													</TableRow>
												</TableHeader>
												<TableBody>
													{stuckExecutions.map(
														(execution) => (
															<TableRow
																key={
																	execution.execution_id
																}
															>
																<TableCell className="font-mono text-sm">
																	{
																		execution.workflow_name
																	}
																</TableCell>
																<TableCell>
																	<Badge
																		variant={
																			execution.status ===
																			"Pending"
																				? "outline"
																				: "secondary"
																		}
																	>
																		{
																			execution.status
																		}
																	</Badge>
																</TableCell>
																<TableCell>
																	{
																		execution.executed_by_name
																	}
																</TableCell>
																<TableCell className="text-sm">
																	{execution.started_at
																		? formatDate(
																				execution.started_at,
																			)
																		: "-"}
																</TableCell>
															</TableRow>
														),
													)}
												</TableBody>
											</Table>
										</div>
									)}

									<DialogFooter>
										<Button
											variant="outline"
											onClick={() =>
												setCleanupDialogOpen(false)
											}
										>
											Cancel
										</Button>
										<Button
											onClick={handleTriggerCleanup}
											disabled={
												stuckExecutions.length === 0 ||
												cleaningUp
											}
										>
											{cleaningUp && (
												<Loader2 className="mr-2 h-4 w-4 animate-spin" />
											)}
											Cleanup {stuckExecutions.length}{" "}
											Execution
											{stuckExecutions.length !== 1
												? "s"
												: ""}
										</Button>
									</DialogFooter>
								</DialogContent>
							</Dialog>

							<Button
								variant="outline"
								size="icon"
								onClick={() => refetch()}
								disabled={isFetching}
							>
								<RefreshCw
									className={`h-4 w-4 ${
										isFetching ? "animate-spin" : ""
									}`}
								/>
							</Button>
						</div>
					</div>
				</CardHeader>
				<CardContent className="flex-1 overflow-hidden flex flex-col">
					<Tabs
						defaultValue="all"
						onValueChange={(v) =>
							setStatusFilter(v as ExecutionStatus | "all")
						}
						className="flex flex-col flex-1 overflow-hidden"
					>
						<div className="flex-shrink-0 space-y-4 mb-4">
							<div className="flex items-center gap-4">
								{/* Search Box */}
								<SearchBox
									value={searchTerm}
									onChange={setSearchTerm}
									placeholder="Search by workflow name, user, or execution ID..."
									className="flex-1 max-w-2xl"
								/>

								{/* Date Range Picker */}
								<DateRangePicker
									dateRange={dateRange}
									onDateRangeChange={setDateRange}
								/>

								{/* Show Local Executions Toggle */}
								<div className="flex items-center gap-2">
									<Checkbox
										id="show-local"
										checked={showLocal}
										onCheckedChange={(checked) =>
											setShowLocal(checked === true)
										}
									/>
									<Label
										htmlFor="show-local"
										className="text-sm font-normal cursor-pointer whitespace-nowrap"
									>
										Show Local Executions
									</Label>
								</div>
							</div>

							{/* Filter Tabs */}
							<TabsList>
								<TabsTrigger value="all">All</TabsTrigger>
								<TabsTrigger value="Success">
									Completed
								</TabsTrigger>
								<TabsTrigger value="Running">
									Running
								</TabsTrigger>
								<TabsTrigger value="Failed">Failed</TabsTrigger>
								<TabsTrigger value="Pending">
									Pending
								</TabsTrigger>
							</TabsList>
						</div>

						<TabsContent
							value={statusFilter}
							className="mt-0 flex-1 overflow-auto"
						>
							{isFetching && !executions.length ? (
								<div className="flex items-center justify-center py-12">
									<Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
								</div>
							) : filteredExecutions.length > 0 ? (
								<div className="border rounded-lg overflow-hidden h-full">
									<div className="h-full overflow-auto">
										<table className="relative w-full caption-bottom text-sm">
											<TableHeader className="sticky top-0 bg-background/80 backdrop-blur-sm z-10">
												<TableRow>
													{isGlobalScope && (
														<TableHead>
															Scope
														</TableHead>
													)}
													<TableHead>
														Workflow
													</TableHead>
													<TableHead>
														Status
													</TableHead>
													<TableHead>
														Executed By
													</TableHead>
													<TableHead>
														Started At
													</TableHead>
													<TableHead>
														Completed At
													</TableHead>
													<TableHead>
														Duration
													</TableHead>
													<TableHead className="text-right"></TableHead>
												</TableRow>
											</TableHeader>
											<TableBody>
												{filteredExecutions.map(
													(execution) => {
														const duration =
															execution.completed_at &&
															execution.started_at
																? Math.round(
																		(new Date(
																			execution.completed_at,
																		).getTime() -
																			new Date(
																				execution.started_at,
																			).getTime()) /
																			1000,
																	)
																: null;

														// For now, treat all executions as global since orgId is not available in Execution schema
														const isGlobalExecution = true;

														return (
															<TableRow
																key={
																	execution.execution_id
																}
																className="cursor-pointer hover:bg-muted/50"
																onClick={() =>
																	handleViewDetails(
																		execution.execution_id,
																	)
																}
															>
																{isGlobalScope && (
																	<TableCell>
																		<Badge
																			variant={
																				isGlobalExecution
																					? "default"
																					: "outline"
																			}
																			className="text-xs"
																		>
																			{isGlobalExecution ? (
																				<>
																					<Globe className="mr-1 h-3 w-3" />
																					Global
																				</>
																			) : (
																				<>
																					<Building2 className="mr-1 h-3 w-3" />
																					Global
																				</>
																			)}
																		</Badge>
																	</TableCell>
																)}
																<TableCell className="font-mono text-sm">
																	<div className="flex items-center gap-2">
																		{
																			execution.workflow_name
																		}
																		{execution.session_id && (
																			<TooltipProvider>
																				<Tooltip>
																					<TooltipTrigger
																						asChild
																					>
																						<Button
																							variant="ghost"
																							size="icon"
																							className="h-6 w-6 text-muted-foreground hover:text-primary"
																							onClick={(
																								e,
																							) => {
																								e.stopPropagation();
																								navigate(
																									`/cli/${execution.session_id}`,
																								);
																							}}
																						>
																							<Terminal className="h-4 w-4" />
																						</Button>
																					</TooltipTrigger>
																					<TooltipContent side="right">
																						<p className="text-sm">
																							Dev
																							run
																							-
																							Click
																							to
																							view
																							session
																						</p>
																					</TooltipContent>
																				</Tooltip>
																			</TooltipProvider>
																		)}
																	</div>
																</TableCell>
																<TableCell>
																	<div className="flex items-center gap-2">
																		{getStatusBadge(
																			execution.status,
																		)}
																		{execution.error_message && (
																			<TooltipProvider>
																				<Tooltip>
																					<TooltipTrigger
																						asChild
																					>
																						<Info className="h-4 w-4 text-destructive cursor-help" />
																					</TooltipTrigger>
																					<TooltipContent
																						side="right"
																						className="max-w-md bg-popover text-popover-foreground"
																					>
																						<p className="text-sm">
																							{
																								execution.error_message
																							}
																						</p>
																					</TooltipContent>
																				</Tooltip>
																			</TooltipProvider>
																		)}
																	</div>
																</TableCell>
																<TableCell>
																	{
																		execution.executed_by_name
																	}
																</TableCell>
																<TableCell className="text-sm">
																	{execution.started_at
																		? formatDate(
																				execution.started_at,
																			)
																		: "-"}
																</TableCell>
																<TableCell className="text-sm">
																	{execution.completed_at
																		? formatDate(
																				execution.completed_at,
																			)
																		: "-"}
																</TableCell>
																<TableCell className="text-sm text-muted-foreground">
																	{duration !==
																	null
																		? `${duration}s`
																		: "-"}
																</TableCell>
																<TableCell className="text-right">
																	<div className="flex items-center justify-end gap-1">
																		{(execution.status ===
																			"Running" ||
																			execution.status ===
																				"Pending") && (
																			<Button
																				variant="ghost"
																				size="icon"
																				onClick={(
																					e,
																				) => {
																					e.stopPropagation();
																					handleCancelExecution(
																						execution.execution_id,
																						execution.workflow_name,
																					);
																				}}
																				title="Cancel Execution"
																			>
																				<XCircle className="h-4 w-4" />
																			</Button>
																		)}
																		<Button
																			variant="ghost"
																			size="icon"
																			onClick={(
																				e,
																			) => {
																				e.stopPropagation();
																				handleViewDetails(
																					execution.execution_id,
																				);
																			}}
																			title="View Details"
																		>
																			<Eye className="h-4 w-4" />
																		</Button>
																	</div>
																</TableCell>
															</TableRow>
														);
													},
												)}
											</TableBody>
										</table>

										{/* Pagination - Always Visible */}
										<div className="sticky bottom-0 px-6 py-4 border-t bg-background/80 backdrop-blur-sm flex items-center justify-center z-10">
											<Pagination>
												<PaginationContent>
													<PaginationItem>
														<PaginationPrevious
															onClick={(e) => {
																e.preventDefault();
																handlePreviousPage();
															}}
															className={
																pageStack.length ===
																	0 ||
																isFetching
																	? "pointer-events-none opacity-50"
																	: "cursor-pointer"
															}
															aria-disabled={
																pageStack.length ===
																	0 ||
																isFetching
															}
														/>
													</PaginationItem>
													<PaginationItem>
														<PaginationLink
															isActive
														>
															{pageStack.length +
																1}
														</PaginationLink>
													</PaginationItem>
													<PaginationItem>
														<PaginationNext
															onClick={(e) => {
																e.preventDefault();
																handleNextPage();
															}}
															className={
																!hasMore ||
																isFetching
																	? "pointer-events-none opacity-50"
																	: "cursor-pointer"
															}
															aria-disabled={
																!hasMore ||
																isFetching
															}
														/>
													</PaginationItem>
												</PaginationContent>
											</Pagination>
										</div>
									</div>
								</div>
							) : (
								<div className="flex flex-col items-center justify-center py-12 text-center">
									<HistoryIcon className="h-12 w-12 text-muted-foreground" />
									<h3 className="mt-4 text-lg font-semibold">
										{searchTerm
											? "No executions match your search"
											: "No executions found"}
									</h3>
									<p className="mt-2 text-sm text-muted-foreground">
										{searchTerm
											? "Try adjusting your search term or clear the filter"
											: "Execute a workflow to see it appear here"}
									</p>
								</div>
							)}
						</TabsContent>
					</Tabs>
				</CardContent>
			</Card>
		</div>
	);
}
