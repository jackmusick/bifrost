/**
 * Metrics API service - type-safe with openapi-fetch
 * Platform admin endpoints for dashboard analytics
 */

import { apiClient } from "@/lib/api-client";
import type { components } from "@/lib/v1";

// Type aliases for cleaner code
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

export const metricsService = {
	/**
	 * Get daily execution metrics (platform admin only)
	 */
	async getDailyMetrics(
		days: number = 7,
		organizationId?: string,
	): Promise<DailyMetricsResponse> {
		const { data, error } = await apiClient.GET(
			"/api/metrics/executions/daily",
			{
				params: {
					query: {
						days,
						organization_id: organizationId,
					},
				},
			},
		);
		if (error) throw new Error(`Failed to fetch daily metrics: ${error}`);
		return data!;
	},

	/**
	 * Get resource usage trends (platform admin only)
	 */
	async getResourceMetrics(
		days: number = 7,
	): Promise<ResourceMetricsResponse> {
		const { data, error } = await apiClient.GET("/api/metrics/resources", {
			params: { query: { days } },
		});
		if (error)
			throw new Error(`Failed to fetch resource metrics: ${error}`);
		return data!;
	},

	/**
	 * Get organization breakdown (platform admin only)
	 */
	async getOrganizationMetrics(
		days: number = 30,
		limit: number = 10,
	): Promise<OrganizationMetricsResponse> {
		const { data, error } = await apiClient.GET(
			"/api/metrics/organizations",
			{
				params: { query: { days, limit } },
			},
		);
		if (error)
			throw new Error(`Failed to fetch organization metrics: ${error}`);
		return data!;
	},

	/**
	 * Get workflow-level metrics (platform admin only)
	 */
	async getWorkflowMetrics(
		days: number = 30,
		sortBy: "executions" | "memory" | "duration" | "cpu" = "executions",
		limit: number = 20,
	): Promise<WorkflowMetricsResponse> {
		const { data, error } = await apiClient.GET("/api/metrics/workflows", {
			params: { query: { days, sort_by: sortBy, limit } },
		});
		if (error)
			throw new Error(`Failed to fetch workflow metrics: ${error}`);
		return data!;
	},
};
