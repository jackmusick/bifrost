/**
 * Platform hook: useWorkflow
 *
 * React hook for fetching data via workflow execution.
 * Provides loading, error, and refresh states.
 */

import { useState, useEffect, useCallback, useRef } from "react";
import { runWorkflow } from "./runWorkflow";

interface UseWorkflowOptions {
	/** Whether to enable the query (default: true) */
	enabled?: boolean;
}

interface UseWorkflowResult<T> {
	/** The workflow result data */
	data: T | undefined;
	/** Whether the workflow is currently loading */
	isLoading: boolean;
	/** Error message if the workflow failed */
	error: string | undefined;
	/** Function to manually refresh the data */
	refresh: () => void;
}

/**
 * Hook for fetching data via workflow execution
 *
 * @param workflowId - The workflow ID or name to execute
 * @param params - Optional parameters to pass to the workflow
 * @param options - Optional configuration (enabled)
 * @returns Object with data, isLoading, error, and refresh function
 *
 * @example
 * ```jsx
 * const { data: clients, isLoading, error, refresh } = useWorkflow('list_clients');
 *
 * if (isLoading) return <Skeleton />;
 * if (error) return <Alert>{error}</Alert>;
 *
 * return (
 *   <DataTable data={clients} onRefresh={refresh} />
 * );
 * ```
 *
 * @example
 * ```jsx
 * // With parameters
 * const { data: client } = useWorkflow('get_client', { id: clientId });
 *
 * // Conditionally enabled
 * const { data } = useWorkflow('get_details', { id }, { enabled: !!id });
 * ```
 */
export function useWorkflow<T = unknown>(
	workflowId: string,
	params?: Record<string, unknown>,
	options?: UseWorkflowOptions,
): UseWorkflowResult<T> {
	const [data, setData] = useState<T | undefined>(undefined);
	const [isLoading, setIsLoading] = useState(true);
	const [error, setError] = useState<string | undefined>(undefined);

	// Track if component is mounted to avoid state updates after unmount
	const isMountedRef = useRef(true);

	// Serialize params for dependency tracking
	const paramsKey = JSON.stringify(params ?? {});

	const enabled = options?.enabled ?? true;

	const fetchData = useCallback(async () => {
		if (!enabled) {
			setIsLoading(false);
			return;
		}

		setIsLoading(true);
		setError(undefined);

		try {
			const result = await runWorkflow<T>(workflowId, params);
			if (isMountedRef.current) {
				setData(result);
				setError(undefined);
			}
		} catch (err) {
			if (isMountedRef.current) {
				setError(
					err instanceof Error ? err.message : "Workflow execution failed",
				);
			}
		} finally {
			if (isMountedRef.current) {
				setIsLoading(false);
			}
		}
		// eslint-disable-next-line react-hooks/exhaustive-deps
	}, [workflowId, paramsKey, enabled]);

	// Fetch on mount and when dependencies change
	useEffect(() => {
		isMountedRef.current = true;
		fetchData();

		return () => {
			isMountedRef.current = false;
		};
	}, [fetchData]);

	// Refresh function for manual re-fetch
	const refresh = useCallback(() => {
		fetchData();
	}, [fetchData]);

	return {
		data,
		isLoading,
		error,
		refresh,
	};
}
