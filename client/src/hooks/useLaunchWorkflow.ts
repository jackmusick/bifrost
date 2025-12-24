/**
 * Hook to execute launch workflow on form load
 *
 * When a form has a launchWorkflowId, this hook:
 * 1. Executes the workflow when the form loads
 * 2. Extracts results into form context
 * 3. Enables field visibility based on workflow results
 */

import { useEffect, useMemo } from "react";
import { useFormContext } from "@/contexts/FormContext";
import { executeFormStartup } from "@/hooks/useForms";
import type { components } from "@/lib/v1";

type Form = components["schemas"]["FormPublic"];

interface UseLaunchWorkflowOptions {
	form: Form;
	/** Additional parameters to pass to launch workflow */
	workflowParams?: Record<string, unknown>;
}

/**
 * Execute launch workflow if form has launchWorkflowId
 */
export function useLaunchWorkflow({
	form,
	workflowParams = {},
}: UseLaunchWorkflowOptions) {
	const { context, setWorkflowResults, setIsLoadingLaunchWorkflow } =
		useFormContext();

	// Memoize serialized objects for dependency comparison
	const serializedQuery = useMemo(
		() => JSON.stringify(context.query),
		[context.query],
	);
	const serializedParams = useMemo(
		() => JSON.stringify(workflowParams),
		[workflowParams],
	);

	useEffect(() => {
		// Only execute if form has a launch workflow configured
		if (!form.launch_workflow_id) {
			return;
		}

		const executeLaunchWorkflow = async () => {
			try {
				setIsLoadingLaunchWorkflow(true);

				// Merge default launch params with provided params
				// Using workflowParams from closure (serializedParams ensures correct deps)
				const inputData = {
					...(form.default_launch_params || {}),
					...workflowParams,
				};

				// Execute the startup workflow
				const response = await executeFormStartup(form.id, inputData);

				// Set workflow results in context (or empty object if no result)
				setWorkflowResults(
					(response.result as Record<string, unknown>) || {},
				);
			} catch (error) {
				console.error("Failed to execute launch workflow:", error);
				// Set empty results on error so form still works
				setWorkflowResults({});
			} finally {
				setIsLoadingLaunchWorkflow(false);
			}
		};

		executeLaunchWorkflow();
		// eslint-disable-next-line react-hooks/exhaustive-deps
	}, [
		form.id,
		form.launch_workflow_id,
		form.default_launch_params,
		serializedQuery,
		serializedParams, // Serialized to track changes without object identity issues
		setWorkflowResults,
		setIsLoadingLaunchWorkflow,
	]);
}
