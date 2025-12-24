/**
 * Hook for checking LLM configuration status
 *
 * Used to determine if AI chat is available and configured.
 * Only works for platform admins (the config endpoint requires admin access).
 */

import { $api } from "@/lib/api-client";
import { useUserPermissions } from "@/hooks/useUserPermissions";

/**
 * Hook to check if LLM provider is configured
 *
 * Returns:
 * - isConfigured: whether the LLM provider is set up with an API key
 * - isLoading: whether the query is in progress
 * - config: the full config response (for admins only)
 */
export function useLLMConfig() {
	const { isPlatformAdmin, isLoading: permissionsLoading } =
		useUserPermissions();

	const {
		data: config,
		isLoading: configLoading,
		error,
	} = $api.useQuery("get", "/api/admin/llm/config", undefined, {
		// Only fetch if user is a platform admin
		enabled: isPlatformAdmin && !permissionsLoading,
		// Cache for 5 minutes
		staleTime: 5 * 60 * 1000,
		// Don't retry on 404 (not configured)
		retry: false,
	});

	// For non-admins, we can't check config - assume it might work
	// They'll get an error when trying to chat if not configured
	const isConfigured = isPlatformAdmin
		? (config?.is_configured ?? false)
		: null; // null means "unknown" for non-admins

	return {
		isConfigured,
		isPlatformAdmin,
		isLoading: permissionsLoading || (isPlatformAdmin && configLoading),
		config,
		error,
	};
}
