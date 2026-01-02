/**
 * Workflow Execution Modal for App Builder
 *
 * Shows a modal with WorkflowParametersForm when a workflow requires user input.
 * Used by the AppRenderer to collect parameters before workflow execution.
 */

import { useState, useCallback } from "react";
import {
	Dialog,
	DialogContent,
	DialogDescription,
	DialogHeader,
	DialogTitle,
} from "@/components/ui/dialog";
import { WorkflowParametersForm } from "@/components/workflows/WorkflowParametersForm";
import type { components } from "@/lib/v1";

type WorkflowMetadata = components["schemas"]["WorkflowMetadata"];
type WorkflowParameter = components["schemas"]["WorkflowParameter"];

interface PendingWorkflow {
	/** The workflow to execute */
	workflow: WorkflowMetadata;
	/** Parameters already provided (from action config, evaluated expressions) */
	providedParams: Record<string, unknown>;
	/** Callback when execution is confirmed */
	onExecute: (params: Record<string, unknown>) => Promise<void>;
	/** Callback when execution is cancelled */
	onCancel: () => void;
}

interface WorkflowExecutionModalProps {
	/** The pending workflow execution request, or null if no modal should show */
	pending: PendingWorkflow | null;
	/** Whether execution is in progress */
	isExecuting?: boolean;
}

/**
 * Determine which parameters still need user input
 *
 * Returns parameters that are:
 * - Required AND not provided, OR
 * - Optional but have no default and not provided
 *
 * Parameters that already have values in providedParams are excluded.
 */
function getMissingParameters(
	parameters: WorkflowParameter[] | undefined,
	providedParams: Record<string, unknown>,
): WorkflowParameter[] {
	if (!parameters) return [];

	return parameters.filter((param) => {
		const paramName = param.name ?? "";
		const hasProvidedValue = paramName in providedParams;

		// If we already have a value for this param, don't ask again
		if (hasProvidedValue) return false;

		// If it's required and not provided, we need it
		if (param.required) return true;

		// For optional params with no default, let user provide a value
		if (param.default_value === undefined) return true;

		return false;
	});
}

/**
 * Workflow Execution Modal Component
 *
 * Displays a dialog for collecting workflow parameters before execution.
 * Merges user-provided parameters with pre-configured parameters.
 *
 * @example
 * <WorkflowExecutionModal
 *   pending={{
 *     workflow: myWorkflow,
 *     providedParams: { row: { id: "123" } },
 *     onExecute: async (params) => executeWorkflow(params),
 *     onCancel: () => setPending(null),
 *   }}
 *   isExecuting={isExecuting}
 * />
 */
export function WorkflowExecutionModal({
	pending,
	isExecuting = false,
}: WorkflowExecutionModalProps) {
	// Form values state
	const [formValues, setFormValues] = useState<Record<string, unknown>>({});

	// Get the parameters that need user input
	const missingParams = pending
		? getMissingParameters(
				pending.workflow.parameters,
				pending.providedParams,
			)
		: [];

	// Handle form submission
	const handleExecute = useCallback(
		async (userParams: Record<string, unknown>) => {
			if (!pending) return;

			// Merge provided params with user-entered params
			// User params take precedence for any overlapping keys
			const mergedParams = {
				...pending.providedParams,
				...userParams,
			};

			await pending.onExecute(mergedParams);
		},
		[pending],
	);

	// Handle dialog open change (close on escape/click outside)
	const handleOpenChange = useCallback(
		(open: boolean) => {
			if (!open && pending) {
				pending.onCancel();
			}
		},
		[pending],
	);

	// Reset form values when modal opens with new workflow
	const handleFormValuesChange = useCallback(
		(values: Record<string, unknown>) => {
			setFormValues(values);
		},
		[],
	);

	if (!pending) return null;

	return (
		<Dialog open={true} onOpenChange={handleOpenChange}>
			<DialogContent className="max-w-md">
				<DialogHeader>
					<DialogTitle>{pending.workflow.name}</DialogTitle>
					{pending.workflow.description && (
						<DialogDescription>
							{pending.workflow.description}
						</DialogDescription>
					)}
				</DialogHeader>

				<WorkflowParametersForm
					parameters={missingParams}
					onExecute={handleExecute}
					isExecuting={isExecuting}
					showExecuteButton={true}
					executeButtonText="Execute"
					values={formValues}
					onChange={handleFormValuesChange}
				/>
			</DialogContent>
		</Dialog>
	);
}

export type { PendingWorkflow };
