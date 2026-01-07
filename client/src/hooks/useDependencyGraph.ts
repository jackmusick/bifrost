/**
 * Dependency Graph API hooks
 *
 * Provides hooks for fetching entity dependency graphs.
 */

import { $api } from "@/lib/api-client";
import type { components } from "@/lib/v1";

// Re-export types for convenience
export type GraphNode = components["schemas"]["GraphNodeResponse"];
export type GraphEdge = components["schemas"]["GraphEdgeResponse"];
export type DependencyGraph = components["schemas"]["DependencyGraphResponse"];
export type EntityType = "workflow" | "form" | "app" | "agent";

/**
 * Hook to fetch dependency graph for an entity
 *
 * @param entityType - Type of the root entity (workflow, form, app, agent)
 * @param entityId - UUID of the root entity
 * @param depth - Maximum traversal depth (1-5, default 2)
 */
export function useDependencyGraph(
	entityType: EntityType | undefined,
	entityId: string | undefined,
	depth: number = 2,
) {
	return $api.useQuery(
		"get",
		"/api/dependencies/{entity_type}/{entity_id}",
		{
			params: {
				path: {
					entity_type: entityType ?? "workflow",
					entity_id: entityId ?? "",
				},
				query: { depth },
			},
		},
		{
			enabled: !!entityType && !!entityId,
			staleTime: 30000, // Cache for 30 seconds
		},
	);
}
