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
	type ReactNode,
} from "react";
import { useNavigate } from "react-router-dom";
import type {
	ExpressionContext,
	ExpressionUser,
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
	/** Register a custom action handler */
	registerCustomAction: (
		actionId: string,
		handler: (params?: Record<string, unknown>) => void,
	) => void;
}

const AppContext = createContext<AppContextValue | null>(null);

interface AppContextProviderProps {
	children: ReactNode;
	/** Initial page variables */
	initialVariables?: Record<string, unknown>;
	/** Initial data from data sources */
	initialData?: Record<string, unknown>;
	/** Custom workflow trigger handler */
	onTriggerWorkflow?: (
		workflowId: string,
		params?: Record<string, unknown>,
	) => void;
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
	onTriggerWorkflow,
}: AppContextProviderProps) {
	const navigate = useNavigate();
	const { user: authUser } = useAuth();

	// State for variables and data
	const [variables, setVariablesState] =
		useState<Record<string, unknown>>(initialVariables);
	const [data, setDataState] =
		useState<Record<string, unknown>>(initialData);

	// Custom action handlers registry
	const [customActions, setCustomActions] = useState<
		Map<string, (params?: Record<string, unknown>) => void>
	>(new Map());

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

	// Navigation handler
	const handleNavigate = useCallback(
		(path: string) => {
			navigate(path);
		},
		[navigate],
	);

	// Workflow trigger handler
	const handleTriggerWorkflow = useCallback(
		(workflowId: string, params?: Record<string, unknown>) => {
			if (onTriggerWorkflow) {
				onTriggerWorkflow(workflowId, params);
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
				console.warn(`No handler registered for custom action: ${actionId}`);
			}
		},
		[customActions],
	);

	// Build the expression context
	const context = useMemo(
		(): ExpressionContext => ({
			user: expressionUser,
			variables,
			data,
			navigate: handleNavigate,
			triggerWorkflow: handleTriggerWorkflow,
			onCustomAction: handleCustomAction,
		}),
		[
			expressionUser,
			variables,
			data,
			handleNavigate,
			handleTriggerWorkflow,
			handleCustomAction,
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
		(actionId: string, handler: (params?: Record<string, unknown>) => void) => {
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
			registerCustomAction,
		}),
		[context, setVariable, setVariables, setData, registerCustomAction],
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
		throw new Error("useAppContext must be used within an AppContextProvider");
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
