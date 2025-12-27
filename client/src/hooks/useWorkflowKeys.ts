/**
 * React Query hooks for workflow key management
 * Uses org scope for cache key differentiation
 */

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
	workflowKeysService,
	type WorkflowKeyCreateRequest,
} from "@/services/workflowKeys";
import { toast } from "sonner";
import { useScopeStore } from "@/stores/scopeStore";

export function useWorkflowKeys(params?: {
	workflowId?: string;
	includeRevoked?: boolean;
}) {
	const orgId = useScopeStore((state) => state.scope.orgId);

	return useQuery({
		queryKey: ["workflow-keys", orgId, params],
		queryFn: () => workflowKeysService.listWorkflowKeys(params),
		// Don't use cached data from previous scope
		staleTime: 0,
		// Always refetch when component mounts (navigating to page)
		refetchOnMount: "always",
		meta: {
			onError: (error: Error) => {
				toast.error("Failed to load workflow keys", {
					description: error.message,
				});
			},
		},
	});
}

export function useCreateWorkflowKey() {
	const queryClient = useQueryClient();

	return useMutation({
		mutationFn: (data: WorkflowKeyCreateRequest) =>
			workflowKeysService.createWorkflowKey(data),
		onSuccess: () => {
			queryClient.invalidateQueries({ queryKey: ["workflow-keys"] });
			// Don't show generic success toast - component will handle showing the key
		},
		onError: (error: Error) => {
			toast.error("Failed to create workflow key", {
				description: error.message,
			});
		},
	});
}

export function useRevokeWorkflowKey() {
	const queryClient = useQueryClient();

	return useMutation({
		mutationFn: (keyId: string) =>
			workflowKeysService.revokeWorkflowKey(keyId),
		onSuccess: () => {
			queryClient.invalidateQueries({ queryKey: ["workflow-keys"] });
			toast.success("Workflow key revoked", {
				description:
					"The API key has been revoked and can no longer be used",
			});
		},
		onError: (error: Error) => {
			toast.error("Failed to revoke workflow key", {
				description: error.message,
			});
		},
	});
}
