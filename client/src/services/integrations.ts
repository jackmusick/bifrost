/**
 * Integrations API service using openapi-react-query pattern
 */

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
 * Hook to fetch all integrations
 */
export function useIntegrations() {
	return $api.useQuery("get", "/api/integrations");
}

/**
 * Hook to fetch a single integration
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
	return $api.useMutation("post", "/api/integrations");
}

/**
 * Hook to update an integration
 */
export function useUpdateIntegration() {
	return $api.useMutation("put", "/api/integrations/{integration_id}");
}

/**
 * Hook to delete an integration
 */
export function useDeleteIntegration() {
	return $api.useMutation("delete", "/api/integrations/{integration_id}");
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
	return $api.useMutation(
		"post",
		"/api/integrations/{integration_id}/mappings",
	);
}

/**
 * Hook to update an integration mapping
 */
export function useUpdateMapping() {
	return $api.useMutation(
		"put",
		"/api/integrations/{integration_id}/mappings/{mapping_id}",
	);
}

/**
 * Hook to delete an integration mapping
 */
export function useDeleteMapping() {
	return $api.useMutation(
		"delete",
		"/api/integrations/{integration_id}/mappings/{mapping_id}",
	);
}
