/**
 * Hook for knowledge namespace management
 *
 * Used for selecting knowledge sources in agent configuration.
 */

import { useQuery } from "@tanstack/react-query";

export interface KnowledgeNamespaceInfo {
	namespace: string;
	scopes: {
		global: number;
		org: number;
		total: number;
	};
}

/**
 * Fetch knowledge namespaces from the CLI API
 *
 * @param scope - Optional organization scope filter:
 *   - undefined: don't send scope param (backend uses DeveloperContext)
 *   - "global": only global knowledge sources
 *   - UUID string: that org's knowledge sources + global (cascade)
 */
async function fetchKnowledgeNamespaces(
	scope?: string,
): Promise<KnowledgeNamespaceInfo[]> {
	const params = new URLSearchParams();
	if (scope) {
		params.set("scope", scope);
	}
	const url = `/api/cli/knowledge/namespaces${params.toString() ? `?${params}` : ""}`;

	const response = await fetch(url, {
		method: "GET",
		headers: {
			"Content-Type": "application/json",
		},
		credentials: "include",
	});

	if (!response.ok) {
		if (response.status === 404) {
			// No knowledge namespaces exist yet
			return [];
		}
		throw new Error(`Failed to fetch namespaces: ${response.status}`);
	}

	return response.json();
}

/**
 * Hook to fetch available knowledge namespaces
 *
 * Returns list of namespace info with document counts.
 * Used in AgentDialog for selecting knowledge sources.
 *
 * @param scope - Organization scope filter:
 *   - undefined: don't send scope param (backend uses DeveloperContext)
 *   - null: global only - sends scope=global
 *   - UUID string: that org + global (cascade)
 */
export function useKnowledgeNamespaces(scope?: string | null) {
	// Convert null to "global", undefined means don't send scope param
	const scopeParam = scope === null ? "global" : scope;

	return useQuery({
		queryKey: ["knowledge", "namespaces", scopeParam],
		queryFn: () => fetchKnowledgeNamespaces(scopeParam),
		staleTime: 60 * 1000, // Cache for 1 minute
		retry: false,
	});
}
