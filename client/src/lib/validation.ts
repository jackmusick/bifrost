import { validateWorkflow } from "@/hooks/useWorkflows";
import { useEditorStore } from "@/stores/editorStore";
import { queryClient } from "@/lib/queryClient";
import { useScopeStore } from "@/stores/scopeStore";
import type { components } from "@/lib/v1";

type WorkflowValidationResponse =
	components["schemas"]["WorkflowValidationResponse"];
type ValidationIssue = components["schemas"]["ValidationIssue"];

/**
 * Silently validates a Python workflow file and updates the Run panel.
 * Errors are logged to the terminal, but no success toasts are shown.
 * After successful validation, invalidates the workflow metadata cache to refresh the Run panel.
 */
export async function silentValidateWorkflow(
	filePath: string,
	fileContent?: string,
): Promise<void> {
	// Only validate Python files
	if (!filePath.endsWith(".py")) {
		return;
	}

	try {
		const result: WorkflowValidationResponse =
			await validateWorkflow(filePath, fileContent);

		// Always log to terminal (errors and success)
		const errors = (result.issues || []).filter(
			(i: ValidationIssue) => i.severity === "error",
		);
		const warnings = (result.issues || []).filter(
			(i: ValidationIssue) => i.severity === "warning",
		);

		// Build terminal output with validation results
		const loggerOutput: Array<{
			level: string;
			message: string;
			source: string;
		}> = [];

		if (result.valid && result.metadata) {
			// Success message
			loggerOutput.push({
				level: "INFO",
				message: `Workflow "${result.metadata.name}" validated successfully`,
				source: "validation",
			});
		} else if (errors.length > 0 || warnings.length > 0) {
			// Error/warning messages
			loggerOutput.push({
				level: "ERROR",
				message: "Workflow validation failed:",
				source: "validation",
			});

			errors.forEach((issue: ValidationIssue) => {
				const lineInfo = issue.line ? ` (line ${issue.line})` : "";
				loggerOutput.push({
					level: "ERROR",
					message: `  ${issue.message}${lineInfo}`,
					source: "validation",
				});
			});

			warnings.forEach((issue: ValidationIssue) => {
				const lineInfo = issue.line ? ` (line ${issue.line})` : "";
				loggerOutput.push({
					level: "WARNING",
					message: `  ${issue.message}${lineInfo}`,
					source: "validation",
				});
			});
		}

		// Append to terminal
		useEditorStore.getState().appendTerminalOutput({
			loggerOutput,
			variables: {},
			status: result.valid ? "completed" : "failed",
			error: result.valid ? undefined : "Validation failed",
		});

		// Invalidate query cache to refresh Run panel if validation succeeded
		if (result.valid) {
			const orgId = useScopeStore.getState().scope.orgId;
			// Use the exact same invalidation as the manual validate button
			await queryClient.invalidateQueries({
				queryKey: ["workflows", "metadata", orgId],
			});
		}
	} catch (error) {
		// Log validation API errors to terminal
		useEditorStore.getState().appendTerminalOutput({
			loggerOutput: [
				{
					level: "ERROR",
					message: `Validation error: ${error instanceof Error ? error.message : String(error)}`,
					source: "validation",
				},
			],
			variables: {},
			status: "failed",
			error: error instanceof Error ? error.message : String(error),
		});
	}
}
