/**
 * App Code Platform Type Definitions
 *
 * This file provides TypeScript type definitions for the App Builder platform.
 * These types are used by the Monaco editor to provide IntelliSense support
 * when users write components in the App Builder.
 *
 * All types defined here correspond to the actual runtime implementations
 * in the app-code-platform/ directory.
 */

// =============================================================================
// Platform Hooks
// =============================================================================

/**
 * Options for the useWorkflow hook
 */
export interface UseWorkflowOptions {
	/**
	 * Whether to enable the query.
	 * When false, the workflow will not execute.
	 * @default true
	 */
	enabled?: boolean;
}

/**
 * Result object returned by the useWorkflow hook
 * @template T - The type of data returned by the workflow
 */
export interface UseWorkflowResult<T> {
	/**
	 * The workflow result data.
	 * Undefined while loading or if an error occurred.
	 */
	data: T | undefined;

	/**
	 * Whether the workflow is currently loading.
	 * True during initial load and refreshes.
	 */
	isLoading: boolean;

	/**
	 * Error message if the workflow execution failed.
	 * Undefined if successful or still loading.
	 */
	error: string | undefined;

	/**
	 * Function to manually refresh/re-execute the workflow.
	 * Useful for refetching data after mutations.
	 */
	refresh: () => void;
}

/**
 * Hook for fetching data via workflow execution.
 * Provides loading, error, and refresh states for data fetching workflows.
 *
 * @template T - The type of data returned by the workflow
 * @param workflowId - The workflow ID or name to execute
 * @param params - Optional parameters to pass to the workflow
 * @param options - Optional configuration (enabled)
 * @returns Object with data, isLoading, error, and refresh function
 *
 * @example
 * ```jsx
 * // Basic usage - fetch list of clients
 * const { data: clients, isLoading, error, refresh } = useWorkflow('list_clients');
 *
 * if (isLoading) return <Skeleton />;
 * if (error) return <Alert>{error}</Alert>;
 *
 * return (
 *   <DataTable data={clients} onRefresh={refresh} />
 * );
 * ```
 *
 * @example
 * ```jsx
 * // With parameters
 * const { data: client } = useWorkflow('get_client', { id: clientId });
 *
 * // Conditionally enabled (only fetch when id is available)
 * const { data } = useWorkflow('get_details', { id }, { enabled: !!id });
 * ```
 */
export declare function useWorkflow<T = unknown>(
	workflowId: string,
	params?: Record<string, unknown>,
	options?: UseWorkflowOptions,
): UseWorkflowResult<T>;

/**
 * Current user information available in apps
 */
export interface AppCodeUser {
	/** User's unique identifier */
	id: string;

	/** User's email address */
	email: string;

	/** User's display name */
	name: string;

	/**
	 * User's primary role.
	 * This is the first role in the user's roles array, or empty string if no roles.
	 */
	role: string;

	/**
	 * User's organization ID.
	 * Empty string for platform users who aren't associated with an organization.
	 */
	organizationId: string;
}

/**
 * Hook to get the current authenticated user information.
 * Returns a consistent shape even if the user is not authenticated.
 *
 * @returns User object with id, email, name, role, and organizationId
 *
 * @example
 * ```jsx
 * const user = useUser();
 *
 * return (
 *   <div>
 *     <Text>Welcome, {user.name}</Text>
 *     <Text muted>{user.email}</Text>
 *     {user.role === 'Admin' && (
 *       <Button onClick={() => navigate('/settings')}>
 *         Settings
 *       </Button>
 *     )}
 *   </div>
 * );
 * ```
 */
export declare function useUser(): AppCodeUser;

/**
 * Hook to get URL path parameters from the current route.
 * Returns all dynamic segments defined in the route path.
 *
 * @returns Object containing all URL parameters as string values
 *
 * @example
 * ```jsx
 * // URL: /clients/123/contacts
 * // Route: /clients/:clientId/contacts
 *
 * const params = useParams();
 * // params = { clientId: "123" }
 *
 * const { data: client } = useWorkflow('get_client', { id: params.clientId });
 * ```
 */
export declare function useParams(): Record<string, string>;

