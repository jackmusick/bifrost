import { useParams, useNavigate, useLocation } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";
import {
	ArrowLeft,
	CheckCircle,
	XCircle,
	Loader2,
	Clock,
	PlayCircle,
	RefreshCw,
	Code2,
	Sparkles,
	ChevronDown,
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
	Collapsible,
	CollapsibleContent,
	CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { Badge } from "@/components/ui/badge";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
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
import { PageLoader } from "@/components/PageLoader";
import { useExecution, cancelExecution } from "@/hooks/useExecutions";
import { useAuth } from "@/contexts/AuthContext";
import { executeWorkflowWithContext } from "@/hooks/useWorkflows";
import { useWorkflowsMetadata } from "@/hooks/useWorkflows";
import { useEditorStore } from "@/stores/editorStore";
import { fileService } from "@/services/fileService";
import { toast } from "sonner";
import { Skeleton } from "@/components/ui/skeleton";
import { useExecutionStream } from "@/hooks/useExecutionStream";
import { useExecutionStreamStore } from "@/stores/executionStreamStore";
import { PrettyInputDisplay } from "@/components/execution/PrettyInputDisplay";
import { SafeHTMLRenderer } from "@/components/execution/SafeHTMLRenderer";
import { VariablesTreeView } from "@/components/ui/variables-tree-view";
import {
	formatDate,
	formatBytes,
	formatNumber,
	formatCost,
	formatDuration,
} from "@/lib/utils";
import type { components } from "@/lib/v1";
import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useState, useRef, useCallback } from "react";

type ExecutionStatus =
	| components["schemas"]["ExecutionStatus"]
	| "Cancelling"
	| "Cancelled";
type WorkflowExecution = components["schemas"]["WorkflowExecution"];
type WorkflowMetadata = components["schemas"]["WorkflowMetadata"];
type FileMetadata = components["schemas"]["FileMetadata"];
type WorkflowExecutionResponse =
	components["schemas"]["WorkflowExecutionResponse"];
type AIUsagePublicSimple = components["schemas"]["AIUsagePublicSimple"];

// Type for metadata response from useWorkflowsMetadata hook
interface WorkflowsMetadataResponse {
	workflows: WorkflowMetadata[];
	dataProviders: unknown[];
}
// Type for execution result response
interface ExecutionResultData {
	result?: unknown;
	result_type?: string;
}

// Type for execution log entry
interface ExecutionLogEntry {
	id?: number; // Unique log ID for exact deduplication
	level?: string;
	message?: string;
	timestamp?: string;
	data?: Record<string, unknown>;
	sequence?: number; // For ordering and range-based deduplication
}

interface ExecutionDetailsProps {
	/** Execution ID - if not provided, uses URL param */
	executionId?: string;
	/** Embedded mode - hides navigation header for use in panels */
	embedded?: boolean;
}

