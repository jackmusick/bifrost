/**
 * Agent Management API hooks
 *
 * Provides hooks for:
 * - Listing and fetching agents
 * - Creating, updating, and deleting agents
 * - Managing agent tools and delegations
 */

import { useQueryClient } from "@tanstack/react-query";
import { $api } from "@/lib/api-client";
import { toast } from "sonner";
import type { components } from "@/lib/v1";

// Re-export types for convenience
export type AgentPublic = components["schemas"]["AgentPublic"];
export type AgentSummary = components["schemas"]["AgentSummary"];
export type AgentCreate = components["schemas"]["AgentCreate"];
export type AgentUpdate = components["schemas"]["AgentUpdate"];

/** Helper to extract error message from API error response */
function getErrorMessage(error: unknown, fallback: string): string {
	if (typeof error === "object" && error && "message" in error) {
		return String((error as Record<string, unknown>)["message"]);
	}
	if (error instanceof Error) {
		return error.message;
	}
	return fallback;
}

// ==================== Query Hooks ====================

/** Hook to fetch all agents */
export function useAgents() {
	return $api.useQuery("get", "/api/agents", {});
}

/** Hook to fetch a specific agent */
export function useAgent(agentId: string | undefined) {
	return $api.useQuery(
		"get",
		"/api/agents/{agent_id}",
		{ params: { path: { agent_id: agentId ?? "" } } },
		{ enabled: !!agentId },
	);
}

/** Hook to fetch agent tools */
export function useAgentTools(agentId: string | undefined) {
	return $api.useQuery(
		"get",
		"/api/agents/{agent_id}/tools",
		{ params: { path: { agent_id: agentId ?? "" } } },
		{ enabled: !!agentId },
	);
}

/** Hook to fetch agent delegations */
export function useAgentDelegations(agentId: string | undefined) {
	return $api.useQuery(
		"get",
		"/api/agents/{agent_id}/delegations",
		{ params: { path: { agent_id: agentId ?? "" } } },
		{ enabled: !!agentId },
	);
}

// ==================== Mutation Hooks ====================

/** Hook to create a new agent */
export function useCreateAgent() {
	const queryClient = useQueryClient();

	return $api.useMutation("post", "/api/agents", {
		onSuccess: (_data, variables) => {
			queryClient.invalidateQueries({ queryKey: ["get", "/api/agents"] });
			const name = (variables.body as AgentCreate)?.name;
			toast.success("Agent created", {
				description: `Agent "${name}" has been created`,
			});
		},
		onError: (error) => {
			toast.error("Failed to create agent", {
				description: getErrorMessage(error, "Unknown error"),
			});
		},
	});
}

/** Hook to update an agent */
export function useUpdateAgent() {
	const queryClient = useQueryClient();

	return $api.useMutation("put", "/api/agents/{agent_id}", {
		onSuccess: (_data, variables) => {
			const agentId = (variables.params as { path: { agent_id: string } })
				.path.agent_id;
			queryClient.invalidateQueries({ queryKey: ["get", "/api/agents"] });
			queryClient.invalidateQueries({
				queryKey: [
					"get",
					"/api/agents/{agent_id}",
					{ params: { path: { agent_id: agentId } } },
				],
			});
			toast.success("Agent updated");
		},
		onError: (error) => {
			toast.error("Failed to update agent", {
				description: getErrorMessage(error, "Unknown error"),
			});
		},
	});
}

/** Hook to delete an agent (soft delete) */
export function useDeleteAgent() {
	const queryClient = useQueryClient();

	return $api.useMutation("delete", "/api/agents/{agent_id}", {
		onSuccess: () => {
			queryClient.invalidateQueries({ queryKey: ["get", "/api/agents"] });
			toast.success("Agent deleted");
		},
		onError: (error) => {
			toast.error("Failed to delete agent", {
				description: getErrorMessage(error, "Unknown error"),
			});
		},
	});
}

/** Hook to assign tools to an agent */
export function useAssignAgentTools() {
	const queryClient = useQueryClient();

	return $api.useMutation("post", "/api/agents/{agent_id}/tools", {
		onSuccess: (_data, variables) => {
			const agentId = (variables.params as { path: { agent_id: string } })
				.path.agent_id;
			queryClient.invalidateQueries({
				queryKey: [
					"get",
					"/api/agents/{agent_id}/tools",
					{ params: { path: { agent_id: agentId } } },
				],
			});
			toast.success("Tools assigned");
		},
		onError: (error) => {
			toast.error("Failed to assign tools", {
				description: getErrorMessage(error, "Unknown error"),
			});
		},
	});
}

/** Hook to remove a tool from an agent */
export function useRemoveAgentTool() {
	const queryClient = useQueryClient();

	return $api.useMutation(
		"delete",
		"/api/agents/{agent_id}/tools/{workflow_id}",
		{
			onSuccess: (_data, variables) => {
				const agentId = (
					variables.params as {
						path: { agent_id: string; workflow_id: string };
					}
				).path.agent_id;
				queryClient.invalidateQueries({
					queryKey: [
						"get",
						"/api/agents/{agent_id}/tools",
						{ params: { path: { agent_id: agentId } } },
					],
				});
				toast.success("Tool removed");
			},
			onError: (error) => {
				toast.error("Failed to remove tool", {
					description: getErrorMessage(error, "Unknown error"),
				});
			},
		},
	);
}

/** Hook to assign delegations to an agent */
export function useAssignAgentDelegations() {
	const queryClient = useQueryClient();

	return $api.useMutation("post", "/api/agents/{agent_id}/delegations", {
		onSuccess: (_data, variables) => {
			const agentId = (variables.params as { path: { agent_id: string } })
				.path.agent_id;
			queryClient.invalidateQueries({
				queryKey: [
					"get",
					"/api/agents/{agent_id}/delegations",
					{ params: { path: { agent_id: agentId } } },
				],
			});
			toast.success("Delegations assigned");
		},
		onError: (error) => {
			toast.error("Failed to assign delegations", {
				description: getErrorMessage(error, "Unknown error"),
			});
		},
	});
}

/** Hook to remove a delegation from an agent */
export function useRemoveAgentDelegation() {
	const queryClient = useQueryClient();

	return $api.useMutation(
		"delete",
		"/api/agents/{agent_id}/delegations/{delegate_id}",
		{
			onSuccess: (_data, variables) => {
				const agentId = (
					variables.params as {
						path: { agent_id: string; delegate_id: string };
					}
				).path.agent_id;
				queryClient.invalidateQueries({
					queryKey: [
						"get",
						"/api/agents/{agent_id}/delegations",
						{ params: { path: { agent_id: agentId } } },
					],
				});
				toast.success("Delegation removed");
			},
			onError: (error) => {
				toast.error("Failed to remove delegation", {
					description: getErrorMessage(error, "Unknown error"),
				});
			},
		},
	);
}