/**
 * Hook to get query string parameters from the current URL.
 * Returns a URLSearchParams object for accessing query parameters.
 *
 * @returns URLSearchParams object for accessing query parameters
 *
 * @example
 * ```jsx
 * // URL: /clients?status=active&page=2
 *
 * const searchParams = useSearchParams();
 *
 * const status = searchParams.get('status'); // "active"
 * const page = searchParams.get('page'); // "2"
 *
 * // Iterate over all params
 * for (const [key, value] of searchParams) {
 *   console.log(key, value);
 * }
 * ```
 */
export declare function useSearchParams(): URLSearchParams;

/**
 * Hook to get a navigation function for programmatic navigation.
 * Returns a stable function that navigates to the specified path.
 *
 * @returns A function that navigates to the specified path
 *
 * @example
 * ```jsx
 * const nav = useNavigate();
 *
 * return (
 *   <Button onClick={() => nav('/clients/new')}>
 *     Add Client
 *   </Button>
 * );
 * ```
 */
export declare function useNavigate(): (path: string) => void;

/**
 * Hook for cross-page app state that persists across page navigations.
 * Similar to useState but state is shared across all pages in the app.
 * State is reset when the app is closed or switched to a different app.
 *
 * @template T - The type of the state value
 * @param key - Unique key for the state value (must be unique within the app)
 * @param initialValue - Initial value if state is not already set
 * @returns Tuple of [value, setValue] similar to useState
 *
 * @example
 * ```jsx
 * // In any page or component
 * const [selectedClientId, setSelectedClientId] = useAppState('selectedClient', null);
 *
 * // Value persists when navigating to other pages
 * <Button onClick={() => {
 *   setSelectedClientId(client.id);
 *   navigate('/client-details');
 * }}>
 *   View Details
 * </Button>
 * ```
 *
 * @example
 * ```jsx
 * // Sharing state across pages
 *
 * // Page 1: Set the state
 * const [cart, setCart] = useAppState('cart', []);
 * setCart([...cart, newItem]);
 *
 * // Page 2: Read the same state
 * const [cart] = useAppState('cart', []);
 * // cart contains items added from Page 1
 * ```
 */
export declare function useAppState<T>(
	key: string,
	initialValue: T,
): [T, (value: T) => void];

// =============================================================================
// Platform Utilities
// =============================================================================

/**
 * Execute a workflow and return the result.
 * Used for mutations or one-off workflow calls where you don't need
 * loading/error state management. For data fetching, use useWorkflow instead.
 *
 * @template T - The type of data returned by the workflow
 * @param workflowId - The workflow ID or name to execute
 * @param params - Optional parameters to pass to the workflow
 * @returns Promise that resolves to the workflow result data
 * @throws Error if workflow execution fails
 *
 * @example
 * ```jsx
 * // In a button click handler
 * const handleSave = async () => {
 *   try {
 *     await runWorkflow('update_client', { id: clientId, name: newName });
 *     toast.success('Saved!');
 *     refresh(); // Refresh the data
 *   } catch (error) {
 *     toast.error('Failed to save: ' + error.message);
 *   }
 * };
 *
 * return (
 *   <Button onClick={handleSave} disabled={isSaving}>
 *     Save Changes
 *   </Button>
 * );
 * ```
 *
 * @example
 * ```jsx
 * // Create a new record and navigate
 * const handleCreate = async () => {
 *   const newClient = await runWorkflow('create_client', { name: 'Acme Corp' });
 *   navigate(`/clients/${newClient.id}`);
 * };
 * ```
 */
export declare function runWorkflow<T = unknown>(
	workflowId: string,
	params?: Record<string, unknown>,
): Promise<T>;

/**
 * Navigate to a page path programmatically.
 *
 * Note: This is an imperative function. For navigation within components,
 * prefer using the useNavigate hook which provides a stable callback.
 * This function is useful in async callbacks where hooks aren't available.
 *
 * @param path - The path to navigate to (relative to the app root)
 *
 * @example
 * ```jsx
 * // In a component, prefer useNavigate:
 * const nav = useNavigate();
 * <Button onClick={() => nav('/clients')}>Go</Button>
 *
 * // This imperative version works in async callbacks:
 * const handleSuccess = async () => {
 *   await runWorkflow('save_client', data);
 *   navigate('/clients'); // Imperative navigation after async work
 * };
 * ```
 */
