/**
 * Data Providers hooks and utilities using openapi-react-query pattern
 */

import { $api } from "@/lib/api-client";
import type { components } from "@/lib/v1";

// Auto-generated types from OpenAPI spec
export type DataProvider = components["schemas"]["DataProviderMetadata"];

// Types for data provider options
export type DataProviderOption = {
	label: string;
	value: string;
	description?: string;
};

// Response type for invoke endpoint
interface DataProviderInvokeResponse {
	options: Array<{
		value: string;
		label: string;
		description?: string | null;
	}>;
}

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
		// Use fetch directly since the generated types may not include this endpoint yet
		const response = await fetch(
			`/api/data-providers/${providerId}/invoke`,
			{
				method: "POST",
				headers: {
					"Content-Type": "application/json",
				},
				credentials: "include",
				body: JSON.stringify({ inputs: inputs || {} }),
			},
		);

		if (!response.ok) {
			console.error(
				"Failed to invoke data provider:",
				response.statusText,
			);
			return [];
		}

		const data: DataProviderInvokeResponse = await response.json();

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
