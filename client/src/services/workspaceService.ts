/**
 * Workspaces API service.
 *
 * Wraps `/api/workspaces`. Workspaces have three scopes:
 *   - `personal` — Private to the owner.
 *   - `org`      — Shared with the workspace's organization.
 *   - `role`     — Shared with members of a specific role.
 *
 * Conversations may belong to a workspace OR live in the general pool
 * (workspace_id IS NULL — the unscoped chat list). There's no synthetic
 * "Personal" workspace; users create private workspaces explicitly.
 */

import { useQueryClient } from "@tanstack/react-query";

import { $api } from "@/lib/api-client";
import type { components } from "@/lib/v1";

export type Workspace = components["schemas"]["WorkspacePublic"];
export type WorkspaceSummary = components["schemas"]["WorkspaceSummary"];
export type WorkspaceCreate = components["schemas"]["WorkspaceCreate"];
export type WorkspaceUpdate = components["schemas"]["WorkspaceUpdate"];
export type WorkspaceScope = components["schemas"]["WorkspaceScope"];

const WORKSPACES_KEY = ["get", "/api/workspaces"] as const;

/** List workspaces visible to the current user. */
export function useWorkspaces(activeOnly = true) {
	return $api.useQuery("get", "/api/workspaces", {
		params: { query: { active_only: activeOnly } },
	});
}

/** Single workspace by id. */
export function useWorkspace(workspaceId: string | undefined) {
	return $api.useQuery(
		"get",
		"/api/workspaces/{workspace_id}",
		{
			params: { path: { workspace_id: workspaceId ?? "" } },
		},
		{ enabled: !!workspaceId },
	);
}

/** Create a workspace at any scope (personal / org / role). */
export function useCreateWorkspace() {
	const queryClient = useQueryClient();
	return $api.useMutation("post", "/api/workspaces", {
		onSuccess: () => {
			queryClient.invalidateQueries({ queryKey: WORKSPACES_KEY });
		},
	});
}

/** Update mutable fields of a workspace. Scope is immutable. */
export function useUpdateWorkspace() {
	const queryClient = useQueryClient();
	return $api.useMutation(
		"patch",
		"/api/workspaces/{workspace_id}",
		{
			onSuccess: (data) => {
				queryClient.invalidateQueries({ queryKey: WORKSPACES_KEY });
				queryClient.invalidateQueries({
					queryKey: [
						"get",
						"/api/workspaces/{workspace_id}",
						{ params: { path: { workspace_id: data.id } } },
					],
				});
			},
		},
	);
}

/** Soft-delete a workspace. */
export function useDeleteWorkspace() {
	const queryClient = useQueryClient();
	return $api.useMutation(
		"delete",
		"/api/workspaces/{workspace_id}",
		{
			onSuccess: () => {
				queryClient.invalidateQueries({ queryKey: WORKSPACES_KEY });
			},
		},
	);
}

/**
 * Move a chat into a workspace (or back to the general pool).
 * Pass `workspace_id: null` in the body to move to the general pool.
 */
export function useMoveConversation() {
	const queryClient = useQueryClient();
	return $api.useMutation(
		"patch",
		"/api/chat/conversations/{conversation_id}",
		{
			onSuccess: () => {
				queryClient.invalidateQueries({
					queryKey: ["get", "/api/chat/conversations"],
				});
				queryClient.invalidateQueries({ queryKey: WORKSPACES_KEY });
			},
		},
	);
}
