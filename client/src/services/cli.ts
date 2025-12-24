/**
 * CLI Sessions service for CLI<->Web workflow execution communication
 *
 * Replaces local-runner.ts with session-based API endpoints.
 */

import { authFetch } from "@/lib/api-client";
import type { components } from "@/lib/v1";

// Re-export types from generated API
export type WorkflowParameter = components["schemas"]["WorkflowParameter"];
export type CLIRegisteredWorkflow =
	components["schemas"]["CLIRegisteredWorkflow"];
export type CLISessionExecutionSummary =
	components["schemas"]["CLISessionExecutionSummary"];
export type CLISessionResponse = components["schemas"]["CLISessionResponse"];
export type CLISessionListResponse =
	components["schemas"]["CLISessionListResponse"];
export type CLISessionContinueRequest =
	components["schemas"]["CLISessionContinueRequest"];
export type CLISessionContinueResponse =
	components["schemas"]["CLISessionContinueResponse"];

/**
 * Get list of all CLI sessions for current user
 */
export async function getCLISessions(): Promise<CLISessionListResponse> {
	const response = await authFetch("/api/cli/sessions");
	if (!response.ok) {
		const error = await response.json().catch(() => ({}));
		throw new Error(
			error.detail ||
				`Failed to get CLI sessions: ${response.statusText}`,
		);
	}
	return response.json();
}

/**
 * Get a specific CLI session by ID
 * Returns null if session not found
 */
export async function getCLISession(
	sessionId: string,
): Promise<CLISessionResponse | null> {
	const response = await authFetch(`/api/cli/sessions/${sessionId}`);
	if (response.status === 204 || response.status === 404) {
		return null;
	}
	if (!response.ok) {
		const error = await response.json().catch(() => ({}));
		throw new Error(
			error.detail || `Failed to get CLI session: ${response.statusText}`,
		);
	}
	return response.json();
}

/**
 * Delete a CLI session
 */
export async function deleteCLISession(sessionId: string): Promise<void> {
	const response = await authFetch(`/api/cli/sessions/${sessionId}`, {
		method: "DELETE",
	});
	if (!response.ok && response.status !== 204) {
		const error = await response.json().catch(() => ({}));
		throw new Error(
			error.detail ||
				`Failed to delete CLI session: ${response.statusText}`,
		);
	}
}

/**
 * Submit parameters to continue workflow execution in a session
 */
export async function continueCLISession(
	sessionId: string,
	request: CLISessionContinueRequest,
): Promise<CLISessionContinueResponse> {
	const response = await authFetch(
		`/api/cli/sessions/${sessionId}/continue`,
		{
			method: "POST",
			headers: { "Content-Type": "application/json" },
			body: JSON.stringify(request),
		},
	);
	if (!response.ok) {
		const error = await response.json().catch(() => ({}));
		throw new Error(
			error.detail ||
				`Failed to continue CLI session: ${response.statusText}`,
		);
	}
	return response.json();
}

export const cliService = {
	getCLISessions,
	getCLISession,
	deleteCLISession,
	continueCLISession,
};
