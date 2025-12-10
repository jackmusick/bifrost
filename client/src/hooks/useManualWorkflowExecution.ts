/**
 * Hook for manually executing workflows in the form builder
 * Used for testing launch workflows before form publication
 */

import { $api } from "@/lib/api-client";
import { getErrorMessage } from "@/lib/api-error";
import { toast } from "sonner";

/**
 * Execute a workflow manually and return its results
 * Useful for testing launch workflows in the form builder
 */
export function useManualWorkflowExecution() {
	return $api.useMutation("post", "/api/workflows/execute", {
		onError: (error) => {
			toast.error("Failed to execute workflow", {
				description: getErrorMessage(error, "Unknown error occurred"),
			});
		},
	});
}
