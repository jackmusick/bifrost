/**
 * Page Data Loading Hook
 *
 * Manages data sources and launch workflow execution for App Builder pages.
 * Handles loading data on page mount and provides refresh functionality.
 */

import { useState, useEffect, useCallback, useMemo, useRef } from "react";
import { toast } from "sonner";
import { apiClient } from "@/lib/api-client";
import type {
	DataSource,
	PageDefinition,
	WorkflowResult,
	ExpressionContext,
} from "@/lib/app-builder-types";
import { evaluateExpression } from "@/lib/expression-parser";

interface PageDataState {
	/** Data loaded from data sources, keyed by data source ID */
	data: Record<string, unknown>;
	/** Whether data is currently loading */
	isLoading: boolean;
	/** Whether launch workflow is executing */
	isLaunchWorkflowLoading: boolean;
	/** Any error that occurred during loading */
	error: Error | null;
	/** Result from launch workflow (available as {{ workflow.* }}) */
	launchWorkflowResult: WorkflowResult | undefined;
}

interface UsePageDataOptions {
	/** The page definition with data sources and launch workflow */
	page: PageDefinition | null;
	/** Base expression context for evaluating input params */
	baseContext: Partial<ExpressionContext>;
	/** Callback to execute a workflow */
	executeWorkflow: (
		workflowId: string,
		params: Record<string, unknown>,
	) => Promise<WorkflowResult | undefined>;
	/** Callback to execute a data provider */
	executeDataProvider?: (
		providerId: string,
		params: Record<string, unknown>,
	) => Promise<unknown>;
}

