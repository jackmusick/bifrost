/**
 * React Query hooks for user management
 * Uses openapi-react-query for type-safe API calls
 */

import { useQueryClient } from "@tanstack/react-query";
import { $api } from "@/lib/api-client";
import { useScopeStore } from "@/stores/scopeStore";

/**
 * Fetch all users filtered by current scope (from X-Organization-Id header)
 */
export function useUsers() {
	const orgId = useScopeStore((state) => state.scope.orgId);

	return $api.useQuery(
		"get",
		"/api/users",
		{},
		{
			// Include orgId in the key so React Query automatically refetches when scope changes
			queryKey: ["users", orgId],
			// Don't use cached data from previous scope
			staleTime: 0,
			// Remove from cache immediately when component unmounts
			gcTime: 0,
			// Always refetch when component mounts (navigating to page)
			refetchOnMount: "always",
		},
	);
}

/**
 * Fetch a specific user by ID
 */
export function useUser(userId: string | undefined) {
	return $api.useQuery(
		"get",
		"/api/users/{user_id}",
		{
			params: { path: { user_id: userId! } },
		},
		{
			queryKey: ["users", userId],
			enabled: !!userId,
		},
	);
}

/**
 * Fetch roles for a specific user
 */
export function useUserRoles(userId: string | undefined) {
	return $api.useQuery(
		"get",
		"/api/users/{user_id}/roles",
		{
			params: { path: { user_id: userId! } },
		},
		{
			queryKey: ["users", userId, "roles"],
			enabled: !!userId,
		},
	);
}

/**
 * Fetch forms accessible to a specific user
 */
export function useUserForms(userId: string | undefined) {
	return $api.useQuery(
		"get",
		"/api/users/{user_id}/forms",
		{
			params: { path: { user_id: userId! } },
		},
		{
			queryKey: ["users", userId, "forms"],
			enabled: !!userId,
		},
	);
}

/**
 * Create a new user
 */
export function useCreateUser() {
	const queryClient = useQueryClient();
	return $api.useMutation("post", "/api/users", {
		onSuccess: () => {
			queryClient.invalidateQueries({ queryKey: ["users"] });
		},
	});
}

/**
 * Update an existing user
 */
export function useUpdateUser() {
	const queryClient = useQueryClient();
	return $api.useMutation("patch", "/api/users/{user_id}", {
		onSuccess: () => {
			queryClient.invalidateQueries({ queryKey: ["users"] });
		},
	});
}

/**
 * Delete a user
 */
export function useDeleteUser() {
	const queryClient = useQueryClient();
	return $api.useMutation("delete", "/api/users/{user_id}", {
		onSuccess: () => {
			queryClient.invalidateQueries({ queryKey: ["users"] });
		},
	});
}
