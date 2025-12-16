/**
 * CLI Sessions service for CLI<->Web workflow execution communication
 *
 * Replaces local-runner.ts with session-based API endpoints.
 *
 * TODO: Once types are regenerated, replace manual interfaces with:
 * export type CLISessionResponse = components["schemas"]["CLISessionResponse"];
 * etc.
 */

import { authFetch } from "@/lib/api-client";
import type { components } from "@/lib/v1";

// Re-export types from generated API
export type WorkflowParameter = components["schemas"]["WorkflowParameter"];

// Manual type definitions until types are regenerated
// These match the Pydantic models in api/src/models/contracts/cli.py
export interface CLIRegisteredWorkflow {
	name: string;
	description: string;
	parameters: WorkflowParameter[];
}

export interface CLISessionExecutionSummary {
	id: string;
	workflow_name: string;
	status: string;
	created_at: string;
	duration_ms: number | null;
}

export interface CLISessionResponse {
	id: string;
	user_id: string;
	file_path: string;
	workflows: CLIRegisteredWorkflow[];
	selected_workflow: string | null;
	params: Record<string, unknown> | null;
	pending: boolean;
	last_seen: string | null;
	created_at: string;
	is_connected: boolean;
	executions: CLISessionExecutionSummary[];
}

export interface CLISessionListResponse {
	sessions: CLISessionResponse[];
}

export interface CLISessionContinueRequest {
	workflow_name: string;
	params: Record<string, unknown>;
}

export interface CLISessionContinueResponse {
	status: string;
	execution_id: string;
	workflow: string;
}

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
