/**
 * React Query hooks for roles management using openapi-react-query pattern
 */

import { useQueryClient } from "@tanstack/react-query";
import { $api, apiClient } from "@/lib/api-client";
import type { components } from "@/lib/v1";
import { toast } from "sonner";
import { useScopeStore } from "@/stores/scopeStore";

type RoleCreate = components["schemas"]["RoleCreate"];
type AssignUsersToRoleRequest =
	components["schemas"]["AssignUsersToRoleRequest"];
type AssignFormsToRoleRequest =
	components["schemas"]["AssignFormsToRoleRequest"];

export function useRoles() {
	const orgId = useScopeStore((state) => state.scope.orgId);

	return $api.useQuery("get", "/api/roles", {}, {
		queryKey: ["roles", orgId],
		// Don't use cached data from previous scope
		staleTime: 0,
		// Always refetch when component mounts (navigating to page)
		refetchOnMount: "always",
	});
}

export function useCreateRole() {
	const queryClient = useQueryClient();

	return $api.useMutation("post", "/api/roles", {
		onSuccess: (_, variables) => {
			queryClient.invalidateQueries({ queryKey: ["roles"] });
			const name = (variables.body as RoleCreate)?.name || "Role";
			toast.success("Role created", {
				description: `Role "${name}" has been created`,
			});
		},
		onError: (error) => {
			const message = typeof error === "object" && error && "detail" in error
				? String(error.detail)
				: "Failed to create role";
			toast.error("Failed to create role", {
				description: message,
			});
		},
	});
}

export function useUpdateRole() {
	const queryClient = useQueryClient();

	return $api.useMutation("patch", "/api/roles/{role_id}", {
		onSuccess: () => {
			queryClient.invalidateQueries({ queryKey: ["roles"] });
			toast.success("Role updated", {
				description: "The role has been updated successfully",
			});
		},
		onError: (error) => {
			const message = typeof error === "object" && error && "detail" in error
				? String(error.detail)
				: "Failed to update role";
			toast.error("Failed to update role", {
				description: message,
			});
		},
	});
}

export function useDeleteRole() {
	const queryClient = useQueryClient();

	return $api.useMutation("delete", "/api/roles/{role_id}", {
		onSuccess: () => {
			queryClient.invalidateQueries({ queryKey: ["roles"] });
			toast.success("Role deleted", {
				description: "The role has been removed",
			});
		},
		onError: (error) => {
			const message = typeof error === "object" && error && "detail" in error
				? String(error.detail)
				: "Failed to delete role";
			toast.error("Failed to delete role", {
				description: message,
			});
		},
	});
}

export function useRoleUsers(roleId: string | undefined) {
	return $api.useQuery("get", "/api/roles/{role_id}/users",
		{ params: { path: { role_id: roleId ?? "" } } },
		{
			queryKey: ["roles", roleId, "users"],
			enabled: !!roleId,
		},
	);
}

export function useAssignUsersToRole() {
	const queryClient = useQueryClient();

	return $api.useMutation("post", "/api/roles/{role_id}/users", {
		onSuccess: (_, variables) => {
			const roleId = variables.params?.path?.role_id;
			const userIds = (variables.body as AssignUsersToRoleRequest)?.userIds || [];
			queryClient.invalidateQueries({
				queryKey: ["roles", roleId, "users"],
			});
			toast.success("Users assigned", {
				description: `${userIds.length} user(s) assigned to role`,
			});
		},
		onError: (error) => {
			const message = typeof error === "object" && error && "detail" in error
				? String(error.detail)
				: "Failed to assign users";
			toast.error("Failed to assign users", {
				description: message,
			});
		},
	});
}

export function useRemoveUserFromRole() {
	const queryClient = useQueryClient();

	return $api.useMutation("delete", "/api/roles/{role_id}/users/{user_id}", {
		onSuccess: (_, variables) => {
			const roleId = variables.params?.path?.role_id;
			queryClient.invalidateQueries({
				queryKey: ["roles", roleId, "users"],
			});
			toast.success("User removed", {
				description: "User has been removed from the role",
			});
		},
		onError: (error) => {
			const message = typeof error === "object" && error && "detail" in error
				? String(error.detail)
				: "Failed to remove user";
			toast.error("Failed to remove user", {
				description: message,
			});
		},
	});
}

export function useRoleForms(roleId: string | undefined) {
	return $api.useQuery("get", "/api/roles/{role_id}/forms",
		{ params: { path: { role_id: roleId ?? "" } } },
		{
			queryKey: ["roles", roleId, "forms"],
			enabled: !!roleId,
		},
	);
}

export function useAssignFormsToRole() {
	const queryClient = useQueryClient();

	return $api.useMutation("post", "/api/roles/{role_id}/forms", {
		onSuccess: (_, variables) => {
			const roleId = variables.params?.path?.role_id;
			const formIds = (variables.body as AssignFormsToRoleRequest)?.formIds || [];
			queryClient.invalidateQueries({
				queryKey: ["roles", roleId, "forms"],
			});
			toast.success("Forms assigned", {
				description: `${formIds.length} form(s) assigned to role`,
			});
		},
		onError: (error) => {
			const message = typeof error === "object" && error && "detail" in error
				? String(error.detail)
				: "Failed to assign forms";
			toast.error("Failed to assign forms", {
				description: message,
			});
		},
	});
}

/**
 * Assign roles to a form - imperative function using apiClient
 * This handles the form->roles relationship by assigning each role to the form
 */
export async function assignRolesToForm(formId: string, roleIds: string[]): Promise<void> {
	// Assign each role to this form
	for (const roleId of roleIds) {
		const { error } = await apiClient.POST("/api/roles/{role_id}/forms", {
			params: { path: { role_id: roleId } },
			body: { formIds: [formId] } as AssignFormsToRoleRequest,
		});
		if (error) throw new Error(`Failed to assign role to form: ${error}`);
	}
}

/**
 * Remove a form from a role
 * NOTE: Not implemented - the endpoint is not available in the API
 */
// export function useRemoveFormFromRole() {
// 	const queryClient = useQueryClient();

// 	return useMutation({
// 		mutationFn: ({ roleId, formId }: { roleId: string; formId: string }) =>
// 			rolesService.removeFormFromRole(roleId, formId),
// 		onSuccess: (_, variables) => {
// 			queryClient.invalidateQueries({
// 				queryKey: ["roles", variables.roleId, "forms"],
// 			});
// 			toast.success("Form removed", {
// 				description: "Form has been removed from the role",
// 			});
// 		},
// 		onError: (error: Error) => {
// 			toast.error("Failed to remove form", {
// 				description: error.message,
// 			});
// 		},
// 	});
// }
