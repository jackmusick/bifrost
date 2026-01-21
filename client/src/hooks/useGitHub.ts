/**
 * GitHub Integration hooks using openapi-react-query pattern
 *
 * Exports both hooks for React components and standalone async functions
 * for imperative usage outside of React hooks
 */

import { $api, apiClient } from "@/lib/api-client";
import { useQueryClient } from "@tanstack/react-query";
import type { components } from "@/lib/v1";

// =============================================================================
// Types - Auto-generated from OpenAPI spec
// =============================================================================

export type GitHubConnectRequest = components["schemas"]["GitHubConfigRequest"];
export type GitHubConfigResponse =
	components["schemas"]["GitHubConfigResponse"];
export type GitHubRepoInfo = components["schemas"]["GitHubRepoInfo"];
export type GitHubBranchInfo = components["schemas"]["GitHubBranchInfo"];
export type CreateRepoRequest = components["schemas"]["CreateRepoRequest"];
export type CreateRepoResponse = components["schemas"]["CreateRepoResponse"];
export type GitStatusResponse =
	components["schemas"]["GitRefreshStatusResponse"];
export type FileChange = components["schemas"]["FileChange"];
export type CommitInfo = components["schemas"]["CommitInfo"];
export type ConflictInfo = components["schemas"]["ConflictInfo"];
export type CommitHistoryResponse =
	components["schemas"]["CommitHistoryResponse"];

// Sync types - manually defined since SyncPreviewResponse is now sent via WebSocket
// and not exposed as an HTTP response, so it's pruned from the OpenAPI schema.
// These must match the Python models in api/src/models/contracts/github.py

export type SyncActionType = "add" | "modify" | "delete";

export interface SyncAction {
	path: string;
	action: SyncActionType;
	sha?: string | null;
	display_name?: string | null;
	entity_type?: string | null;
	parent_slug?: string | null;
}

export interface SyncConflictInfo {
	path: string;
	local_content?: string | null;
	remote_content?: string | null;
	local_sha: string;
	remote_sha: string;
	display_name?: string | null;
	entity_type?: string | null;
	parent_slug?: string | null;
}

export interface WorkflowReference {
	type: string;
	id: string;
	name: string;
}

export interface OrphanInfo {
	workflow_id: string;
	workflow_name: string;
	function_name: string;
	last_path: string;
	used_by: WorkflowReference[];
}

export interface SyncUnresolvedRefInfo {
	entity_type: string;
	entity_path: string;
	field_path: string;
	portable_ref: string;
}

export interface SyncSerializationError {
	entity_type: string;
	entity_id: string;
	entity_name: string;
	path: string;
	error: string;
}

export interface SyncPreviewResponse {
	to_pull: SyncAction[];
	to_push: SyncAction[];
	conflicts: SyncConflictInfo[];
	will_orphan: OrphanInfo[];
	unresolved_refs: SyncUnresolvedRefInfo[];
	serialization_errors: SyncSerializationError[];
	is_empty: boolean;
}

export type SyncPreviewJobResponse = components["schemas"]["SyncPreviewJobResponse"];
export type SyncExecuteRequest = components["schemas"]["SyncExecuteRequest"];
export type SyncExecuteResponse = components["schemas"]["SyncExecuteResponse"];

// =============================================================================
// Query Hooks
// =============================================================================

/**
 * Get current Git status
 */
export function useGitStatus() {
	return $api.useQuery("get", "/api/github/status", {}, {});
}

/**
 * Get current GitHub configuration
 */
export function useGitHubConfig() {
	return $api.useQuery("get", "/api/github/config", {}, {});
}

/**
 * List repositories accessible with saved token
 * Only runs when enabled is true (defaults to true)
 */
export function useGitHubRepositories(enabled: boolean = true) {
	return $api.useQuery("get", "/api/github/repositories", {}, { enabled });
}

/**
 * Get commit history with pagination
 * Query parameters are passed via the query key to enable proper caching
 */
export function useGitCommits(limit: number = 20, offset: number = 0) {
	return $api.useQuery(
		"get",
		"/api/github/commits",
		{
			params: {
				query: { limit, offset },
			},
		},
		{},
	);
}

/**
 * List branches for a repository
 */
export function useGitHubBranches(repoFullName?: string) {
	return $api.useQuery(
		"get",
		"/api/github/branches",
		{
			params: {
				query: { repo: repoFullName || "" },
			},
		},
		{
			enabled: !!repoFullName,
		},
	);
}

