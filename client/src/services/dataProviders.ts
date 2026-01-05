/**
 * Data Providers hooks and utilities
 *
 * Data providers are a special type of workflow (type='data_provider') that return
 * options for form fields and other dynamic data sources.
 *
 * - Listing: Use GET /api/workflows?type=data_provider
 * - Execution: Use POST /api/workflows/execute (returns options in result field)
 */

import { $api, apiClient } from "@/lib/api-client";
import type { components } from "@/lib/v1";

// Auto-generated types from OpenAPI spec
export type DataProvider = components["schemas"]["WorkflowMetadata"];

// Types for data provider options
export type DataProviderOption = {
	label: string;
	value: string;
	description?: string;
};

/**
 * Hook to fetch all available data providers
 *
 * Data providers are workflows with type='data_provider', so we use the
 * workflows endpoint with a type filter.
 */
export function useDataProviders() {
	return $api.useQuery("get", "/api/workflows", {
		params: { query: { type: "data_provider" } },
	});
}

/**
 * Standalone async function to get options from a data provider
 *
 * Uses the unified /execute endpoint which handles data providers specially,
 * returning the options list directly in the result field.
 *
 * @param providerId - Data provider UUID (workflow_id)
 * @param inputs - Optional input parameters for the data provider
 */
export async function getDataProviderOptions(
	providerId: string,
	inputs?: Record<string, unknown>,
): Promise<DataProviderOption[]> {
	try {
		const { data, error } = await apiClient.POST("/api/workflows/execute", {
			body: {
				workflow_id: providerId,
				input_data: inputs || {},
				transient: true, // Data providers are transient (no execution tracking)
			},
		});

		if (error || !data || data.status !== "Success") {
			console.error(
				"Failed to invoke data provider:",
				error || data?.error,
			);
			return [];
		}

		// Data provider returns list of options in the result field
		const options = data.result as Array<{
			value?: string;
			label?: string;
			description?: string;
		}> | null;

		if (!options || !Array.isArray(options)) {
			return [];
		}

		return options.map((opt) => ({
			value: String(opt.value ?? ""),
			label: String(opt.label ?? opt.value ?? ""),
			description: opt.description,
		}));
	} catch (error) {
		console.error("Error invoking data provider:", error);
		return [];
	}
}
