/**
 * React Query hooks for workflows
 * Uses openapi-react-query for type-safe API calls
 */

import { useEffect, useMemo } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { $api, apiClient, withUserContext } from "@/lib/api-client";
import { useWorkflowsStore } from "@/stores/workflowsStore";
import type { components } from "@/lib/v1";

type WorkflowExecutionRequest =
	components["schemas"]["WorkflowExecutionRequest"];
type WorkflowValidationRequest =
	components["schemas"]["WorkflowValidationRequest"];

/**
 * Fetch all workflows.
 */
export function useWorkflows() {
	return $api.useQuery("get", "/api/workflows", {});
}

/**
 * Fetch workflows with optional entity filters and org scope.
 * Used by the Workflows page for sidebar filtering.
 *
 * @param options.scope - Organization scope filter (consistent with forms):
 *   - undefined: all workflows (platform admins only) - don't send scope param
 *   - null: global workflows only - send scope=global
 *   - UUID string: only that org's workflows (no global fallback)
 */
export function useWorkflowsFiltered(options?: {
	scope?: string | null;
	type?: string;
	filterByForm?: string;
	filterByApp?: string;
	filterByAgent?: string;
}) {
	// Build query params - scope is the filter parameter
	// undefined = don't send scope (show all)
	// null = send "global" (global only)
	// UUID = send the UUID (org only, no global)
	const queryParams: Record<string, string | undefined> = {};

	if (options?.scope === null) {
		queryParams.scope = "global";
	} else if (options?.scope !== undefined) {
		queryParams.scope = options.scope;
	}
	// undefined = don't send scope param (backend defaults to "all")

	if (options?.type) {
		queryParams.type = options.type;
	}

	return $api.useQuery("get", "/api/workflows", {
		params: {
			query: {
				scope: queryParams.scope,
				type: queryParams.type,
				filter_by_form: options?.filterByForm,
				filter_by_app: options?.filterByApp,
				filter_by_agent: options?.filterByAgent,
			},
		},
	});
}

/**
 * Update a workflow's properties (e.g., organization scope).
 * Platform admin only.
 *
 * Note: Uses direct fetch since the PATCH endpoint may not be in generated types yet.
 */
export function useUpdateWorkflow() {
	const queryClient = useQueryClient();

	return {
		mutateAsync: async (
			workflowId: string,
			organizationId: string | null,
		) => {
			// Use direct fetch since the PATCH endpoint might not be in generated types
			const response = await fetch(`/api/workflows/${workflowId}`, {
				method: "PATCH",
				headers: {
					"Content-Type": "application/json",
				},
				credentials: "include",
				body: JSON.stringify({ organization_id: organizationId }),
			});

			if (!response.ok) {
				const error = await response.json().catch(() => ({}));
				throw new Error(
					error.detail || `Failed to update workflow: ${response.status}`,
				);
			}

			const data = await response.json();

			// Invalidate workflows query to refresh the list
			queryClient.invalidateQueries({
				queryKey: ["get", "/api/workflows"],
			});

			return data;
		},
	};
}

/**
 * Fetch workflows that can be used as agent tools.
 * Uses the type="tool" query parameter for server-side filtering.
 */
export function useToolWorkflows() {
	return $api.useQuery("get", "/api/workflows", {
		params: { query: { type: "tool" } },
	});
}

/**
 * Fetch workflow metadata (includes all types: workflow, tool, data_provider).
 *
 * Note: Workflows are platform-wide resources (not org-scoped).
 * They are loaded from the file system and shared across all organizations.
 * The org scope only affects workflow EXECUTIONS (stored per-org), not the
 * workflows themselves.
 *
 * Data providers are now stored as workflows with type="data_provider".
 */
export function useWorkflowsMetadata() {
	const setWorkflows = useWorkflowsStore((state) => state.setWorkflows);

	// Fetch all workflows (includes type: workflow, tool, data_provider)
	const workflowsQuery = $api.useQuery("get", "/api/workflows", {});

	// Update Zustand store when workflows change
	// MUST be in useEffect to avoid infinite re-render loop
	// (setWorkflows updates lastUpdated, which triggers subscribers to re-render)
	useEffect(() => {
		if (workflowsQuery.data) {
			setWorkflows(workflowsQuery.data);
		}
	}, [workflowsQuery.data, setWorkflows]);

	// Memoize to prevent infinite re-render loops
	// (consumers depend on this object reference in useEffect deps)
	const data = useMemo(
		() => ({ workflows: workflowsQuery.data || [] }),
		[workflowsQuery.data],
	);

	return {
		data,
		isLoading: workflowsQuery.isLoading,
		isError: workflowsQuery.isError,
		error: workflowsQuery.error,
		refetch: workflowsQuery.refetch,
	};
}

export function useExecuteWorkflow() {
	return $api.useMutation("post", "/api/workflows/execute", {
		// Note: Error handling moved to RunPanel.tsx - errors shown in terminal
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
 * Execute a workflow with user context override (admin only)
 * Used when re-running executions from ExecutionDetails page
 *
 * @param workflowId - UUID of the workflow to execute (required if code not provided)
 * @param parameters - Input parameters for the workflow
 * @param transient - If true, skip database persistence (for debugging)
 * @param code - Optional Python code to execute instead of a workflow
 * @param scriptName - Name for the script (used for logging when code is provided)
 * @param options - Optional user context override (orgId is ignored, org filtering uses query params)
 */
export async function executeWorkflowWithContext(
	workflowId: string | undefined,
	parameters: Record<string, unknown>,
	transient?: boolean,
	code?: string,
	scriptName?: string,
	options?: { orgId?: string; userId?: string },
) {
	const client = options?.userId
		? withUserContext(options.userId)
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