// =============================================================================
// Mutation Hooks
// =============================================================================

/**
 * Validate GitHub token and list repositories
 */
export function useValidateGitHubToken() {
	const queryClient = useQueryClient();
	return $api.useMutation("post", "/api/github/validate", {
		onSuccess: () => {
			// Invalidate repositories cache after validation
			queryClient.invalidateQueries({
				queryKey: ["get", "/api/github/repositories"],
			});
		},
	});
}

/**
 * Configure GitHub integration
 */
export function useConfigureGitHub() {
	const queryClient = useQueryClient();
	return $api.useMutation("post", "/api/github/configure", {
		onSuccess: () => {
			// Invalidate related queries after configuration
			queryClient.invalidateQueries({
				queryKey: ["get", "/api/github/config"],
			});
			queryClient.invalidateQueries({
				queryKey: ["get", "/api/github/status"],
			});
		},
	});
}

/**
 * Create a new GitHub repository
 */
export function useCreateGitHubRepository() {
	const queryClient = useQueryClient();
	return $api.useMutation("post", "/api/github/create-repository", {
		onSuccess: () => {
			// Invalidate repositories list after creation
			queryClient.invalidateQueries({
				queryKey: ["get", "/api/github/repositories"],
			});
		},
	});
}

/**
 * Disconnect GitHub integration
 */
export function useDisconnectGitHub() {
	const queryClient = useQueryClient();
	return $api.useMutation("post", "/api/github/disconnect", {
		onSuccess: () => {
			// Clear all GitHub-related caches
			queryClient.invalidateQueries({
				queryKey: ["get", "/api/github/config"],
			});
			queryClient.invalidateQueries({
				queryKey: ["get", "/api/github/status"],
			});
			queryClient.invalidateQueries({
				queryKey: ["get", "/api/github/repositories"],
			});
		},
	});
}

/**
 * Queue sync preview job - returns immediately with job_id
 *
 * The caller should subscribe to WebSocket channel git:{job_id} to receive:
 * - Progress updates (git_progress messages with phases like 'cloning', 'scanning')
 * - Completion with full preview data (git_preview_complete message)
 *
 * Returns a mutation-like interface for imperative usage (mutateAsync pattern).
 */
export function useSyncPreview() {
	return {
		mutateAsync: async (): Promise<SyncPreviewJobResponse> => {
			const response = await apiClient.GET("/api/github/sync");
			if (!response.data) {
				const errorDetail =
					(response.error as { detail?: string } | undefined)?.detail ||
					"Failed to queue sync preview";
				throw new Error(errorDetail);
			}
			return response.data as SyncPreviewJobResponse;
		},
		isPending: false,
	};
}

/**
 * Execute sync with conflict resolutions and orphan confirmation
 *
 * NOTE: This queues a background job and returns immediately with job_id.
 * The client should subscribe to WebSocket channel git:{job_id} AFTER
 * receiving the response to get progress/completion messages.
 * Query invalidation should happen in the UI when WebSocket completion is received.
 *
 * Returns a mutation-like interface for imperative usage (mutateAsync pattern).
 */
export function useSyncExecute() {
	return {
		mutateAsync: async (params: {
			body: SyncExecuteRequest;
		}): Promise<SyncExecuteResponse> => {
			const response = await apiClient.POST("/api/github/sync", {
				body: params.body,
			});
			if (!response.data) {
				const errorDetail =
					(response.error as { detail?: string } | undefined)?.detail ||
					"Failed to queue sync";
				throw new Error(errorDetail);
			}
			// Returns job_id and status="queued", actual results come via WebSocket
			return response.data as SyncExecuteResponse;
		},
		isPending: false,
	};
}

// =============================================================================
// Standalone async functions for imperative usage (outside React)
// =============================================================================

/**
 * Validate GitHub token and list repositories (imperative)
 */
export async function validateGitHubToken(token: string) {
	const response = await apiClient.POST("/api/github/validate", {
		body: { token },
	});

	if (response.error) {
		throw new Error("Failed to validate token");
	}

	return response.data;
}

/**
 * List branches for a repository (imperative)
 */
export async function listGitHubBranches(repoFullName: string) {
	const response = await apiClient.GET("/api/github/branches", {
		params: {
			query: { repo: repoFullName },
		},
	});

	if (response.error) {
		throw new Error("Failed to list branches");
	}

	const data = response.data as { branches: GitHubBranchInfo[] };
	return data.branches;
}
