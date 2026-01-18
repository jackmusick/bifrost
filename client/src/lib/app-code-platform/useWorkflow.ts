/**
 * Platform hook: useWorkflow
 *
 * React hook for executing workflows with real-time streaming updates.
 * Provides loading, error, completion states, streaming logs, and result.
 *
 * Composes existing infrastructure:
 * - executeWorkflow API call
 * - useExecutionStream WebSocket subscription
 * - useExecutionStreamStore for reactive state
 */

import { useState, useCallback, useRef } from "react";
import { apiClient } from "@/lib/api-client";
import { useExecutionStream } from "@/hooks/useExecutionStream";
import {
	useExecutionStreamStore,
	type ExecutionStatus,
	type StreamingLog,
} from "@/stores/executionStreamStore";
import { getExecution } from "@/hooks/useExecutions";

interface UseWorkflowResult<T> {
	/** Start workflow execution with optional parameters */
	execute: (params?: Record<string, unknown>) => Promise<string>;
	/** Current execution ID (null if not started) */
	executionId: string | null;
	/** Current execution status */
	status: ExecutionStatus | null;
	/** True while workflow is Pending or Running */
	loading: boolean;
	/** True when workflow completed successfully */
	completed: boolean;
	/** True when workflow failed */
	failed: boolean;
	/** The workflow result data (null until completed) */
	result: T | null;
	/** Error message if workflow failed */
	error: string | null;
	/** Streaming logs array (updates in real-time) */
	logs: StreamingLog[];
}

/**
 * Hook for executing workflows with real-time streaming updates
 *
 * @param workflowId - The workflow ID or name to execute
 * @returns Object with execute function and reactive state
 *
 * @example
 * ```tsx
 * // Load on mount
 * const workflow = useWorkflow<Customer[]>('list-customers');
 *
 * useEffect(() => {
 *   workflow.execute({ limit: 10 });
 * }, []);
 *
 * if (workflow.loading) return <Spinner />;
 * if (workflow.failed) return <Alert>{workflow.error}</Alert>;
 *
 * return <CustomerList data={workflow.result} />;
 * ```
 *
 * @example
 * ```tsx
 * // Button trigger with loading state
 * const workflow = useWorkflow('create-customer');
 *
 * <Button
 *   onClick={() => workflow.execute({ name: 'Acme' })}
 *   disabled={workflow.loading}
 * >
 *   {workflow.loading ? <Spinner /> : 'Create'}
 * </Button>
 * ```
 *
 * @example
 * ```tsx
 * // With streaming logs
 * const workflow = useWorkflow('long-running-task');
 *
 * {workflow.loading && (
 *   <LogViewer logs={workflow.logs} />
 * )}
 * ```
 */
export function useWorkflow<T = unknown>(
	workflowId: string,
): UseWorkflowResult<T> {
	const [executionId, setExecutionId] = useState<string | null>(null);
	const [result, setResult] = useState<T | null>(null);
	const [executeError, setExecuteError] = useState<string | null>(null);

	// Use ref to track previous execution ID for cleanup without causing execute to be recreated
	const prevExecutionIdRef = useRef<string | null>(null);

	// Clear stream from store when execution changes (cleanup previous)
	const clearStream = useExecutionStreamStore((state) => state.clearStream);

	// Memoize the onComplete callback to prevent infinite re-renders
	// useExecutionStream has onComplete in its dependency array, so this must be stable
	const onComplete = useCallback(async (completedExecutionId: string) => {
		// Fetch the completed execution to get the result
		try {
			const execution = await getExecution(completedExecutionId);
			if (execution.status === "Success") {
				setResult(execution.result as T);
			} else if (execution.error_message) {
				setExecuteError(execution.error_message);
			}
		} catch (err) {
			console.error(
				"[useWorkflow] Failed to fetch completed execution:",
				err,
			);
			setExecuteError(
				err instanceof Error
					? err.message
					: "Failed to fetch result",
			);
		}
	}, []);

	// Subscribe to WebSocket updates for current execution
	useExecutionStream({
		executionId: executionId || "",
		enabled: !!executionId,
		onComplete,
	});

	// Get reactive state from store
	const streamState = useExecutionStreamStore((state) =>
		executionId ? state.streams[executionId] : undefined,
	);

	// Execute workflow
	const execute = useCallback(
		async (params?: Record<string, unknown>): Promise<string> => {
			// Clear previous execution state using ref (avoids stale closure)
			if (prevExecutionIdRef.current) {
				clearStream(prevExecutionIdRef.current);
			}
			setResult(null);
			setExecuteError(null);

			// Call the execute API
			const { data, error } = await apiClient.POST(
				"/api/workflows/execute",
				{
					body: {
						workflow_id: workflowId,
						input_data: params ?? {},
						form_id: null,
						transient: false,
						code: null,
						script_name: null,
					},
				},
			);

			if (error) {
				const errorMessage =
					typeof error === "object" &&
					error !== null &&
					"detail" in error
						? String((error as { detail: unknown }).detail)
						: "Workflow execution failed";
				setExecuteError(errorMessage);
				throw new Error(errorMessage);
			}

			if (!data?.execution_id) {
				const errorMessage = "No execution ID returned";
				setExecuteError(errorMessage);
				throw new Error(errorMessage);
			}

			// Update ref and state - ref is updated synchronously for next execute call
			prevExecutionIdRef.current = data.execution_id;
			setExecutionId(data.execution_id);

			return data.execution_id;
		},
		[workflowId, clearStream],
	);

	// Derive state from stream
	const status = streamState?.status ?? null;
	// Loading is true if:
	// 1. We have an executionId but no stream state yet (waiting for WebSocket to connect)
	// 2. Status is Pending or Running
	const loading =
		(executionId !== null && !streamState) ||
		status === "Pending" ||
		status === "Running";
	const completed = status === "Success";
	const failed =
		status === "Failed" ||
		status === "Timeout" ||
		status === "Cancelled" ||
		status === "CompletedWithErrors";

	// Combine stream error with execute error
	const error = streamState?.error ?? executeError;

	// Get logs from stream
	const logs = streamState?.streamingLogs ?? [];

	return {
		execute,
		executionId,
		status,
		loading,
		completed,
		failed,
		result,
		error,
		logs,
	};
}
