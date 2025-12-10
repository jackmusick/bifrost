import { $api } from "@/lib/api-client";
import type { components } from "@/lib/v1";

// Re-export types for convenience
export type DailyMetricsEntry = components["schemas"]["DailyMetricsEntry"];
export type DailyMetricsResponse =
	components["schemas"]["DailyMetricsResponse"];
export type ResourceMetricsEntry =
	components["schemas"]["ResourceMetricsEntry"];
export type ResourceMetricsResponse =
	components["schemas"]["ResourceMetricsResponse"];
export type OrganizationMetricsSummary =
	components["schemas"]["OrganizationMetricsSummary"];
export type OrganizationMetricsResponse =
	components["schemas"]["OrganizationMetricsResponse"];
export type WorkflowMetricsSummary =
	components["schemas"]["WorkflowMetricsSummary"];
export type WorkflowMetricsResponse =
	components["schemas"]["WorkflowMetricsResponse"];

/**
 * Hook for fetching resource usage trends (memory, CPU)
 * Platform admin only
 */
export function useResourceMetrics(days: number = 7, enabled: boolean = true) {
	return $api.useQuery(
		"get",
		"/api/metrics/resources",
		{
			params: { query: { days } },
		},
		{
			queryKey: ["resource-metrics", days],
			enabled,
			staleTime: 60000, // 1 minute
			refetchInterval: 60000,
		},
	);
}

/**
 * Hook for fetching organization breakdown
 * Platform admin only
 */
export function useOrganizationMetrics(
	days: number = 30,
	limit: number = 10,
	enabled: boolean = true,
) {
	return $api.useQuery(
		"get",
		"/api/metrics/organizations",
		{
			params: { query: { days, limit } },
		},
		{
			queryKey: ["organization-metrics", days, limit],
			enabled,
			staleTime: 60000,
			refetchInterval: 60000,
		},
	);
}

/**
 * Hook for fetching workflow-level metrics
 * Platform admin only
 */
export function useWorkflowMetrics(
	days: number = 30,
	sortBy: "executions" | "memory" | "duration" | "cpu" = "executions",
	limit: number = 20,
	enabled: boolean = true,
) {
	return $api.useQuery(
		"get",
		"/api/metrics/workflows",
		{
			params: { query: { days, sort_by: sortBy, limit } },
		},
		{
			queryKey: ["workflow-metrics", days, sortBy, limit],
			enabled,
			staleTime: 60000,
			refetchInterval: 60000,
		},
	);
}
