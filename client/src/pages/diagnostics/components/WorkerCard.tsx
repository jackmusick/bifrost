import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
	Server,
	Clock,
	ChevronDown,
	ChevronRight,
	Loader2,
	RefreshCw,
	TrendingUp,
	TrendingDown,
	Cpu,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
	AlertDialog,
	AlertDialogAction,
	AlertDialogCancel,
	AlertDialogContent,
	AlertDialogDescription,
	AlertDialogFooter,
	AlertDialogHeader,
	AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { ProcessCard } from "./ProcessCard";
import {
	usePool,
	useRecycleAllProcesses,
	type PoolSummary,
	type PoolDetail,
	type ProcessInfo,
} from "@/services/workers";
import type { ExecutionRowData } from "./ExecutionRow";
import type { ScalingState, ProgressState } from "../hooks/useWorkerWebSocket";
import { toast } from "sonner";

/**
 * Skeleton placeholder for a process being spawned
 */
function ProcessSkeleton({ index }: { index: number }) {
	return (
		<motion.div
			layout
			initial={{ opacity: 0, y: -10, scale: 0.95 }}
			animate={{ opacity: 1, y: 0, scale: 1 }}
			exit={{ opacity: 0, scale: 0.95, height: 0, marginBottom: 0 }}
			transition={{ duration: 0.2, delay: index * 0.05 }}
			className="border rounded-lg p-4 bg-card border-dashed border-green-500/50"
		>
			<div className="flex items-center justify-between">
				<div className="flex items-center gap-3">
					<div className="p-1">
						<ChevronRight className="h-4 w-4 text-muted-foreground/30" />
					</div>
					<Cpu className="h-5 w-5 text-green-500/50 animate-pulse" />
					<Skeleton className="h-5 w-24" />
					<Skeleton className="h-5 w-16" />
					<Badge variant="outline" className="border-green-500 text-green-600 bg-green-50 dark:bg-green-950">
						<Loader2 className="h-3 w-3 mr-1 animate-spin" />
						Spawning...
					</Badge>
				</div>
				<Skeleton className="h-8 w-20" />
			</div>
			<div className="mt-3 flex items-center gap-6 ml-10">
				<Skeleton className="h-4 w-24" />
				<Skeleton className="h-4 w-16" />
				<Skeleton className="h-4 w-20" />
			</div>
		</motion.div>
	);
}

// Accept either PoolSummary (from REST) or PoolDetail (from WebSocket)
type PoolData = PoolSummary | PoolDetail;

interface PoolCardProps {
	pool: PoolData;
	scalingState?: ScalingState;
	progressState?: ProgressState;
}

// Helper to get pool counts - works with both PoolSummary and PoolDetail
function getPoolCounts(pool: PoolData): { poolSize: number; idleCount: number; busyCount: number } {
	// PoolDetail has processes array, compute counts from it
	if ("processes" in pool && Array.isArray(pool.processes)) {
		const processes = pool.processes;
		return {
			poolSize: processes.length,
			idleCount: processes.filter((p) => p.state === "idle").length,
			busyCount: processes.filter((p) => p.state === "busy").length,
		};
	}
	// PoolSummary has direct counts
	return {
		poolSize: (pool as PoolSummary).pool_size ?? 0,
		idleCount: (pool as PoolSummary).idle_count ?? 0,
		busyCount: (pool as PoolSummary).busy_count ?? 0,
	};
}

/**
 * Format relative time from ISO date string
 */
function formatRelativeTime(dateStr: string | null | undefined): string {
	if (!dateStr) return "Unknown";
	const date = new Date(dateStr);
	const now = new Date();
	const diffMs = now.getTime() - date.getTime();
	const diffSec = Math.floor(diffMs / 1000);

	if (diffSec < 60) return `${diffSec}s ago`;
	const minutes = Math.floor(diffSec / 60);
	if (minutes < 60) return `${minutes}m ago`;
	const hours = Math.floor(minutes / 60);
	if (hours < 24) return `${hours}h ago`;
	const days = Math.floor(hours / 24);
	return `${days}d ago`;
}

/**
 * Get status badge variant based on pool status
 */
function getStatusVariant(
	status: string | null | undefined
): "default" | "secondary" | "destructive" | "warning" {
	switch (status?.toLowerCase()) {
		case "online":
		case "active":
			return "default";
		case "offline":
		case "error":
			return "destructive";
		default:
			return "secondary";
	}
}

