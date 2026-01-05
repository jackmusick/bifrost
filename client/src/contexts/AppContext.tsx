/**
 * App Builder Context
 *
 * Provides expression context to the component tree for the App Builder.
 * Manages page variables, user info, and navigation functions.
 */

import {
	createContext,
	useContext,
	useMemo,
	useCallback,
	useState,
	useEffect,
	type ReactNode,
} from "react";
import { useNavigate } from "react-router-dom";
import type {
	ExpressionContext,
	ExpressionUser,
	WorkflowResult,
	OnCompleteAction,
} from "@/lib/app-builder-types";
import { useAuth } from "./AuthContext";

/**
 * Value provided by the AppContext
 */
interface AppContextValue {
	/** The expression context for evaluating expressions */
	context: ExpressionContext;
	/** Update a page variable */
	setVariable: (key: string, value: unknown) => void;
	/** Update multiple page variables */
	setVariables: (updates: Record<string, unknown>) => void;
	/** Set data from a data source */
	setData: (key: string, data: unknown) => void;
	/** Set a field value (for form inputs) */
	setFieldValue: (fieldId: string, value: unknown) => void;
	/** Get all field values (for form submission) */
	getFieldValues: () => Record<string, unknown>;
	/** Clear all field values */
	clearFieldValues: () => void;
	/** Register a custom action handler */
	registerCustomAction: (
		actionId: string,
		handler: (params?: Record<string, unknown>) => void,
	) => void;
	/** Set workflow result (for {{ workflow.result.* }} access) */
	setWorkflowResult: (result: WorkflowResult | undefined) => void;
}

const AppContext = createContext<AppContextValue | null>(null);

interface AppContextProviderProps {
	children: ReactNode;
	/** Initial page variables */
	initialVariables?: Record<string, unknown>;
	/** Initial data from data sources */
	initialData?: Record<string, unknown>;
	/** Whether any data source is currently loading */
	isDataLoading?: boolean;
	/** Custom workflow trigger handler with onComplete actions */
	onTriggerWorkflow?: (
		workflowId: string,
		params?: Record<string, unknown>,
		onComplete?: OnCompleteAction[],
		onError?: OnCompleteAction[],
	) => void;
	/** Handler for refreshing a data table */
	onRefreshTable?: (dataSourceKey: string) => void;
	/** Externally controlled workflow result (for injection from parent) */
	workflowResult?: WorkflowResult;
	/** Custom navigate function (defaults to react-router navigate) */
	customNavigate?: (path: string) => void;
	/** Route parameters from URL (e.g., { id: "123" } for /tickets/:id) */
	routeParams?: Record<string, string>;
	/** Currently executing workflow IDs/names for loading states */
	activeWorkflows?: Set<string>;
}

/**
 * App Context Provider
 *
 * Wraps the application or page to provide expression context.
 * Integrates with the auth context to provide user information.
 *
 * @example
 * <AppContextProvider
 *   initialVariables={{ count: 0 }}
 *   onTriggerWorkflow={(id, params) => console.log("Trigger", id, params)}
 * >
 *   <AppRenderer definition={appDefinition} />
 * </AppContextProvider>
 */
