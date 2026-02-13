/**
 * GitHub Integration hooks using openapi-react-query pattern
 *
 * Exports both hooks for React components and standalone async functions
 * for imperative usage outside of React hooks
 */

import { $api, apiClient, authFetch } from "@/lib/api-client";
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

// Preflight types - used by CommitResult
export interface PreflightIssue {
	path: string;
	line?: number | null;
	message: string;
	severity: "error" | "warning";
	category: "syntax" | "lint" | "ref" | "orphan" | "manifest" | "health";
	fix_hint?: string | null;
	auto_fixable?: boolean;
}

export interface PreflightResult {
	valid: boolean;
	issues: PreflightIssue[];
}

// Desktop-style git types - manually defined since results are sent via WebSocket
// These match the Python models in api/src/models/contracts/github.py

export interface GitJobResponse {
	job_id: string;
	status: string;
}

export interface ChangedFile {
	path: string;
	change_type: "added" | "modified" | "deleted" | "renamed" | "untracked";
	display_name?: string | null;
	entity_type?: string | null;
}

export interface MergeConflict {
	path: string;
	ours_content?: string | null;
	theirs_content?: string | null;
	display_name?: string | null;
	entity_type?: string | null;
}

export interface FetchResult {
	success: boolean;
	commits_ahead: number;
	commits_behind: number;
	remote_branch_exists: boolean;
	error?: string | null;
}

export interface WorkingTreeStatus {
	changed_files: ChangedFile[];
	total_changes: number;
	conflicts?: MergeConflict[];
}

export interface CommitResult {
	success: boolean;
	commit_sha?: string | null;
	files_committed: number;
	error?: string | null;
	preflight?: PreflightResult | null;
}

export interface PullResult {
	success: boolean;
	pulled: number;
	commit_sha?: string | null;
	conflicts: MergeConflict[];
	error?: string | null;
}

export interface PushResult {
	success: boolean;
	commit_sha?: string | null;
	pushed_commits: number;
	error?: string | null;
}

export interface ResolveResult {
	success: boolean;
	pulled: number;
	error?: string | null;
}

export interface DiffResult {
	path: string;
	head_content?: string | null;
	working_content?: string | null;
}

export interface DiscardResult {
	success: boolean;
	discarded: string[];
	error?: string | null;
}

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

// =============================================================================
// Desktop-style git operation hooks
// =============================================================================

/**
 * Queue a git fetch operation - returns job_id for WebSocket tracking
 */
export function useFetch() {
	return {
		mutateAsync: async (): Promise<GitJobResponse> => {
			const response = await authFetch("/api/github/fetch", { method: "POST" });
			if (!response.ok) {
				const error = await response.json().catch(() => ({}));
				throw new Error(error.detail || "Failed to queue fetch");
			}
			return (await response.json()) as GitJobResponse;
		},
		isPending: false,
	};
}

/**
 * Queue a git commit operation - returns job_id for WebSocket tracking
 */
export function useCommit() {
	return {
		mutateAsync: async (message: string): Promise<GitJobResponse> => {
			const response = await authFetch("/api/github/commit", {
				method: "POST",
				body: JSON.stringify({ message }),
			});
			if (!response.ok) {
				const error = await response.json().catch(() => ({}));
				throw new Error(error.detail || "Failed to queue commit");
			}
			return (await response.json()) as GitJobResponse;
		},
		isPending: false,
	};
}

/**
 * Queue a git pull operation - returns job_id for WebSocket tracking
 */
export function usePull() {
	return {
		mutateAsync: async (): Promise<GitJobResponse> => {
			const response = await authFetch("/api/github/pull", { method: "POST" });
			if (!response.ok) {
				const error = await response.json().catch(() => ({}));
				throw new Error(error.detail || "Failed to queue pull");
			}
			return (await response.json()) as GitJobResponse;
		},
		isPending: false,
	};
}

/**
 * Queue a git push operation - returns job_id for WebSocket tracking
 */
export function usePush() {
	return {
		mutateAsync: async (): Promise<GitJobResponse> => {
			const response = await authFetch("/api/github/push", { method: "POST" });
			if (!response.ok) {
				const error = await response.json().catch(() => ({}));
				throw new Error(error.detail || "Failed to queue push");
			}
			return (await response.json()) as GitJobResponse;
		},
		isPending: false,
	};
}

/**
 * Queue a working tree status check - returns job_id for WebSocket tracking
 */
export function useWorkingTreeChanges() {
	return {
		mutateAsync: async (): Promise<GitJobResponse> => {
			const response = await authFetch("/api/github/changes", {
				method: "POST",
			});
			if (!response.ok) {
				const error = await response.json().catch(() => ({}));
				throw new Error(error.detail || "Failed to queue status check");
			}
			return (await response.json()) as GitJobResponse;
		},
		isPending: false,
	};
}

/**
 * Queue conflict resolution - returns job_id for WebSocket tracking
 */
export function useResolveConflicts() {
	return {
		mutateAsync: async (
			resolutions: Record<string, "ours" | "theirs">,
		): Promise<GitJobResponse> => {
			const response = await authFetch("/api/github/resolve", {
				method: "POST",
				body: JSON.stringify({ resolutions }),
			});
			if (!response.ok) {
				const error = await response.json().catch(() => ({}));
				throw new Error(error.detail || "Failed to queue conflict resolution");
			}
			return (await response.json()) as GitJobResponse;
		},
		isPending: false,
	};
}

/**
 * Queue a discard operation - returns job_id for WebSocket tracking
 */
export function useDiscard() {
	return {
		mutateAsync: async (paths: string[]): Promise<GitJobResponse> => {
			const response = await authFetch("/api/github/discard", {
				method: "POST",
				body: JSON.stringify({ paths }),
			});
			if (!response.ok) {
				const error = await response.json().catch(() => ({}));
				throw new Error(error.detail || "Failed to queue discard");
			}
			return (await response.json()) as GitJobResponse;
		},
		isPending: false,
	};
}

/**
 * Queue a file diff operation - returns job_id for WebSocket tracking
 */
export function useFileDiff() {
	return {
		mutateAsync: async (path: string): Promise<GitJobResponse> => {
			const response = await authFetch("/api/github/diff", {
				method: "POST",
				body: JSON.stringify({ path }),
			});
			if (!response.ok) {
				const error = await response.json().catch(() => ({}));
				throw new Error(error.detail || "Failed to queue diff");
			}
			return (await response.json()) as GitJobResponse;
		},
		isPending: false,
	};
}

export function useCleanupOrphaned() {
	return $api.useMutation("post", "/api/maintenance/cleanup-orphaned");
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
