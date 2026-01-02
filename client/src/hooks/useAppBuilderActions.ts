/**
 * App Builder Actions Hook
 *
 * Provides action handlers for App Builder applications:
 * - navigate: Navigate to a page within the app
 * - setVariable: Set a runtime variable
 * - executeWorkflow: Trigger a workflow execution
 * - refreshTable: Refresh a data table's data source
 * - openModal: Open a modal (for forms, confirmations, etc.)
 */

import { useCallback, useMemo } from "react";
import { useNavigate as useRouterNavigate } from "react-router-dom";
import { toast } from "sonner";
import { useAppBuilderStore } from "@/stores/app-builder.store";
import type { ExpressionContext } from "@/lib/app-builder-types";

/**
 * Generate a unique execution ID
 */
function generateExecutionId(): string {
	return `exec_${Date.now()}_${Math.random().toString(36).slice(2, 9)}`;
}

/**
 * Options for workflow execution
 */
interface ExecuteWorkflowOptions {
	/** Input parameters for the workflow */
	input?: Record<string, unknown>;
	/** Show toast on success */
	showSuccessToast?: boolean;
	/** Show toast on error */
	showErrorToast?: boolean;
	/** Callback on success */
	onSuccess?: (result: unknown) => void;
	/** Callback on error */
	onError?: (error: string) => void;
}

/**
 * Action handlers returned by the hook
 */
interface AppBuilderActions {
	/** Navigate to a page path within the app */
	navigate: (path: string) => void;
	/** Set a runtime variable */
	setVariable: (name: string, value: unknown) => void;
	/** Execute a workflow by ID */
	executeWorkflow: (
		workflowId: string,
		options?: ExecuteWorkflowOptions,
	) => Promise<void>;
	/** Trigger a data source refresh */
	refreshDataSource: (key: string) => void;
	/** Select a table row */
	selectRow: (tableId: string, rowId: string) => void;
	/** Deselect a table row */
	deselectRow: (tableId: string, rowId: string) => void;
	/** Clear all selections for a table */
	clearSelectedRows: (tableId: string) => void;
}

/**
 * Hook options
 */
interface UseAppBuilderActionsOptions {
	/** Base path for the app (e.g., /apps/my-app) */
	basePath?: string;
	/** Callback to execute workflow via API */
	onExecuteWorkflow?: (
		workflowId: string,
		input?: Record<string, unknown>,
	) => Promise<unknown>;
}

/**
 * Hook for App Builder action handlers
 *
 * Provides a set of action handlers that can be passed to the expression
 * context and used by components within the App Builder.
 *
 * @example
 * ```tsx
 * const actions = useAppBuilderActions({
 *   basePath: "/apps/my-app",
 *   onExecuteWorkflow: async (workflowId, input) => {
 *     return await api.executeWorkflow(workflowId, input);
 *   },
 * });
 *
 * // Use in expression context
 * const context: ExpressionContext = {
 *   ...otherContext,
 *   navigate: actions.navigate,
 *   setVariable: actions.setVariable,
 *   triggerWorkflow: actions.executeWorkflow,
 * };
 * ```
 */
export function useAppBuilderActions(
	options: UseAppBuilderActionsOptions = {},
): AppBuilderActions {
	const { basePath = "", onExecuteWorkflow } = options;

	const routerNavigate = useRouterNavigate();
	const store = useAppBuilderStore();

	// Navigate to a page within the app
	const navigate = useCallback(
		(path: string) => {
			// Handle absolute vs relative paths
			const fullPath = path.startsWith("/")
				? `${basePath}${path}`
				: `${basePath}/${path}`;

			routerNavigate(fullPath);
		},
		[basePath, routerNavigate],
	);

	// Set a runtime variable
	const setVariable = useCallback(
		(name: string, value: unknown) => {
			store.setVariable(name, value);
		},
		[store],
	);

	// Execute a workflow
	const executeWorkflow = useCallback(
		async (
			workflowId: string,
			execOptions: ExecuteWorkflowOptions = {},
		) => {
			const {
				input,
				showSuccessToast = true,
				showErrorToast = true,
				onSuccess,
				onError,
			} = execOptions;

			const executionId = generateExecutionId();

			// Start tracking execution
			store.startExecution(executionId, workflowId, input);

			try {
				if (!onExecuteWorkflow) {
					throw new Error("Workflow execution not configured");
				}

				const result = await onExecuteWorkflow(workflowId, input);

				// Mark as complete
				store.completeExecution(executionId, result);

				if (showSuccessToast) {
					toast.success("Workflow completed successfully");
				}

				onSuccess?.(result);
			} catch (error) {
				const errorMessage =
					error instanceof Error
						? error.message
						: "Workflow execution failed";

				// Mark as failed
				store.failExecution(executionId, errorMessage);

				if (showErrorToast) {
					toast.error(errorMessage);
				}

				onError?.(errorMessage);
			}
		},
		[onExecuteWorkflow, store],
	);

	// Refresh a data source
	const refreshDataSource = useCallback(
		(key: string) => {
			store.refreshDataSource(key);
		},
		[store],
	);

	// Table row selection
	const selectRow = useCallback(
		(tableId: string, rowId: string) => {
			store.selectRow(tableId, rowId);
		},
		[store],
	);

	const deselectRow = useCallback(
		(tableId: string, rowId: string) => {
			store.deselectRow(tableId, rowId);
		},
		[store],
	);

	const clearSelectedRows = useCallback(
		(tableId: string) => {
			store.clearSelectedRows(tableId);
		},
		[store],
	);

	return useMemo(
		() => ({
			navigate,
			setVariable,
			executeWorkflow,
			refreshDataSource,
			selectRow,
			deselectRow,
			clearSelectedRows,
		}),
		[
			navigate,
			setVariable,
			executeWorkflow,
			refreshDataSource,
			selectRow,
			deselectRow,
			clearSelectedRows,
		],
	);
}

/**
 * Additional context options for expression evaluation
 */
interface ExpressionContextOptions {
	/** Current user information */
	user?: ExpressionContext["user"];
	/** Page-level variables */
	variables?: Record<string, unknown>;
	/** Data from data sources */
	data?: Record<string, unknown>;
}

/**
 * Create an expression context with action handlers
 *
 * Utility function to create a complete expression context for
 * evaluating expressions within App Builder components.
 */
export function createExpressionContext(
	actions: AppBuilderActions,
	options: ExpressionContextOptions = {},
): ExpressionContext {
	return {
		user: options.user,
		variables: options.variables ?? {},
		data: options.data ?? {},
		navigate: actions.navigate,
		triggerWorkflow: (workflowId, input) =>
			actions.executeWorkflow(workflowId, { input }),
	};
}
