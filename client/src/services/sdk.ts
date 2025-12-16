/**
 * SDK Service
 *
 * API methods for developer context and API key management.
 * Enables local SDK development workflow.
 *
 * Note: These endpoints are not in the OpenAPI spec, so we use authFetch
 * instead of the typed apiClient.
 */

import { authFetch } from "@/lib/api-client";

// =============================================================================
// Types
// =============================================================================

export interface DeveloperContext {
	user: {
		id: string;
		email: string;
		name: string;
	};
	organization: {
		id: string;
		name: string;
	} | null;
	default_parameters: Record<string, unknown>;
	track_executions: boolean;
}

export interface DeveloperApiKey {
	id: string;
	name: string;
	key_prefix: string;
	created_at: string;
	last_used_at: string | null;
	expires_at: string | null;
	is_active: boolean;
}

export interface CreateApiKeyRequest {
	name: string;
	expires_in_days?: number | null;
}

export interface CreateApiKeyResponse {
	id: string;
	name: string;
	key: string; // Full key - only shown once
	key_prefix: string;
	created_at: string;
	expires_at: string | null;
}

export interface UpdateContextRequest {
	default_org_id?: string | null;
	default_parameters?: Record<string, unknown>;
	track_executions?: boolean;
}

// =============================================================================
// Developer Context
// =============================================================================

export async function getContext(): Promise<DeveloperContext> {
	const response = await authFetch("/api/cli/context");
	if (!response.ok) {
		throw new Error(`Failed to get context: ${response.statusText}`);
	}
	return response.json();
}

export async function updateContext(
	data: UpdateContextRequest,
): Promise<DeveloperContext> {
	const response = await authFetch("/api/cli/context", {
		method: "PUT",
		body: JSON.stringify(data),
	});
	if (!response.ok) {
		throw new Error(`Failed to update context: ${response.statusText}`);
	}
	return response.json();
}

// =============================================================================
// API Keys
// =============================================================================

export async function listApiKeys(): Promise<DeveloperApiKey[]> {
	const response = await authFetch("/api/cli/keys");
	if (!response.ok) {
		throw new Error(`Failed to list API keys: ${response.statusText}`);
	}
	const data = await response.json();
	return data.keys;
}

export async function createApiKey(
	data: CreateApiKeyRequest,
): Promise<CreateApiKeyResponse> {
	const response = await authFetch("/api/cli/keys", {
		method: "POST",
		body: JSON.stringify(data),
	});
	if (!response.ok) {
		throw new Error(`Failed to create API key: ${response.statusText}`);
	}
	return response.json();
}

export async function revokeApiKey(keyId: string): Promise<void> {
	const response = await authFetch(`/api/cli/keys/${keyId}`, {
		method: "DELETE",
	});
	if (!response.ok) {
		throw new Error(`Failed to revoke API key: ${response.statusText}`);
	}
}

// =============================================================================
// SDK Download
// =============================================================================

export function getSdkDownloadUrl(): string {
	return "/api/cli/download";
}

// =============================================================================
// Service Export
// =============================================================================

export const sdkService = {
	getContext,
	updateContext,
	listApiKeys,
	createApiKey,
	revokeApiKey,
	getSdkDownloadUrl,
};
