/**
 * Agent stats API service.
 *
 * Wraps the per-agent and fleet-wide stats endpoints. Core agent CRUD lives
 * in `@/hooks/useAgents` — this module covers the analytics surfaces added
 * for the agent management UI (T8/T27).
 */

import { $api } from "@/lib/api-client";
import type { components } from "@/lib/v1";

// Re-export types for convenience
export type AgentStats = components["schemas"]["AgentStatsResponse"];
export type FleetStats = components["schemas"]["FleetStatsResponse"];

/**
 * Hook to fetch per-agent run stats over a sliding window.
 *
 * @param agentId - UUID of the agent. Hook is disabled while undefined.
 * @param windowDays - Lookback window in days (default 7).
 */
export function useAgentStats(agentId: string | undefined, windowDays = 7) {
	return $api.useQuery(
		"get",
		"/api/agents/{agent_id}/stats",
		{
			params: {
				path: { agent_id: agentId ?? "" },
				query: { window_days: windowDays },
			},
		},
		{ enabled: !!agentId },
	);
}

/**
 * Hook to fetch fleet-wide agent stats.
 *
 * Superusers see cross-org totals; org users are scoped to their org.
 *
 * @param windowDays - Lookback window in days (default 7).
 */
export function useFleetStats(windowDays = 7) {
	return $api.useQuery("get", "/api/agents/stats/fleet", {
		params: { query: { window_days: windowDays } },
	});
}
