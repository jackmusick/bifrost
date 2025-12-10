/**
 * React Query hooks for config management
 * Uses openapi-react-query pattern with $api for type-safe queries and mutations
 * All hooks automatically handle X-Organization-Id header via apiClient middleware
 */

import { useQueryClient } from "@tanstack/react-query";
import { $api, apiClient } from "@/lib/api-client";
import type { components } from "@/lib/v1";
import type { ConfigScope } from "@/lib/client-types";
import { toast } from "sonner";
import { useScopeStore } from "@/stores/scopeStore";

type SetConfigRequest = components["schemas"]["SetConfigRequest"];
type Config = components["schemas"]["Config"];

export function useConfigs(scope: ConfigScope = "GLOBAL") {
	const currentOrgId = useScopeStore((state) => state.scope.orgId);

	return $api.useQuery(
		"get",
		"/api/config",
		{},
		{
			queryKey: ["configs", scope, currentOrgId],
			// Don't use cached data from previous scope
			staleTime: 0,
			// Remove from cache immediately when component unmounts
			gcTime: 0,
			// Always refetch when component mounts (navigating to page)
			refetchOnMount: "always",
		},
	);
}

export function useSetConfig() {
	const queryClient = useQueryClient();

	return $api.useMutation(
		"post",
		"/api/config",
		{
			onSuccess: (_, variables) => {
				queryClient.invalidateQueries({ queryKey: ["configs"] });
				toast.success("Configuration saved", {
					description: `Config key "${variables.body.key}" has been updated`,
				});
			},
			onError: (error) => {
				const errorMessage =
					typeof error === "object" && error && "detail" in error
						? String((error as Record<string, unknown>)["detail"])
						: "Unknown error";
				toast.error("Failed to save configuration", {
					description: errorMessage,
				});
			},
		},
	);
}

export function useDeleteConfig() {
	const queryClient = useQueryClient();

	return $api.useMutation(
		"delete",
		"/api/config/{key}",
		{
			onSuccess: (_, variables) => {
				queryClient.invalidateQueries({ queryKey: ["configs"] });
				toast.success("Configuration deleted", {
					description: `Config key "${variables.params.path.key}" has been removed`,
				});
			},
			onError: (error) => {
				const errorMessage =
					typeof error === "object" && error && "detail" in error
						? String((error as Record<string, unknown>)["detail"])
						: "Unknown error";
				toast.error("Failed to delete configuration", {
					description: errorMessage,
				});
			},
		},
	);
}

/**
 * Standalone function for imperative config operations outside React hooks
 * Use when you need to set config without React Query machinery
 */
export async function setConfigImperative(request: SetConfigRequest): Promise<Config> {
	const { data, error } = await apiClient.POST("/api/config", {
		body: request,
	});
	if (error) {
		throw new Error(
			typeof error === "object" && error && "message" in error
				? String((error as Record<string, unknown>)["message"])
				: JSON.stringify(error),
		);
	}
	return data!;
}
