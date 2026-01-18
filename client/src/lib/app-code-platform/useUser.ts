/**
 * Platform hook: useUser
 *
 * Returns the current authenticated user information.
 * Wraps the auth context to provide a simplified interface for JSX apps.
 */

import { useAuth } from "@/contexts/AuthContext";

interface JsxUser {
	/** User's unique ID */
	id: string;
	/** User's email address */
	email: string;
	/** User's display name */
	name: string;
	/** All roles assigned to the user */
	roles: string[];
	/** Check if user has a specific role */
	hasRole: (role: string) => boolean;
	/** User's organization ID (empty string if platform user) */
	organizationId: string;
}

/**
 * Get the current authenticated user
 *
 * @returns User object with id, email, name, roles, hasRole(), and organizationId
 *
 * @example
 * ```jsx
 * const user = useUser();
 *
 * return (
 *   <div>
 *     <Text>Welcome, {user.name}</Text>
 *     <Text muted>{user.email}</Text>
 *     {user.hasRole('Admin') && (
 *       <Button onClick={() => navigate('/settings')}>
 *         Settings
 *       </Button>
 *     )}
 *   </div>
 * );
 * ```
 */
export function useUser(): JsxUser {
	const { user } = useAuth();

	// Return a consistent shape even if user is null
	// (shouldn't happen in JSX apps since they require auth)
	if (!user) {
		return {
			id: "",
			email: "",
			name: "",
			roles: [],
			hasRole: () => false,
			organizationId: "",
		};
	}

	const roles = user.roles ?? [];

	return {
		id: user.id,
		email: user.email,
		name: user.name,
		roles,
		hasRole: (role: string) => roles.includes(role),
		organizationId: user.organizationId ?? "",
	};
}
