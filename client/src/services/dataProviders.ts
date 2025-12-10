/**
 * Data Providers hooks and utilities using openapi-react-query pattern
 */

import { $api } from "@/lib/api-client";
import type { components } from "@/lib/v1";

// Auto-generated types from OpenAPI spec
export type DataProvider = components["schemas"]["DataProviderMetadata"];

// TODO: These types will be added when the data provider options endpoint is implemented
export type DataProviderOption = {
	label: string;
	value: string;
	description?: string;
};

/**
 * Hook to fetch all available data providers
 */
export function useDataProviders() {
	return $api.useQuery("get", "/api/data-providers", {}, {
		queryKey: ["data-providers"],
		staleTime: 10 * 60 * 1000, // 10 minutes
	});
}

/**
 * Standalone async function to get options from a data provider in the context of a form
 *
 * NOTE: This endpoint is currently not implemented in the API.
 * This function is a placeholder for when it becomes available.
 *
 * @param _formId - Form ID (UUID)
 * @param _providerName - Data provider name
 * @param _inputs - Optional input parameters for the data provider
 */
export async function getDataProviderOptions(
	_formId: string,
	_providerName: string,
	_inputs?: Record<string, unknown>,
): Promise<DataProviderOption[]> {
	// TODO: Implement when endpoint /api/forms/{form_id}/data-providers/{provider_name} is available
	// For now, return empty options
	return [];
}
