/**
 * Agent tuning session API service.
 *
 * Wraps the consolidated tuning endpoints used by the agent-tuning UI:
 *
 * - `POST /api/agents/{id}/tuning-session` — generate a consolidated prompt
 *   proposal from this agent's flagged runs.
 * - `POST /api/agents/{id}/tuning-session/dry-run` — per-run dry-run of a
 *   proposed prompt across this agent's flagged runs (capped server-side).
 * - `POST /api/agents/{id}/tuning-session/apply` — apply the proposal:
 *   update the prompt, write a history entry, clear flagged verdicts.
 */

import { $api } from "@/lib/api-client";
import type { components } from "@/lib/v1";

// Re-export types for convenience
export type ConsolidatedProposal =
	components["schemas"]["ConsolidatedProposalResponse"];
export type ConsolidatedDryRunRequest =
	components["schemas"]["ConsolidatedDryRunRequest"];
export type ConsolidatedDryRunResponse =
	components["schemas"]["ConsolidatedDryRunResponse"];
export type ApplyTuningRequest = components["schemas"]["ApplyTuningRequest"];
export type ApplyTuningResponse = components["schemas"]["ApplyTuningResponse"];

/**
 * Generate a consolidated tuning proposal for an agent from its flagged runs.
 *
 * Mutation (not a query) because the server runs an LLM call to synthesize
 * the proposal; the UI should trigger it explicitly when the user opens the
 * tuning workflow.
 */
export function useTuningSession() {
	return $api.useMutation("post", "/api/agents/{agent_id}/tuning-session");
}

/**
 * Per-run dry-run of a proposed prompt across this agent's flagged runs.
 *
 * Service layer caps at 10 runs to bound cost.
 */
export function useTuningDryRun() {
	return $api.useMutation(
		"post",
		"/api/agents/{agent_id}/tuning-session/dry-run",
	);
}

/**
 * Apply a consolidated tuning proposal: update prompt, write history, clear
 * verdicts on the affected flagged runs.
 */
export function useApplyTuning() {
	return $api.useMutation(
		"post",
		"/api/agents/{agent_id}/tuning-session/apply",
	);
}
