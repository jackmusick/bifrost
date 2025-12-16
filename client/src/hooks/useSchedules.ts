/**
 * React Query hooks for schedules
 * Uses openapi-react-query for type-safe API access
 */

import { $api, apiClient } from "@/lib/api-client";
import { useQueryClient } from "@tanstack/react-query";
import type { components } from "@/lib/v1";

export type ScheduleMetadata = components["schemas"]["ScheduleMetadata"];

export function useSchedules() {
	return $api.useQuery("get", "/api/schedules", {});
}

export function useTriggerSchedule() {
	const queryClient = useQueryClient();

	return $api.useMutation("post", "/api/workflows/execute", {
		onSuccess: () => {
			// Invalidate schedules list to refresh last run times
			queryClient.invalidateQueries({
				queryKey: ["get", "/api/schedules"],
			});
		},
	});
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
export async function triggerSchedule(workflowId: string) {
	const { data, error } = await apiClient.POST("/api/workflows/execute", {
		body: {
			workflow_id: workflowId,
			input_data: {},
			form_id: null,
			transient: false,
			script_name: null,
		},
	});
	if (error) throw new Error(`Failed to trigger schedule: ${error}`);
	return data;
}
