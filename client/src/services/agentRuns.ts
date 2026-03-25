/**
 * Agent Runs API service
 */

import { useEffect, useRef } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";
import { webSocketService, type AgentRunUpdate, type AgentRunStepUpdate } from "@/services/websocket";

// ============================================================================
// Types (manual until OpenAPI types are regenerated)
// ============================================================================

export interface AgentRunStep {
	id: string;
	run_id: string;
	step_number: number;
	type: string;
	content: Record<string, unknown> | null;
	tokens_used: number | null;
	duration_ms: number | null;
	created_at: string;
}

export interface AgentRun {
	id: string;
	agent_id: string;
	agent_name: string | null;
	trigger_type: string;
	trigger_source: string | null;
	conversation_id: string | null;
	event_delivery_id: string | null;
	input: Record<string, unknown> | null;
	output: Record<string, unknown> | null;
	status: string;
	error: string | null;
	org_id: string | null;
	caller_user_id: string | null;
	caller_email: string | null;
	caller_name: string | null;
	iterations_used: number;
	tokens_used: number;
	budget_max_iterations: number | null;
	budget_max_tokens: number | null;
	duration_ms: number | null;
	llm_model: string | null;
	created_at: string;
	started_at: string | null;
	completed_at: string | null;
	parent_run_id: string | null;
}

export interface AIUsageEntry {
	provider: string;
	model: string;
	input_tokens: number;
	output_tokens: number;
	cost: string | null;
	duration_ms: number | null;
	timestamp: string;
	sequence: number;
}

export interface AIUsageTotals {
	total_input_tokens: number;
	total_output_tokens: number;
	total_cost: string;
	total_duration_ms: number;
	call_count: number;
}

export interface AgentRunDetail extends AgentRun {
	steps: AgentRunStep[];
	child_run_ids: string[];
	ai_usage: AIUsageEntry[] | null;
	ai_totals: AIUsageTotals | null;
}

export interface AgentRunListResponse {
	items: AgentRun[];
	total: number;
	next_cursor: string | null;
}

// ============================================================================
// Hooks
// ============================================================================

export function useAgentRuns(params?: {
	agentId?: string;
	status?: string;
	triggerType?: string;
	orgId?: string;
	startDate?: string;
	endDate?: string;
	limit?: number;
	offset?: number;
}) {
	return useQuery({
		queryKey: ["agent-runs", params],
		queryFn: async () => {
			const searchParams = new URLSearchParams();
			if (params?.agentId) searchParams.set("agent_id", params.agentId);
			if (params?.status) searchParams.set("status", params.status);
			if (params?.triggerType) searchParams.set("trigger_type", params.triggerType);
			if (params?.orgId) searchParams.set("org_id", params.orgId);
			if (params?.startDate) searchParams.set("start_date", params.startDate);
			if (params?.endDate) searchParams.set("end_date", params.endDate);
			if (params?.limit) searchParams.set("limit", String(params.limit));
			if (params?.offset) searchParams.set("offset", String(params.offset));
			const qs = searchParams.toString();
			const url = `/api/agent-runs${qs ? `?${qs}` : ""}`;
			// eslint-disable-next-line @typescript-eslint/no-explicit-any
			const { data, error } = await apiClient.GET(url as any, {});
			if (error) throw error;
			return data as unknown as AgentRunListResponse;
		},
	});
}

export function useAgentRun(runId: string | undefined, options?: { refetchInterval?: number | false | ((query: { state: { data: AgentRunDetail | undefined } }) => number | false) }) {
	const queryClient = useQueryClient();
	return useQuery({
		queryKey: ["agent-runs", runId],
		queryFn: async () => {
			// eslint-disable-next-line @typescript-eslint/no-explicit-any
			const { data, error } = await apiClient.GET(`/api/agent-runs/${runId}` as any, {});
			if (error) throw error;
			const fetched = data as unknown as AgentRunDetail;
			// Merge any WS-buffered steps that arrived before this fetch completed
			const existing = queryClient.getQueryData<AgentRunDetail>(["agent-runs", runId]);
			if (existing?.steps?.length) {
				const fetchedIds = new Set(fetched.steps.map(s => s.id));
				const buffered = existing.steps.filter(s => !fetchedIds.has(s.id));
				if (buffered.length) {
					fetched.steps = [...fetched.steps, ...buffered].sort(
						(a, b) => a.step_number - b.step_number
					);
				}
			}
			return fetched;
		},
		enabled: !!runId,
		// eslint-disable-next-line @typescript-eslint/no-explicit-any
		refetchInterval: options?.refetchInterval as any,
	});
}

/**
 * Hook for real-time agent run list updates via WebSocket.
 * Updates React Query cache in-place (no refetch) when updates arrive.
 */
