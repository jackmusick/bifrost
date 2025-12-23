/**
 * Data Providers hooks and utilities using openapi-react-query pattern
 */

import { $api, apiClient } from "@/lib/api-client";
import type { components } from "@/lib/v1";

// Auto-generated types from OpenAPI spec
export type DataProvider = components["schemas"]["DataProviderMetadata"];

// Types for data provider options
export type DataProviderOption = {
	label: string;
	value: string;
	description?: string;
};

/**
 * Hook to fetch all available data providers
 */
export function useDataProviders() {
	return $api.useQuery("get", "/api/data-providers");
}

/**
 * Standalone async function to get options from a data provider
 *
 * @param providerId - Data provider UUID
 * @param inputs - Optional input parameters for the data provider
 */
export async function getDataProviderOptions(
	providerId: string,
	inputs?: Record<string, unknown>,
): Promise<DataProviderOption[]> {
	try {
		const { data, error } = await apiClient.POST(
			"/api/data-providers/{provider_id}/invoke",
			{
				params: { path: { provider_id: providerId } },
				body: { inputs: inputs || {} },
			},
		);

		if (error || !data) {
			console.error("Failed to invoke data provider:", error);
			return [];
		}

		return (data.options || []).map((opt) => ({
			value: opt.value,
			label: opt.label,
			description: opt.description ?? undefined,
		}));
	} catch (error) {
		console.error("Error invoking data provider:", error);
		return [];
	}
}
