/**
 * Dev Run service for CLI<->Web workflow execution communication
 */

import { authFetch } from "@/lib/api-client";

// Types matching backend models
export interface WorkflowParameterInfo {
	name: string;
	type: string;
	label: string | null;
	required: boolean;
	default_value: unknown | null;
}

export interface RegisteredWorkflow {
	name: string;
	description: string;
	parameters: WorkflowParameterInfo[];
}

export interface DevRunStateResponse {
	file_path: string;
	workflows: RegisteredWorkflow[];
	selected_workflow: string | null;
	pending: boolean;
}

export interface DevRunContinueRequest {
	workflow_name: string;
	params: Record<string, unknown>;
}

/**
 * Get current dev run state for web UI
 * Returns null if no active session
 */
export async function getDevRunState(): Promise<DevRunStateResponse | null> {
	const response = await authFetch("/api/sdk/run/state");
	if (response.status === 204) {
		return null;
	}
	if (!response.ok) {
		const error = await response.json().catch(() => ({}));
		throw new Error(error.detail || `Failed to get dev run state: ${response.statusText}`);
	}
	return response.json();
}

/**
 * Submit parameters to continue workflow execution
 */
export async function continueDevRun(request: DevRunContinueRequest): Promise<{ status: string; workflow: string }> {
	const response = await authFetch("/api/sdk/run/continue", {
		method: "POST",
		headers: { "Content-Type": "application/json" },
		body: JSON.stringify(request),
	});
	if (!response.ok) {
		const error = await response.json().catch(() => ({}));
		throw new Error(error.detail || `Failed to continue dev run: ${response.statusText}`);
	}
	return response.json();
}

export const devRunService = {
	getDevRunState,
	continueDevRun,
};
