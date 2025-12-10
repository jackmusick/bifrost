/**
 * React Query hooks for workflow executions
 * Uses openapi-react-query for type-safe API access
 */

import { $api, apiClient } from "@/lib/api-client";
import type { ExecutionFilters } from "@/lib/client-types";
import { useScopeStore } from "@/stores/scopeStore";
import { useQueryClient } from "@tanstack/react-query";

// Re-export types for convenience
export type { ExecutionFilters };

export function useExecutions(
	filters?: ExecutionFilters,
	continuationToken?: string,
) {
	const orgId = useScopeStore((state) => state.scope.orgId);

	// Build query params
	const queryParams: Record<string, string> = {};
	if (filters?.workflow_name) queryParams["workflow_name"] = filters.workflow_name;
	if (filters?.status) queryParams["status"] = filters.status;
	if (filters?.start_date) queryParams["start_date"] = filters.start_date;
	if (filters?.end_date) queryParams["end_date"] = filters.end_date;
	if (filters?.limit) queryParams["limit"] = filters.limit.toString();
	if (continuationToken) queryParams["continuation_token"] = continuationToken;

	return $api.useQuery(
		"get",
		"/api/executions",
		{ params: { query: queryParams } },
		{
			// Include orgId in query key so it refetches when scope changes
			queryKey: ["executions", orgId, filters, continuationToken],
			staleTime: 0, // No caching - always fetch fresh data
			refetchOnMount: true,
			refetchOnWindowFocus: false,
		},
	);
}

export function useExecution(
	executionId: string | undefined,
	disablePolling = false,
) {
	return $api.useQuery(
		"get",
		"/api/executions/{execution_id}",
		{ params: { path: { execution_id: executionId! } } },
		{
			queryKey: ["executions", executionId],
			enabled: !!executionId,
			staleTime: 0, // No caching - always fetch fresh data
			// Retry on 404 for a short period (Redis-first architecture)
			// The execution may be in Redis pending but not yet in PostgreSQL
			retry: (failureCount, error) => {
				// Only retry 404s up to 5 times (10 seconds total with 2s interval)
				if (error instanceof Error && error.message.includes("404")) {
					return failureCount < 5;
				}
				// Don't retry other errors
				return false;
			},
			retryDelay: 2000, // Retry every 2 seconds
			refetchInterval: (query) => {
				// Disable polling if Web PubSub is handling updates
				if (disablePolling) {
					return false;
				}

				// Poll every 2 seconds if status is Pending or Running
				// Also poll if we haven't got data yet (waiting for worker to create record)
				const status = query.state.data?.status;
				if (!query.state.data) {
					return 2000; // Poll while waiting for execution to appear
				}
				return status === "Pending" || status === "Running" ? 2000 : false;
			},
		},
	);
}

/**
 * Progressive loading hook: Get only execution result
 */
export function useExecutionResult(
	executionId: string | undefined,
	enabled = true,
) {
	return $api.useQuery(
		"get",
		"/api/executions/{execution_id}/result",
		{ params: { path: { execution_id: executionId! } } },
		{
			queryKey: ["executions", executionId, "result"],
			enabled: !!executionId && enabled,
			staleTime: 0, // No caching - always fetch fresh data
		},
	);
}

/**
 * Progressive loading hook: Get only execution logs (admin only)
 */
export function useExecutionLogs(
	executionId: string | undefined,
	enabled = true,
) {
	return $api.useQuery(
		"get",
		"/api/executions/{execution_id}/logs",
		{ params: { path: { execution_id: executionId! } } },
		{
			queryKey: ["executions", executionId, "logs"],
			enabled: !!executionId && enabled,
			staleTime: 0, // No caching - always fetch fresh data
			refetchOnMount: true,
		},
	);
}

/**
 * Progressive loading hook: Get only execution variables (admin only)
 */
export function useExecutionVariables(
	executionId: string | undefined,
	enabled = true,
) {
	return $api.useQuery(
		"get",
		"/api/executions/{execution_id}/variables",
		{ params: { path: { execution_id: executionId! } } },
		{
			queryKey: ["executions", executionId, "variables"],
			enabled: !!executionId && enabled,
			staleTime: 0, // No caching - always fetch fresh data
		},
	);
}

/**
 * Mutation hook for canceling an execution
 */
export function useCancelExecution() {
	const queryClient = useQueryClient();

	return $api.useMutation("post", "/api/executions/{execution_id}/cancel", {
		onSuccess: (_, variables) => {
			// Invalidate the specific execution query
			queryClient.invalidateQueries({
				queryKey: ["executions", variables.params.path.execution_id],
			});
			// Also invalidate the executions list
			queryClient.invalidateQueries({ queryKey: ["executions"] });
		},
	});
}

// ============================================================================
// Imperative functions for non-hook usage (polling, etc.)
// ============================================================================

/**
 * Fetch a single execution imperatively (for polling/non-hook contexts)
 */
export async function getExecution(executionId: string) {
	const { data, error } = await apiClient.GET(
		"/api/executions/{execution_id}",
		{ params: { path: { execution_id: executionId } } },
	);
	if (error) throw new Error(`Failed to fetch execution: ${error}`);
	return data!;
}

/**
 * Fetch execution variables imperatively
 */
export async function getExecutionVariables(executionId: string) {
	const { data, error } = await apiClient.GET(
		"/api/executions/{execution_id}/variables",
		{ params: { path: { execution_id: executionId } } },
	);
	if (error) throw new Error(`Failed to fetch execution variables: ${error}`);
	return data as Record<string, unknown>;
}

/**
 * Cancel an execution imperatively
 */
export async function cancelExecution(executionId: string) {
	const { data, error } = await apiClient.POST(
		"/api/executions/{execution_id}/cancel",
		{ params: { path: { execution_id: executionId } } },
	);
	if (error) throw new Error(`Failed to cancel execution: ${error}`);
	return data;
}
