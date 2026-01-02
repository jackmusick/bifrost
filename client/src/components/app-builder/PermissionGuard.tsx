/**
 * Permission Guard Component
 *
 * Protects pages based on user permissions and access rules.
 * Redirects to access denied page or specified redirect path if access is denied.
 */

import { useMemo } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { ShieldX, Lock } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/contexts/AuthContext";
import type {
	ApplicationDefinition,
	PageDefinition,
	ExpressionContext,
} from "@/lib/app-builder-types";
import {
	hasAppAccess,
	hasPageAccess,
	getPageRedirectPath,
} from "@/lib/app-builder-permissions";

interface PermissionGuardProps {
	/** The application definition */
	app: ApplicationDefinition;
	/** The current page (optional, for page-level checks) */
	page?: PageDefinition;
	/** Children to render if access is granted */
	children: React.ReactNode;
	/** Optional fallback component for access denied */
	fallback?: React.ReactNode;
}

/**
 * Default Access Denied component
 */
function AccessDenied({
	message = "You don't have permission to view this page.",
	showLogin = false,
}: {
	message?: string;
	showLogin?: boolean;
}) {
	return (
		<div className="flex min-h-[400px] flex-col items-center justify-center gap-6 p-8 text-center">
			<div className="rounded-full bg-destructive/10 p-4">
				<ShieldX className="h-12 w-12 text-destructive" />
			</div>
			<div className="space-y-2">
				<h2 className="text-2xl font-semibold">Access Denied</h2>
				<p className="text-muted-foreground max-w-md">{message}</p>
			</div>
			{showLogin && (
				<Button asChild>
					<a href="/login">Sign In</a>
				</Button>
			)}
		</div>
	);
}

/**
 * Login Required component
 */
function LoginRequired() {
	const location = useLocation();

	return (
		<div className="flex min-h-[400px] flex-col items-center justify-center gap-6 p-8 text-center">
			<div className="rounded-full bg-primary/10 p-4">
				<Lock className="h-12 w-12 text-primary" />
			</div>
			<div className="space-y-2">
				<h2 className="text-2xl font-semibold">Sign In Required</h2>
				<p className="text-muted-foreground max-w-md">
					Please sign in to access this application.
				</p>
			</div>
			<Button asChild>
				<a
					href={`/login?redirect=${encodeURIComponent(location.pathname)}`}
				>
					Sign In
				</a>
			</Button>
		</div>
	);
}

/**
 * Permission Guard
 *
 * Wraps content and checks permissions before rendering.
 * Handles both app-level and page-level access control.
 */
export function PermissionGuard({
	app,
	page,
	children,
	fallback,
}: PermissionGuardProps) {
	const { user, isAuthenticated } = useAuth();

	// Get user roles
	const userRoles = useMemo(() => {
		if (!user?.roles) return [];
		return user.roles;
	}, [user?.roles]);

	// Build expression context for permission evaluation
	const expressionContext: Partial<ExpressionContext> = useMemo(
		() => ({
			user: user
				? {
						id: user.id,
						name: user.name || "",
						email: user.email || "",
						role: userRoles[0] || "user",
					}
				: undefined,
			variables: {},
			data: {},
		}),
		[user, userRoles],
	);

	// Check app-level access
	const hasAppLevelAccess = useMemo(
		() => hasAppAccess(app, userRoles, isAuthenticated),
		[app, userRoles, isAuthenticated],
	);

	// Check page-level access (if page provided)
	const hasPageLevelAccess = useMemo(() => {
		if (!page) return true;
		return hasPageAccess(page, userRoles, expressionContext);
	}, [page, userRoles, expressionContext]);

	// If app is public but user isn't authenticated and page requires it
	if (!isAuthenticated && !app.permissions?.public) {
		return <LoginRequired />;
	}

	// Check app-level access
	if (!hasAppLevelAccess) {
		if (fallback) return <>{fallback}</>;
		return (
			<AccessDenied message="You don't have access to this application." />
		);
	}

	// Check page-level access
	if (!hasPageLevelAccess) {
		const redirectPath = page ? getPageRedirectPath(page) : undefined;

		if (redirectPath) {
			return <Navigate to={`/apps/${app.id}/${redirectPath}`} replace />;
		}

		if (fallback) return <>{fallback}</>;
		return (
			<AccessDenied message="You don't have permission to view this page." />
		);
	}

	// Access granted
	return <>{children}</>;
}

/**
 * Standalone Access Denied page component
 */
export function AccessDeniedPage({
	message,
	showLogin,
}: {
	message?: string;
	showLogin?: boolean;
}) {
	return <AccessDenied message={message} showLogin={showLogin} />;
}

export default PermissionGuard;