export function AppContextProvider({
	children,
	initialVariables = {},
	initialData = {},
	isDataLoading = false,
	onTriggerWorkflow,
	onRefreshTable,
	workflowResult: externalWorkflowResult,
	customNavigate,
	routeParams = {},
	activeWorkflows,
}: AppContextProviderProps) {
	const navigate = useNavigate();
	const { user: authUser } = useAuth();

	// State for variables, data, and field values
	const [variables, setVariablesState] =
		useState<Record<string, unknown>>(initialVariables);
	const [data, setDataState] = useState<Record<string, unknown>>(initialData);
	const [fieldValues, setFieldValuesState] = useState<
		Record<string, unknown>
	>({});

	// Sync initialData prop changes to internal data state
	// This is needed because useState only uses initialData on first mount
	useEffect(() => {
		setDataState(initialData);
	}, [initialData]);

	// Custom action handlers registry
	const [customActions, setCustomActions] = useState<
		Map<string, (params?: Record<string, unknown>) => void>
	>(new Map());

	// Workflow result state (for {{ workflow.result.* }} access)
	// Can be controlled externally via prop or internally via setWorkflowResult
	const [internalWorkflowResult, setWorkflowResultState] = useState<
		WorkflowResult | undefined
	>(undefined);

	// Use external prop if provided, otherwise use internal state
	const workflowResult = externalWorkflowResult ?? internalWorkflowResult;

	// Convert auth user to expression user format
	const expressionUser = useMemo((): ExpressionUser | undefined => {
		if (!authUser) return undefined;

		return {
			id: authUser.id,
			name: authUser.name,
			email: authUser.email,
			role: authUser.roles[0] || "user",
		};
	}, [authUser]);

	// Navigation handler - use custom navigate if provided, else default
	const handleNavigate = useCallback(
		(path: string) => {
			if (customNavigate) {
				customNavigate(path);
			} else {
				navigate(path);
			}
		},
		[navigate, customNavigate],
	);

	// Workflow trigger handler
	const handleTriggerWorkflow = useCallback(
		(
			workflowId: string,
			params?: Record<string, unknown>,
			onComplete?: OnCompleteAction[],
			onError?: OnCompleteAction[],
		) => {
			if (onTriggerWorkflow) {
				onTriggerWorkflow(workflowId, params, onComplete, onError);
			} else {
				console.warn(
					`No workflow handler registered. Cannot trigger workflow: ${workflowId}`,
				);
			}
		},
		[onTriggerWorkflow],
	);

	// Custom action handler
	const handleCustomAction = useCallback(
		(actionId: string, params?: Record<string, unknown>) => {
			const handler = customActions.get(actionId);
			if (handler) {
				handler(params);
			} else {
				console.warn(
					`No handler registered for custom action: ${actionId}`,
				);
			}
		},
		[customActions],
	);

	// Field value setter (used by input components)
	const setFieldValue = useCallback((fieldId: string, value: unknown) => {
		setFieldValuesState((prev) => ({ ...prev, [fieldId]: value }));
	}, []);

	// Get all field values (for form submission)
	const getFieldValues = useCallback(() => {
		return { ...fieldValues };
	}, [fieldValues]);

	// Clear all field values
	const clearFieldValues = useCallback(() => {
		setFieldValuesState({});
	}, []);

	// Submit form handler - collects field values and triggers workflow
	const handleSubmitForm = useCallback(
		(
			workflowId: string,
			additionalParams?: Record<string, unknown>,
			onComplete?: OnCompleteAction[],
			onError?: OnCompleteAction[],
		) => {
			// Merge field values with any additional params
			const params = {
				...fieldValues,
				...additionalParams,
			};

			// Trigger the workflow with the form data and onComplete/onError actions
			if (onTriggerWorkflow) {
				onTriggerWorkflow(workflowId, params, onComplete, onError);
			} else {
				console.warn(
					`No workflow handler registered. Cannot submit form to workflow: ${workflowId}`,
				);
			}
		},
		[fieldValues, onTriggerWorkflow],
	);

	// Refresh table handler
	const handleRefreshTable = useCallback(
		(dataSourceKey: string) => {
			if (onRefreshTable) {
				onRefreshTable(dataSourceKey);
			} else {
				console.warn(
					`No refresh handler registered. Cannot refresh table: ${dataSourceKey}`,
				);
			}
		},
		[onRefreshTable],
	);

	// Variable setter for expression context (delegates to state setter)
	const handleSetVariable = useCallback((key: string, value: unknown) => {
		setVariablesState((prev) => ({ ...prev, [key]: value }));
	}, []);

	// Workflow result setter
	const setWorkflowResult = useCallback(
		(result: WorkflowResult | undefined) => {
			setWorkflowResultState(result);
		},
		[],
	);

	// Build the expression context
	const context = useMemo(
		(): ExpressionContext => ({
			user: expressionUser,
			variables,
			data,
			field: fieldValues,
			workflow: workflowResult,
			params: routeParams,
			isDataLoading,
			navigate: handleNavigate,
			triggerWorkflow: handleTriggerWorkflow,
			submitForm: handleSubmitForm,
			onCustomAction: handleCustomAction,
			setFieldValue,
			refreshTable: handleRefreshTable,
			setVariable: handleSetVariable,
			activeWorkflows,
		}),
		[
			expressionUser,
			variables,
			data,
			fieldValues,
			workflowResult,
			routeParams,
			isDataLoading,
			handleNavigate,
			handleTriggerWorkflow,
			handleSubmitForm,
			handleCustomAction,
			setFieldValue,
			handleRefreshTable,
			handleSetVariable,
			activeWorkflows,
		],
	);

	// Variable setters
	const setVariable = useCallback((key: string, value: unknown) => {
		setVariablesState((prev) => ({ ...prev, [key]: value }));
	}, []);

	const setVariables = useCallback((updates: Record<string, unknown>) => {
		setVariablesState((prev) => ({ ...prev, ...updates }));
	}, []);

	// Data setter
	const setData = useCallback((key: string, value: unknown) => {
		setDataState((prev) => ({ ...prev, [key]: value }));
	}, []);

	// Register custom action handler
	const registerCustomAction = useCallback(
		(
			actionId: string,
			handler: (params?: Record<string, unknown>) => void,
		) => {
			setCustomActions((prev) => {
				const next = new Map(prev);
				next.set(actionId, handler);
				return next;
			});
		},
		[],
	);

	const value = useMemo(
		(): AppContextValue => ({
			context,
			setVariable,
			setVariables,
			setData,
			setFieldValue,
			getFieldValues,
			clearFieldValues,
			registerCustomAction,
			setWorkflowResult,
		}),
		[
			context,
			setVariable,
			setVariables,
			setData,
			setFieldValue,
			getFieldValues,
			clearFieldValues,
			registerCustomAction,
			setWorkflowResult,
		],
	);

	return <AppContext.Provider value={value}>{children}</AppContext.Provider>;
}

/**
 * Hook to access the App Context
 *
 * @returns The app context value
 * @throws Error if used outside of AppContextProvider
 *
 * @example
 * function MyComponent() {
 *   const { context, setVariable } = useAppContext();
 *
 *   return (
 *     <button onClick={() => setVariable("count", context.variables.count + 1)}>
 *       Count: {context.variables.count}
 *     </button>
 *   );
 * }
 */
export function useAppContext(): AppContextValue {
	const context = useContext(AppContext);
	if (!context) {
		throw new Error(
			"useAppContext must be used within an AppContextProvider",
		);
	}
	return context;
}

/**
 * Hook to access just the expression context
 *
 * @returns The expression context for evaluating expressions
 *
 * @example
 * function MyComponent() {
 *   const context = useExpressionContext();
 *   const value = evaluateExpression("{{ user.name }}", context);
 * }
 */
export function useExpressionContext(): ExpressionContext {
	const { context } = useAppContext();
	return context;
}
