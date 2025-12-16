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
export type WorkspaceAnalysisResponse =
	components["schemas"]["WorkspaceAnalysisResponse"];
export type CreateRepoRequest = components["schemas"]["CreateRepoRequest"];
export type CreateRepoResponse = components["schemas"]["CreateRepoResponse"];
export type GitStatusResponse =
	components["schemas"]["GitRefreshStatusResponse"];
export type PullRequest = components["schemas"]["PullFromGitHubRequest"];
export type PushRequest = components["schemas"]["PushToGitHubRequest"];
export type FileChange = components["schemas"]["FileChange"];
export type CommitInfo = components["schemas"]["CommitInfo"];
export type ConflictInfo = components["schemas"]["ConflictInfo"];
export type CommitHistoryResponse =
	components["schemas"]["CommitHistoryResponse"];
export type DiscardCommitsResponse =
	components["schemas"]["DiscardUnpushedCommitsResponse"];

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
 */
export function useGitHubRepositories() {
	return $api.useQuery("get", "/api/github/repositories", {}, {});
}

/**
 * Get list of local changes
 */
export function useGitChanges() {
	return $api.useQuery("get", "/api/github/changes", {}, {});
}

/**
 * Get merge conflicts
 */
export function useGitConflicts() {
	return $api.useQuery("get", "/api/github/conflicts", {}, {});
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
 * Refresh Git status - uses GitHub API to get complete Git status
 */
export function useRefreshGitStatus() {
	const queryClient = useQueryClient();
	return $api.useMutation("post", "/api/github/refresh", {
		onSuccess: () => {
			// Invalidate status cache after refresh
			queryClient.invalidateQueries({
				queryKey: ["get", "/api/github/status"],
			});
		},
	});
}

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
 * Analyze workspace before configuration
 */
export function useAnalyzeWorkspace() {
	return $api.useMutation("post", "/api/github/analyze-workspace", {});
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
			queryClient.invalidateQueries({
				queryKey: ["get", "/api/github/changes"],
			});
		},
	});
}

/**
 * Initialize Git repository with remote
 */
export function useInitRepo() {
	const queryClient = useQueryClient();
	return $api.useMutation("post", "/api/github/init", {
		onSuccess: () => {
			queryClient.invalidateQueries({
				queryKey: ["get", "/api/github/status"],
			});
		},
	});
}

/**
 * Pull changes from remote repository
 */
export function usePullFromGitHub() {
	const queryClient = useQueryClient();
	return $api.useMutation("post", "/api/github/pull", {
		onSuccess: () => {
			queryClient.invalidateQueries({
				queryKey: ["get", "/api/github/status"],
			});
			queryClient.invalidateQueries({
				queryKey: ["get", "/api/github/changes"],
			});
			queryClient.invalidateQueries({
				queryKey: ["get", "/api/github/commits"],
			});
		},
	});
}

/**
 * Commit local changes
 */
export function useCommitChanges() {
	const queryClient = useQueryClient();
	return $api.useMutation("post", "/api/github/commit", {
		onSuccess: () => {
			queryClient.invalidateQueries({
				queryKey: ["get", "/api/github/status"],
			});
			queryClient.invalidateQueries({
				queryKey: ["get", "/api/github/changes"],
			});
			queryClient.invalidateQueries({
				queryKey: ["get", "/api/github/commits"],
			});
		},
	});
}

/**
 * Push committed changes to remote repository
 */
export function usePushToGitHub() {
	const queryClient = useQueryClient();
	return $api.useMutation("post", "/api/github/push", {
		onSuccess: () => {
			queryClient.invalidateQueries({
				queryKey: ["get", "/api/github/status"],
			});
			queryClient.invalidateQueries({
				queryKey: ["get", "/api/github/commits"],
			});
		},
	});
}

/**
 * Discard all unpushed commits
 */
export function useDiscardUnpushedCommits() {
	const queryClient = useQueryClient();
	return $api.useMutation("post", "/api/github/discard-unpushed", {
		onSuccess: () => {
			queryClient.invalidateQueries({
				queryKey: ["get", "/api/github/status"],
			});
			queryClient.invalidateQueries({
				queryKey: ["get", "/api/github/commits"],
			});
		},
	});
}

/**
 * Discard a specific commit and all newer commits
 */
export function useDiscardCommit() {
	const queryClient = useQueryClient();
	return $api.useMutation("post", "/api/github/discard-commit", {
		onSuccess: () => {
			queryClient.invalidateQueries({
				queryKey: ["get", "/api/github/status"],
			});
			queryClient.invalidateQueries({
				queryKey: ["get", "/api/github/commits"],
			});
		},
	});
}

/**
 * Abort current merge operation
 */
export function useAbortMerge() {
	const queryClient = useQueryClient();
	return $api.useMutation("post", "/api/github/abort-merge", {
		onSuccess: () => {
			queryClient.invalidateQueries({
				queryKey: ["get", "/api/github/status"],
			});
			queryClient.invalidateQueries({
				queryKey: ["get", "/api/github/conflicts"],
			});
		},
	});
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
