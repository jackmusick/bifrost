import { useState, useEffect, useRef, useCallback } from "react";
import {
	Play,
	Loader2,
	Workflow,
	Database,
	FileCode,
	AlertCircle,
	ChevronDown,
	ChevronRight,
	CheckCircle,
} from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { useEditorStore } from "@/stores/editorStore";
import { useWorkflowsMetadata, useExecuteWorkflow } from "@/hooks/useWorkflows";
import { useExecutionStream } from "@/hooks/useExecutionStream";
import { useExecutionStreamStore } from "@/stores/executionStreamStore";
import { useScopeStore } from "@/stores/scopeStore";
import { WorkflowParametersForm } from "@/components/workflows/WorkflowParametersForm";
import { VariablesTreeView } from "@/components/ui/variables-tree-view";
import { toast } from "sonner";
import { getExecutionVariables } from "@/hooks/useExecutions";
import { validateWorkflow } from "@/hooks/useWorkflows";
import type { components } from "@/lib/v1";

type WorkflowMetadata = components["schemas"]["WorkflowMetadata"];
type DataProviderMetadata = components["schemas"]["DataProviderMetadata"];
type WorkflowExecutionResponse =
	components["schemas"]["WorkflowExecutionResponse"];
type WorkflowValidationResponse =
	components["schemas"]["WorkflowValidationResponse"];
type ValidationIssue = components["schemas"]["ValidationIssue"];

// Log entry type from execution response
interface LogEntry {
	level: string;
	message: string;
	timestamp: string;
	source: string;
}

/**
 * Run panel for executing workflows, data providers, and scripts
 * Shows detected file type and appropriate inputs
 */
