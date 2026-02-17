import { useAuth } from "@/contexts/AuthContext";
import { NoAccess } from "@/components/NoAccess";

interface ProtectedRouteProps {
	children: React.ReactNode;
	requirePlatformAdmin?: boolean;
	requireOrgUser?: boolean;
}

/**
 * Protected route component that checks user roles
 *
 * @param requirePlatformAdmin - Route requires PlatformAdmin role
 * @param requireOrgUser - Route requires OrgUser role (or PlatformAdmin)
 */
export function ProtectedRoute({
	children,
	requirePlatformAdmin = false,
	requireOrgUser = false,
}: ProtectedRouteProps) {
	const { isPlatformAdmin, isOrgUser, isLoading, hasRole } = useAuth();

	// Wait for auth to load
	if (isLoading) {
		return null;
	}

	// Check for PlatformAdmin requirement
	if (requirePlatformAdmin && !isPlatformAdmin) {
		return <NoAccess />;
	}

	// Check for OrgUser requirement (PlatformAdmin and EmbedUser also have access)
	if (requireOrgUser && !isOrgUser && !isPlatformAdmin && !hasRole("EmbedUser")) {
		return <NoAccess />;
	}

	return <>{children}</>;
}