export function useAgentRunListStream(options: { enabled?: boolean } = {}) {
	const { enabled = true } = options;
	const queryClient = useQueryClient();

	useEffect(() => {
		if (!enabled) return;

		let unsubscribe: (() => void) | null = null;

		const init = async () => {
			try {
				await webSocketService.connect(["agent-runs"]);
				unsubscribe = webSocketService.onAgentRunUpdate(
					(update: AgentRunUpdate) => {
						// Update ALL agent-runs query caches in-place
						const caches = queryClient.getQueriesData<AgentRunListResponse>({
							queryKey: ["agent-runs"],
						});

						caches.forEach(([queryKey, oldData]) => {
							if (!oldData?.items) return;

							const existingIndex = oldData.items.findIndex(
								(run) => run.id === update.run_id,
							);

							if (existingIndex >= 0) {
								// Update existing run in-place
								const newItems = [...oldData.items];
								newItems[existingIndex] = {
									...newItems[existingIndex],
									status: update.status,
									iterations_used: update.iterations_used,
									tokens_used: update.tokens_used,
									duration_ms: update.duration_ms ?? newItems[existingIndex].duration_ms,
									error: update.error ?? newItems[existingIndex].error,
								};
								queryClient.setQueryData(queryKey, { ...oldData, items: newItems });
							} else {
								// New run — prepend to list
								const newRun: AgentRun = {
									id: update.run_id,
									agent_id: update.agent_id,
									agent_name: update.agent_name,
									trigger_type: update.trigger_type,
									status: update.status,
									iterations_used: update.iterations_used,
									tokens_used: update.tokens_used,
									duration_ms: update.duration_ms ?? null,
									error: update.error ?? null,
									org_id: update.org_id ?? null,
									trigger_source: null,
									conversation_id: null,
									event_delivery_id: null,
									input: null,
									output: null,
									caller_user_id: null,
									caller_email: null,
									caller_name: null,
									budget_max_iterations: null,
									budget_max_tokens: null,
									llm_model: null,
									created_at: update.timestamp,
									started_at: update.started_at ?? update.timestamp,
									completed_at: update.completed_at ?? null,
									parent_run_id: null,
								};
								queryClient.setQueryData(queryKey, {
									...oldData,
									items: [newRun, ...oldData.items],
									total: oldData.total + 1,
								});
							}
						});
					},
				);
			} catch (error) {
				console.error("[useAgentRunListStream] Failed to connect:", error);
			}
		};

		init();

		return () => {
			if (unsubscribe) unsubscribe();
			webSocketService.unsubscribe("agent-runs");
		};
	}, [enabled, queryClient]);
}

/**
 * Hook for real-time agent run detail updates via WebSocket.
 * Adds new steps and updates run status in real-time.
 */
export function useAgentRunStream(
	runId: string | undefined,
	options: { enabled?: boolean; onComplete?: (runId: string) => void } = {},
) {
	const { enabled = true, onComplete } = options;
	const queryClient = useQueryClient();
	const hasCaughtUp = useRef(false);

	useEffect(() => {
		if (!enabled || !runId) return;

		// Reset on runId change so a new run gets its own catch-up fetch
		hasCaughtUp.current = false;

		let unsubUpdate: (() => void) | null = null;
		let unsubStep: (() => void) | null = null;

		const init = async () => {
			try {
				const channel = `agent-run:${runId}`;
				await webSocketService.connect([channel]);

				// Listen for status updates
				unsubUpdate = webSocketService.onAgentRunUpdate(
					(update: AgentRunUpdate) => {
						if (update.run_id !== runId) return;
						// Update the cached run detail
						queryClient.setQueryData<AgentRunDetail>(
							["agent-runs", runId],
							(old) => {
								if (!old) return old;
								return {
									...old,
									status: update.status,
									iterations_used: update.iterations_used,
									tokens_used: update.tokens_used,
									duration_ms: update.duration_ms,
									error: update.error,
								};
							},
						);

						// On terminal status, refetch full data and notify
						const isTerminal = ["completed", "failed", "budget_exceeded"].includes(update.status);
						if (isTerminal) {
							queryClient.invalidateQueries({ queryKey: ["agent-runs", runId] });
							onComplete?.(runId);
						}
					},
				);

				// Listen for new steps
				unsubStep = webSocketService.onAgentRunStep(
					runId,
					(update: AgentRunStepUpdate) => {
						queryClient.setQueryData<AgentRunDetail>(
							["agent-runs", runId],
							(old) => {
								const step = { ...update.step, created_at: update.timestamp };
								if (!old) {
									// Fetch still in-flight — seed a minimal shell so steps accumulate.
									return { id: runId, steps: [step] } as AgentRunDetail;
								}
								const existingIds = new Set(old.steps.map((s) => s.id));
								if (existingIds.has(update.step.id)) return old;
								return { ...old, steps: [...old.steps, step] };
							},
						);
					},
				);
				// One-shot refetch to catch steps published before WS connected
				if (!hasCaughtUp.current) {
					hasCaughtUp.current = true;
					queryClient.refetchQueries({ queryKey: ["agent-runs", runId] });
				}
			} catch (error) {
				console.error("[useAgentRunStream] Failed to connect:", error);
			}
		};

		init();

		return () => {
			if (unsubUpdate) unsubUpdate();
			if (unsubStep) unsubStep();
			if (runId) webSocketService.unsubscribe(`agent-run:${runId}`);
		};
	}, [runId, enabled, queryClient, onComplete]);
}