export function RunPanel() {
	// Track render count for debugging
	const renderCountRef = useRef(0);
	renderCountRef.current += 1;

	const queryClient = useQueryClient();
	const orgId = useScopeStore((state) => state.scope.orgId);

	const tabs = useEditorStore((state) => state.tabs);
	const activeTabIndex = useEditorStore((state) => state.activeTabIndex);
	const appendTerminalOutput = useEditorStore(
		(state) => state.appendTerminalOutput,
	);
	const setCurrentStreamingExecutionId = useEditorStore(
		(state) => state.setCurrentStreamingExecutionId,
	);

	// Compute active tab from state
	const activeTab =
		activeTabIndex >= 0 && activeTabIndex < tabs.length
			? tabs[activeTabIndex]
			: null;

	const openFile = activeTab?.file || null;
	const fileContent = activeTab?.content || "";

	const { data: metadata, isLoading: isLoadingMetadata } =
		useWorkflowsMetadata() as {
			data?: {
				workflows?: WorkflowMetadata[];
				dataProviders?: DataProviderMetadata[];
			};
			isLoading: boolean;
		};
	const executeWorkflow = useExecuteWorkflow();
	const [isExecuting, setIsExecuting] = useState(false);
	const [isValidating, setIsValidating] = useState(false);
	const [currentExecutionId, setCurrentExecutionId] = useState<string | null>(
		null,
	);
	const [variablesExpanded, setVariablesExpanded] = useState(true);
	const [lastExecutionVariables, setLastExecutionVariables] = useState<
		Record<string, unknown>
	>({});

	const [detectedItem, setDetectedItem] = useState<{
		type: "workflow" | "data_provider" | "script" | null;
		metadata?: WorkflowMetadata | DataProviderMetadata;
	}>({ type: null });
	const firstInputRef = useRef<HTMLInputElement>(null);

	// Get stream state and actions from store
	const streamState = useExecutionStreamStore((state) =>
		currentExecutionId ? state.streams[currentExecutionId] : undefined,
	);

	const clearStream = useExecutionStreamStore((state) => state.clearStream);

	// Use streaming logs as the source of truth for loading state
	const isLoading =
		(streamState?.streamingLogs?.length ?? 0) > 0 || isExecuting;

	// Wrap onComplete in useCallback to prevent infinite loop
	// Without this, onComplete is recreated on every render, triggering useExecutionStream effect
	const handleStreamComplete = useCallback(async (executionId: string) => {
		// Fetch variables when execution completes
		try {
			const variablesData = await getExecutionVariables(executionId);
			setLastExecutionVariables(
				(variablesData || {}) as Record<string, unknown>,
			);
		} catch (error) {
			console.error("Failed to fetch variables:", error);
		}
	}, []); // Empty deps - this function is stable

	// Stream real-time logs for the current execution
	useExecutionStream({
		executionId: currentExecutionId || "",
		enabled: !!currentExecutionId,
		onComplete: handleStreamComplete,
	});

	// When execution completes, move streaming logs to terminal output
	useEffect(() => {
		if (streamState?.isComplete && currentExecutionId) {
			// Helper to get completion message and level based on status
			const getCompletionMessage = (
				status: string,
				executionId: string,
			) => {
				const link = `[View Details](/history/${executionId})`;
				switch (status) {
					case "Success":
						return {
							message: `✓ Execution completed successfully: ${link}`,
							level: "SUCCESS",
						};
					case "Failed":
						return {
							message: `✗ Execution failed: ${link}`,
							level: "ERROR",
						};
					case "CompletedWithErrors":
						return {
							message: `⚠ Execution completed with errors: ${link}`,
							level: "WARNING",
						};
					case "Timeout":
						return {
							message: `✗ Execution timed out: ${link}`,
							level: "ERROR",
						};
					case "Cancelled":
						return {
							message: `✗ Execution cancelled: ${link}`,
							level: "WARNING",
						};
					default:
						return {
							message: `Execution completed with status: ${status} - ${link}`,
							level: "INFO",
						};
				}
			};

			const completion = getCompletionMessage(
				streamState.status || "Unknown",
				currentExecutionId,
			);

			// Append logs + completion message to terminal output
			appendTerminalOutput({
				executionId: currentExecutionId,
				loggerOutput: [
					...(streamState.streamingLogs || []).map((log) => ({
						level: log.level,
						message: log.message,
						timestamp: log.timestamp,
						source: "stream",
					})),
					{
						level: completion.level,
						message: completion.message,
						timestamp: new Date().toISOString(),
						source: "system",
					},
				],
				variables: {},
				status: streamState.status || "Unknown",
				error: undefined,
			});

			// Show completion toast based on status
			if (streamState.status === "Success") {
				toast.success("Workflow completed successfully");
			} else if (streamState.status === "Failed") {
				toast.error("Workflow execution failed");
			}

			// Clear execution state
			const executionId = currentExecutionId;
			setCurrentExecutionId(null);
			setCurrentStreamingExecutionId(null);
			setIsExecuting(false);

			// Clean up stream from store
			if (executionId) {
				clearStream(executionId);
			}
		}
		// Only depend on isComplete and currentExecutionId - we don't want to re-run when logs change
		// eslint-disable-next-line react-hooks/exhaustive-deps
	}, [streamState?.isComplete, currentExecutionId]);

	// Detect file type when file or metadata changes
	// First check is_workflow/is_data_provider flags from file metadata (fast path)
	// Then fall back to matching against workflow/data_provider metadata for full details
	useEffect(() => {
		if (!openFile || !openFile.name.endsWith(".py")) {
			setDetectedItem({ type: null });
			return;
		}

		// Fast path: Check is_workflow flag from file metadata
		if (openFile.is_workflow) {
			// Look up full workflow metadata for parameters
			const workflow = metadata?.workflows?.find(
				(w: WorkflowMetadata) =>
					w.relative_file_path === openFile.path ||
					w.source_file_path?.endsWith(openFile.path),
			);
			// Set as workflow with metadata if found, or without if still loading
			setDetectedItem({ type: "workflow", metadata: workflow });
			return;
		}

		// Fast path: Check is_data_provider flag from file metadata
		if (openFile.is_data_provider) {
			const dataProvider = metadata?.dataProviders?.find(
				(dp: DataProviderMetadata) =>
					dp.source_file_path?.endsWith(openFile.path),
			);
			// Set as data_provider with metadata if found, or without if still loading
			setDetectedItem({ type: "data_provider", metadata: dataProvider });
			return;
		}

		// Slow path: File doesn't have flags set, check metadata (for backwards compat)
		if (metadata) {
			const workflow = metadata.workflows?.find(
				(w: WorkflowMetadata) =>
					w.relative_file_path === openFile.path ||
					w.source_file_path?.endsWith(openFile.path),
			);
			if (workflow) {
				setDetectedItem({ type: "workflow", metadata: workflow });
				return;
			}

			const dataProvider = metadata.dataProviders?.find(
				(dp: DataProviderMetadata) =>
					dp.source_file_path?.endsWith(openFile.path),
			);
			if (dataProvider) {
				setDetectedItem({
					type: "data_provider",
					metadata: dataProvider,
				});
				return;
			}
		}

		// Otherwise it's a regular script
		setDetectedItem({ type: "script" });
	}, [openFile, metadata]);

	const handleExecuteWorkflow = async (params: Record<string, unknown>) => {
		if (detectedItem.type !== "workflow" || !detectedItem.metadata) return;

		performance.mark("workflow-execute-start");

		setIsExecuting(true);
		setLastExecutionVariables({}); // Clear variables on new execution
		try {
			const result = (await executeWorkflow.mutateAsync({
				body: {
					workflow_id: (detectedItem.metadata as WorkflowMetadata).id,
					input_data: params,
					form_id: null,
					transient: true, // Editor executions are transient (no DB writes)
					code: null,
					script_name: null,
				},
			})) as WorkflowExecutionResponse;

			performance.mark("workflow-execute-end");
			performance.measure(
				"workflow-execute",
				"workflow-execute-start",
				"workflow-execute-end",
			);

			// For synchronous executions, logs come back immediately in the response
			// Display them directly instead of waiting for streaming
			if (result.logs && result.logs.length > 0) {
				appendTerminalOutput({
					loggerOutput: result.logs.map(
						(log: Record<string, unknown>) => {
							const logEntry: LogEntry = {
								level: String(log["level"] || "INFO"),
								message: String(log["message"] || ""),
								timestamp: log["timestamp"]
									? String(log["timestamp"])
									: new Date().toISOString(),
								source: String(log["source"] || "workflow"),
							};
							return logEntry;
						},
					),
					variables: {},
					status: result.status || "Unknown",
					error: result.error || undefined,
				});
				// Set variables directly for synchronous execution
				setLastExecutionVariables(
					(result.variables as Record<string, unknown>) || {},
				);
				// Synchronous execution - done immediately
				setIsExecuting(false);

				// Show completion toast for sync execution
				if (result.status === "Success") {
					toast.success("Workflow executed successfully");
				} else if (result.status === "Failed") {
					toast.error("Workflow execution failed", {
						description: result.error || undefined,
					});
				}
			} else {
				// No immediate logs - this is an async execution
				// Enable streaming for this execution
				// Keep isExecuting true - it will be cleared when streaming completes

				// Initialize the stream in the store and add "started" message
				const store = useExecutionStreamStore.getState();
				store.startStreaming(result.execution_id, "Running");
				store.appendLog(result.execution_id, {
					level: "INFO",
					message: `Workflow execution started: [View Details](/history/${result.execution_id})`,
					timestamp: new Date().toISOString(),
				});

				// Set execution ID to trigger useExecutionStream hook
				setCurrentExecutionId(result.execution_id);
				setCurrentStreamingExecutionId(result.execution_id);
			}
		} catch (error) {
			// On error, clear executing state
			setIsExecuting(false);
			throw error;
		}
	};

	const handleExecuteScript = useCallback(async () => {
		if (!openFile || !fileContent) {
			toast.error("No file content to execute");
			return;
		}

		// Get filename without extension to use as identifier
		const fileName = openFile.name.replace(".py", "");

		setIsExecuting(true);
		setLastExecutionVariables({}); // Clear variables on new execution
		try {
			// Encode file content as base64
			const codeBase64 = btoa(fileContent);

			// Execute script via workflow API with transient flag and code
			const result = (await executeWorkflow.mutateAsync({
				body: {
					workflow_id: null,
					input_data: {},
					form_id: null,
					transient: true, // Editor executions are transient (no DB writes)
					code: codeBase64, // Base64-encoded script content
					script_name: fileName, // Script identifier for logging
				},
			})) as WorkflowExecutionResponse;

			// For synchronous executions, logs come back immediately in the response
			// Display them directly instead of waiting for streaming
			if (result.logs && result.logs.length > 0) {
				appendTerminalOutput({
					loggerOutput: result.logs.map(
						(log: Record<string, unknown>) => {
							const logEntry: LogEntry = {
								level: String(log["level"] || "INFO"),
								message: String(log["message"] || ""),
								timestamp: log["timestamp"]
									? String(log["timestamp"])
									: new Date().toISOString(),
								source: String(log["source"] || "script"),
							};
							return logEntry;
						},
					),
					variables: {},
					status: result.status || "Unknown",
					error: result.error || undefined,
				});
				// Set variables directly for synchronous execution
				setLastExecutionVariables(
					(result.variables as Record<string, unknown>) || {},
				);
				// Synchronous execution - done immediately
				setIsExecuting(false);

				// Show completion toast for sync execution
				if (result.status === "Success") {
					toast.success("Script executed successfully", {
						description: result.duration_ms
							? `Completed in ${result.duration_ms}ms`
							: undefined,
					});
				} else {
					toast.error("Script execution failed", {
						description: result.error || "Unknown error",
					});
				}
			} else {
				// No immediate logs - this is an async execution
				// Enable streaming for this execution
				// Keep isExecuting true - it will be cleared when streaming completes

				// Initialize the stream in the store and add "started" message
				const store = useExecutionStreamStore.getState();
				store.startStreaming(result.execution_id, "Running");
				store.appendLog(result.execution_id, {
					level: "INFO",
					message: `Script execution started (ID: ${result.execution_id})`,
					timestamp: new Date().toISOString(),
				});

				// Set execution ID to trigger useExecutionStream hook
				setCurrentExecutionId(result.execution_id);
				setCurrentStreamingExecutionId(result.execution_id);
			}
		} catch (error) {
			// On error, clear executing state
			setIsExecuting(false);
			toast.error("Failed to execute script", {
				description:
					error instanceof Error ? error.message : String(error),
			});
		}
	}, [
		openFile,
		fileContent,
		executeWorkflow,
		appendTerminalOutput,
		setCurrentStreamingExecutionId,
	]);

	const handleValidateWorkflow = useCallback(async () => {
		if (!openFile || !fileContent) {
			toast.error("No file to validate");
			return;
		}

		setIsValidating(true);
		try {
			// Call validation API
			const result = (await validateWorkflow(
				openFile.path,
				fileContent,
			)) as WorkflowValidationResponse;

			// Build terminal output based on validation results
			const logs: LogEntry[] = [];

			if (result.valid) {
				// Success - workflow is valid
				logs.push({
					level: "SUCCESS",
					message: `✓ Workflow validation passed: ${result.metadata?.name || openFile.name}`,
					source: "validation",
					timestamp: new Date().toISOString(),
				});

				if (result.metadata) {
					logs.push({
						level: "INFO",
						message: `  Description: ${result.metadata.description}`,
						source: "validation",
						timestamp: new Date().toISOString(),
					});

					if (
						result.metadata.parameters &&
						result.metadata.parameters.length > 0
					) {
						logs.push({
							level: "INFO",
							message: `  Parameters: ${result.metadata.parameters.length}`,
							source: "validation",
							timestamp: new Date().toISOString(),
						});
					}

					if (result.metadata.category) {
						logs.push({
							level: "INFO",
							message: `  Category: ${result.metadata.category}`,
							source: "validation",
							timestamp: new Date().toISOString(),
						});
					}
				}

				// Show warnings if any
				const warnings = (result.issues || []).filter(
					(i: ValidationIssue) => i.severity === "warning",
				);
				if (warnings.length > 0) {
					logs.push({
						level: "WARNING",
						message: `⚠ ${warnings.length} warning(s):`,
						source: "validation",
						timestamp: new Date().toISOString(),
					});
					warnings.forEach((warning: ValidationIssue) => {
						logs.push({
							level: "WARNING",
							message: `  ${warning.message}`,
							source: "validation",
							timestamp: new Date().toISOString(),
						});
					});
				}

				toast.success("Workflow is valid!");

				// Invalidate workflows metadata to trigger refetch and update the Run panel
				await queryClient.invalidateQueries({
					queryKey: ["workflows", "metadata", orgId],
				});
			} else {
				// Failed validation - show errors
				logs.push({
					level: "ERROR",
					message: `✗ Workflow validation failed for ${openFile.name}`,
					source: "validation",
					timestamp: new Date().toISOString(),
				});

				const errors = (result.issues || []).filter(
					(i: ValidationIssue) => i.severity === "error",
				);
				errors.forEach((error: ValidationIssue) => {
					const lineInfo = error.line ? `[Line ${error.line}] ` : "";
					logs.push({
						level: "ERROR",
						message: `  ${lineInfo}${error.message}`,
						source: "validation",
						timestamp: new Date().toISOString(),
					});
				});

				toast.error("Workflow validation failed", {
					description: `${errors.length} error(s) found`,
				});
			}

			// Append validation results to terminal
			appendTerminalOutput({
				loggerOutput: logs,
				variables: {},
				status: result.valid ? "Success" : "Failed",
				executionId: `validation-${Date.now()}`,
				error: result.valid ? undefined : "Validation failed",
			});
		} catch (error) {
			setIsValidating(false);
			toast.error("Failed to validate workflow", {
				description:
					error instanceof Error ? error.message : String(error),
			});
		} finally {
			setIsValidating(false);
		}
	}, [openFile, fileContent, appendTerminalOutput, queryClient, orgId]);

	// Listen for execute-editor-file event (dispatched after panel switch)
	useEffect(() => {
		const handleExecuteEvent = () => {
			// Check if there are parameters
			const hasParameters =
				detectedItem.type === "workflow" &&
				detectedItem.metadata &&
				(detectedItem.metadata as WorkflowMetadata)?.parameters &&
				((detectedItem.metadata as WorkflowMetadata)?.parameters
					?.length ?? 0) > 0;

			if (hasParameters && firstInputRef.current) {
				// Focus first input if there are parameters
				setTimeout(() => firstInputRef.current?.focus(), 50);
			} else if (detectedItem.type === "script") {
				// Execute script immediately if no parameters
				handleExecuteScript();
			}
		};

		window.addEventListener("execute-editor-file", handleExecuteEvent);
		return () => {
			window.removeEventListener(
				"execute-editor-file",
				handleExecuteEvent,
			);
		};
	}, [detectedItem, handleExecuteScript]);

	// No file open
	if (!openFile) {
		return (
			<div className="flex h-full flex-col items-center justify-center text-center">
				<FileCode className="h-12 w-12 mb-3 text-muted-foreground" />
				<p className="text-sm text-muted-foreground">
					Open a Python file to run it
				</p>
			</div>
		);
	}

	// Not a Python file
	if (!openFile.name.endsWith(".py")) {
		return (
			<div className="flex h-full flex-col items-center justify-center text-center">
				<AlertCircle className="h-12 w-12 mb-3 text-muted-foreground" />
				<p className="text-sm text-muted-foreground">
					Only Python files can be executed
				</p>
			</div>
		);
	}

	// Loading metadata
	if (isLoadingMetadata) {
		return (
			<div className="flex h-full flex-col items-center justify-center">
				<Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
				<p className="text-sm text-muted-foreground mt-3">
					Detecting file type...
				</p>
			</div>
		);
	}

	// Render based on detected type
	return (
		<div className="flex h-full flex-col">
			{/* Content */}
			<div className="flex-1 overflow-auto">
				{detectedItem.type === "workflow" && (
					<>
						<div className="border-b px-3 py-2">
							<div className="flex items-center gap-2">
								<Workflow className="h-4 w-4 text-primary" />
								<div className="flex-1">
									<h3 className="text-sm font-semibold">
										Workflow
									</h3>
									<p className="text-xs text-muted-foreground">
										{openFile.name}
									</p>
								</div>
							</div>
							{detectedItem.metadata?.description && (
								<p className="text-xs text-muted-foreground mt-2">
									{detectedItem.metadata.description}
								</p>
							)}
						</div>
						<div className="p-3">
							<WorkflowParametersForm
								parameters={
									(detectedItem.metadata as WorkflowMetadata)
										?.parameters || []
								}
								onExecute={handleExecuteWorkflow}
								isExecuting={isLoading}
								executeButtonText="Run Workflow"
							/>
						</div>

						{/* Variables Section - show from last execution */}
						{Object.keys(lastExecutionVariables).length > 0 && (
							<div className="border-t">
								<button
									onClick={() =>
										setVariablesExpanded(!variablesExpanded)
									}
									className="w-full flex items-center justify-between px-4 py-2 hover:bg-muted/50 transition-colors"
								>
									<span className="text-sm font-medium">
										VARIABLES
									</span>
									{variablesExpanded ? (
										<ChevronDown className="h-4 w-4 text-muted-foreground" />
									) : (
										<ChevronRight className="h-4 w-4 text-muted-foreground" />
									)}
								</button>
								{variablesExpanded && (
									<div className="py-2 px-3 overflow-x-auto">
										<VariablesTreeView
											data={lastExecutionVariables}
										/>
									</div>
								)}
							</div>
						)}
					</>
				)}

				{detectedItem.type === "data_provider" && (
					<>
						<div className="border-b px-3 py-2">
							<div className="flex items-center gap-2">
								<Database className="h-4 w-4 text-primary" />
								<div className="flex-1">
									<h3 className="text-sm font-semibold">
										Data Provider
									</h3>
									<p className="text-xs text-muted-foreground">
										{detectedItem.metadata?.name ||
											openFile.name}
									</p>
								</div>
							</div>
							{detectedItem.metadata?.description && (
								<p className="text-xs text-muted-foreground mt-2">
									{detectedItem.metadata.description}
								</p>
							)}
						</div>
						<div className="p-3 space-y-3">
							<div className="rounded-lg border border-border/50 bg-muted/30 p-3">
								<div className="flex items-start gap-2">
									<Database className="h-4 w-4 text-muted-foreground mt-0.5 flex-shrink-0" />
									<div className="flex-1 min-w-0 text-xs text-muted-foreground">
										<p className="font-medium mb-1">
											Test via Forms
										</p>
										<p>
											Data providers can be tested through
											the Forms interface where they're
											used as dynamic dropdown options.
										</p>
									</div>
								</div>
							</div>

							{/* Show parameters if any */}
							{detectedItem.metadata?.parameters &&
								detectedItem.metadata.parameters.length > 0 && (
									<div className="space-y-2">
										<p className="text-xs font-medium text-muted-foreground">
											Parameters:
										</p>
										<div className="space-y-1.5">
											{detectedItem.metadata.parameters.map(
												(param) => (
													<div
														key={
															param.name ??
															"param"
														}
														className="text-xs pl-3 border-l-2 border-border"
													>
														<span className="font-mono font-medium">
															{param.name}
														</span>
														<span className="text-muted-foreground ml-2">
															({param.type})
														</span>
														{param.required && (
															<span className="text-destructive ml-1">
																*
															</span>
														)}
														{param.description && (
															<p className="text-muted-foreground mt-0.5">
																{
																	param.description
																}
															</p>
														)}
													</div>
												),
											)}
										</div>
									</div>
								)}
						</div>
					</>
				)}

				{detectedItem.type === "script" && (
					<>
						<div className="m-3 mb-0">
							<div className="border rounded flex items-center gap-3 p-2 bg-muted/30">
								<button
									onClick={handleExecuteScript}
									disabled={isLoading}
									className="flex items-center justify-center w-8 h-8 bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50 disabled:pointer-events-none transition-colors"
								>
									{isLoading ? (
										<Loader2 className="h-4 w-4 animate-spin" />
									) : (
										<Play className="h-4 w-4" />
									)}
								</button>
								<button
									onClick={handleValidateWorkflow}
									disabled={isValidating}
									className="flex items-center justify-center w-8 h-8 bg-green-600 text-white hover:bg-green-700 disabled:opacity-50 disabled:pointer-events-none transition-colors"
									title="Validate Workflow"
								>
									{isValidating ? (
										<Loader2 className="h-4 w-4 animate-spin" />
									) : (
										<CheckCircle className="h-4 w-4" />
									)}
								</button>
								<div className="flex items-center gap-2 flex-1 min-w-0">
									<FileCode className="h-4 w-4 text-muted-foreground flex-shrink-0" />
									<div className="min-w-0">
										<h3 className="text-sm font-semibold">
											Script
										</h3>
										<p className="text-xs text-muted-foreground truncate">
											{openFile.name}
										</p>
									</div>
								</div>
							</div>
						</div>

						{/* Variables Section - show from last execution */}
						{Object.keys(lastExecutionVariables).length > 0 && (
							<div className="border-t">
								<button
									onClick={() =>
										setVariablesExpanded(!variablesExpanded)
									}
									className="w-full flex items-center justify-between px-4 py-2 hover:bg-muted/50 transition-colors"
								>
									<span className="text-sm font-medium">
										VARIABLES
									</span>
									{variablesExpanded ? (
										<ChevronDown className="h-4 w-4 text-muted-foreground" />
									) : (
										<ChevronRight className="h-4 w-4 text-muted-foreground" />
									)}
								</button>
								{variablesExpanded && (
									<div className="py-2 px-3 overflow-x-auto">
										<VariablesTreeView
											data={lastExecutionVariables}
										/>
									</div>
								)}
							</div>
						)}
					</>
				)}
			</div>
		</div>
	);
}
