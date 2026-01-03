/**
 * Workflow Execution Hook with WebSocket Subscription
 *
 * Combines workflow API execution with real-time WebSocket updates.
 * Unlike the basic useExecuteWorkflow hook, this hook:
 * - Subscribes to execution updates via WebSocket
 * - Waits for actual completion before resolving
 * - Tracks active executions for loading indicators
 * - Handles timeouts and cleanup
 */

import { useState, useCallback, useRef, useEffect } from "react";
import { useExecuteWorkflow } from "@/hooks/useWorkflows";
import { webSocketService, type ExecutionUpdate } from "@/services/websocket";
import type { WorkflowResult } from "@/lib/app-builder-types";

const DEFAULT_TIMEOUT = 5 * 60 * 1000; // 5 minutes

interface UseWorkflowExecutionOptions {
	/** Timeout in milliseconds (default: 5 minutes) */
	timeout?: number;
	/** Called when a workflow execution starts */
	onExecutionStart?: (executionId: string, workflowName: string) => void;
	/** Called when a workflow execution completes (success or failure) */
	onExecutionComplete?: (executionId: string, result: WorkflowResult) => void;
}

interface ExecutionTracker {
	executionId: string;
	workflowId: string;
	workflowName: string;
	startedAt: number;
	resolve: (result: WorkflowResult) => void;
	reject: (error: Error) => void;
	timeoutId: ReturnType<typeof setTimeout>;
	unsubscribe: () => void;
}

interface UseWorkflowExecutionReturn {
	/** Execute a workflow and wait for completion */
	executeWorkflow: (
		workflowId: string,
		params: Record<string, unknown>,
	) => Promise<WorkflowResult>;
	/** List of currently executing workflow execution IDs */
	activeExecutionIds: string[];
	/** Whether any workflow is currently executing */
	isExecuting: boolean;
	/** Map of execution ID to workflow name for display */
	activeWorkflowNames: Map<string, string>;
}

/**
 * Check if a status indicates the execution is complete
 */
function isCompleteStatus(status: string): boolean {
	return [
		"Success",
		"Failed",
		"CompletedWithErrors",
		"Timeout",
		"Cancelled",
	].includes(status);
}

/**
 * Map API status to WorkflowResult status
 */
function mapStatus(apiStatus: string): WorkflowResult["status"] {
	switch (apiStatus) {
		case "Success":
		case "CompletedWithErrors":
			return "completed";
		case "Failed":
		case "Timeout":
		case "Cancelled":
			return "failed";
		case "Running":
		case "Cancelling":
			return "running";
		default:
			return "pending";
	}
}

/**
 * Hook for executing workflows with real-time result subscription
 *
 * @example
 * const { executeWorkflow, isExecuting, activeExecutionIds } = useWorkflowExecution({
 *   onExecutionComplete: (id, result) => {
 *     if (result.status === "completed") {
 *       toast.success("Workflow completed!");
 *     }
 *   },
 * });
 *
 * // Execute and wait for completion
 * const result = await executeWorkflow("my-workflow-id", { param1: "value" });
 * console.log(result.result); // Actual workflow output
 */
