/**
 * Platform function: navigate
 *
 * Navigation function for JSX runtime.
 * Since this needs to work outside of React components (or be called imperatively),
 * we export a function that gets the navigate function from context.
 *
 * Note: This module provides both a hook (useNavigate) and a standalone function.
 * The standalone function should be used sparingly - prefer useNavigate in components.
 *
 * Path Transformation:
 * Both the hook and the imperative function automatically transform absolute paths
 * (starting with "/") to include the app's base path. For example:
 * - "/customers" -> "/apps/my-app/preview/customers" (in preview mode)
 * - "/customers" -> "/apps/my-app/customers" (in published mode)
 */

import { useNavigate as useRouterNavigate } from "react-router-dom";
import { useCallback } from "react";
import { useAppBuilderStore } from "@/stores/app-builder.store";
import { transformPath } from "./navigation";

/**
 * Get a navigation function for use in components
 *
 * Automatically transforms absolute paths to include the app's base path.
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
export function useNavigate(): (path: string) => void {
	const routerNavigate = useRouterNavigate();
	const getBasePath = useAppBuilderStore((state) => state.getBasePath);

	const navigate = useCallback(
		(path: string) => {
			const basePath = getBasePath();
			const transformedPath = transformPath(path, basePath);
			routerNavigate(transformedPath);
		},
		[routerNavigate, getBasePath],
	);

	return navigate;
}

/**
 * Navigation context holder for imperative navigation
 * This is set by the JSX runtime shell component
 */
let navigateRef: ((path: string) => void) | null = null;

/**
 * Set the navigate function reference (called by JSX runtime shell)
 * @internal
 */
export function setNavigateRef(fn: (path: string) => void): void {
	navigateRef = fn;
}

/**
 * Clear the navigate function reference (called on unmount)
 * @internal
 */
export function clearNavigateRef(): void {
	navigateRef = null;
}

/**
 * Navigate to a page path (imperative version)
 *
 * Automatically transforms absolute paths to include the app's base path.
 *
 * Note: Prefer using the useNavigate hook in components.
 * This function is for use in event handlers where hooks aren't available.
 *
 * @param path - The path to navigate to
 *
 * @example
 * ```jsx
 * // In a component, prefer useNavigate:
 * const nav = useNavigate();
 * <Button onClick={() => nav('/clients')}>Go</Button>
 *
 * // This imperative version works in callbacks:
 * const handleSuccess = async () => {
 *   navigate('/clients'); // Imperative navigation
 * };
 * ```
 */
export function navigate(path: string): void {
	if (!navigateRef) {
		console.error(
			"navigate() called before JSX runtime initialized. Use useNavigate hook instead.",
		);
		return;
	}

	// Transform path using the store's base path
	const basePath = useAppBuilderStore.getState().getBasePath();
	const transformedPath = transformPath(path, basePath);
	navigateRef(transformedPath);
}