export declare function navigate(path: string): void;

// =============================================================================
// React Hooks (Re-exported from React for convenience)
// =============================================================================

/**
 * These React hooks are available directly in code without imports.
 * They are the standard React hooks from the React library.
 */

export declare const useState: typeof import("react").useState;
export declare const useEffect: typeof import("react").useEffect;
export declare const useMemo: typeof import("react").useMemo;
export declare const useCallback: typeof import("react").useCallback;
export declare const useRef: typeof import("react").useRef;
export declare const useContext: typeof import("react").useContext;
export declare const useReducer: typeof import("react").useReducer;
export declare const useLayoutEffect: typeof import("react").useLayoutEffect;
export declare const useImperativeHandle: typeof import("react").useImperativeHandle;
export declare const useDebugValue: typeof import("react").useDebugValue;
export declare const useDeferredValue: typeof import("react").useDeferredValue;
export declare const useTransition: typeof import("react").useTransition;
export declare const useId: typeof import("react").useId;
export declare const useSyncExternalStore: typeof import("react").useSyncExternalStore;

// =============================================================================
// React Utilities (Re-exported from React for convenience)
// =============================================================================

/**
 * These React utilities are available directly in code without imports.
 */

export declare const React: typeof import("react");
export declare const Fragment: typeof import("react").Fragment;
export declare const createElement: typeof import("react").createElement;
export declare const createContext: typeof import("react").createContext;
export declare const forwardRef: typeof import("react").forwardRef;
export declare const memo: typeof import("react").memo;
export declare const lazy: typeof import("react").lazy;
export declare const Suspense: typeof import("react").Suspense;

// =============================================================================
// Aggregate Types for Monaco Editor Integration
// =============================================================================

/**
 * Complete platform scope type for Monaco editor IntelliSense.
 * This interface describes all APIs available to code at runtime.
 */
export interface PlatformScope {
	// React core
	React: typeof import("react");

	// React hooks
	useState: typeof import("react").useState;
	useEffect: typeof import("react").useEffect;
	useMemo: typeof import("react").useMemo;
	useCallback: typeof import("react").useCallback;
	useRef: typeof import("react").useRef;
	useContext: typeof import("react").useContext;
	useReducer: typeof import("react").useReducer;
	useLayoutEffect: typeof import("react").useLayoutEffect;
	useImperativeHandle: typeof import("react").useImperativeHandle;
	useDebugValue: typeof import("react").useDebugValue;
	useDeferredValue: typeof import("react").useDeferredValue;
	useTransition: typeof import("react").useTransition;
	useId: typeof import("react").useId;
	useSyncExternalStore: typeof import("react").useSyncExternalStore;

	// React utilities
	Fragment: typeof import("react").Fragment;
	createElement: typeof import("react").createElement;
	createContext: typeof import("react").createContext;
	forwardRef: typeof import("react").forwardRef;
	memo: typeof import("react").memo;
	lazy: typeof import("react").lazy;
	Suspense: typeof import("react").Suspense;

	// Platform hooks
	useWorkflow: typeof useWorkflow;
	useUser: typeof useUser;
	useParams: typeof useParams;
	useSearchParams: typeof useSearchParams;
	useNavigate: typeof useNavigate;
	useAppState: typeof useAppState;

	// Platform utilities
	runWorkflow: typeof runWorkflow;
	navigate: typeof navigate;
}

/**
 * Type definitions string for Monaco editor.
 * This can be used to register type definitions with Monaco's TypeScript support.
 *
 * @example
 * ```typescript
 * import { MONACO_TYPE_DEFINITIONS } from '@/lib/app-code-platform.d.ts';
 *
 * monaco.languages.typescript.typescriptDefaults.addExtraLib(
 *   MONACO_TYPE_DEFINITIONS,
 *   'app-code-platform.d.ts'
 * );
 * ```
 */
export declare const MONACO_TYPE_DEFINITIONS: string;
