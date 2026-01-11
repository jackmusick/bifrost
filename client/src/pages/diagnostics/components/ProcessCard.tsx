import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Cpu, Clock, CheckCircle, RefreshCw, ChevronDown, ChevronRight, MemoryStick, TrendingDown } from "lucide-react";
import { toast } from "sonner";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
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
import { useRecycleProcess, type ProcessInfo, type ProcessState } from "@/services/workers";
import { ExecutionRow, type ExecutionRowData } from "./ExecutionRow";

interface ProcessCardProps {
	workerId: string;
	process: ProcessInfo;
	executions?: ExecutionRowData[];
	isBeingRemoved?: boolean;
}

/**
 * Format uptime from seconds to human-readable duration
 */
function formatUptime(uptimeSeconds: number): string {
	if (uptimeSeconds < 60) return `${Math.floor(uptimeSeconds)}s`;
	const minutes = Math.floor(uptimeSeconds / 60);
	if (minutes < 60) return `${minutes}m`;
	const hours = Math.floor(minutes / 60);
	const remainingMinutes = minutes % 60;
	if (hours < 24) return `${hours}h ${remainingMinutes}m`;
	const days = Math.floor(hours / 24);
	const remainingHours = hours % 24;
	return `${days}d ${remainingHours}h`;
}

const stateVariants: Record<ProcessState | "unknown", { label: string; variant: "default" | "secondary" | "destructive" | "warning" }> = {
	idle: { label: "Idle", variant: "secondary" },
	busy: { label: "Busy", variant: "default" },
	killed: { label: "Killed", variant: "destructive" },
	unknown: { label: "Unknown", variant: "secondary" },
};

export function ProcessCard({ workerId, process, executions = [], isBeingRemoved = false }: ProcessCardProps) {
	const [recycleDialogOpen, setRecycleDialogOpen] = useState(false);
	const [isExpanded, setIsExpanded] = useState(executions.length > 0);
	const recycleMutation = useRecycleProcess();

	const stateConfig = stateVariants[process.state] || stateVariants.unknown;
	const canRecycle = process.state === "idle" && process.is_alive;

	const handleRecycle = async () => {
		try {
			await recycleMutation.mutateAsync({
				params: {
					path: {
						worker_id: workerId,
						pid: process.pid,
					},
				},
				body: {
					reason: "Manual recycle from Diagnostics UI",
				},
			});
			toast.success("Recycle request sent", {
				description: `Process ${process.process_id} (PID ${process.pid}) will be recycled.`,
			});
			setRecycleDialogOpen(false);
		} catch {
			toast.error("Failed to recycle process", {
				description: "Please try again or check pool status.",
			});
		}
	};

	return (
		<motion.div
			className={cn(
				"border rounded-lg p-4 bg-card",
				isBeingRemoved && "border-dashed border-orange-500/50 opacity-60"
			)}
			animate={isBeingRemoved ? { opacity: [0.6, 0.4, 0.6] } : {}}
			transition={isBeingRemoved ? { duration: 1.5, repeat: Infinity } : {}}
		>
			{/* Process Header */}
			<div className="flex items-center justify-between">
				<div className="flex items-center gap-3">
					<button
						onClick={() => setIsExpanded(!isExpanded)}
						className="p-1 hover:bg-muted rounded"
						disabled={executions.length === 0}
					>
						{isExpanded ? (
							<ChevronDown className="h-4 w-4" />
						) : (
							<ChevronRight className="h-4 w-4" />
						)}
					</button>
					<Cpu className={cn("h-5 w-5", isBeingRemoved ? "text-orange-500/50" : "text-muted-foreground")} />
					<span className="font-semibold">{process.process_id}</span>
					<span className="text-sm text-muted-foreground">(PID {process.pid})</span>
					<Badge variant={stateConfig.variant}>{stateConfig.label}</Badge>
					{isBeingRemoved && (
						<Badge variant="outline" className="border-orange-500 text-orange-600 bg-orange-50 dark:bg-orange-950">
							<TrendingDown className="h-3 w-3 mr-1" />
							Terminating...
						</Badge>
					)}
					{process.pending_recycle && !isBeingRemoved && (
						<Badge variant="warning" className="border-orange-500 text-orange-600 bg-orange-50 dark:bg-orange-950">
							Pending Recycle
						</Badge>
					)}
					{!process.is_alive && (
						<Badge variant="destructive">Dead</Badge>
					)}
				</div>
				<Button
					variant="outline"
					size="sm"
					onClick={() => setRecycleDialogOpen(true)}
					disabled={!canRecycle || recycleMutation.isPending}
					title={process.state === "busy" ? "Cannot recycle busy process" : undefined}
				>
					<RefreshCw
						className={cn("h-4 w-4 mr-2", recycleMutation.isPending && "animate-spin")}
					/>
					Recycle
				</Button>
			</div>

			{/* Process Stats */}
			<div className="mt-3 flex items-center gap-6 text-sm text-muted-foreground ml-10">
				<div className="flex items-center gap-1">
					<Clock className="h-4 w-4" />
					<span>Uptime: {formatUptime(process.uptime_seconds)}</span>
				</div>
				<div className="flex items-center gap-1">
					<CheckCircle className="h-4 w-4" />
					<span>Jobs: {process.executions_completed}</span>
				</div>
				<div className="flex items-center gap-1">
					<MemoryStick className="h-4 w-4" />
					<span>Memory: {process.memory_mb.toFixed(1)} MB</span>
				</div>
			</div>

			{/* Active Executions */}
			<AnimatePresence>
				{isExpanded && executions.length > 0 && (
					<motion.div
						initial={{ opacity: 0, height: 0 }}
						animate={{ opacity: 1, height: "auto" }}
						exit={{ opacity: 0, height: 0 }}
						transition={{ duration: 0.2 }}
						className="mt-4 ml-10"
					>
						<p className="text-sm font-medium mb-2">Active Execution:</p>
						<div className="border rounded-lg divide-y">
							<AnimatePresence>
								{executions.map((execution) => (
									<ExecutionRow
										key={execution.execution_id}
										execution={execution}
									/>
								))}
							</AnimatePresence>
						</div>
					</motion.div>
				)}
			</AnimatePresence>

			{/* Recycle Confirmation Dialog */}
			<AlertDialog open={recycleDialogOpen} onOpenChange={setRecycleDialogOpen}>
				<AlertDialogContent>
					<AlertDialogHeader>
						<AlertDialogTitle>Recycle Process?</AlertDialogTitle>
						<AlertDialogDescription>
							This will terminate the idle process and spawn a new one to
							replace it. This is useful for refreshing process state or
							recovering from memory issues.
						</AlertDialogDescription>
					</AlertDialogHeader>
					<AlertDialogFooter>
						<AlertDialogCancel>Cancel</AlertDialogCancel>
						<AlertDialogAction
							onClick={handleRecycle}
							disabled={recycleMutation.isPending}
						>
							{recycleMutation.isPending ? "Recycling..." : "Recycle"}
						</AlertDialogAction>
					</AlertDialogFooter>
				</AlertDialogContent>
			</AlertDialog>
		</motion.div>
	);
}
