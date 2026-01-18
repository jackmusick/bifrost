/**
 * Navigation Components for App Code Platform
 *
 * Wrapped versions of React Router's navigation components that automatically
 * prepend the app's base path for absolute paths.
 *
 * This enables user code to write `<Link to="/customers">` and have it
 * correctly navigate to `/apps/{slug}/preview/customers` or `/apps/{slug}/customers`
 * depending on the current mode.
 */

import React, { forwardRef } from "react";
import {
	Link as RouterLink,
	NavLink as RouterNavLink,
	Navigate as RouterNavigate,
	type LinkProps,
	type NavLinkProps,
	type NavigateProps,
} from "react-router-dom";
import { useAppBuilderStore } from "@/stores/app-builder.store";

/**
 * Transform a path by prepending the app's base path for absolute paths
 *
 * Rules:
 * - Absolute paths starting with "/" are transformed (e.g., "/customers" -> "/apps/my-app/customers")
 * - Paths already starting with "/apps/" are passed through unchanged
 * - External URLs (starting with "http") are passed through unchanged
 * - Relative paths (not starting with "/") are passed through unchanged
 *
 * @param path - The path to transform
 * @param basePath - The app's base path (e.g., "/apps/my-app/preview")
 * @returns The transformed path
 */
export function transformPath(path: string, basePath: string): string {
	// Only transform string paths that:
	// - Start with "/" (absolute)
	// - Don't start with "/apps/" (already prefixed)
	// - Don't start with "http" (external URLs)
	if (
		typeof path === "string" &&
		path.startsWith("/") &&
		!path.startsWith("/apps/") &&
		!path.startsWith("http")
	) {
		// Remove the leading "/" and combine with base path
		const relativePath = path.slice(1);
		// Handle root path case
		if (!relativePath) {
			return basePath;
		}
		return `${basePath}/${relativePath}`;
	}
	return path;
}

/**
 * Transform a 'to' prop which can be a string or an object with pathname
 */
function transformTo(
	to: LinkProps["to"],
	basePath: string,
): LinkProps["to"] {
	if (typeof to === "string") {
		return transformPath(to, basePath);
	}

	// Handle object form: { pathname, search, hash }
	if (typeof to === "object" && to !== null && "pathname" in to) {
		const pathname = to.pathname;
		if (typeof pathname === "string") {
			return {
				...to,
				pathname: transformPath(pathname, basePath),
			};
		}
	}

	return to;
}

/**
 * Wrapped Link component that transforms absolute paths
 *
 * @example
 * ```tsx
 * // In app code:
 * <Link to="/customers">Customers</Link>
 *
 * // When in preview mode at /apps/my-app/preview:
 * // Navigates to /apps/my-app/preview/customers
 *
 * // When in published mode at /apps/my-app:
 * // Navigates to /apps/my-app/customers
 * ```
 */
export const Link = forwardRef<HTMLAnchorElement, LinkProps>(
	function Link({ to, ...props }, ref) {
		const basePath = useAppBuilderStore((state) => state.getBasePath());
		const transformedTo = transformTo(to, basePath);

		return <RouterLink ref={ref} to={transformedTo} {...props} />;
	},
);

/**
 * Wrapped NavLink component that transforms absolute paths
 *
 * Preserves all NavLink functionality including:
 * - Active state detection (automatically works with transformed paths)
 * - className/style functions that receive isActive/isPending
 *
 * @example
 * ```tsx
 * <NavLink
 *   to="/customers"
 *   className={({ isActive }) => isActive ? "bg-accent" : ""}
 * >
 *   Customers
 * </NavLink>
 * ```
 */
export const NavLink = forwardRef<HTMLAnchorElement, NavLinkProps>(
	function NavLink({ to, ...props }, ref) {
		const basePath = useAppBuilderStore((state) => state.getBasePath());
		const transformedTo = transformTo(to, basePath);

		return <RouterNavLink ref={ref} to={transformedTo} {...props} />;
	},
);

/**
 * Wrapped Navigate component for declarative navigation
 *
 * @example
 * ```tsx
 * // Redirect to another page
 * if (!user) return <Navigate to="/login" replace />;
 * ```
 */
export function Navigate({ to, ...props }: NavigateProps): React.ReactElement {
	const basePath = useAppBuilderStore((state) => state.getBasePath());
	const transformedTo = transformTo(to, basePath);

	return <RouterNavigate to={transformedTo} {...props} />;
}
