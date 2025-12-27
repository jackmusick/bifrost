import { useQuery } from "@tanstack/react-query";
import { useAuth } from "@/contexts/AuthContext";
import { authFetch } from "@/lib/api-client";

interface UserDetails {
	id: string;
	email: string;
	name: string;
	user_type: "PLATFORM" | "ORG";
	is_superuser: boolean;
	is_active: boolean;
	is_verified: boolean;
	last_login?: string;
	created_at: string;
	organization_id: string | null;
	roles: string[];
}

/**
 * Hook to fetch user details and permissions from the backend
 */
export function useUserPermissions() {
	const { user, isLoading: authLoading } = useAuth();

	const {
		data: userDetails,
		isLoading: detailsLoading,
		error,
	} = useQuery<UserDetails>({
		queryKey: ["user", "me"],
		queryFn: async () => {
			// Use /api/auth/me which works for any authenticated user
			// (unlike /api/users/:id which requires platform admin)
			const response = await authFetch("/api/auth/me");

			if (!response.ok) {
				// User doesn't exist in database - treat as unauthorized
				throw new Error("User not found in system");
			}

			return response.json();
		},
		enabled: !!user?.id,
		staleTime: 5 * 60 * 1000, // 5 minutes
		retry: false, // Don't retry on 404
	});

	return {
		userDetails,
		isPlatformAdmin: userDetails?.is_superuser ?? false,
		isOrgUser: userDetails?.user_type === "ORG",
		isLoading: authLoading || detailsLoading,
		error,
		hasAccess: !!userDetails && !error,
	};
}
