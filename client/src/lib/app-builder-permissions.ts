/**
 * App Builder Permission Utilities
 *
 * Functions for checking user permissions against app and page configurations.
 */

import type {
	ApplicationDefinition,
	PageDefinition,
	ExpressionContext,
} from "./app-builder-types";
import { evaluateExpression } from "./expression-parser";

/**
 * Check if a user has access to an application
 */
export function hasAppAccess(
	app: ApplicationDefinition,
	userRoles: string[],
	isAuthenticated: boolean,
): boolean {
	const permissions = app.permissions;

	// If no permissions defined, allow all authenticated users
	if (!permissions) {
		return isAuthenticated;
	}

	// Public apps allow everyone
	if (permissions.public) {
		return true;
	}

	// Not authenticated = no access (unless public)
	if (!isAuthenticated) {
		return false;
	}

	// Check if user has any matching role in rules
	if (permissions.rules && permissions.rules.length > 0) {
		for (const rule of permissions.rules) {
			// Wildcard matches all authenticated users
			if (rule.role === "*") {
				return true;
			}
			// Check if user has this role
			if (userRoles.includes(rule.role)) {
				return true;
			}
		}
		// No matching rules found
		return false;
	}

	// No rules defined, use default level
	const defaultLevel = permissions.defaultLevel || "view";
	return defaultLevel !== "none";
}

/**
 * Get the permission level for a user on an application
 */
export function getAppPermissionLevel(
	app: ApplicationDefinition,
	userRoles: string[],
): "none" | "view" | "edit" | "admin" {
	const permissions = app.permissions;

	// If no permissions defined, default to view for authenticated users
	if (!permissions) {
		return "view";
	}

	// Check rules for highest permission level
	let highestLevel: "none" | "view" | "edit" | "admin" =
		permissions.defaultLevel || "none";

	if (permissions.rules) {
		for (const rule of permissions.rules) {
			const hasRole = rule.role === "*" || userRoles.includes(rule.role);
			if (hasRole) {
				// Update to higher permission level
				if (rule.level === "admin") {
					highestLevel = "admin";
					break; // Admin is highest, no need to continue
				} else if (rule.level === "edit" && highestLevel !== "admin") {
					highestLevel = "edit";
				} else if (rule.level === "view" && highestLevel === "none") {
					highestLevel = "view";
				}
			}
		}
	}

	return highestLevel;
}

/**
 * Check if a user has access to a specific page
 */
export function hasPageAccess(
	page: PageDefinition,
	userRoles: string[],
	context: Partial<ExpressionContext>,
): boolean {
	const permission = page.permission;

	// No permission config = allow access
	if (!permission) {
		return true;
	}

	// Check allowed roles
	if (permission.allowedRoles && permission.allowedRoles.length > 0) {
		const hasRole = permission.allowedRoles.some(
			(role) => role === "*" || userRoles.includes(role),
		);
		if (!hasRole) {
			return false;
		}
	}

	// Check access expression
	if (permission.accessExpression) {
		try {
			const result = evaluateExpression(
				permission.accessExpression,
				context as ExpressionContext,
			);
			if (result === false) {
				return false;
			}
		} catch {
			// If expression fails, deny access for safety
			return false;
		}
	}

	return true;
}

/**
 * Filter pages based on user permissions
 */
export function filterAccessiblePages(
	pages: PageDefinition[],
	userRoles: string[],
	context: Partial<ExpressionContext>,
): PageDefinition[] {
	return pages.filter((page) => hasPageAccess(page, userRoles, context));
}

/**
 * Get redirect path for a denied page
 */
export function getPageRedirectPath(page: PageDefinition): string | undefined {
	return page.permission?.redirectTo;
}
