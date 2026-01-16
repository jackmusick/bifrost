/**
 * Page Data Loading Hook
 *
 * Manages launch workflow execution for App Builder pages.
 * Access data via {{ workflow.<dataSourceId> }}
 */

import { useState, useEffect, useRef, useCallback } from "react";
import { toast } from "sonner";
import type {
	PageDefinition,
	WorkflowResult,
	ExpressionContext,
} from "@/types/app-builder";
import { evaluateExpression } from "@/lib/expression-parser";

interface PageDataState {
	/** Whether the launch workflow is executing */
	isLoading: boolean;
	/** Any error that occurred during loading */
	error: Error | null;
	/**
	 * Workflow results keyed by dataSourceId.
	 * Access via {{ workflow.<dataSourceId> }}
	 */
	workflow: Record<string, unknown>;
}

interface UsePageDataOptions {
	/** The page definition with launch workflow configuration */
	page: PageDefinition | null;
	/** Base expression context for evaluating input params */
	baseContext: Partial<ExpressionContext>;
	/** Callback to execute a workflow */
	executeWorkflow: (
		workflowId: string,
		params: Record<string, unknown>,
	) => Promise<WorkflowResult | undefined>;
}

interface UsePageDataResult extends PageDataState {
	/** Re-execute the launch workflow to refresh data */
	refresh: () => Promise<void>;
}

/**
 * Evaluate input parameters using expression context
 */
function evaluateInputParams(
	params: Record<string, unknown> | undefined,
	context: Partial<ExpressionContext>,
): Record<string, unknown> {
	if (!params) return {};

	const evaluated: Record<string, unknown> = {};
	for (const [key, value] of Object.entries(params)) {
		if (typeof value === "string" && value.includes("{{")) {
			evaluated[key] = evaluateExpression(
				value,
				context as ExpressionContext,
			);
		} else {
			evaluated[key] = value;
		}
	}
	return evaluated;
}

/**
 * Hook for loading page data via launch workflow
 *
 * Pages configure data loading with:
 * - launch_workflow_id: The workflow to execute on page mount
 * - launch_workflow_params: Parameters to pass (supports expressions like {{ params.id }})
 * - launch_workflow_data_source_id: Key name for accessing results (defaults to workflow name)
 *
 * @example
 * const { isLoading, workflow, refresh } = usePageData({
 *   page: currentPage,
 *   baseContext: { user, variables, params },
 *   executeWorkflow: handleExecuteWorkflow,
 * });
 *
 * // Access data: workflow.clientsList.clients
 */
export function usePageData({
	page,
	baseContext,
	executeWorkflow,
}: UsePageDataOptions): UsePageDataResult {
	const [state, setState] = useState<PageDataState>({
		isLoading: false,
		error: null,
		workflow: {},
	});

	// Ref to hold current executeWorkflow function - prevents effect re-triggers
	const executeWorkflowRef = useRef(executeWorkflow);

	// Keep ref in sync with latest function
	useEffect(() => {
		executeWorkflowRef.current = executeWorkflow;
	}, [executeWorkflow]);

	const pageId = page?.id;

	// Get launch workflow config (flat or nested format)
	// Note: API returns null/undefined, but evaluateInputParams expects undefined
	const launchWorkflowId =
		page?.launch_workflow_id ?? page?.launch_workflow?.workflow_id;
	const launchWorkflowParams =
		(page?.launch_workflow_params ?? page?.launch_workflow?.params) ?? undefined;
	const launchWorkflowDataSourceId =
		page?.launch_workflow_data_source_id ?? page?.launch_workflow?.data_source_id ?? undefined;

	// Create stable key for route params to avoid infinite loops
	const routeParamsKey = JSON.stringify(baseContext.params || {});

	// Execute the launch workflow
	const executeLaunchWorkflow = useCallback(async () => {
		if (!launchWorkflowId) return;

		setState((prev) => ({ ...prev, isLoading: true }));

		try {
			const params = evaluateInputParams(launchWorkflowParams, baseContext);
			const result = await executeWorkflowRef.current(
				launchWorkflowId,
				params,
			);

			if (result) {
				// Use dataSourceId if provided, otherwise fall back to workflow name
				const dataSourceKey =
					launchWorkflowDataSourceId ||
					result.workflowName ||
					"default";

				setState((prev) => ({
					...prev,
					isLoading: false,
					workflow: {
						...prev.workflow,
						[dataSourceKey]: result.result,
					},
				}));
			} else {
				setState((prev) => ({ ...prev, isLoading: false }));
			}
		} catch (error) {
			console.error("Launch workflow failed:", error);
			toast.error(
				`Failed to load page data: ${error instanceof Error ? error.message : "Unknown error"}`,
			);
			setState((prev) => ({
				...prev,
				isLoading: false,
				error:
					error instanceof Error
						? error
						: new Error("Launch workflow failed"),
			}));
		}
	}, [launchWorkflowId, launchWorkflowParams, launchWorkflowDataSourceId, baseContext]);

	// Execute on mount and when route params change
	useEffect(() => {
		if (!launchWorkflowId) {
			return;
		}

		let cancelled = false;

		const run = async () => {
			setState((prev) => ({ ...prev, isLoading: true }));

			try {
				const params = evaluateInputParams(
					launchWorkflowParams,
					baseContext,
				);

				const result = await executeWorkflowRef.current(
					launchWorkflowId,
					params,
				);

				if (!cancelled && result) {
					const dataSourceKey =
						launchWorkflowDataSourceId ||
						result.workflowName ||
						"default";

					setState((prev) => ({
						...prev,
						isLoading: false,
						workflow: {
							...prev.workflow,
							[dataSourceKey]: result.result,
						},
					}));
				} else if (!cancelled) {
					setState((prev) => ({ ...prev, isLoading: false }));
				}
			} catch (error) {
				if (!cancelled) {
					console.error("Launch workflow failed:", error);
					toast.error(
						`Failed to load page data: ${error instanceof Error ? error.message : "Unknown error"}`,
					);
					setState((prev) => ({
						...prev,
						isLoading: false,
						error:
							error instanceof Error
								? error
								: new Error("Launch workflow failed"),
					}));
				}
			}
		};

		run();

		return () => {
			cancelled = true;
		};
		// eslint-disable-next-line react-hooks/exhaustive-deps
	}, [launchWorkflowId, routeParamsKey, pageId]);

	// Refresh handler - re-executes launch workflow
	const refresh = useCallback(async () => {
		await executeLaunchWorkflow();
	}, [executeLaunchWorkflow]);

	return {
		...state,
		refresh,
	};
}

export default usePageData;
