/**
 * React Query hooks for organization management
 * Uses openapi-react-query for type-safe API calls
 */

import { useQueryClient } from "@tanstack/react-query";
import { $api } from "@/lib/api-client";
import { getErrorMessage } from "@/lib/api-error";
import { toast } from "sonner";
import { useScopeStore } from "@/stores/scopeStore";

/**
 * Fetch all organizations visible to the current user
 */
export function useOrganizations(options?: { enabled?: boolean }) {
	const orgId = useScopeStore((state) => state.scope.orgId);

	return $api.useQuery(
		"get",
		"/api/organizations",
		{},
		{
			// Include orgId in query key so cache updates when scope changes
			queryKey: ["organizations", orgId],
			enabled: options?.enabled ?? true,
			// Don't use cached data from previous scope
			staleTime: 0,
			// Always refetch when component mounts (navigating to page)
			refetchOnMount: "always",
			meta: {
				onError: (error: unknown) => {
					toast.error("Failed to load organizations", {
						description: getErrorMessage(
							error,
							"Unknown error occurred",
						),
					});
				},
			},
		},
	);
}

/**
 * Fetch a specific organization by ID
 */
export function useOrganization(orgId: string | undefined) {
	return $api.useQuery(
		"get",
		"/api/organizations/{org_id}",
		{
			params: { path: { org_id: orgId! } },
		},
		{
			enabled: !!orgId,
		},
	);
}

/**
 * Create a new organization
 */
export function useCreateOrganization() {
	const queryClient = useQueryClient();

	return $api.useMutation("post", "/api/organizations", {
		onSuccess: () => {
			queryClient.invalidateQueries({ queryKey: ["organizations"] });
			toast.success("Organization created", {
				description: "The organization has been successfully created",
			});
		},
		onError: (error) => {
			toast.error("Failed to create organization", {
				description: getErrorMessage(error, "Unknown error occurred"),
			});
		},
	});
}

/**
 * Update an existing organization
 */
export function useUpdateOrganization() {
	const queryClient = useQueryClient();

	return $api.useMutation("patch", "/api/organizations/{org_id}", {
		onSuccess: (_data, variables) => {
			const orgId = variables.params?.path?.org_id;
			queryClient.invalidateQueries({ queryKey: ["organizations"] });
			if (orgId) {
				queryClient.invalidateQueries({
					queryKey: ["organizations", orgId],
				});
			}
			toast.success("Organization updated", {
				description: "The organization has been successfully updated",
			});
		},
		onError: (error) => {
			toast.error("Failed to update organization", {
				description: getErrorMessage(error, "Unknown error occurred"),
			});
		},
	});
}

/**
 * Delete an organization
 */
export function useDeleteOrganization() {
	const queryClient = useQueryClient();

	return $api.useMutation("delete", "/api/organizations/{org_id}", {
		onSuccess: () => {
			queryClient.invalidateQueries({ queryKey: ["organizations"] });
			toast.success("Organization deleted", {
				description: "The organization has been successfully deleted",
			});
		},
		onError: (error) => {
			toast.error("Failed to delete organization", {
				description: getErrorMessage(error, "Unknown error occurred"),
			});
		},
	});
}
