/**
 * React Query client configuration
 */

import { QueryClient, focusManager } from "@tanstack/react-query";

// Use Page Visibility API so all interval-based polling pauses when the tab is hidden
focusManager.setEventListener((handleFocus) => {
	const onVisibilityChange = () => handleFocus(!document.hidden);
	document.addEventListener("visibilitychange", onVisibilityChange);
	return () => document.removeEventListener("visibilitychange", onVisibilityChange);
});

export const queryClient = new QueryClient({
	defaultOptions: {
		queries: {
			// Refetch when tab becomes visible again (works with focusManager above)
			refetchOnWindowFocus: true,
			// Disable retries for all queries
			retry: false,
			// No caching - always refetch fresh data
			staleTime: 0,
			// Only refetch if data is stale (not on every mount)
			refetchOnMount: true,
		},
		mutations: {
			// IMPORTANT: Disable retries for ALL mutations globally
			// Mutations are typically NOT idempotent (create, update, delete, execute operations)
			// Retrying failed mutations can cause:
			// - Duplicate workflow executions
			// - Duplicate records created
			// - Unintended side effects
			// If a specific mutation needs retries, it should opt-in explicitly
			retry: false,
		},
	},
});
