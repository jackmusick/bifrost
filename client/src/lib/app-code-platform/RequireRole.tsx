/**
 * Platform component: RequireRole
 *
 * Conditionally renders children based on user role.
 * Provides a declarative alternative to manual role checks.
 */

import React from "react";
import { useUser } from "./useUser";

interface RequireRoleProps {
	role: string;
	children: React.ReactNode;
	fallback?: React.ReactNode;
}

export function RequireRole({
	role,
	children,
	fallback = null,
}: RequireRoleProps): React.ReactElement | null {
	const user = useUser();
	if (!user.hasRole(role)) return fallback as React.ReactElement | null;
	return children as React.ReactElement;
}
