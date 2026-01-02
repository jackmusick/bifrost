/**
 * Reports API service using openapi-react-query pattern
 *
 * NOTE: These endpoints are implemented in the backend but not yet in the OpenAPI spec.
 * Run `npm run generate:types` after the next OpenAPI spec update to use typed endpoints.
 *
 * Organization filtering is handled via the `scope` query parameter:
 * - undefined/omit: Return data for all organizations
 * - null/"global": Return only global (platform-level) data
 * - string (UUID): Return data for the specified organization
 */

import { $api } from "@/lib/api-client";

// Type definitions matching backend API contracts
export interface ROISummary {
	start_date: string;
	end_date: string;
	total_executions: number;
	successful_executions: number;
	total_time_saved: number; // in minutes
	total_value: number;
	time_saved_unit: string;
	value_unit: string;
}

export interface WorkflowROI {
	workflow_id: string;
	workflow_name: string;
	execution_count: number;
	success_count: number;
	time_saved_per_execution: number;
	value_per_execution: number;
	total_time_saved: number;
	total_value: number;
}

export interface ROIByWorkflow {
	workflows: WorkflowROI[];
	total_workflows: number;
	time_saved_unit: string;
	value_unit: string;
}

export interface OrganizationROI {
	organization_id: string;
	organization_name: string;
	execution_count: number;
	success_count: number;
	total_time_saved: number;
	total_value: number;
}

export interface ROIByOrganization {
	organizations: OrganizationROI[];
	time_saved_unit: string;
	value_unit: string;
}

export interface ROITrendEntry {
	period: string;
	execution_count: number;
	success_count: number;
	time_saved: number;
	value: number;
}

export interface ROITrends {
	entries: ROITrendEntry[];
	granularity: string;
	time_saved_unit: string;
	value_unit: string;
}

/**
 * Hook to fetch ROI summary for a date range.
 *
 * @param startDate - Start date in YYYY-MM-DD format
 * @param endDate - End date in YYYY-MM-DD format
 * @param scope - Optional scope filter (undefined = all, null = global, string = specific org UUID)
 */
export function useROISummary(
	startDate: string,
	endDate: string,
	scope?: string | null,
) {
	return $api.useQuery("get", "/api/reports/roi/summary", {
		params: {
			query: {
				start_date: startDate,
				end_date: endDate,
				// Pass scope: 'global' for null, org UUID for string, omit for undefined (all)
				...(scope === null
					? { scope: "global" }
					: typeof scope === "string"
						? { scope }
						: {}),
			},
		},
	}) as { data: ROISummary | undefined; isLoading: boolean; error: unknown };
}

/**
 * Hook to fetch ROI by workflow for a date range.
 *
 * @param startDate - Start date in YYYY-MM-DD format
 * @param endDate - End date in YYYY-MM-DD format
 * @param scope - Optional scope filter (undefined = all, null = global, string = specific org UUID)
 */
export function useROIByWorkflow(
	startDate: string,
	endDate: string,
	scope?: string | null,
) {
	return $api.useQuery("get", "/api/reports/roi/by-workflow", {
		params: {
			query: {
				start_date: startDate,
				end_date: endDate,
				...(scope === null
					? { scope: "global" }
					: typeof scope === "string"
						? { scope }
						: {}),
			},
		},
	}) as {
		data: ROIByWorkflow | undefined;
		isLoading: boolean;
		error: unknown;
	};
}

/**
 * Hook to fetch ROI by organization for a date range.
 * This endpoint always returns all organizations (ignores org header).
 */
export function useROIByOrganization(startDate: string, endDate: string) {
	return $api.useQuery("get", "/api/reports/roi/by-organization", {
		params: {
			query: {
				start_date: startDate,
				end_date: endDate,
			},
		},
	}) as {
		data: ROIByOrganization | undefined;
		isLoading: boolean;
		error: unknown;
	};
}

/**
 * Hook to fetch ROI trends over time.
 *
 * @param startDate - Start date in YYYY-MM-DD format
 * @param endDate - End date in YYYY-MM-DD format
 * @param granularity - Time granularity (day, week, month)
 * @param scope - Optional scope filter (undefined = all, null = global, string = specific org UUID)
 */
export function useROITrends(
	startDate: string,
	endDate: string,
	granularity: "day" | "week" | "month" = "day",
	scope?: string | null,
) {
	return $api.useQuery("get", "/api/reports/roi/trends", {
		params: {
			query: {
				start_date: startDate,
				end_date: endDate,
				granularity,
				...(scope === null
					? { scope: "global" }
					: typeof scope === "string"
						? { scope }
						: {}),
			},
		},
	}) as { data: ROITrends | undefined; isLoading: boolean; error: unknown };
}