export function PoolCard({ pool, scalingState, progressState }: PoolCardProps) {
	const [isExpanded, setIsExpanded] = useState(false);
	const [recycleAllDialogOpen, setRecycleAllDialogOpen] = useState(false);

	// Use processes from pool prop if available (real-time from WebSocket)
	// Only fetch via REST API as fallback when pool doesn't have processes
	const hasProcessesFromProp = "processes" in pool && Array.isArray(pool.processes);
	const { data: poolDetail } = usePool(
		isExpanded && !hasProcessesFromProp ? pool.worker_id : ""
	);

	const recycleAll = useRecycleAllProcesses();

	// Build execution data from process info
	const getProcessExecutions = (process: ProcessInfo): ExecutionRowData[] => {
		if (!process.current_execution_id) return [];
		return [
			{
				execution_id: process.current_execution_id,
				workflow_name: "Running workflow",
				status: "RUNNING",
				elapsed_seconds: process.uptime_seconds,
			},
		];
	};

	const handleRecycleAll = async () => {
		try {
			const result = await recycleAll.mutateAsync({
				workerId: pool.worker_id,
				reason: "Manual recycle from Diagnostics UI",
			});
			toast.success("Recycle initiated", {
				description: `${result.processes_affected} processes will be recycled`,
			});
		} catch (err) {
			const message = err instanceof Error ? err.message : "Unknown error";
			toast.error("Failed to recycle processes", { description: message });
		}
		setRecycleAllDialogOpen(false);
	};

	// Prefer processes from WebSocket (real-time), fallback to REST API
	const processes = hasProcessesFromProp
		? (pool as PoolDetail).processes
		: (poolDetail?.processes || []);

	return (
		<motion.div
			initial={{ opacity: 0, y: 20 }}
			animate={{ opacity: 1, y: 0 }}
			transition={{ duration: 0.3 }}
		>
			<Card>
				<CardHeader className="pb-3">
					<div className="flex items-center justify-between">
						<div className="flex items-center gap-3">
							<button
								onClick={() => setIsExpanded(!isExpanded)}
								className="p-1 hover:bg-muted rounded"
							>
								{isExpanded ? (
									<ChevronDown className="h-4 w-4" />
								) : (
									<ChevronRight className="h-4 w-4" />
								)}
							</button>
							<Server className="h-5 w-5 text-muted-foreground" />
							<CardTitle className="text-lg">
								Pool: {pool.worker_id}
							</CardTitle>
							<Badge variant={getStatusVariant(pool.status)}>
								{pool.status || "Unknown"}
							</Badge>
							{/* Progress message takes priority over scaling state */}
							{progressState ? (
								<motion.div
									initial={{ opacity: 0, scale: 0.8 }}
									animate={{ opacity: 1, scale: 1 }}
									exit={{ opacity: 0, scale: 0.8 }}
									className="flex items-center gap-1"
								>
									<Badge
										variant="outline"
										className={
											progressState.action === "scale_up"
												? "border-green-500 text-green-600 bg-green-50 dark:bg-green-950"
												: progressState.action === "recycle_all"
													? "border-blue-500 text-blue-600 bg-blue-50 dark:bg-blue-950"
													: "border-orange-500 text-orange-600 bg-orange-50 dark:bg-orange-950"
										}
									>
										{progressState.action === "scale_up" ? (
											<TrendingUp className="h-3 w-3 mr-1" />
										) : progressState.action === "recycle_all" ? (
											<RefreshCw className="h-3 w-3 mr-1 animate-spin" />
										) : (
											<TrendingDown className="h-3 w-3 mr-1" />
										)}
										{progressState.message}
									</Badge>
								</motion.div>
							) : scalingState && (
								<motion.div
									initial={{ opacity: 0, scale: 0.8 }}
									animate={{ opacity: 1, scale: 1 }}
									exit={{ opacity: 0, scale: 0.8 }}
									className="flex items-center gap-1"
								>
									<Badge
										variant="outline"
										className={
											scalingState.action === "scale_up"
												? "border-green-500 text-green-600 bg-green-50 dark:bg-green-950"
												: scalingState.action === "recycle_all"
													? "border-blue-500 text-blue-600 bg-blue-50 dark:bg-blue-950"
													: "border-orange-500 text-orange-600 bg-orange-50 dark:bg-orange-950"
										}
									>
										{scalingState.action === "scale_up" ? (
											<TrendingUp className="h-3 w-3 mr-1" />
										) : scalingState.action === "recycle_all" ? (
											<RefreshCw className="h-3 w-3 mr-1 animate-spin" />
										) : (
											<TrendingDown className="h-3 w-3 mr-1" />
										)}
										{scalingState.action === "scale_up"
											? `Scaling up (+${scalingState.processes_affected})`
											: scalingState.action === "recycle_all"
												? `Recycling (${scalingState.processes_affected})`
												: `Scaling down (-${scalingState.processes_affected})`}
									</Badge>
								</motion.div>
							)}
						</div>
						<div className="flex items-center gap-4">
							{(() => {
								const { poolSize, idleCount, busyCount } = getPoolCounts(pool);
								return (
									<div className="flex items-center gap-4 text-sm text-muted-foreground">
										<span>{poolSize} processes</span>
										<div className="flex items-center gap-2">
											<span className="flex items-center gap-1">
												<span className="w-2 h-2 bg-green-500 rounded-full" />
												{idleCount} idle
											</span>
											<span className="flex items-center gap-1">
												<span className="w-2 h-2 bg-yellow-500 rounded-full" />
												{busyCount} busy
											</span>
										</div>
									</div>
								);
							})()}
							<Button
								variant="outline"
								size="sm"
								onClick={() => setRecycleAllDialogOpen(true)}
								disabled={recycleAll.isPending}
							>
								{recycleAll.isPending ? (
									<Loader2 className="h-4 w-4 animate-spin" />
								) : (
									<RefreshCw className="h-4 w-4" />
								)}
								<span className="ml-1 hidden sm:inline">Recycle All</span>
							</Button>
						</div>
					</div>
					<div className="flex items-center gap-4 text-sm text-muted-foreground ml-10 mt-2">
						{pool.hostname && <span>Host: {pool.hostname}</span>}
						<div className="flex items-center gap-1">
							<Clock className="h-4 w-4" />
							<span>
								Online since: {formatRelativeTime(pool.started_at)}
							</span>
						</div>
						{pool.last_heartbeat && (
							<span>
								Last heartbeat: {formatRelativeTime(pool.last_heartbeat)}
							</span>
						)}
					</div>
				</CardHeader>

				{isExpanded && (
					<CardContent className="pt-0">
						{processes.length > 0 || (progressState?.action === "scale_up") ? (
							<div className="space-y-3">
								{/* Show skeletons for processes being spawned */}
								<AnimatePresence mode="popLayout">
									{progressState?.action === "scale_up" && (() => {
										const remaining = progressState.total - progressState.current;
										return Array.from({ length: remaining }, (_, i) => (
											<ProcessSkeleton key={`skeleton-${i}`} index={i} />
										));
									})()}
								</AnimatePresence>
								{/* Show actual processes */}
								{processes.map((process, index) => {
									// Determine if this process is marked for removal during scale_down
									// Scale down removes idle processes from the end of the list
									const isBeingRemoved = progressState?.action === "scale_down" &&
										process.state === "idle" &&
										index >= processes.length - (progressState.total - progressState.current);

									return (
										<ProcessCard
											key={process.process_id}
											workerId={pool.worker_id}
											process={process}
											executions={getProcessExecutions(process)}
											isBeingRemoved={isBeingRemoved}
										/>
									);
								})}
							</div>
						) : (
							<p className="text-sm text-muted-foreground text-center py-4">
								No processes registered
							</p>
						)}
					</CardContent>
				)}
			</Card>

			{/* Recycle All Confirmation Dialog */}
			<AlertDialog
				open={recycleAllDialogOpen}
				onOpenChange={setRecycleAllDialogOpen}
			>
				<AlertDialogContent>
					<AlertDialogHeader>
						<AlertDialogTitle>Recycle All Processes?</AlertDialogTitle>
						<AlertDialogDescription>
							This will recycle all {getPoolCounts(pool).poolSize} processes in this pool.
							Idle processes will be recycled immediately. Busy processes will
							be recycled after their current execution completes.
						</AlertDialogDescription>
					</AlertDialogHeader>
					<AlertDialogFooter>
						<AlertDialogCancel>Cancel</AlertDialogCancel>
						<AlertDialogAction onClick={handleRecycleAll}>
							Recycle All
						</AlertDialogAction>
					</AlertDialogFooter>
				</AlertDialogContent>
			</AlertDialog>
		</motion.div>
	);
}
