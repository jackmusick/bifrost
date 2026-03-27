import { useParams, useNavigate, useLocation } from "react-router-dom";
import { motion } from "framer-motion";
import {
	ArrowLeft,
	XCircle,
	Loader2,
	Code2,
	RefreshCw,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { PageLoader } from "@/components/PageLoader";
import { useExecution, cancelExecution } from "@/hooks/useExecutions";
import { useAuth } from "@/contexts/AuthContext";
import { executeWorkflowWithContext } from "@/hooks/useWorkflows";
import { useWorkflowsMetadata } from "@/hooks/useWorkflows";
import { useEditorStore } from "@/stores/editorStore";
import { fileService } from "@/services/fileService";
import { toast } from "sonner";
import { useExecutionStream } from "@/hooks/useExecutionStream";
import {
	useExecutionStreamStore,
	type StreamingLog,
} from "@/stores/executionStreamStore";
import {
	ExecutionResultPanel,
	ExecutionLogsPanel,
	ExecutionSidebar,
	ExecutionCancelDialog,
	ExecutionRerunDialog,
	type LogEntry,
} from "@/components/execution";
import type { components } from "@/lib/v1";
import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useState, useCallback } from "react";

type ExecutionStatus =
	| components["schemas"]["ExecutionStatus"]
	| "Cancelling"
	| "Cancelled";
type WorkflowExecution = components["schemas"]["WorkflowExecution"];
type WorkflowMetadata = components["schemas"]["WorkflowMetadata"];
type FileMetadata = components["schemas"]["FileMetadata"];
type WorkflowExecutionResponse =
	components["schemas"]["WorkflowExecutionResponse"];

