/**
 * React Query hooks for workflows
 * Uses openapi-react-query for type-safe API calls
 */

import { useEffect, useMemo } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { $api, apiClient, withContext } from "@/lib/api-client";
import { getErrorMessage } from "@/lib/api-error";
import { toast } from "sonner";
import { useWorkflowsStore } from "@/stores/workflowsStore";
import type { components } from "@/lib/v1";

type WorkflowExecutionRequest =
	components["schemas"]["WorkflowExecutionRequest"];
type WorkflowValidationRequest =
	components["schemas"]["WorkflowValidationRequest"];

/**
 * Fetch workflow and data provider metadata.
 *
 * Note: Workflows and data providers are platform-wide resources (not org-scoped).
 * They are loaded from the file system and shared across all organizations.
 * The org scope only affects workflow EXECUTIONS (stored per-org), not the
 * workflows themselves.
 */
export function useWorkflowsMetadata() {
	const setWorkflows = useWorkflowsStore((state) => state.setWorkflows);

	// Fetch workflows
	const workflowsQuery = $api.useQuery("get", "/api/workflows", {});

	// Fetch data providers
	const dataProvidersQuery = $api.useQuery("get", "/api/data-providers", {});

	// Update Zustand store when workflows change
	// MUST be in useEffect to avoid infinite re-render loop
	// (setWorkflows updates lastUpdated, which triggers subscribers to re-render)
	useEffect(() => {
		if (workflowsQuery.data) {
			setWorkflows(workflowsQuery.data);
		}
	}, [workflowsQuery.data, setWorkflows]);

	// Memoize combined data to prevent infinite re-render loops
	// (consumers depend on this object reference in useEffect deps)
	const data = useMemo(
		() => ({
			workflows: workflowsQuery.data || [],
			dataProviders: dataProvidersQuery.data || [],
		}),
		[workflowsQuery.data, dataProvidersQuery.data],
	);

	// Return combined metadata with combined loading/error states
	return {
		data,
		isLoading: workflowsQuery.isLoading || dataProvidersQuery.isLoading,
		isError: workflowsQuery.isError || dataProvidersQuery.isError,
		error: workflowsQuery.error || dataProvidersQuery.error,
		refetch: () => {
			workflowsQuery.refetch();
			dataProvidersQuery.refetch();
		},
	};
}

export function useExecuteWorkflow() {
	return $api.useMutation("post", "/api/workflows/execute", {
		// Note: onSuccess toast removed - let caller handle toasts based on sync vs async
		// RunPanel shows different toasts for sync (immediate success) vs async (started)
		onError: (error) => {
			toast.error("Failed to execute workflow", {
				description: getErrorMessage(error, "Unknown error occurred"),
			});
		},
	});
}

/**
 * Incrementally reload a single workflow file
 * Used when a file is saved in the editor to update workflows store
 * without triggering a full workspace scan
 */
export function useReloadWorkflowFile() {
	const setWorkflows = useWorkflowsStore((state) => state.setWorkflows);
	const queryClient = useQueryClient();

	// Use a manual mutation that fetches workflows via apiClient
	return {
		mutate: async () => {
			try {
				const { data, error } = await apiClient.GET(
					"/api/workflows",
					{},
				);
				if (error) {
					console.error("Failed to reload workflow file:", error);
					return;
				}
				// Update store with refreshed workflow list
				if (data) {
					setWorkflows(data);
				}
				// Also invalidate the query cache
				queryClient.invalidateQueries({
					queryKey: ["get", "/api/workflows"],
				});
			} catch (error) {
				console.error("Failed to reload workflow file:", error);
				// Silent failure - don't show toast for background operations
			}
		},
	};
}

/**
 * Execute a workflow with context override (admin only)
 * Used when re-running executions from ExecutionDetails page
 *
 * @param workflowId - UUID of the workflow to execute (required if code not provided)
 * @param parameters - Input parameters for the workflow
 * @param transient - If true, skip database persistence (for debugging)
 * @param code - Optional Python code to execute instead of a workflow
 * @param scriptName - Name for the script (used for logging when code is provided)
 * @param options - Optional org/user context override
 */
export async function executeWorkflowWithContext(
	workflowId: string | undefined,
	parameters: Record<string, unknown>,
	transient?: boolean,
	code?: string,
	scriptName?: string,
	options?: { orgId?: string; userId?: string },
) {
	const client =
		options?.orgId && options?.userId
			? withContext(options.orgId, options.userId)
			: apiClient;

	const { data, error } = await client.POST("/api/workflows/execute", {
		body: {
			workflow_id: workflowId ?? null,
			input_data: parameters,
			form_id: null,
			transient: transient ?? false,
			code: code ?? null,
			script_name: scriptName ?? null,
		} as WorkflowExecutionRequest,
	});

	if (error) throw new Error(`Failed to execute workflow: ${error}`);
	return data!;
}

/**
 * Validate a workflow file for syntax errors and decorator issues
 * @param path - Relative workspace path to the workflow file
 * @param content - Optional file content to validate (if not provided, reads from disk)
 */
export async function validateWorkflow(path: string, content?: string) {
	const { data, error } = await apiClient.POST("/api/workflows/validate", {
		body: {
			path,
			content: content ?? null,
		} as WorkflowValidationRequest,
	});

	if (error) throw new Error(`Failed to validate workflow: ${error}`);
	return data!;
}
