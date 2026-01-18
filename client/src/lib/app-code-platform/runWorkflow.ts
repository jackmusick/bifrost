/**
 * Platform function: runWorkflow
 *
 * Executes a workflow by ID and returns the result.
 * Used for mutations or one-off workflow calls.
 * For data fetching with loading/error states, use useWorkflow hook instead.
 */

import { apiClient } from "@/lib/api-client";

/**
 * Execute a workflow and return the result
 *
 * @param workflowId - The workflow ID or name to execute
 * @param params - Optional parameters to pass to the workflow
 * @returns The workflow result data
 * @throws Error if workflow execution fails
 *
 * @example
 * ```jsx
 * // In a button click handler
 * const handleSave = async () => {
 *   try {
 *     await runWorkflow('update_client', { id: clientId, name: newName });
 *     toast.success('Saved!');
 *   } catch (error) {
 *     toast.error('Failed to save');
 *   }
 * };
 * ```
 */
export async function runWorkflow<T = unknown>(
	workflowId: string,
	params?: Record<string, unknown>,
): Promise<T> {
	const { data, error } = await apiClient.POST("/api/workflows/execute", {
		body: {
			workflow_id: workflowId,
			input_data: params ?? {},
			form_id: null,
			transient: false,
			code: null,
			script_name: null,
		},
	});

	if (error) {
		const errorMessage =
			typeof error === "object" && error !== null && "detail" in error
				? String((error as { detail: unknown }).detail)
				: "Workflow execution failed";
		throw new Error(errorMessage);
	}

	if (!data) {
		throw new Error("No response from workflow execution");
	}

	// Return the result field from the execution response
	return data.result as T;
}
