import { useState, useMemo } from "react";
import { RefreshCw, Loader2, WifiOff, Server, Activity, Settings } from "lucide-react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { usePools, useQueueStatus, usePoolConfig } from "@/services/workers";
import { getErrorMessage } from "@/lib/api-error";
import { QueueBadge } from "./QueueBadge";
import { PoolCard } from "./WorkerCard";
import { PoolConfigForm } from "./PoolConfigForm";
import { useWorkerWebSocket } from "../hooks/useWorkerWebSocket";

export function WorkersTab() {
	// Fetch initial data via REST API
	const {
		data: poolsData,
		isLoading: poolsLoading,
		error: poolsError,
		refetch: refetchPools,
	} = usePools();

	const {
		data: queueData,
		isLoading: queueLoading,
		refetch: refetchQueue,
	} = useQueueStatus({ limit: 50 });

	// Global pool configuration
	const { data: configData } = usePoolConfig();
	const [configDialogOpen, setConfigDialogOpen] = useState(false);

	// Real-time updates via WebSocket
	const { pools: wsPools, isConnected, scalingStates, progressStates } = useWorkerWebSocket();

	const [isRefreshing, setIsRefreshing] = useState(false);

	const handleRefresh = async () => {
		setIsRefreshing(true);
		try {
			await Promise.all([refetchPools(), refetchQueue()]);
		} finally {
			setIsRefreshing(false);
		}
	};

	// Use WebSocket pools if available (real-time), fall back to REST API
	const restPools = poolsData?.pools || [];
	const pools = wsPools.length > 0 ? wsPools : restPools;
	const queueItems = queueData?.items || [];
	const currentMin = configData?.new_min ?? 2;
	const currentMax = configData?.new_max ?? 10;

	// Compute stats from pools data (real-time from WebSocket)
	const statsData = useMemo(() => {
		if (pools.length === 0) return null;

		let totalProcesses = 0;
		let totalIdle = 0;
		let totalBusy = 0;

		for (const pool of pools) {
			// PoolDetail has processes array
			if ("processes" in pool && Array.isArray(pool.processes)) {
				totalProcesses += pool.processes.length;
				totalIdle += pool.processes.filter((p) => p.state === "idle").length;
				totalBusy += pool.processes.filter((p) => p.state === "busy").length;
			} else {
				// PoolSummary has counts directly
				const summary = pool as { pool_size?: number; idle_count?: number; busy_count?: number };
				totalProcesses += summary.pool_size ?? 0;
				totalIdle += summary.idle_count ?? 0;
				totalBusy += summary.busy_count ?? 0;
			}
		}

		return {
			total_pools: pools.length,
			total_processes: totalProcesses,
			total_idle: totalIdle,
			total_busy: totalBusy,
		};
	}, [pools]);

	return (
		<div className="space-y-6">
			{/* Connection Status Banner */}
			{!isConnected && (
				<Alert className="border-amber-500/50 text-amber-700 dark:text-amber-400 [&>svg]:text-amber-600">
					<WifiOff className="h-4 w-4" />
					<AlertDescription>
						Connecting to real-time worker updates... Data may not be
						current.
					</AlertDescription>
				</Alert>
			)}

			{/* Error State */}
			{poolsError && (
				<Alert variant="destructive">
					<AlertDescription>
						Failed to load pools:{" "}
						{getErrorMessage(poolsError, "Unknown error")}
					</AlertDescription>
				</Alert>
			)}

			{/* Header with Refresh, Queue Badge, and Global Config */}
			<div className="flex items-center justify-between">
				<div className="flex items-center gap-3">
					<h2 className="text-lg font-semibold">Process Pools</h2>
					{isConnected && (
						<span className="flex items-center gap-1 text-xs text-green-600">
							<span className="w-2 h-2 bg-green-500 rounded-full animate-pulse" />
							Live
						</span>
					)}
					<QueueBadge items={queueItems} isLoading={queueLoading} />
				</div>
				<div className="flex items-center gap-2">
					<span className="text-sm text-muted-foreground">
						Workers: {currentMin}-{currentMax}
					</span>
					<Button
						variant="outline"
						size="sm"
						onClick={() => setConfigDialogOpen(true)}
					>
						<Settings className="h-4 w-4 mr-2" />
						Configure
					</Button>
					<Button
						variant="outline"
						size="sm"
						onClick={handleRefresh}
						disabled={isRefreshing || poolsLoading}
					>
						<RefreshCw
							className={`h-4 w-4 mr-2 ${isRefreshing ? "animate-spin" : ""}`}
						/>
						Refresh
					</Button>
				</div>
			</div>

			{/* Pool Stats Summary */}
			{statsData && (
				<div className="grid grid-cols-4 gap-4">
					<Card>
						<CardContent className="pt-4">
							<div className="flex items-center gap-2">
								<Server className="h-4 w-4 text-muted-foreground" />
								<span className="text-sm text-muted-foreground">Pools</span>
							</div>
							<p className="text-2xl font-bold">{statsData.total_pools}</p>
						</CardContent>
					</Card>
					<Card>
						<CardContent className="pt-4">
							<div className="flex items-center gap-2">
								<Activity className="h-4 w-4 text-muted-foreground" />
								<span className="text-sm text-muted-foreground">Processes</span>
							</div>
							<p className="text-2xl font-bold">{statsData.total_processes}</p>
						</CardContent>
					</Card>
					<Card>
						<CardContent className="pt-4">
							<div className="flex items-center gap-2">
								<span className="w-2 h-2 bg-green-500 rounded-full" />
								<span className="text-sm text-muted-foreground">Idle</span>
							</div>
							<p className="text-2xl font-bold text-green-600">{statsData.total_idle}</p>
						</CardContent>
					</Card>
					<Card>
						<CardContent className="pt-4">
							<div className="flex items-center gap-2">
								<span className="w-2 h-2 bg-yellow-500 rounded-full" />
								<span className="text-sm text-muted-foreground">Busy</span>
							</div>
							<p className="text-2xl font-bold text-yellow-600">{statsData.total_busy}</p>
						</CardContent>
					</Card>
				</div>
			)}

			{/* Pools List */}
			{poolsLoading && pools.length === 0 ? (
				<div className="flex items-center justify-center py-12">
					<Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
				</div>
			) : pools.length === 0 ? (
				<Card>
					<CardContent className="flex flex-col items-center justify-center py-12 text-center">
						<Server className="h-12 w-12 text-muted-foreground mb-4" />
						<h3 className="text-lg font-semibold">No pools connected</h3>
						<p className="mt-2 text-sm text-muted-foreground max-w-md">
							Process pools register themselves when workers start.
							If you expect pools to be running, check the worker logs
							for connection issues.
						</p>
					</CardContent>
				</Card>
			) : (
				<div className="space-y-4">
					{pools.map((pool) => (
						<PoolCard
							key={pool.worker_id}
							pool={pool}
							scalingState={scalingStates.get(pool.worker_id)}
							progressState={progressStates.get(pool.worker_id)}
						/>
					))}
				</div>
			)}

			{/* Global Pool Config Dialog */}
			<PoolConfigForm
				currentMin={currentMin}
				currentMax={currentMax}
				open={configDialogOpen}
				onOpenChange={setConfigDialogOpen}
			/>
		</div>
	);
}