interface UsePageDataResult extends PageDataState {
	/** Refresh a specific data source by ID */
	refreshDataSource: (dataSourceId: string) => Promise<void>;
	/** Refresh all data sources */
	refreshAll: () => Promise<void>;
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
 * Hook for loading and managing page data
 *
 * Handles:
 * - Launch workflow execution on page mount
 * - Data source loading (data providers, workflows, static, API)
 * - Expression evaluation for input parameters
 * - Data refresh functionality
 *
 * @example
 * const { data, isLoading, launchWorkflowResult, refreshDataSource } = usePageData({
 *   page: currentPage,
 *   baseContext: { user, variables, query },
 *   executeWorkflow: handleExecuteWorkflow,
 * });
 */
export function usePageData({
	page,
	baseContext,
	executeWorkflow,
	executeDataProvider,
}: UsePageDataOptions): UsePageDataResult {
	const [state, setState] = useState<PageDataState>({
		data: {},
		isLoading: false,
		isLaunchWorkflowLoading: false,
		error: null,
		launchWorkflowResult: undefined,
	});

	// Track whether initial data load has occurred to prevent infinite loops
	const hasLoadedRef = useRef(false);

	// Ref to hold current executeWorkflow function - prevents effect re-triggers
	// when the callback reference changes due to upstream dependency changes
	const executeWorkflowRef = useRef(executeWorkflow);

	// Keep ref in sync with latest function
	useEffect(() => {
		executeWorkflowRef.current = executeWorkflow;
	}, [executeWorkflow]);
	const pageId = page?.id;

	// Reset loaded flag when page changes
	useEffect(() => {
		hasLoadedRef.current = false;
	}, [pageId]);

	// Build expression context including loaded data
	const expressionContext = useMemo(
		(): Partial<ExpressionContext> => ({
			...baseContext,
			data: state.data,
			workflow: state.launchWorkflowResult,
		}),
		[baseContext, state.data, state.launchWorkflowResult],
	);

	// Load a single data source
	const loadDataSource = useCallback(
		async (dataSource: DataSource): Promise<unknown> => {
			// Support both 'inputParams' (canonical) and 'params' (shorthand) for data sources
			const inputParams =
				dataSource.inputParams ??
				(dataSource as unknown as { params?: Record<string, unknown> })
					.params;
			const params = evaluateInputParams(inputParams, expressionContext);

			switch (dataSource.type) {
				case "static":
					return dataSource.data;

				case "data-provider":
					if (!dataSource.dataProviderId) {
						console.warn(
							`Data source "${dataSource.id}" has no dataProviderId`,
						);
						return null;
					}
					if (executeDataProvider) {
						return executeDataProvider(
							dataSource.dataProviderId,
							params,
						);
					}
					// Fall back to API call via /execute endpoint
					try {
						const response = await apiClient.POST(
							"/api/workflows/execute",
							{
								body: {
									workflow_id: dataSource.dataProviderId,
									input_data: params,
									transient: true, // Data providers are transient
								},
							},
						);
						// Data providers return options in result field
						return response.data?.result ?? null;
					} catch (error) {
						console.error(
							`Failed to load data provider "${dataSource.dataProviderId}":`,
							error,
						);
						toast.error(
							`Failed to load data: ${error instanceof Error ? error.message : "Unknown error"}`,
						);
						return null;
					}

				case "workflow":
					if (!dataSource.workflowId) {
						console.warn(
							`Data source "${dataSource.id}" has no workflowId`,
						);
						return null;
					}
					try {
						const result = await executeWorkflow(
							dataSource.workflowId,
							params,
						);
						return result?.result ?? null;
					} catch (error) {
						console.error(
							`Failed to execute workflow "${dataSource.workflowId}":`,
							error,
						);
						toast.error(
							`Failed to load data: ${error instanceof Error ? error.message : "Unknown error"}`,
						);
						return null;
					}

				case "api":
					if (!dataSource.endpoint) {
						console.warn(
							`Data source "${dataSource.id}" has no endpoint`,
						);
						return null;
					}
					try {
						const response = await fetch(dataSource.endpoint);
						return response.json();
					} catch (error) {
						console.error(
							`Failed to fetch "${dataSource.endpoint}":`,
							error,
						);
						toast.error(
							`Failed to load data: ${error instanceof Error ? error.message : "Unknown error"}`,
						);
						return null;
					}

				case "computed":
					if (!dataSource.expression) {
						console.warn(
							`Data source "${dataSource.id}" has no expression`,
						);
						return null;
					}
					return evaluateExpression(
						dataSource.expression,
						expressionContext as ExpressionContext,
					);

				default:
					console.warn(
						`Unknown data source type: ${dataSource.type}`,
					);
					return null;
			}
		},
		[expressionContext, executeDataProvider, executeWorkflow],
	);

	// Refresh a specific data source
	const refreshDataSource = useCallback(
		async (dataSourceId: string) => {
			if (!page?.dataSources) return;

			const dataSource = page.dataSources.find(
				(ds) => ds.id === dataSourceId,
			);
			if (!dataSource) {
				console.warn(`Data source "${dataSourceId}" not found`);
				return;
			}

			try {
				const result = await loadDataSource(dataSource);
				setState((prev) => ({
					...prev,
					data: { ...prev.data, [dataSourceId]: result },
				}));
			} catch (error) {
				console.error(
					`Failed to refresh data source "${dataSourceId}":`,
					error,
				);
				toast.error(
					`Failed to refresh data: ${error instanceof Error ? error.message : "Unknown error"}`,
				);
			}
		},
		[page, loadDataSource],
	);

	// Refresh all data sources
	const refreshAll = useCallback(async () => {
		if (!page?.dataSources?.length) return;

		setState((prev) => ({ ...prev, isLoading: true }));

		try {
			const results = await Promise.all(
				page.dataSources.map(async (ds) => ({
					id: ds.id,
					data: await loadDataSource(ds),
				})),
			);

			const data: Record<string, unknown> = {};
			for (const { id, data: result } of results) {
				data[id] = result;
			}

			setState((prev) => ({ ...prev, data, isLoading: false }));
		} catch (error) {
			setState((prev) => ({
				...prev,
				isLoading: false,
				error:
					error instanceof Error
						? error
						: new Error("Failed to load data"),
			}));
		}
	}, [page, loadDataSource]);

	// Execute launch workflow on page mount
	// Support both flat format (launchWorkflowId) and nested format (launchWorkflow.workflowId)
	const launchWorkflowId =
		page?.launchWorkflowId ?? page?.launchWorkflow?.workflowId;
	const launchWorkflowParams =
		page?.launchWorkflowParams ?? page?.launchWorkflow?.params;

	// Create stable key for route params to avoid infinite loops
	// baseContext is an object that changes reference on each render,
	// so we extract just the params as a stable string for dependency tracking
	const routeParamsKey = JSON.stringify(baseContext.params || {});

	useEffect(() => {
		if (!launchWorkflowId) return;

		let cancelled = false;

		const executeLaunchWorkflow = async () => {
			setState((prev) => ({ ...prev, isLaunchWorkflowLoading: true }));

			try {
				const params = evaluateInputParams(
					launchWorkflowParams,
					baseContext,
				);
				// Use ref.current to avoid effect re-triggers when callback reference changes
				const result = await executeWorkflowRef.current(
					launchWorkflowId,
					params,
				);

				if (!cancelled) {
					setState((prev) => ({
						...prev,
						isLaunchWorkflowLoading: false,
						launchWorkflowResult: result,
					}));
				}
			} catch (error) {
				if (!cancelled) {
					console.error("Launch workflow failed:", error);
					toast.error(
						`Failed to initialize page: ${error instanceof Error ? error.message : "Unknown error"}`,
					);
					setState((prev) => ({
						...prev,
						isLaunchWorkflowLoading: false,
						error:
							error instanceof Error
								? error
								: new Error("Launch workflow failed"),
					}));
				}
			}
		};

		executeLaunchWorkflow();

		return () => {
			cancelled = true;
		};
		// Note: baseContext, launchWorkflowParams, and executeWorkflow are used inside but
		// excluded from deps to prevent infinite loops. We use:
		// - routeParamsKey: stable string for route param values
		// - executeWorkflowRef: ref pattern for stable callback access
		// eslint-disable-next-line react-hooks/exhaustive-deps
	}, [launchWorkflowId, routeParamsKey]);

	// Load data sources on page mount (after launch workflow completes if present)
	// Note: refreshAll is intentionally excluded from deps to prevent infinite loops.
	// The hasLoadedRef ensures this only runs once per page.
	useEffect(() => {
		if (!page?.dataSources?.length) return;
		// Wait for launch workflow to complete if present
		if (launchWorkflowId && state.isLaunchWorkflowLoading) return;
		// Prevent re-runs after initial load (breaks dependency cycle)
		if (hasLoadedRef.current) return;

		hasLoadedRef.current = true;
		refreshAll();
		// eslint-disable-next-line react-hooks/exhaustive-deps
	}, [page, state.isLaunchWorkflowLoading]);

	return {
		...state,
		refreshDataSource,
		refreshAll,
	};
}

export default usePageData;