export function ExecutionDetails({
	executionId: propExecutionId,
	embedded = false,
}: ExecutionDetailsProps = {}) {
	const { executionId: urlExecutionId } = useParams();
	const executionId = propExecutionId || urlExecutionId;
	const navigate = useNavigate();
	const location = useLocation();
	const { isPlatformAdmin } = useAuth();
	const queryClient = useQueryClient();

	// Check if we came from an execution trigger (has navigation state)
	// If so, we defer the GET until WebSocket confirms the execution exists
	const hasNavigationState = location.state != null;

	const [signalrEnabled, setSignalrEnabled] = useState(false);
	const logsEndRef = useRef<HTMLDivElement>(null);
	const logsContainerRef = useRef<HTMLDivElement>(null);
	const [autoScroll, setAutoScroll] = useState(true);

	// Fallback timer - enable fetch after 5s if WebSocket hasn't received updates
	const [fetchFallbackEnabled, setFetchFallbackEnabled] = useState(false);
	useEffect(() => {
		// Reset fallback when execution ID changes (important for rerun navigation)
		setFetchFallbackEnabled(false);

		// If we have no navigation state (direct link), fetch immediately
		if (!hasNavigationState) {
			setFetchFallbackEnabled(true);
			return;
		}
		// Otherwise, wait 5s as fallback in case WebSocket fails
		const timer = setTimeout(() => setFetchFallbackEnabled(true), 5000);
		return () => clearTimeout(timer);
	}, [executionId, hasNavigationState]);

	// Get streaming logs from store
	// Use stable selector to avoid infinite loops
	const streamState = useExecutionStreamStore((state) =>
		executionId ? state.streams[executionId] : undefined,
	);
	const streamingLogs = streamState?.streamingLogs ?? [];

	// Determine if we should fetch from API
	// Fetch when:
	// - Stream received update (confirms DB write), OR
	// - Fallback timer expired (5s after navigation), OR
	// - No navigation state (direct link/refresh - fetch immediately!)
	const hasReceivedUpdate = streamState?.hasReceivedUpdate ?? false;
	const shouldFetchExecution =
		hasReceivedUpdate || fetchFallbackEnabled || !hasNavigationState;

	// State for confirmation dialogs
	const [showCancelDialog, setShowCancelDialog] = useState(false);
	const [showRerunDialog, setShowRerunDialog] = useState(false);
	const [isRerunning, setIsRerunning] = useState(false);
	const [isOpeningInEditor, setIsOpeningInEditor] = useState(false);

	// State for collapsible sections
	const [isAiUsageOpen, setIsAiUsageOpen] = useState(true);

	// Editor store actions
	const openFileInTab = useEditorStore((state) => state.openFileInTab);
	const openEditor = useEditorStore((state) => state.openEditor);
	const setSidebarPanel = useEditorStore((state) => state.setSidebarPanel);
	const minimizeEditor = useEditorStore((state) => state.minimizeEditor);

	// Fetch workflow metadata to get source file path
	const { data: metadataData } = useWorkflowsMetadata();
	const metadata = metadataData as WorkflowsMetadataResponse | undefined;

	// Fetch execution data - deferred until stream confirms DB write or fallback expires
	const {
		data: executionData,
		isLoading,
		isFetching,
		error,
	} = useExecution(
		shouldFetchExecution ? executionId : undefined,
		signalrEnabled,
	);

	// Cast execution data to the correct type
	const execution = executionData as WorkflowExecution | undefined;

	// Execution status and completion check
	const executionStatus = execution?.status as ExecutionStatus | undefined;
	const isComplete =
		executionStatus === "Success" ||
		executionStatus === "Failed" ||
		executionStatus === "CompletedWithErrors" ||
		executionStatus === "Timeout" ||
		executionStatus === "Cancelled";

	// Data now comes from single API call - create adapter variables for compatibility
	const resultData = execution
		? { result: execution.result, result_type: execution.result_type }
		: undefined;
	const logsData = execution?.logs as ExecutionLogEntry[] | undefined;
	const variablesData = execution?.variables as
		| Record<string, unknown>
		| undefined;

	// Loading states - all data comes at once now
	const isLoadingResult = isLoading;
	const isLoadingLogs = isLoading;
	const isLoadingVariables = isLoading;

	// Enable Web PubSub for running executions
	// Only disable when stream explicitly completes (not when status changes in cache)
	// This prevents race condition where we disconnect before completion callback fires
	useEffect(() => {
		// If we came from an execution trigger (has navigation state), start WebSocket immediately
		// We know the execution is fresh and will be Pending/Running
		if (hasNavigationState) {
			setSignalrEnabled(true);
			return;
		}
		// Otherwise, enable streaming if execution is in a running state
		if (
			executionStatus === "Pending" ||
			executionStatus === "Running" ||
			executionStatus === "Cancelling"
		) {
			setSignalrEnabled(true);
		}
		// Only disable on initial load if already complete (not from stream updates)
		// The stream's onComplete callback will handle cleanup for live executions
	}, [executionStatus, hasNavigationState]);

	// Disable streaming when stream reports completion
	useEffect(() => {
		if (streamState?.isComplete) {
			setSignalrEnabled(false);
		}
	}, [streamState?.isComplete]);

	// Wrap onComplete in useCallback to prevent infinite loop
	const handleStreamComplete = useCallback(() => {
		// Refetch full execution data when complete
		// Use openapi-react-query's query key format
		queryClient.invalidateQueries({
			queryKey: [
				"get",
				"/api/executions/{execution_id}",
				{ params: { path: { execution_id: executionId } } },
			],
		});
	}, [queryClient, executionId]);

	// Real-time updates via Web PubSub (only for running/pending/cancelling executions)
	const { isConnected } = useExecutionStream({
		executionId: executionId || "",
		enabled: !!executionId && signalrEnabled,
		onComplete: handleStreamComplete,
	});

	// Update execution status optimistically from stream
	useEffect(() => {
		if (streamState && executionId) {
			// Use openapi-react-query's query key format
			queryClient.setQueryData(
				[
					"get",
					"/api/executions/{execution_id}",
					{ params: { path: { execution_id: executionId } } },
				],
				(old: unknown) => {
					if (!old || typeof old !== "object") return old;
					return {
						...(old as Record<string, unknown>),
						status: streamState.status,
					};
				},
			);
		}
	}, [streamState, executionId, queryClient]);

	// Auto-scroll to bottom when new streaming logs arrive
	useEffect(() => {
		const container = logsContainerRef.current;
		if (
			autoScroll &&
			logsEndRef.current &&
			streamingLogs.length > 0 &&
			container
		) {
			// Only scroll if content exceeds container height
			if (container.scrollHeight > container.clientHeight) {
				logsEndRef.current.scrollIntoView({ behavior: "smooth" });
			}
		}
	}, [streamingLogs.length, autoScroll]);

	// Handle scroll to detect if user has scrolled up (pause auto-scroll)
	const handleLogsScroll = useCallback(() => {
		const container = logsContainerRef.current;
		if (!container) return;

		// Check if scrolled to bottom (with 50px threshold)
		const isAtBottom =
			container.scrollHeight -
				container.scrollTop -
				container.clientHeight <
			50;
		setAutoScroll(isAtBottom);
	}, []);

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
						<PlayCircle className="mr-1 h-3 w-3" />
						Running
					</Badge>
				);
			case "Pending": {
				// Show queue position or memory pressure info from stream state
				const queuePosition = streamState?.queuePosition;
				const waitReason = streamState?.waitReason;
				const availableMemory = streamState?.availableMemoryMb;
				const requiredMemory = streamState?.requiredMemoryMb;

				if (waitReason === "queued" && queuePosition) {
					return (
						<Badge variant="outline">
							<Clock className="mr-1 h-3 w-3" />
							Queued - Position {queuePosition}
						</Badge>
					);
				} else if (waitReason === "memory_pressure") {
					return (
						<Badge variant="outline" className="border-orange-500">
							<Loader2 className="mr-1 h-3 w-3 animate-spin" />
							Heavy Load ({availableMemory ?? "?"}MB /{" "}
							{requiredMemory ?? "?"}MB)
						</Badge>
					);
				}
				return (
					<Badge variant="outline">
						<Clock className="mr-1 h-3 w-3" />
						Pending
					</Badge>
				);
			}
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
			case "CompletedWithErrors":
				return (
					<Badge variant="secondary" className="bg-yellow-500">
						<XCircle className="mr-1 h-3 w-3" />
						Completed with Errors
					</Badge>
				);
			case "Timeout":
				return (
					<Badge variant="destructive">
						<XCircle className="mr-1 h-3 w-3" />
						Timeout
					</Badge>
				);
			default:
				return null;
		}
	};

	const getStatusIcon = (status: ExecutionStatus) => {
		switch (status) {
			case "Success":
				return <CheckCircle className="h-12 w-12 text-green-500" />;
			case "Failed":
				return <XCircle className="h-12 w-12 text-red-500" />;
			case "Running":
				return (
					<Loader2 className="h-12 w-12 text-blue-500 animate-spin" />
				);
			case "Pending":
				return <Clock className="h-12 w-12 text-gray-500" />;
			case "Cancelling":
				return (
					<Loader2 className="h-12 w-12 text-orange-500 animate-spin" />
				);
			case "Cancelled":
				return <XCircle className="h-12 w-12 text-gray-500" />;
			case "CompletedWithErrors":
				return <XCircle className="h-12 w-12 text-yellow-500" />;
			case "Timeout":
				return <XCircle className="h-12 w-12 text-red-500" />;
			default:
				return null;
		}
	};

	const handleCancelExecution = async () => {
		if (!executionId || !execution) return;

		try {
			await cancelExecution(executionId);
			toast.success(
				`Cancellation requested for ${execution.workflow_name}`,
			);
			setShowCancelDialog(false);
			// Refetch to show updated status - use openapi-react-query's query key format
			queryClient.invalidateQueries({
				queryKey: [
					"get",
					"/api/executions/{execution_id}",
					{ params: { path: { execution_id: executionId } } },
				],
			});
		} catch (error) {
			toast.error(`Failed to cancel execution: ${error}`);
			setShowCancelDialog(false);
		}
	};

	const handleRerunExecution = async () => {
		if (!execution) return;

		// Look up the workflow ID from metadata
		const workflow = metadata?.workflows?.find(
			(w: WorkflowMetadata) => w.name === execution.workflow_name,
		);

		if (!workflow?.id) {
			toast.error("Cannot rerun: workflow not found in metadata");
			setShowRerunDialog(false);
			return;
		}

		setIsRerunning(true);
		try {
			const result = (await executeWorkflowWithContext(
				workflow.id,
				execution.input_data as Record<string, unknown>,
			)) as WorkflowExecutionResponse;

			toast.success(
				`Workflow ${execution.workflow_name} restarted successfully`,
			);
			setShowRerunDialog(false);

			// Navigate to the new execution with context to avoid 404 race condition
			if (result?.execution_id) {
				navigate(`/history/${result.execution_id}`, {
					state: {
						workflow_name: execution.workflow_name,
						workflow_id: workflow.id,
						input_data: execution.input_data,
					},
				});
			}
		} catch (error) {
			toast.error(`Failed to rerun workflow: ${error}`);
			setShowRerunDialog(false);
		} finally {
			setIsRerunning(false);
		}
	};

	const handleOpenInEditor = async () => {
		if (!execution) return;

		// Find the workflow's relative file path from metadata
		const workflow = metadata?.workflows?.find(
			(w: WorkflowMetadata) => w.name === execution.workflow_name,
		);
		const relativeFilePath = workflow?.relative_file_path;

		if (!relativeFilePath) {
			toast.error("Cannot open in editor: source file not found");
			return;
		}

		setIsOpeningInEditor(true);
		try {
			// Read the file using the relative path directly
			const fileResponse = await fileService.readFile(relativeFilePath);

			// Get file name from path
			const fileName =
				relativeFilePath.split("/").pop() || relativeFilePath;
			const extension = fileName.includes(".")
				? fileName.split(".").pop()!
				: null;

			// Create a minimal FileMetadata object for the tab
			const fileMetadata: FileMetadata = {
				name: fileName,
				path: relativeFilePath,
				type: "file",
				size: 0,
				extension,
				modified: new Date().toISOString(),
				entity_type: null,
				entity_id: null,
			};

			// Minimize the current details page
			minimizeEditor();

			// Open editor
			openEditor();

			// Open file in a new tab
			openFileInTab(
				fileMetadata,
				fileResponse.content,
				fileResponse.encoding as "utf-8" | "base64",
				fileResponse.etag,
			);

			// Switch to run panel to show the terminal
			setSidebarPanel("run");

			toast.success("Opened in editor");
		} catch (error) {
			console.error("Failed to open in editor:", error);
			toast.error("Failed to open file in editor");
		} finally {
			setIsOpeningInEditor(false);
		}
	};

	// Show loading state during initial load or background fetches/retries
	// This prevents the "Waiting for execution" message from flashing on refresh
	if (isLoading || isFetching) {
		if (embedded) {
			return (
				<div className="flex items-center justify-center h-full p-8">
					<Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
				</div>
			);
		}
		return <PageLoader message="Loading execution details..." />;
	}

	// Handle case where execution is not found yet (Redis-first architecture)
	// This "waiting" state is ONLY for fresh executions when we navigate from
	// the execution trigger (hasNavigationState is true). For page refreshes
	// or direct links, we should show the loading state or error state instead.
	if (!execution && !error && hasNavigationState) {
		if (embedded) {
			return (
				<div className="flex flex-col items-center justify-center h-full p-8 text-center">
					<Loader2 className="h-12 w-12 text-muted-foreground animate-spin" />
					<p className="text-sm text-muted-foreground mt-4">
						Waiting for execution to start...
					</p>
				</div>
			);
		}
		return (
			<div className="flex items-center justify-center min-h-[60vh] p-6">
				<motion.div
					initial={{ opacity: 0, y: 20 }}
					animate={{ opacity: 1, y: 0 }}
					transition={{ duration: 0.3 }}
					className="max-w-md w-full space-y-6"
				>
					<div className="flex justify-center">
						<Loader2 className="h-16 w-16 text-muted-foreground animate-spin" />
					</div>
					<div className="text-center">
						<h2 className="text-xl font-semibold">
							Waiting for execution to start...
						</h2>
						<p className="text-muted-foreground mt-2">
							The execution is being prepared. This page will
							update automatically.
						</p>
					</div>
				</motion.div>
			</div>
		);
	}

	if (error || !execution) {
		if (embedded) {
			return (
				<div className="flex flex-col items-center justify-center h-full p-8 text-center">
					<XCircle className="h-12 w-12 text-destructive" />
					<p className="text-sm text-destructive mt-4">
						{error
							? "Failed to load execution"
							: "Execution not found"}
					</p>
				</div>
			);
		}
		return (
			<div className="flex items-center justify-center min-h-[60vh] p-6">
				<motion.div
					initial={{ opacity: 0, y: 20 }}
					animate={{ opacity: 1, y: 0 }}
					transition={{ duration: 0.3 }}
					className="max-w-md w-full space-y-6"
				>
					<div className="flex justify-center">
						<XCircle className="h-16 w-16 text-destructive" />
					</div>
					<Alert variant="destructive">
						<XCircle className="h-4 w-4" />
						<AlertTitle>Error</AlertTitle>
						<AlertDescription>
							{error
								? "Failed to load execution details. The execution may not exist or you may not have permission to view it."
								: "Execution not found"}
						</AlertDescription>
					</Alert>
					<div className="flex justify-center">
						<Button
							onClick={() => navigate("/history")}
							variant="outline"
						>
							<ArrowLeft className="mr-2 h-4 w-4" />
							Back to History
						</Button>
					</div>
				</motion.div>
			</div>
		);
	}

	return (
		<div
			className={
				embedded ? "h-full overflow-y-auto" : "h-full overflow-y-auto"
			}
		>
			{/* Page Header - hidden in embedded mode */}
			{!embedded && (
				<div className="sticky top-0 bg-background/80 backdrop-blur-sm py-6 border-b flex items-center gap-4 px-6 lg:px-8 z-10">
					<Button
						variant="ghost"
						size="icon"
						onClick={() => navigate("/history")}
					>
						<ArrowLeft className="h-4 w-4" />
					</Button>
					<div className="flex-1">
						<h1 className="text-4xl font-extrabold tracking-tight">
							Execution Details
						</h1>
						<p className="mt-2 text-muted-foreground">
							Execution ID:{" "}
							<span className="font-mono">
								{execution.execution_id}
							</span>
						</p>
					</div>
					<div className="flex gap-2">
						{/* Open in Editor button - show for workflows with source files */}
						{metadata?.workflows?.find(
							(w: WorkflowMetadata) =>
								w.name === execution.workflow_name,
						)?.source_file_path && (
							<Button
								variant="outline"
								onClick={handleOpenInEditor}
								disabled={isOpeningInEditor}
							>
								{isOpeningInEditor ? (
									<Loader2 className="mr-2 h-4 w-4 animate-spin" />
								) : (
									<Code2 className="mr-2 h-4 w-4" />
								)}
								Open in Editor
							</Button>
						)}
						{/* Rerun button - show when complete */}
						{isComplete && (
							<Button
								variant="outline"
								onClick={() => setShowRerunDialog(true)}
								disabled={isRerunning}
							>
								{isRerunning ? (
									<Loader2 className="mr-2 h-4 w-4 animate-spin" />
								) : (
									<RefreshCw className="mr-2 h-4 w-4" />
								)}
								Rerun
							</Button>
						)}
						{/* Cancel button - show when running/pending */}
						{(execution.status === "Running" ||
							execution.status === "Pending") && (
							<Button
								variant="outline"
								onClick={() => setShowCancelDialog(true)}
							>
								<XCircle className="mr-2 h-4 w-4" />
								Cancel
							</Button>
						)}
					</div>
				</div>
			)}

			{/* Two-column layout: Content on left, Sidebar on right */}
			<div className={embedded ? "p-4" : "p-6 lg:p-8"}>
				<div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
					{/* Left Column - Main Content (2/3 width) */}
					<div className="lg:col-span-2 space-y-6">
						{/* Result Section */}
						{isComplete && (
							<motion.div
								initial={{ opacity: 0, y: 20 }}
								animate={{ opacity: 1, y: 0 }}
								transition={{ duration: 0.3 }}
							>
								<Card>
									<CardHeader>
										<CardTitle>Result</CardTitle>
										<CardDescription>
											Workflow execution result
										</CardDescription>
									</CardHeader>
									<CardContent>
										<AnimatePresence mode="wait">
											{isLoadingResult ? (
												<motion.div
													key="loading"
													initial={{ opacity: 0 }}
													animate={{ opacity: 1 }}
													exit={{ opacity: 0 }}
													transition={{
														duration: 0.2,
													}}
													className="space-y-3"
												>
													<Skeleton className="h-4 w-full" />
													<Skeleton className="h-4 w-3/4" />
													<Skeleton className="h-4 w-5/6" />
												</motion.div>
											) : (
													resultData as ExecutionResultData
											  )?.result === null ? (
												<motion.div
													key="empty"
													initial={{ opacity: 0 }}
													animate={{ opacity: 1 }}
													exit={{ opacity: 0 }}
													transition={{
														duration: 0.2,
													}}
													className="text-center text-muted-foreground py-8"
												>
													No result returned
												</motion.div>
											) : (
												<motion.div
													key="content"
													initial={{ opacity: 0 }}
													animate={{ opacity: 1 }}
													exit={{ opacity: 0 }}
													transition={{
														duration: 0.2,
													}}
												>
													{(
														resultData as ExecutionResultData
													)?.result_type === "json" &&
														typeof (
															resultData as ExecutionResultData
														)?.result ===
															"object" && (
															<PrettyInputDisplay
																inputData={
																	(
																		resultData as ExecutionResultData
																	)
																		.result as Record<
																		string,
																		unknown
																	>
																}
																showToggle={
																	true
																}
																defaultView="pretty"
															/>
														)}
													{(
														resultData as ExecutionResultData
													)?.result_type === "html" &&
														typeof (
															resultData as ExecutionResultData
														)?.result ===
															"string" && (
															<SafeHTMLRenderer
																html={
																	(
																		resultData as ExecutionResultData
																	)
																		.result as string
																}
																title={`${execution.workflow_name} - Execution Result`}
															/>
														)}
													{(
														resultData as ExecutionResultData
													)?.result_type === "text" &&
														typeof (
															resultData as ExecutionResultData
														)?.result ===
															"string" && (
															<pre className="whitespace-pre-wrap font-mono text-sm bg-muted p-4 rounded">
																{
																	(
																		resultData as ExecutionResultData
																	)
																		.result as string
																}
															</pre>
														)}
													{!(
														resultData as ExecutionResultData
													)?.result_type &&
														typeof (
															resultData as ExecutionResultData
														)?.result ===
															"object" &&
														(
															resultData as ExecutionResultData
														)?.result !== null && (
															<PrettyInputDisplay
																inputData={
																	(
																		resultData as ExecutionResultData
																	)
																		.result as Record<
																		string,
																		unknown
																	>
																}
																showToggle={
																	true
																}
																defaultView="pretty"
															/>
														)}
												</motion.div>
											)}
										</AnimatePresence>
									</CardContent>
								</Card>
							</motion.div>
						)}

						{/* Error Section */}
						{execution.error_message && (
							<motion.div
								initial={{ opacity: 0, y: 20 }}
								animate={{ opacity: 1, y: 0 }}
								transition={{ duration: 0.3 }}
							>
								<Card className="border-destructive">
									<CardHeader>
										<CardTitle className="flex items-center gap-2 text-destructive">
											<XCircle className="h-5 w-5" />
											Error
										</CardTitle>
										<CardDescription>
											Workflow execution failed
										</CardDescription>
									</CardHeader>
									<CardContent>
										<pre className="text-sm whitespace-pre-wrap break-words font-mono bg-destructive/10 p-4 rounded-md overflow-x-auto">
											{execution.error_message}
										</pre>
									</CardContent>
								</Card>
							</motion.div>
						)}

						{/* Logs Section - All users (DEBUG logs filtered for non-admins) */}
						<motion.div
							initial={{ opacity: 0, y: 20 }}
							animate={{ opacity: 1, y: 0 }}
							transition={{ duration: 0.3, delay: 0.1 }}
						>
							<Card>
								<CardHeader>
									<CardTitle className="flex items-center gap-2">
										Logs
										{isConnected &&
											(execution?.status === "Running" ||
												execution?.status ===
													"Pending") && (
												<Badge
													variant="secondary"
													className="text-xs"
												>
													<Loader2 className="mr-1 h-3 w-3 animate-spin" />
													Live
												</Badge>
											)}
									</CardTitle>
									<CardDescription>
										Python logger output from workflow
										execution
										{!isPlatformAdmin &&
											" (INFO, WARNING, ERROR only)"}
									</CardDescription>
								</CardHeader>
								<CardContent>
									{/* Show streaming logs during execution, progressively loaded logs when complete */}
									{(() => {
										// During execution, show existing logs + streaming logs
										if (
											executionStatus === "Running" ||
											executionStatus === "Pending" ||
											executionStatus === "Cancelling"
										) {
											// Combine API logs with real-time streaming logs
											const existingLogs =
												(logsData as ExecutionLogEntry[]) ||
												[];
											const logsToDisplay = [
												...existingLogs,
												...streamingLogs,
											];

											if (
												logsToDisplay.length === 0 &&
												!isLoadingLogs
											) {
												return (
													<div className="text-center text-muted-foreground py-8">
														Waiting for logs...
													</div>
												);
											}

											if (
												isLoadingLogs &&
												logsToDisplay.length === 0
											) {
												return (
													<div className="text-center text-muted-foreground py-8">
														<Loader2 className="h-4 w-4 animate-spin inline mr-2" />
														Loading logs...
													</div>
												);
											}

											return (
												<div
													ref={logsContainerRef}
													onScroll={handleLogsScroll}
													className="space-y-2 max-h-[70vh] overflow-y-auto"
												>
													{logsToDisplay.map(
														(
															log: ExecutionLogEntry,
															index: number,
														) => {
															const level =
																(
																	log.level as string
																)?.toLowerCase() ||
																"info";
															const levelColor =
																{
																	debug: "text-gray-500",
																	info: "text-blue-600",
																	warning:
																		"text-yellow-600",
																	error: "text-red-600",
																	traceback:
																		"text-orange-600",
																}[
																	level as
																		| "debug"
																		| "info"
																		| "warning"
																		| "error"
																		| "traceback"
																] ||
																"text-gray-600";

															return (
																<div
																	key={index}
																	className="flex gap-3 text-sm font-mono border-b pb-2 last:border-0"
																>
																	<span className="text-muted-foreground whitespace-nowrap">
																		{log.timestamp
																			? new Date(
																					log.timestamp,
																				).toLocaleTimeString()
																			: ""}
																	</span>
																	<span
																		className={`font-semibold uppercase min-w-[60px] ${levelColor}`}
																	>
																		{
																			log.level
																		}
																	</span>
																	<span className="flex-1 whitespace-pre-wrap">
																		{
																			log.message
																		}
																	</span>
																	{log.data &&
																		Object.keys(
																			log.data,
																		)
																			.length >
																			0 && (
																			<details className="text-xs">
																				<summary className="cursor-pointer text-muted-foreground">
																					data
																				</summary>
																				<pre className="mt-1 p-2 bg-muted rounded">
																					{JSON.stringify(
																						log.data,
																						null,
																						2,
																					)}
																				</pre>
																			</details>
																		)}
																</div>
															);
														},
													)}
													{/* Scroll anchor for auto-scroll */}
													<div ref={logsEndRef} />
												</div>
											);
										}

										// When complete, show progressively loaded logs
										if (isComplete) {
											return (
												<AnimatePresence mode="wait">
													{isLoadingLogs ? (
														<motion.div
															key="loading"
															initial={{
																opacity: 0,
															}}
															animate={{
																opacity: 1,
															}}
															exit={{
																opacity: 0,
															}}
															transition={{
																duration: 0.2,
															}}
															className="space-y-2"
														>
															<Skeleton className="h-4 w-full" />
															<Skeleton className="h-4 w-5/6" />
															<Skeleton className="h-4 w-4/5" />
														</motion.div>
													) : (
														(() => {
															const completedLogs =
																(logsData as ExecutionLogEntry[]) ||
																[];

															if (
																completedLogs.length ===
																0
															) {
																return (
																	<motion.div
																		key="empty"
																		initial={{
																			opacity: 0,
																		}}
																		animate={{
																			opacity: 1,
																		}}
																		exit={{
																			opacity: 0,
																		}}
																		transition={{
																			duration: 0.2,
																		}}
																		className="text-center text-muted-foreground py-8"
																	>
																		No logs
																		captured
																	</motion.div>
																);
															}

															return (
																<motion.div
																	key="content"
																	initial={{
																		opacity: 0,
																	}}
																	animate={{
																		opacity: 1,
																	}}
																	exit={{
																		opacity: 0,
																	}}
																	transition={{
																		duration: 0.2,
																	}}
																	ref={
																		logsContainerRef
																	}
																	className="space-y-2 max-h-[70vh] overflow-y-auto"
																>
																	{completedLogs.map(
																		(
																			log: ExecutionLogEntry,
																			index: number,
																		) => {
																			const level =
																				(
																					log.level as string
																				)?.toLowerCase() ||
																				"info";
																			const levelColor =
																				{
																					debug: "text-gray-500",
																					info: "text-blue-600",
																					warning:
																						"text-yellow-600",
																					error: "text-red-600",
																					traceback:
																						"text-orange-600",
																				}[
																					level as
																						| "debug"
																						| "info"
																						| "warning"
																						| "error"
																						| "traceback"
																				] ||
																				"text-gray-600";

																			return (
																				<div
																					key={
																						index
																					}
																					className="flex gap-3 text-sm font-mono border-b pb-2 last:border-0"
																				>
																					<span className="text-muted-foreground whitespace-nowrap">
																						{log.timestamp
																							? new Date(
																									log.timestamp,
																								).toLocaleTimeString()
																							: ""}
																					</span>
																					<span
																						className={`font-semibold uppercase min-w-[60px] ${levelColor}`}
																					>
																						{
																							log.level
																						}
																					</span>
																					<span className="flex-1 whitespace-pre-wrap">
																						{
																							log.message
																						}
																					</span>
																					{log.data &&
																						Object.keys(
																							log.data,
																						)
																							.length >
																							0 && (
																							<details className="text-xs">
																								<summary className="cursor-pointer text-muted-foreground">
																									data
																								</summary>
																								<pre className="mt-1 p-2 bg-muted rounded">
																									{JSON.stringify(
																										log.data,
																										null,
																										2,
																									)}
																								</pre>
																							</details>
																						)}
																				</div>
																			);
																		},
																	)}
																</motion.div>
															);
														})()
													)}
												</AnimatePresence>
											);
										}

										return null;
									})()}
								</CardContent>
							</Card>
						</motion.div>
					</div>

					{/* Right Column - Sidebar (1/3 width) */}
					<div className="space-y-6">
						{/* Status Card */}
						<Card>
							<CardHeader>
								<CardTitle>Execution Status</CardTitle>
							</CardHeader>
							<CardContent>
								<div className="flex flex-col items-center justify-center py-4 text-center">
									{getStatusIcon(execution.status)}
									<div className="mt-4">
										{getStatusBadge(execution.status)}
									</div>
								</div>
							</CardContent>
						</Card>

						{/* Workflow Information Card */}
						<Card>
							<CardHeader>
								<CardTitle>Workflow Information</CardTitle>
							</CardHeader>
							<CardContent className="space-y-4">
								<div>
									<p className="text-sm font-medium text-muted-foreground">
										Workflow Name
									</p>
									<p className="font-mono text-sm mt-1">
										{execution.workflow_name}
									</p>
								</div>
								<div>
									<p className="text-sm font-medium text-muted-foreground">
										Executed By
									</p>
									<p className="text-sm mt-1">
										{execution.executed_by_name}
									</p>
								</div>
								<div>
									<p className="text-sm font-medium text-muted-foreground">
										Effective Scope
									</p>
									<p className="text-sm mt-1">
										{execution.org_name || "Global"}
									</p>
								</div>
								<div>
									<p className="text-sm font-medium text-muted-foreground">
										Started At
									</p>
									<p className="text-sm mt-1">
										{execution.started_at
											? formatDate(execution.started_at)
											: "N/A"}
									</p>
								</div>
								{execution.completed_at && (
									<div>
										<p className="text-sm font-medium text-muted-foreground">
											Completed At
										</p>
										<p className="text-sm mt-1">
											{formatDate(execution.completed_at)}
										</p>
									</div>
								)}
							</CardContent>
						</Card>

						{/* Input Parameters - All users */}
						<Card>
							<CardHeader>
								<CardTitle>Input Parameters</CardTitle>
								<CardDescription>
									Workflow parameters that were passed in
								</CardDescription>
							</CardHeader>
							<CardContent>
								<PrettyInputDisplay
									inputData={execution.input_data}
									showToggle={true}
									defaultView="pretty"
								/>
							</CardContent>
						</Card>

						{/* Runtime Variables - Platform admins only */}
						{isPlatformAdmin && isComplete && (
							<motion.div
								initial={{ opacity: 0, y: 20 }}
								animate={{ opacity: 1, y: 0 }}
								transition={{ duration: 0.3, delay: 0.2 }}
							>
								<Card>
									<CardHeader>
										<CardTitle>Runtime Variables</CardTitle>
										<CardDescription>
											Variables captured from script
											namespace (admin only)
										</CardDescription>
									</CardHeader>
									<CardContent>
										<AnimatePresence mode="wait">
											{isLoadingVariables ? (
												<motion.div
													key="loading"
													initial={{ opacity: 0 }}
													animate={{ opacity: 1 }}
													exit={{ opacity: 0 }}
													transition={{
														duration: 0.2,
													}}
													className="space-y-2"
												>
													<Skeleton className="h-4 w-full" />
													<Skeleton className="h-4 w-4/5" />
													<Skeleton className="h-4 w-3/4" />
												</motion.div>
											) : !variablesData ||
											  Object.keys(variablesData)
													.length === 0 ? (
												<motion.div
													key="empty"
													initial={{ opacity: 0 }}
													animate={{ opacity: 1 }}
													exit={{ opacity: 0 }}
													transition={{
														duration: 0.2,
													}}
													className="text-center text-muted-foreground py-8"
												>
													No variables captured
												</motion.div>
											) : (
												<motion.div
													key="content"
													initial={{ opacity: 0 }}
													animate={{ opacity: 1 }}
													exit={{ opacity: 0 }}
													transition={{
														duration: 0.2,
													}}
													className="overflow-x-auto"
												>
													<VariablesTreeView
														data={
															variablesData as Record<
																string,
																unknown
															>
														}
													/>
												</motion.div>
											)}
										</AnimatePresence>
									</CardContent>
								</Card>
							</motion.div>
						)}

						{/* Usage Card - Compute resources (admin) + AI usage (all users) */}
						{isComplete &&
							((isPlatformAdmin &&
								(execution?.peak_memory_bytes ||
									execution?.cpu_total_seconds)) ||
								(execution?.ai_usage &&
									execution.ai_usage.length > 0)) && (
								<motion.div
									initial={{ opacity: 0, y: 20 }}
									animate={{ opacity: 1, y: 0 }}
									transition={{ duration: 0.3, delay: 0.2 }}
								>
									<Card>
										<CardHeader className="pb-3">
											<CardTitle>Usage</CardTitle>
											<CardDescription>
												Execution metrics and costs
											</CardDescription>
										</CardHeader>
										<CardContent className="space-y-4">
											{/* Compute Resources - Platform admins only */}
											{isPlatformAdmin &&
												(execution?.peak_memory_bytes ||
													execution?.cpu_total_seconds) && (
													<div className="space-y-3">
														{execution?.peak_memory_bytes && (
															<div>
																<p className="text-sm font-medium text-muted-foreground">
																	Peak Memory
																</p>
																<p className="text-sm font-mono">
																	{formatBytes(
																		execution.peak_memory_bytes,
																	)}
																</p>
															</div>
														)}
														{execution?.cpu_total_seconds && (
															<div>
																<p className="text-sm font-medium text-muted-foreground">
																	CPU Time
																</p>
																<p className="text-sm font-mono">
																	{execution.cpu_total_seconds.toFixed(
																		3,
																	)}
																	s
																</p>
															</div>
														)}
														{execution?.duration_ms && (
															<div>
																<p className="text-sm font-medium text-muted-foreground">
																	Duration
																</p>
																<p className="text-sm font-mono">
																	{(
																		execution.duration_ms /
																		1000
																	).toFixed(
																		2,
																	)}
																	s
																</p>
															</div>
														)}
													</div>
												)}

											{/* Divider when both sections are shown */}
											{isPlatformAdmin &&
												(execution?.peak_memory_bytes ||
													execution?.cpu_total_seconds) &&
												execution?.ai_usage &&
												execution.ai_usage.length >
													0 && (
													<div className="border-t pt-4" />
												)}

											{/* AI Usage - Available to all users */}
											{execution?.ai_usage &&
												execution.ai_usage.length >
													0 && (
													<Collapsible
														open={isAiUsageOpen}
														onOpenChange={
															setIsAiUsageOpen
														}
													>
														<div className="flex items-center justify-between">
															<div className="flex items-center gap-2">
																<Sparkles className="h-4 w-4 text-purple-500" />
																<span className="text-sm font-medium">
																	AI Usage
																</span>
																<Badge
																	variant="secondary"
																	className="text-xs"
																>
																	{execution
																		.ai_totals
																		?.call_count ||
																		execution
																			.ai_usage
																			.length}{" "}
																	{(execution
																		.ai_totals
																		?.call_count ||
																		execution
																			.ai_usage
																			.length) ===
																	1
																		? "call"
																		: "calls"}
																</Badge>
															</div>
															<CollapsibleTrigger
																asChild
															>
																<Button
																	variant="ghost"
																	size="sm"
																>
																	<ChevronDown
																		className={`h-4 w-4 transition-transform duration-200 ${
																			isAiUsageOpen
																				? "rotate-180"
																				: ""
																		}`}
																	/>
																</Button>
															</CollapsibleTrigger>
														</div>
														{execution.ai_totals && (
															<p className="mt-1 text-xs text-muted-foreground">
																Total:{" "}
																{formatNumber(
																	execution
																		.ai_totals
																		.total_input_tokens,
																)}{" "}
																in /{" "}
																{formatNumber(
																	execution
																		.ai_totals
																		.total_output_tokens,
																)}{" "}
																out tokens
																{execution
																	.ai_totals
																	.total_cost &&
																	` | ${formatCost(execution.ai_totals.total_cost)}`}
															</p>
														)}
														<CollapsibleContent>
															<div className="mt-3 overflow-x-auto">
																<table className="w-full text-xs">
																	<thead>
																		<tr className="border-b">
																			<th className="text-left py-2 pr-2 font-medium text-muted-foreground">
																				Provider
																			</th>
																			<th className="text-left py-2 pr-2 font-medium text-muted-foreground">
																				Model
																			</th>
																			<th className="text-right py-2 pr-2 font-medium text-muted-foreground">
																				In
																			</th>
																			<th className="text-right py-2 pr-2 font-medium text-muted-foreground">
																				Out
																			</th>
																			<th className="text-right py-2 pr-2 font-medium text-muted-foreground">
																				Cost
																			</th>
																			<th className="text-right py-2 font-medium text-muted-foreground">
																				Time
																			</th>
																		</tr>
																	</thead>
																	<tbody>
																		{(
																			execution.ai_usage as AIUsagePublicSimple[]
																		).map(
																			(
																				usage,
																				index,
																			) => (
																				<tr
																					key={
																						index
																					}
																					className="border-b last:border-0"
																				>
																					<td className="py-2 pr-2 capitalize">
																						{
																							usage.provider
																						}
																					</td>
																					<td className="py-2 pr-2 font-mono text-muted-foreground">
																						{usage
																							.model
																							.length >
																						20
																							? `${usage.model.substring(0, 18)}...`
																							: usage.model}
																					</td>
																					<td className="py-2 pr-2 text-right font-mono">
																						{formatNumber(
																							usage.input_tokens,
																						)}
																					</td>
																					<td className="py-2 pr-2 text-right font-mono">
																						{formatNumber(
																							usage.output_tokens,
																						)}
																					</td>
																					<td className="py-2 pr-2 text-right font-mono">
																						{formatCost(
																							usage.cost,
																						)}
																					</td>
																					<td className="py-2 text-right font-mono">
																						{formatDuration(
																							usage.duration_ms,
																						)}
																					</td>
																				</tr>
																			),
																		)}
																	</tbody>
																	{execution.ai_totals && (
																		<tfoot>
																			<tr className="bg-muted/50 font-medium">
																				<td
																					colSpan={
																						2
																					}
																					className="py-2 pr-2"
																				>
																					Total
																				</td>
																				<td className="py-2 pr-2 text-right font-mono">
																					{formatNumber(
																						execution
																							.ai_totals
																							.total_input_tokens,
																					)}
																				</td>
																				<td className="py-2 pr-2 text-right font-mono">
																					{formatNumber(
																						execution
																							.ai_totals
																							.total_output_tokens,
																					)}
																				</td>
																				<td className="py-2 pr-2 text-right font-mono">
																					{formatCost(
																						execution
																							.ai_totals
																							.total_cost,
																					)}
																				</td>
																				<td className="py-2 text-right font-mono">
																					{formatDuration(
																						execution
																							.ai_totals
																							.total_duration_ms,
																					)}
																				</td>
																			</tr>
																		</tfoot>
																	)}
																</table>
															</div>
														</CollapsibleContent>
													</Collapsible>
												)}
										</CardContent>
									</Card>
								</motion.div>
							)}
					</div>
				</div>
			</div>

			{/* Cancel Confirmation Dialog */}
			<AlertDialog
				open={showCancelDialog}
				onOpenChange={setShowCancelDialog}
			>
				<AlertDialogContent>
					<AlertDialogHeader>
						<AlertDialogTitle>Cancel Execution?</AlertDialogTitle>
						<AlertDialogDescription>
							Are you sure you want to cancel the execution of{" "}
							<span className="font-semibold">
								{execution.workflow_name}
							</span>
							? This action cannot be undone.
						</AlertDialogDescription>
					</AlertDialogHeader>
					<AlertDialogFooter>
						<AlertDialogCancel>No, keep running</AlertDialogCancel>
						<AlertDialogAction
							onClick={handleCancelExecution}
							className="bg-destructive hover:bg-destructive/90"
						>
							Yes, cancel execution
						</AlertDialogAction>
					</AlertDialogFooter>
				</AlertDialogContent>
			</AlertDialog>

			{/* Rerun Confirmation Dialog */}
			<AlertDialog
				open={showRerunDialog}
				onOpenChange={setShowRerunDialog}
			>
				<AlertDialogContent>
					<AlertDialogHeader>
						<AlertDialogTitle>Rerun Workflow?</AlertDialogTitle>
						<AlertDialogDescription>
							This will execute{" "}
							<span className="font-semibold">
								{execution.workflow_name}
							</span>{" "}
							again with the same input parameters. You will be
							redirected to the new execution.
						</AlertDialogDescription>
					</AlertDialogHeader>
					<AlertDialogFooter>
						<AlertDialogCancel disabled={isRerunning}>
							Cancel
						</AlertDialogCancel>
						<AlertDialogAction
							onClick={handleRerunExecution}
							disabled={isRerunning}
						>
							{isRerunning ? (
								<>
									<Loader2 className="mr-2 h-4 w-4 animate-spin" />
									Rerunning...
								</>
							) : (
								"Yes, rerun workflow"
							)}
						</AlertDialogAction>
					</AlertDialogFooter>
				</AlertDialogContent>
			</AlertDialog>
		</div>
	);
}