export function useWorkflowExecution(
	options: UseWorkflowExecutionOptions = {},
): UseWorkflowExecutionReturn {
	const {
		timeout = DEFAULT_TIMEOUT,
		onExecutionStart,
		onExecutionComplete,
	} = options;
	const executeWorkflowMutation = useExecuteWorkflow();

	// Track active executions
	const activeExecutionsRef = useRef<Map<string, ExecutionTracker>>(
		new Map(),
	);
	const [activeExecutionIds, setActiveExecutionIds] = useState<string[]>([]);
	const [activeWorkflowNames, setActiveWorkflowNames] = useState<
		Map<string, string>
	>(new Map());

	// Update state arrays from ref
	const updateActiveState = useCallback(() => {
		const ids = Array.from(activeExecutionsRef.current.keys());
		const names = new Map<string, string>();
		activeExecutionsRef.current.forEach((tracker, id) => {
			names.set(id, tracker.workflowName);
		});
		setActiveExecutionIds(ids);
		setActiveWorkflowNames(names);
	}, []);

	// Cleanup on unmount
	useEffect(() => {
		const executions = activeExecutionsRef.current;
		return () => {
			executions.forEach((tracker) => {
				clearTimeout(tracker.timeoutId);
				tracker.unsubscribe();
				webSocketService.unsubscribe(
					`execution:${tracker.executionId}`,
				);
			});
		};
	}, []);

	const executeWorkflow = useCallback(
		async (
			workflowId: string,
			params: Record<string, unknown>,
		): Promise<WorkflowResult> => {
			// 1. Start the workflow via API
			const response = await executeWorkflowMutation.mutateAsync({
				body: {
					workflow_id: workflowId,
					input_data: params,
					form_id: null,
					transient: false,
					code: null,
					script_name: null,
				},
			});

			const executionId = response.execution_id;
			const workflowName = response.workflow_name ?? workflowId;

			// 2. Check if already complete (synchronous execution)
			const initialStatus = response.status;
			if (isCompleteStatus(initialStatus)) {
				const result: WorkflowResult = {
					executionId,
					workflowId: response.workflow_id ?? workflowId,
					workflowName,
					status: mapStatus(initialStatus),
					result: response.result ?? undefined,
					error: response.error ?? undefined,
				};
				onExecutionComplete?.(executionId, result);
				return result;
			}

			// 3. Create promise that resolves on WebSocket completion
			return new Promise<WorkflowResult>((resolve, reject) => {
				const channel = `execution:${executionId}`;

				// Setup timeout
				const timeoutId = setTimeout(() => {
					const tracker =
						activeExecutionsRef.current.get(executionId);
					if (tracker) {
						tracker.unsubscribe();
						webSocketService.unsubscribe(channel);
						activeExecutionsRef.current.delete(executionId);
						updateActiveState();

						const timeoutResult: WorkflowResult = {
							executionId,
							workflowId,
							workflowName,
							status: "failed",
							error: `Workflow execution timed out after ${timeout / 1000} seconds`,
						};
						onExecutionComplete?.(executionId, timeoutResult);
						reject(new Error(timeoutResult.error));
					}
				}, timeout);

				// Store tracker IMMEDIATELY so buttons can show loading state
				// This happens before WebSocket connects to avoid race conditions
				activeExecutionsRef.current.set(executionId, {
					executionId,
					workflowId,
					workflowName,
					startedAt: Date.now(),
					resolve,
					reject,
					timeoutId,
					unsubscribe: () => {}, // Placeholder until WebSocket connects
				});
				updateActiveState();
				onExecutionStart?.(executionId, workflowName);

				// Connect to WebSocket and subscribe
				webSocketService
					.connect([channel])
					.then(() => {
						const unsubscribe = webSocketService.onExecutionUpdate(
							executionId,
							(update: ExecutionUpdate) => {
								// Check if execution is complete
								if (
									update.isComplete ||
									isCompleteStatus(update.status)
								) {
									const tracker =
										activeExecutionsRef.current.get(
											executionId,
										);
									if (tracker) {
										clearTimeout(tracker.timeoutId);
										tracker.unsubscribe();
										webSocketService.unsubscribe(channel);
										activeExecutionsRef.current.delete(
											executionId,
										);
										updateActiveState();

										const result: WorkflowResult = {
											executionId,
											workflowId,
											workflowName,
											status: mapStatus(update.status),
											result: update.result,
											error: update.error,
										};

										onExecutionComplete?.(
											executionId,
											result,
										);
										resolve(result);
									}
								}
							},
						);

						// Update tracker with real unsubscribe function
						const tracker =
							activeExecutionsRef.current.get(executionId);
						if (tracker) {
							tracker.unsubscribe = unsubscribe;
						}
					})
					.catch((error) => {
						// WebSocket connection failed - remove from active
						activeExecutionsRef.current.delete(executionId);
						updateActiveState();
						clearTimeout(timeoutId);
						const result: WorkflowResult = {
							executionId,
							workflowId,
							workflowName,
							status: "pending",
							error: `Failed to connect to execution stream: ${error instanceof Error ? error.message : String(error)}`,
						};
						onExecutionComplete?.(executionId, result);
						resolve(result);
					});
			});
		},
		[
			executeWorkflowMutation,
			timeout,
			onExecutionStart,
			onExecutionComplete,
			updateActiveState,
		],
	);

	return {
		executeWorkflow,
		activeExecutionIds,
		isExecuting: activeExecutionIds.length > 0,
		activeWorkflowNames,
	};
}

export default useWorkflowExecution;
