/**
 * Workers API service
 *
 * Provides hooks for:
 * - Listing process pools and their status
 * - Getting pool details
 * - Recycling worker processes
 * - Queue status
 * - Pool statistics
 *
 * Note: These API endpoints are not yet in the OpenAPI spec, so we use
 * manual types and the authFetch function instead of the generated $api.
 */

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { authFetch } from "@/lib/api-client";

// =============================================================================
// Manual Type Definitions (until types are generated)
// =============================================================================

// Process states from ProcessPoolManager: idle, busy, killed
export type ProcessState = "idle" | "busy" | "killed";

export interface ProcessInfo {
	process_id: string;
	pid: number;
	state: ProcessState;
	current_execution_id: string | null;
	executions_completed: number;
	started_at: string | null;
	uptime_seconds: number;
	memory_mb: number;
	is_alive: boolean;
	pending_recycle?: boolean;
}

export interface PoolSummary {
	worker_id: string;
	hostname: string | null;
	status: string | null;
	started_at: string | null;
	pool_size: number;
	idle_count: number;
	busy_count: number;
	last_heartbeat: string | null;
}

export interface PoolDetail {
	worker_id: string;
	hostname: string | null;
	status: string | null;
	started_at: string | null;
	last_heartbeat: string | null;
	min_workers: number;
	max_workers: number;
	processes: ProcessInfo[];
}

export interface PoolsListResponse {
	pools: PoolSummary[];
	total: number;
}

export interface PoolStatsResponse {
	total_pools: number;
	total_processes: number;
	total_idle: number;
	total_busy: number;
}

export interface QueueItem {
	execution_id: string;
	position: number;
	queued_at: string | null;
}

export interface QueueStatusResponse {
	total: number;
	items: QueueItem[];
}

export interface RecycleRequest {
	reason?: string;
}

export interface RecycleResponse {
	success: boolean;
	message: string;
	worker_id: string;
	process_id: string | null;
	pid: number | null;
}

export interface PoolConfigUpdateRequest {
	min_workers: number;
	max_workers: number;
}

export interface PoolConfigUpdateResponse {
	success: boolean;
	message: string;
	worker_id: string;
	old_min: number;
	old_max: number;
	new_min: number;
	new_max: number;
	processes_spawned: number;
	processes_marked_for_removal: number;
}

export interface RecycleAllRequest {
	reason?: string;
}

export interface RecycleAllResponse {
	success: boolean;
	message: string;
	worker_id: string;
	processes_affected: number;
}

// =============================================================================
// Pool Hooks
// =============================================================================

/**
 * Hook to fetch all process pools
 */
export function usePools() {
	return useQuery<PoolsListResponse>({
		queryKey: ["pools"],
		queryFn: async () => {
			const response = await authFetch("/api/platform/workers");
			if (!response.ok) {
				throw new Error(`Failed to fetch pools: ${response.statusText}`);
			}
			return response.json();
		},
		// No polling - real-time updates come via WebSocket (useWorkerWebSocket)
	});
}

/**
 * Hook to fetch a single pool's details
 */
export function usePool(workerId: string) {
	return useQuery<PoolDetail>({
		queryKey: ["pools", workerId],
		queryFn: async () => {
			const response = await authFetch(`/api/platform/workers/${workerId}`);
			if (!response.ok) {
				throw new Error(`Failed to fetch pool: ${response.statusText}`);
			}
			return response.json();
		},
		enabled: !!workerId,
	});
}

/**
 * Hook to fetch pool statistics
 */
export function usePoolStats() {
	return useQuery<PoolStatsResponse>({
		queryKey: ["pools", "stats"],
		queryFn: async () => {
			const response = await authFetch("/api/platform/workers/stats");
			if (!response.ok) {
				throw new Error(`Failed to fetch pool stats: ${response.statusText}`);
			}
			return response.json();
		},
		// No polling - real-time updates come via WebSocket (useWorkerWebSocket)
	});
}

/**
 * Hook to recycle a process in a pool
 */
export function useRecycleProcess() {
	const queryClient = useQueryClient();

	return useMutation<
		RecycleResponse,
		Error,
		{ params: { path: { worker_id: string; pid: number } }; body: RecycleRequest }
	>({
		mutationFn: async ({ params, body }) => {
			const { worker_id, pid } = params.path;
			const response = await authFetch(
				`/api/platform/workers/${worker_id}/processes/${pid}/recycle`,
				{
					method: "POST",
					body: JSON.stringify(body),
				}
			);
			if (!response.ok) {
				throw new Error(`Failed to recycle process: ${response.statusText}`);
			}
			return response.json();
		},
		onSuccess: () => {
			queryClient.invalidateQueries({ queryKey: ["pools"] });
		},
	});
}

// =============================================================================
// Queue Hooks
// =============================================================================

/**
 * Hook to fetch queue status
 */
export function useQueueStatus(params?: { limit?: number; offset?: number }) {
	return useQuery<QueueStatusResponse>({
		queryKey: ["queue", params],
		queryFn: async () => {
			const searchParams = new URLSearchParams();
			if (params?.limit) searchParams.set("limit", String(params.limit));
			if (params?.offset) searchParams.set("offset", String(params.offset));

			const url = `/api/platform/queue${searchParams.toString() ? `?${searchParams}` : ""}`;
			const response = await authFetch(url);
			if (!response.ok) {
				throw new Error(`Failed to fetch queue: ${response.statusText}`);
			}
			return response.json();
		},
		// No polling - real-time updates come via WebSocket (useWorkerWebSocket)
	});
}

/**
 * Hook to get global pool configuration
 */
export function usePoolConfig() {
	return useQuery<PoolConfigUpdateResponse>({
		queryKey: ["pools", "config"],
		queryFn: async () => {
			const response = await authFetch("/api/platform/workers/config");
			if (!response.ok) {
				throw new Error(`Failed to fetch config: ${response.statusText}`);
			}
			return response.json();
		},
	});
}

/**
 * Hook to update global pool configuration (min/max workers)
 */
export function useUpdatePoolConfig() {
	const queryClient = useQueryClient();

	return useMutation<
		PoolConfigUpdateResponse,
		Error,
		PoolConfigUpdateRequest
	>({
		mutationFn: async (config) => {
			const response = await authFetch(
				"/api/platform/workers/config",
				{
					method: "PATCH",
					body: JSON.stringify(config),
				}
			);
			if (!response.ok) {
				const error = await response.json().catch(() => ({}));
				throw new Error(
					error.detail || `Failed to update config: ${response.statusText}`
				);
			}
			return response.json();
		},
		onSuccess: () => {
			queryClient.invalidateQueries({ queryKey: ["pools"] });
		},
	});
}

/**
 * Hook to recycle all processes in a pool
 */
export function useRecycleAllProcesses() {
	const queryClient = useQueryClient();

	return useMutation<
		RecycleAllResponse,
		Error,
		{ workerId: string; reason?: string }
	>({
		mutationFn: async ({ workerId, reason }) => {
			const response = await authFetch(
				`/api/platform/workers/${workerId}/recycle-all`,
				{
					method: "POST",
					body: JSON.stringify({ reason }),
				}
			);
			if (!response.ok) {
				const error = await response.json().catch(() => ({}));
				throw new Error(
					error.detail || `Failed to recycle: ${response.statusText}`
				);
			}
			return response.json();
		},
		onSuccess: () => {
			queryClient.invalidateQueries({ queryKey: ["pools"] });
		},
	});
}

