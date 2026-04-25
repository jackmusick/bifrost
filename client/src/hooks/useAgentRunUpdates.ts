/**
 * Realtime bridge between backend AgentRun broadcasts and react-query caches.
 *
 * The summarizer and execution worker publish `agent_run_update` messages on
 * the `agent-runs` channel (and `agent-run:{id}` for per-run). This hook
 * subscribes once per mounted consumer and invalidates the list-of-runs
 * queries so pages rerender with fresh summary_status / asked / did without
 * polling.
 */

import { useEffect } from "react";
import { useQueryClient } from "@tanstack/react-query";

import {
	webSocketService,
	type AgentRunUpdate,
} from "@/services/websocket";

export interface UseAgentRunUpdatesOptions {
	/** If set, only react to broadcasts for this agent. */
	agentId?: string;
	/** Extra callback (e.g. for toasting or per-row patching). */
	onUpdate?: (update: AgentRunUpdate) => void;
}

export function useAgentRunUpdates(options: UseAgentRunUpdatesOptions = {}) {
	const { agentId, onUpdate } = options;
	const queryClient = useQueryClient();

	useEffect(() => {
		void webSocketService.connect(["agent-runs"]);
		const unsubscribe = webSocketService.onAgentRunUpdate((update) => {
			if (agentId && update.agent_id !== agentId) return;
			// Invalidate the list query (prefix match picks up both
			// ["agent-runs"] and ["agent-runs", <runId>]).
			queryClient.invalidateQueries({ queryKey: ["agent-runs"] });
			// Verdicts and new runs move the needs_review / unreviewed counts
			// on per-agent stats. Prefix-invalidate the stats query so cards
			// reading stats.unreviewed / stats.needs_review refresh live.
			queryClient.invalidateQueries({
				queryKey: ["get", "/api/agents/{agent_id}/stats"],
			});
			// Also invalidate the openapi-react-query key shape used by
			// $api.useQuery callers (e.g. agent stats or any future
			// per-run hook wired through the generated client).
			if (update.run_id) {
				queryClient.invalidateQueries({
					queryKey: [
						"get",
						"/api/agent-runs/{run_id}",
						{ params: { path: { run_id: update.run_id } } },
					],
				});
			}
			onUpdate?.(update);
		});
		return unsubscribe;
	}, [agentId, onUpdate, queryClient]);
}
