/**
 * JSX Runtime
 *
 * Creates React components from compiled JSX code by injecting
 * the platform scope (React hooks, platform APIs, UI components).
 */

import React from "react";
import { compileJsx, wrapAsComponent } from "./jsx-compiler";
import { createPlatformScope } from "./jsx-platform/scope";

/**
 * Platform scope containing all APIs available to JSX code
 *
 * This object is injected into the runtime scope of every component.
 * JSX code can use these without imports:
 *
 * ```jsx
 * const [count, setCount] = useState(0);
 * const { data } = useWorkflow('get_data');
 * navigate('/home');
 * ```
 */
export const PLATFORM_SCOPE: Record<string, unknown> = {
	// React core
	React,

	// React hooks (commonly used, exposed at top level for convenience)
	useState: React.useState,
	useEffect: React.useEffect,
	useMemo: React.useMemo,
	useCallback: React.useCallback,
	useRef: React.useRef,
	useContext: React.useContext,
	useReducer: React.useReducer,
	useLayoutEffect: React.useLayoutEffect,
	useImperativeHandle: React.useImperativeHandle,
	useDebugValue: React.useDebugValue,
	useDeferredValue: React.useDeferredValue,
	useTransition: React.useTransition,
	useId: React.useId,
	useSyncExternalStore: React.useSyncExternalStore,

	// React utilities
	Fragment: React.Fragment,
	createElement: React.createElement,
	createContext: React.createContext,
	forwardRef: React.forwardRef,
	memo: React.memo,
	lazy: React.lazy,
	Suspense: React.Suspense,

	// Platform APIs from jsx-platform
	...createPlatformScope(),

	// UI Components will be added later via customComponents parameter
	// or by extending this scope with jsx-ui components
};

/**
 * Error component displayed when compilation or runtime errors occur
 */
function ErrorComponent({
	title,
	message,
}: {
	title: string;
	message: string;
}): React.ReactElement {
	return React.createElement(
		"div",
		{
			className:
				"p-4 bg-red-50 border border-red-200 rounded-lg text-red-700",
		},
		React.createElement(
			"div",
			{ className: "font-semibold text-red-800 mb-1" },
			title,
		),
		React.createElement(
			"pre",
			{
				className:
					"text-sm whitespace-pre-wrap font-mono bg-red-100 p-2 rounded mt-2",
			},
			message,
		),
	);
}

/**
 * Create a React component from JSX source or pre-compiled code
 *
 * This function:
 * 1. Compiles the source (if not already compiled)
 * 2. Wraps it as a component factory
 * 3. Creates a function with the platform scope injected
 * 4. Returns the resulting React component
 *
 * @param source - JSX source code or pre-compiled JavaScript
 * @param customComponents - Additional components to inject (e.g., app-specific components)
 * @param useCompiled - If true, source is already compiled and doesn't need transformation
 * @returns A React component that renders the JSX
 *
 * @example
 * ```typescript
 * // From source
 * const MyPage = createComponent(`
 *   const { data, isLoading } = useWorkflow('get_clients');
 *   if (isLoading) return <div>Loading...</div>;
 *   return <div>{data.length} clients</div>;
 * `);
 *
 * // From pre-compiled (for production)
 * const MyPage = createComponent(compiledCode, {}, true);
 *
 * // With custom components
 * const MyPage = createComponent(source, { ClientCard, DataGrid });
 * ```
 */
export function createComponent(
	source: string,
	customComponents: Record<string, React.ComponentType> = {},
	useCompiled: boolean = false,
): React.ComponentType {
	// Step 1: Compile if needed
	let compiled: string;

	if (useCompiled) {
		compiled = source;
	} else {
		const result = compileJsx(source);

		if (!result.success) {
			// Return an error component that shows the compilation error
			const errorMessage = result.error || "Unknown compilation error";
			return function CompilationError() {
				return ErrorComponent({
					title: "Compilation Error",
					message: errorMessage,
				});
			};
		}

		compiled = result.compiled!;
	}

	// Step 2: Build the full scope
	const scope = {
		...PLATFORM_SCOPE,
		...customComponents,
	};

	// Step 3: Create argument names and values for the function
	const argNames = Object.keys(scope);
	const argValues = Object.values(scope);

	// Step 4: Wrap the compiled code as a component factory
	const wrapped = wrapAsComponent(compiled);

	// Step 5: Create and execute the factory
	try {
		// Create a function that takes all scope items as arguments
		// and returns a component function
		const factory = new Function(...argNames, wrapped) as (
			...args: unknown[]
		) => React.ComponentType;

		// Execute the factory with our scope values
		const Component = factory(...argValues);

		// Wrap in an error boundary function component
		return function SafeComponent(
			props: Record<string, unknown>,
		): React.ReactElement {
			try {
				return React.createElement(Component, props);
			} catch (err) {
				const errorMessage =
					err instanceof Error ? err.message : "Unknown runtime error";
				return ErrorComponent({
					title: "Runtime Error",
					message: errorMessage,
				});
			}
		};
	} catch (err) {
		// Factory creation or execution failed
		const errorMessage =
			err instanceof Error ? err.message : "Unknown error creating component";
		return function FactoryError() {
			return ErrorComponent({
				title: "Component Factory Error",
				message: errorMessage,
			});
		};
	}
}
