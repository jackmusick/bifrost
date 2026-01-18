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
	/** User's primary role (first role in roles array, or empty string) */
	role: string;
	/** User's organization ID (empty string if platform user) */
	organizationId: string;
}

/**
 * Get the current authenticated user
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
export function useUser(): JsxUser {
	const { user } = useAuth();

	// Return a consistent shape even if user is null
	// (shouldn't happen in JSX apps since they require auth)
	if (!user) {
		return {
			id: "",
			email: "",
			name: "",
			role: "",
			organizationId: "",
		};
	}

	return {
		id: user.id,
		email: user.email,
		name: user.name,
		// Return the first role, or empty string if no roles
		role: user.roles.length > 0 ? user.roles[0] : "",
		// Return organization ID or empty string for platform users
		organizationId: user.organizationId ?? "",
	};
}
