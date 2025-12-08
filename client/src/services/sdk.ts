/**
 * SDK Service
 *
 * API methods for developer context and API key management.
 * Enables local SDK development workflow.
 */

import { apiClient } from "@/lib/api-client";

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
  const response = await apiClient.get<DeveloperContext>("/api/sdk/context");
  return response;
}

export async function updateContext(
  data: UpdateContextRequest
): Promise<DeveloperContext> {
  const response = await apiClient.put<DeveloperContext>(
    "/api/sdk/context",
    data
  );
  return response;
}

// =============================================================================
// API Keys
// =============================================================================

export async function listApiKeys(): Promise<DeveloperApiKey[]> {
  const response = await apiClient.get<{ keys: DeveloperApiKey[] }>(
    "/api/sdk/keys"
  );
  return response.keys;
}

export async function createApiKey(
  data: CreateApiKeyRequest
): Promise<CreateApiKeyResponse> {
  const response = await apiClient.post<CreateApiKeyResponse>(
    "/api/sdk/keys",
    data
  );
  return response;
}

export async function revokeApiKey(keyId: string): Promise<void> {
  await apiClient.delete(`/api/sdk/keys/${keyId}`);
}

// =============================================================================
// SDK Download
// =============================================================================

export function getSdkDownloadUrl(): string {
  return "/api/sdk/download";
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
