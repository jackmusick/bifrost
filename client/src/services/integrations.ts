/**
 * Integrations API service using openapi-react-query pattern
 *
 * All mutations automatically invalidate relevant queries so components
 * reading from useIntegration() will re-render with fresh data.
 */

import { useQueryClient } from "@tanstack/react-query";
import { $api } from "@/lib/api-client";
import type { components } from "@/lib/v1";

// Re-export types from OpenAPI spec
export type Integration = components["schemas"]["IntegrationResponse"];
export type IntegrationDetail =
	components["schemas"]["IntegrationDetailResponse"];
export type IntegrationMapping =
	components["schemas"]["IntegrationMappingResponse"];
export type OAuthConfigSummary = components["schemas"]["OAuthConfigSummary"];
export type ConfigSchemaItem = components["schemas"]["ConfigSchemaItem"];
export type IntegrationCreate = components["schemas"]["IntegrationCreate"];
export type IntegrationUpdate = components["schemas"]["IntegrationUpdate"];
export type IntegrationMappingCreate =
	components["schemas"]["IntegrationMappingCreate"];
export type IntegrationMappingUpdate =
	components["schemas"]["IntegrationMappingUpdate"];

/**
 * Hook to fetch all integrations with optional organization filtering
 * @param organizationId - Organization ID to filter by (null = global only, undefined = all)
 *
 * Note: The organization_id query param is supported by the backend but may not yet
 * be reflected in the generated OpenAPI types. Regenerate types after API changes
 * are deployed: `cd client && npm run generate:types`
 */
export function useIntegrations(organizationId?: string | null) {
	// Build query params - organization_id is supported by backend even if not in generated types
	const queryParams: Record<string, string | undefined> = {};
	if (organizationId !== undefined && organizationId !== null) {
		queryParams.organization_id = organizationId;
	}

	return $api.useQuery("get", "/api/integrations", {
		params: {
			// Type assertion needed until types are regenerated
			query: Object.keys(queryParams).length > 0 ? queryParams : undefined,
		} as { query?: undefined },
	});
}

/**
 * Hook to fetch a single integration (includes mappings)
 */
export function useIntegration(integrationId: string) {
	return $api.useQuery("get", "/api/integrations/{integration_id}", {
		params: {
			path: { integration_id: integrationId },
		},
	});
}

/**
 * Hook to create an integration
 */
export function useCreateIntegration() {
	const queryClient = useQueryClient();

	return $api.useMutation("post", "/api/integrations", {
		onSuccess: () => {
			queryClient.invalidateQueries({
				queryKey: ["get", "/api/integrations"],
			});
		},
	});
}

/**
 * Hook to update an integration
 */
export function useUpdateIntegration() {
	const queryClient = useQueryClient();

	return $api.useMutation("put", "/api/integrations/{integration_id}", {
		onSuccess: (_, variables) => {
			const integrationId = variables.params.path.integration_id;
			// Invalidate both the list and the specific integration
			queryClient.invalidateQueries({
				queryKey: ["get", "/api/integrations"],
			});
			queryClient.invalidateQueries({
				queryKey: [
					"get",
					"/api/integrations/{integration_id}",
					{ params: { path: { integration_id: integrationId } } },
				],
			});
		},
	});
}

/**
 * Hook to delete an integration
 */
export function useDeleteIntegration() {
	const queryClient = useQueryClient();

	return $api.useMutation("delete", "/api/integrations/{integration_id}", {
		onSuccess: () => {
			queryClient.invalidateQueries({
				queryKey: ["get", "/api/integrations"],
			});
		},
	});
}

/**
 * Hook to fetch mappings for an integration
 */
export function useIntegrationMappings(integrationId: string) {
	return $api.useQuery("get", "/api/integrations/{integration_id}/mappings", {
		params: {
			path: { integration_id: integrationId },
		},
	});
}

/**
 * Hook to create an integration mapping
 */
export function useCreateMapping() {
	const queryClient = useQueryClient();

	return $api.useMutation(
		"post",
		"/api/integrations/{integration_id}/mappings",
		{
			onSuccess: (_, variables) => {
				const integrationId = variables.params.path.integration_id;
				// Invalidate the integration detail (which includes mappings)
				queryClient.invalidateQueries({
					queryKey: [
						"get",
						"/api/integrations/{integration_id}",
						{ params: { path: { integration_id: integrationId } } },
					],
				});
			},
		},
	);
}

/**
 * Hook to update an integration mapping
 */
export function useUpdateMapping() {
	const queryClient = useQueryClient();

	return $api.useMutation(
		"put",
		"/api/integrations/{integration_id}/mappings/{mapping_id}",
		{
			onSuccess: (_, variables) => {
				const integrationId = variables.params.path.integration_id;
				// Invalidate the integration detail (which includes mappings)
				queryClient.invalidateQueries({
					queryKey: [
						"get",
						"/api/integrations/{integration_id}",
						{ params: { path: { integration_id: integrationId } } },
					],
				});
			},
		},
	);
}

/**
 * Hook to delete an integration mapping
 */
export function useDeleteMapping() {
	const queryClient = useQueryClient();

	return $api.useMutation(
		"delete",
		"/api/integrations/{integration_id}/mappings/{mapping_id}",
		{
			onSuccess: (_, variables) => {
				const integrationId = variables.params.path.integration_id;
				// Invalidate the integration detail (which includes mappings)
				queryClient.invalidateQueries({
					queryKey: [
						"get",
						"/api/integrations/{integration_id}",
						{ params: { path: { integration_id: integrationId } } },
					],
				});
			},
		},
	);
}

/**
 * Hook to update integration default config values
 */
export function useUpdateIntegrationConfig() {
	const queryClient = useQueryClient();

	return $api.useMutation(
		"put",
		"/api/integrations/{integration_id}/config",
		{
			onSuccess: (_, variables) => {
				const integrationId = variables.params.path.integration_id;
				// Invalidate the integration detail to refresh config
				queryClient.invalidateQueries({
					queryKey: [
						"get",
						"/api/integrations/{integration_id}",
						{ params: { path: { integration_id: integrationId } } },
					],
				});
			},
		},
	);
}

/**
 * Hook to generate SDK from OpenAPI spec
 */
export function useGenerateSDK() {
	const queryClient = useQueryClient();

	return $api.useMutation(
		"post",
		"/api/integrations/{integration_id}/generate-sdk",
		{
			onSuccess: (_, variables) => {
				const integrationId = variables.params.path.integration_id;
				// Invalidate the integration detail
				queryClient.invalidateQueries({
					queryKey: [
						"get",
						"/api/integrations/{integration_id}",
						{ params: { path: { integration_id: integrationId } } },
					],
				});
			},
		},
	);
}
