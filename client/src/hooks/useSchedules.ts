/**
 * React Query hooks for schedules
 * Uses openapi-react-query for type-safe API access
 */

import { $api, apiClient } from "@/lib/api-client";
import { useQueryClient } from "@tanstack/react-query";

export function useSchedules() {
	return $api.useQuery(
		"get",
		"/api/schedules",
		{},
		{
			queryKey: ["schedules"],
			staleTime: 0, // No caching - always fetch fresh data
			refetchOnMount: true,
			refetchOnWindowFocus: false,
		},
	);
}

export function useTriggerSchedule() {
	const queryClient = useQueryClient();

	return $api.useMutation(
		"post",
		"/api/workflows/execute",
		{
			onSuccess: () => {
				// Invalidate schedules list to refresh last run times
				queryClient.invalidateQueries({ queryKey: ["schedules"] });
			},
		},
	);
}

// ============================================================================
// Imperative functions for non-hook usage
// ============================================================================

/**
 * Fetch schedules imperatively
 */
export async function getSchedules() {
	const { data, error } = await apiClient.GET("/api/schedules", {});
	if (error) throw new Error(`Failed to fetch schedules: ${error}`);
	return data!;
}

/**
 * Trigger a schedule imperatively
 */
export async function triggerSchedule(workflowName: string) {
	const { data, error } = await apiClient.POST("/api/workflows/execute", {
		body: {
			workflow_name: workflowName,
			input_data: {},
			form_id: null,
			transient: false,
			script_name: null,
		},
	});
	if (error) throw new Error(`Failed to trigger schedule: ${error}`);
	return data;
}