// Type for metadata response from useWorkflowsMetadata hook
interface WorkflowsMetadataResponse {
	workflows: WorkflowMetadata[];
	dataProviders: unknown[];
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

/**
 * Merge API logs with streaming logs, deduplicating by sequence number.
 * API logs are the baseline; only keep streaming logs with sequence > max API sequence.
 */
function mergeLogsWithDedup(
	apiLogs: ExecutionLogEntry[],
	streamingLogs: StreamingLog[],
): ExecutionLogEntry[] {
	if (streamingLogs.length === 0) return apiLogs;
	if (apiLogs.length === 0) return streamingLogs as ExecutionLogEntry[];

	// Find the highest sequence in API logs — anything at or below is already covered
	const maxApiSeq = apiLogs.reduce(
		(max, log) => Math.max(max, log.sequence ?? -1),
		-1,
	);

	// Only keep streaming logs with sequence beyond what the API returned
	const newStreamingLogs = streamingLogs.filter(
		(log) => (log.sequence ?? -1) > maxApiSeq,
	);

	if (newStreamingLogs.length === 0) return apiLogs;
	return [...apiLogs, ...newStreamingLogs];
}

export function ExecutionDetails({
	executionId: propExecutionId,
	embedded = false,
}: ExecutionDetailsProps) {
	const { executionId: urlExecutionId } = useParams();
	const executionId = propExecutionId || urlExecutionId;
	const navigate = useNavigate();
	const location = useLocation();
	const { isPlatformAdmin, hasRole } = useAuth();
	const isEmbed = hasRole("EmbedUser");
	const queryClient = useQueryClient();

	// Check if we came from an execution trigger (has navigation state).
	// location.state persists across browser refreshes (React Router uses history.state),
	// so we clear it immediately after reading to prevent deferred-fetch on refresh.
	const [hasNavigationState] = useState(() => location.state != null);
	useEffect(() => {
		if (location.state != null) {
			navigate(location.pathname, { replace: true, state: null });
		}
	}, []); // eslint-disable-line react-hooks/exhaustive-deps -- clear once on mount

	// WebSocket streaming enabled state - starts enabled only for new executions from triggers
	const [signalrEnabled, setSignalrEnabled] = useState(false);

	// Fallback timer - enable fetch after 5s if WebSocket hasn't received updates
	const [fetchFallbackEnabled, setFetchFallbackEnabled] = useState(
		!hasNavigationState,
	);

	// Get streaming logs from store
	// Use stable selector to avoid infinite loops
	const streamState = useExecutionStreamStore((state) =>
		executionId ? state.streams[executionId] : undefined,
	);
	const streamingLogs = streamState?.streamingLogs ?? [];

	// Fallback timer effect - reset on ID change and set 5s fallback for navigation state
	useEffect(() => {
		// Reset fallback when execution ID changes (important for rerun navigation)
		setFetchFallbackEnabled(!hasNavigationState);

		// If we have navigation state (from trigger), wait 5s as fallback in case WebSocket fails
		if (hasNavigationState) {
			const timer = setTimeout(() => setFetchFallbackEnabled(true), 5000);
			return () => clearTimeout(timer);
		}
		// No timer needed for direct links - fetchFallbackEnabled is already true
		return undefined;
	}, [executionId, hasNavigationState]);

	// Determine if we should fetch from API
	// Fetch when:
	// - Stream received update (confirms DB write), OR
	// - Fallback timer expired (5s after navigation), OR
	// - No navigation state (direct link/refresh - fetch immediately!)
	const hasReceivedUpdate = streamState?.hasReceivedUpdate ?? false;
	const shouldFetchExecution = hasReceivedUpdate || fetchFallbackEnabled;

	// State for confirmation dialogs
	const [showCancelDialog, setShowCancelDialog] = useState(false);
	const [showRerunDialog, setShowRerunDialog] = useState(false);
	const [isRerunning, setIsRerunning] = useState(false);
	const [isOpeningInEditor, setIsOpeningInEditor] = useState(false);

	// Editor store actions
	const openFileInTab = useEditorStore((state) => state.openFileInTab);
	const openEditor = useEditorStore((state) => state.openEditor);
	const setSidebarPanel = useEditorStore((state) => state.setSidebarPanel);
	const minimizeEditor = useEditorStore((state) => state.minimizeEditor);

	// Fetch workflow metadata to get source file path
	const { data: metadataData } = useWorkflowsMetadata();
	const metadata = metadataData as WorkflowsMetadataResponse | undefined;

	// Wrap onComplete in useCallback to prevent infinite loop
	const handleStreamComplete = useCallback(() => {
		// Refetch full execution data when complete
		queryClient.invalidateQueries({
			queryKey: [
				"get",
				"/api/executions/{execution_id}",
				{ params: { path: { execution_id: executionId } } },
			],
		});
	}, [queryClient, executionId]);

	// Real-time updates via WebSocket (only for running/pending/cancelling executions)
	const { isConnected } = useExecutionStream({
		executionId: executionId || "",
		enabled: !!executionId && signalrEnabled,
		onComplete: handleStreamComplete,
	});

	// Fetch execution data - deferred until stream confirms DB write or fallback expires
	const {
		data: executionData,
		isLoading,
		error,
	} = useExecution(shouldFetchExecution ? executionId : undefined, {
		// Disable polling when WebSocket is connected AND execution is not complete
		// This prevents duplicate API calls while streaming
		disablePolling: isConnected && signalrEnabled,
	});

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

	// Enable WebSocket for running executions
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

	// Update execution status optimistically from stream
	// Only depend on status, not the entire streamState object, to avoid running
	// on every log message (which would trigger setQueryData unnecessarily)
	const streamStatus = streamState?.status;
	useEffect(() => {
		if (streamStatus && executionId) {
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
						status: streamStatus,
					};
				},
			);
		}
	}, [streamStatus, executionId, queryClient]);

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

	// Compute merged logs for the logs panel
	const mergedLogs = (() => {
		const existingLogs = (logsData as ExecutionLogEntry[]) || [];
		if (
			executionStatus === "Running" ||
			executionStatus === "Pending" ||
			executionStatus === "Cancelling"
		) {
			return mergeLogsWithDedup(existingLogs, streamingLogs);
		}
		return existingLogs;
	})();

	// Show "waiting" state when we came from trigger and haven't received data yet
	// This happens before shouldFetchExecution becomes true (waiting for WebSocket or 5s fallback)
	if (!shouldFetchExecution && !execution) {
		if (embedded) {
			return (
				<div className="flex items-center justify-center h-full p-8">
					<Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
				</div>
			);
		}
		return <PageLoader message="Waiting for execution to start..." />;
	}

	// Show loading state during initial load
	if (isLoading) {
		if (embedded) {
			return (
				<div className="flex items-center justify-center h-full p-8">
					<Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
				</div>
			);
		}
		return <PageLoader message="Loading execution details..." />;
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
			{!embedded && !isEmbed && (
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
								<ExecutionResultPanel
									result={resultData?.result}
									resultType={resultData?.result_type}
									workflowName={execution.workflow_name}
									isLoading={isLoadingResult}
								/>
							</motion.div>
						)}

						{/* Logs Section */}
						<motion.div
							initial={{ opacity: 0, y: 20 }}
							animate={{ opacity: 1, y: 0 }}
							transition={{ duration: 0.3, delay: 0.1 }}
						>
							<ExecutionLogsPanel
								logs={mergedLogs as LogEntry[]}
								streamingLogs={streamingLogs}
								status={executionStatus}
								isConnected={isConnected}
								isLoading={isLoadingLogs}
								isPlatformAdmin={isPlatformAdmin}
								maxHeight="70vh"
							/>
						</motion.div>
					</div>

					{/* Right Column - Sidebar (1/3 width) */}
					<ExecutionSidebar
						status={execution.status as ExecutionStatus}
						workflowName={execution.workflow_name}
						executedByName={execution.executed_by_name}
						orgName={execution.org_name}
						startedAt={execution.started_at}
						completedAt={execution.completed_at}
						inputData={execution.input_data}
						isComplete={isComplete}
						isPlatformAdmin={isPlatformAdmin}
						isLoading={isLoading}
						variablesData={variablesData}
						peakMemoryBytes={execution.peak_memory_bytes}
						cpuTotalSeconds={execution.cpu_total_seconds}
						durationMs={execution.duration_ms}
						aiUsage={execution.ai_usage}
						aiTotals={execution.ai_totals}
						streamState={streamState ? {
							queuePosition: streamState.queuePosition,
							waitReason: streamState.waitReason,
							availableMemoryMb: streamState.availableMemoryMb,
							requiredMemoryMb: streamState.requiredMemoryMb,
						} : undefined}
						errorMessage={execution.error_message}
						executionContext={execution.execution_context}
					/>
				</div>
			</div>

			{/* Cancel Confirmation Dialog */}
			<ExecutionCancelDialog
				open={showCancelDialog}
				onOpenChange={setShowCancelDialog}
				workflowName={execution.workflow_name}
				onConfirm={handleCancelExecution}
			/>

			{/* Rerun Confirmation Dialog */}
			<ExecutionRerunDialog
				open={showRerunDialog}
				onOpenChange={setShowRerunDialog}
				workflowName={execution.workflow_name}
				isRerunning={isRerunning}
				onConfirm={handleRerunExecution}
			/>
		</div>
	);
}
