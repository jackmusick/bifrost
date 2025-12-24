/**
 * ToolExecutionCard Component
 *
 * Displays tool/workflow execution status in chat with:
 * - Status badge (pending, running, success, failed)
 * - Live log streaming (during execution)
 * - Input parameters (info popover)
 * - Result display using PrettyInputDisplay
 *
 * Architecture:
 * - Accepts executionId as primary prop
 * - Fetches all data (result, status, logs) from executions API
 * - Supports streaming state override for live updates during execution
 */

import { useState, useRef, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
	Circle,
	CheckCircle2,
	XCircle,
	Clock,
	Info,
	ChevronDown,
	ChevronRight,
	Loader2,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useExecutionStream } from "@/hooks/useExecutionStream";
import { useExecutionStreamStore } from "@/stores/executionStreamStore";
import { useExecution, useExecutionLogs } from "@/hooks/useExecutions";
import {
	Popover,
	PopoverContent,
	PopoverTrigger,
} from "@/components/ui/popover";
import {
	Collapsible,
	CollapsibleContent,
	CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { PrettyInputDisplay } from "@/components/execution/PrettyInputDisplay";
import type { components } from "@/lib/v1";

type ToolCall = components["schemas"]["ToolCall"];
type ExecutionStatus = components["schemas"]["ExecutionStatus"];

// Stable empty array to prevent re-render loops in Zustand selectors
const EMPTY_LOGS: { level: string; message: string; timestamp?: string }[] = [];

export type ToolExecutionStatus =
	| "pending"
	| "running"
	| "success"
	| "failed"
	| "timeout";

export interface ToolExecutionLog {
	level: "debug" | "info" | "warning" | "error";
	message: string;
	timestamp?: string;
}

/** Streaming state passed from chat for live updates during execution */
export interface StreamingToolState {
	status: ToolExecutionStatus;
	logs: ToolExecutionLog[];
	result?: unknown;
	error?: string;
	durationMs?: number;
}

/** Legacy interface for backward compatibility */
export interface ToolExecutionState {
	toolCall: ToolCall;
	status: ToolExecutionStatus;
	executionId?: string;
	logs: ToolExecutionLog[];
	result?: unknown;
	resultType?: "json" | "html" | "text";
	error?: string;
	durationMs?: number;
	startedAt?: string;
}

/** Map API ExecutionStatus to card ToolExecutionStatus */
function mapExecutionStatus(
	apiStatus: ExecutionStatus | undefined,
): ToolExecutionStatus {
	switch (apiStatus) {
		case "Pending":
			return "pending";
		case "Running":
		case "Cancelling":
			return "running";
		case "Success":
		case "CompletedWithErrors":
			return "success";
		case "Failed":
		case "Cancelled":
			return "failed";
		case "Timeout":
			return "timeout";
		default:
			return "pending";
	}
}

interface ToolExecutionCardProps {
	/** Execution ID for fetching data from API (primary mode) */
	executionId?: string;
	/** Tool call info for display (name, arguments) */
	toolCall: ToolCall;
	/** Override with streaming state during live execution */
	streamingState?: StreamingToolState;
	/** Whether this execution is currently streaming */
	isStreaming?: boolean;
	/** Legacy: Full execution state (deprecated, use executionId instead) */
	execution?: ToolExecutionState;
	className?: string;
}

const statusConfig: Record<
	ToolExecutionStatus,
	{
		icon: typeof Circle;
		label: string;
		className: string;
		badgeVariant: "default" | "secondary" | "destructive" | "outline";
	}
> = {
	pending: {
		icon: Clock,
		label: "Pending",
		className: "text-muted-foreground",
		badgeVariant: "secondary",
	},
	running: {
		icon: Loader2,
		label: "Running",
		className: "text-blue-500",
		badgeVariant: "default",
	},
	success: {
		icon: CheckCircle2,
		label: "Success",
		className: "text-green-500",
		badgeVariant: "outline",
	},
	failed: {
		icon: XCircle,
		label: "Failed",
		className: "text-destructive",
		badgeVariant: "destructive",
	},
	timeout: {
		icon: Clock,
		label: "Timeout",
		className: "text-amber-500",
		badgeVariant: "outline",
	},
};

export function ToolExecutionCard({
	executionId,
	toolCall,
	streamingState,
	isStreaming = false,
	execution,
	className,
}: ToolExecutionCardProps) {
	// Auto-expand results when execution completes
	const [isResultOpen, setIsResultOpen] = useState(false);
	const logsEndRef = useRef<HTMLDivElement>(null);

	// Resolve executionId from props or legacy execution object
	const resolvedExecutionId = executionId ?? execution?.executionId;
	const resolvedToolCall = toolCall ?? execution?.toolCall;

	// Fetch execution data from API (disabled during streaming)
	const { data: apiExecution, isLoading: isLoadingExecution } = useExecution(
		resolvedExecutionId,
		isStreaming, // Disable polling during streaming
	);

	// Determine status: streaming state > API data > legacy execution > pending
	const status: ToolExecutionStatus =
		isStreaming && streamingState
			? streamingState.status
			: apiExecution
				? mapExecutionStatus(apiExecution.status)
				: (execution?.status ?? "pending");

	// Determine completion status (needed for log fetching)
	const isComplete =
		status === "success" || status === "failed" || status === "timeout";

	// Subscribe to execution logs via WebSocket when running
	useExecutionStream({
		executionId: resolvedExecutionId || "",
		enabled: !!resolvedExecutionId && status === "running",
	});

	// Get streaming logs from the execution stream store
	const streamingLogs = useExecutionStreamStore((state) =>
		resolvedExecutionId
			? (state.streams[resolvedExecutionId]?.streamingLogs ?? EMPTY_LOGS)
			: EMPTY_LOGS,
	);

	// Fetch persisted logs when result section is expanded and execution is complete
	const { data: persistedLogs } = useExecutionLogs(
		resolvedExecutionId,
		isComplete && isResultOpen && !!resolvedExecutionId,
	);

	// Determine logs to display: streaming logs > persisted logs > streaming state logs > legacy logs
	const baseLogs = streamingState?.logs ?? execution?.logs ?? [];
	const displayLogs =
		status === "running" && streamingLogs.length > 0
			? streamingLogs
			: persistedLogs && persistedLogs.length > 0
				? persistedLogs
				: baseLogs;

	// Determine result: streaming state > API data > legacy execution
	const result =
		isStreaming && streamingState?.result !== undefined
			? streamingState.result
			: (apiExecution?.result ?? execution?.result);

	// Determine error: streaming state > API data > legacy execution
	const error =
		isStreaming && streamingState?.error
			? streamingState.error
			: (apiExecution?.error_message ?? execution?.error);

	// Determine duration: streaming state > API data > legacy execution
	const durationMs =
		isStreaming && streamingState?.durationMs !== undefined
			? streamingState.durationMs
			: (apiExecution?.duration_ms ?? execution?.durationMs);

	const config = statusConfig[status];
	const StatusIcon = config.icon;
	const hasResult = result !== undefined && result !== null;
	const latestLog =
		displayLogs.length > 0 ? displayLogs[displayLogs.length - 1] : null;

	// Auto-scroll logs when new ones arrive
	useEffect(() => {
		if (status === "running" && logsEndRef.current) {
			logsEndRef.current.scrollIntoView({ behavior: "smooth" });
		}
	}, [displayLogs.length, status]);

	// Format duration
	const formatDuration = (ms: number) => {
		if (ms < 1000) return `${ms}ms`;
		return `${(ms / 1000).toFixed(1)}s`;
	};

	// Loading state when fetching execution data and no streaming/legacy data available
	if (isLoadingExecution && !isStreaming && !execution) {
		return (
			<div
				className={cn(
					"border rounded-lg bg-card overflow-hidden",
					className,
				)}
			>
				<div className="flex items-center gap-2 px-3 py-2 bg-muted/30">
					<Skeleton className="h-5 w-16" />
					<Skeleton className="h-4 w-24" />
				</div>
			</div>
		);
	}

	// Guard: need a tool call to render
	if (!resolvedToolCall) {
		return null;
	}

	return (
		<div
			className={cn(
				"border rounded-lg bg-card overflow-hidden",
				status === "running" && "border-blue-500/50",
				status === "failed" && "border-destructive/50",
				className,
			)}
		>
			{/* Header */}
			<div className="flex items-center justify-between px-3 py-2 bg-muted/30">
				<div className="flex items-center gap-2">
					{/* Status Badge */}
					<Badge
						variant={config.badgeVariant}
						className={cn(
							"gap-1 font-normal",
							status === "running" && "animate-pulse",
						)}
					>
						<StatusIcon
							className={cn(
								"h-3 w-3",
								config.className,
								status === "running" && "animate-spin",
							)}
						/>
						{config.label}
					</Badge>

					{/* Tool Name */}
					<span className="font-medium text-sm">
						{resolvedToolCall.name}
					</span>
				</div>

				<div className="flex items-center gap-2">
					{/* Duration */}
					{durationMs !== undefined && (
						<span className="text-xs text-muted-foreground">
							{formatDuration(durationMs)}
						</span>
					)}

					{/* Info Popover - Input Parameters */}
					<Popover>
						<PopoverTrigger asChild>
							<Button
								variant="ghost"
								size="icon"
								className="h-6 w-6"
							>
								<Info className="h-3.5 w-3.5 text-muted-foreground" />
							</Button>
						</PopoverTrigger>
						<PopoverContent
							className="w-96 max-h-80 overflow-auto"
							align="end"
						>
							<div className="space-y-2">
								<h4 className="font-medium text-sm">
									Input Parameters
								</h4>
								{resolvedToolCall.arguments &&
								Object.keys(resolvedToolCall.arguments).length >
									0 ? (
									<PrettyInputDisplay
										inputData={
											resolvedToolCall.arguments as Record<
												string,
												unknown
											>
										}
										showToggle={false}
										defaultView="pretty"
									/>
								) : (
									<p className="text-sm text-muted-foreground">
										No input parameters
									</p>
								)}
							</div>
						</PopoverContent>
					</Popover>
				</div>
			</div>

			{/* Live Logs (while running) */}
			{status === "running" && displayLogs.length > 0 && (
				<div className="border-t bg-muted/10">
					<div className="max-h-32 overflow-y-auto px-3 py-2 space-y-0.5">
						{displayLogs.map((log, index) => (
							<p
								key={`${log.timestamp || index}-${index}`}
								className={cn(
									"text-xs font-mono",
									log.level === "error" && "text-destructive",
									log.level === "warning" && "text-amber-500",
									log.level === "info" &&
										"text-muted-foreground",
									log.level === "debug" &&
										"text-muted-foreground/70",
								)}
							>
								{log.message}
							</p>
						))}
						<div ref={logsEndRef} />
					</div>
				</div>
			)}

			{/* Single log line when pending (no streaming yet) */}
			{status === "pending" && latestLog && (
				<div className="px-3 py-2 border-t bg-muted/10">
					<p className="text-xs font-mono text-muted-foreground truncate">
						{latestLog.message}
					</p>
				</div>
			)}

			{/* Error Message */}
			{status === "failed" && error && (
				<div className="px-3 py-2 border-t bg-destructive/5">
					<p className="text-xs text-destructive font-mono">
						{error}
					</p>
				</div>
			)}

			{/* Result Section (collapsible) */}
			{isComplete && hasResult && (
				<Collapsible open={isResultOpen} onOpenChange={setIsResultOpen}>
					<CollapsibleTrigger asChild>
						<button
							type="button"
							className="flex items-center gap-1 w-full px-3 py-2 border-t bg-muted/10 hover:bg-muted/20 transition-colors text-left"
						>
							{isResultOpen ? (
								<ChevronDown className="h-3.5 w-3.5 text-muted-foreground" />
							) : (
								<ChevronRight className="h-3.5 w-3.5 text-muted-foreground" />
							)}
							<span className="text-xs font-medium">Result</span>
						</button>
					</CollapsibleTrigger>
					<AnimatePresence>
						{isResultOpen && (
							<CollapsibleContent forceMount>
								<motion.div
									initial={{ height: 0, opacity: 0 }}
									animate={{ height: "auto", opacity: 1 }}
									exit={{ height: 0, opacity: 0 }}
									transition={{ duration: 0.2 }}
									className="overflow-hidden"
								>
									<div className="border-t">
										{/* Result Section */}
										<div className="px-3 py-2 max-h-64 overflow-auto">
											{typeof result === "object" &&
											result !== null ? (
												<PrettyInputDisplay
													inputData={
														result as Record<
															string,
															unknown
														>
													}
													showToggle={true}
													defaultView="pretty"
												/>
											) : (
												<pre className="text-xs font-mono whitespace-pre-wrap text-muted-foreground">
													{typeof result === "string"
														? result
														: JSON.stringify(
																result,
																null,
																2,
															)}
												</pre>
											)}
										</div>
										{/* Logs Section */}
										{displayLogs.length > 0 && (
											<div className="px-3 py-2 border-t">
												<h5 className="text-xs font-medium text-muted-foreground mb-1">
													Logs
												</h5>
												<div className="max-h-32 overflow-y-auto space-y-0.5">
													{displayLogs.map(
														(log, index) => (
															<p
																key={`${log.timestamp || index}-${index}`}
																className={cn(
																	"text-xs font-mono",
																	log.level ===
																		"error" &&
																		"text-destructive",
																	log.level ===
																		"warning" &&
																		"text-amber-500",
																	log.level ===
																		"info" &&
																		"text-muted-foreground",
																	log.level ===
																		"debug" &&
																		"text-muted-foreground/70",
																)}
															>
																{log.message}
															</p>
														),
													)}
												</div>
											</div>
										)}
									</div>
								</motion.div>
							</CollapsibleContent>
						)}
					</AnimatePresence>
				</Collapsible>
			)}
		</div>
	);
}
