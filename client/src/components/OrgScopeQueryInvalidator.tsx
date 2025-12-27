import { useEffect, useRef } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useScopeStore } from "@/stores/scopeStore";

/**
 * Invalidates all React Query caches when organization scope changes.
 * This ensures API data is refetched when the user switches organizations.
 *
 * Some queries include org ID in their query keys (for filtering), while
 * others are platform-wide. This component invalidates all queries to
 * ensure a consistent view when the org scope changes.
 */
export function OrgScopeQueryInvalidator() {
	const queryClient = useQueryClient();
	const orgId = useScopeStore((s) => s.scope.orgId);
	const isFirstMount = useRef(true);

	useEffect(() => {
		// Skip initial mount - don't invalidate on first render
		if (isFirstMount.current) {
			isFirstMount.current = false;
			return;
		}

		// Invalidate all queries when org changes
		queryClient.invalidateQueries();
	}, [orgId, queryClient]);

	return null;
}
