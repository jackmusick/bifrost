/**
 * Compact inline execution display for App Builder FormEmbed
 *
 * Shows execution progress, streaming logs, and results within
 * the embedded form container without navigating away.
 */

import { useEffect, useRef, useState, useCallback } from "react";
import { motion } from "framer-motion";
import {
	CheckCircle,
	XCircle,
	Loader2,
	Clock,
	ChevronDown,
	ChevronUp,
	ArrowLeft,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { useExecutionStream } from "@/hooks/useExecutionStream";
import {
	useExecutionStreamStore,
	type ExecutionStatus,
} from "@/stores/executionStreamStore";
import { PrettyInputDisplay } from "@/components/execution/PrettyInputDisplay";
import { SafeHTMLRenderer } from "@/components/execution/SafeHTMLRenderer";
import { useExecution } from "@/hooks/useExecutions";
import { useQueryClient } from "@tanstack/react-query";

interface ExecutionInlineDisplayProps {
	/** Execution ID to monitor */
	executionId: string;
	/** Callback when execution completes */
	onComplete?: (result?: unknown) => void;
	/** Callback to go back to the form */
	onBack?: () => void;
	/** Optional class name */
	className?: string;
}

/**
 * Compact inline display for execution progress and results.
 * Used by FormEmbed to show execution without navigating away.
 */
export function ExecutionInlineDisplay({
	executionId,
	onComplete,
	onBack,
	className,
}: ExecutionInlineDisplayProps) {
	const queryClient = useQueryClient();
	const logsEndRef = useRef<HTMLDivElement>(null);
	const logsContainerRef = useRef<HTMLDivElement>(null);
	const [autoScroll, setAutoScroll] = useState(true);
	const [showLogs, setShowLogs] = useState(true);

	// Get streaming state from store
	const streamState = useExecutionStreamStore(
		(state) => state.streams[executionId],
	);
	const streamingLogs = streamState?.streamingLogs ?? [];
	const streamStatus = streamState?.status;
	const isStreamComplete = streamState?.isComplete ?? false;

	// Fetch full execution data when complete (for result)
	const { data: execution } = useExecution(
		isStreamComplete ? executionId : undefined,
		false,
	);

	// Determine effective status
	const effectiveStatus: ExecutionStatus = streamStatus ?? "Pending";

	// Check if execution is complete
	const isComplete =
		effectiveStatus === "Success" ||
		effectiveStatus === "Failed" ||
		effectiveStatus === "CompletedWithErrors" ||
		effectiveStatus === "Timeout" ||
		effectiveStatus === "Cancelled";

	// Handle stream completion
	const handleStreamComplete = useCallback(() => {
		queryClient.invalidateQueries({
			queryKey: [
				"get",
				"/api/executions/{execution_id}",
				{ params: { path: { execution_id: executionId } } },
			],
		});
	}, [queryClient, executionId]);

	// Connect to WebSocket for real-time updates
	const { isConnected } = useExecutionStream({
		executionId,
		enabled: !!executionId && !isComplete,
		onComplete: handleStreamComplete,
	});

	// Call onComplete when execution finishes
	// Using a ref to track if we've called onComplete avoids the setState-in-effect issue
	const onCompleteCalledRef = useRef(false);
	useEffect(() => {
		if (isComplete && execution && !onCompleteCalledRef.current) {
			onCompleteCalledRef.current = true;
			onComplete?.(execution.result);
		}
	}, [isComplete, execution, onComplete]);

	// Auto-scroll logs
	useEffect(() => {
		const container = logsContainerRef.current;
		if (
			autoScroll &&
			logsEndRef.current &&
			streamingLogs.length > 0 &&
			container
		) {
			if (container.scrollHeight > container.clientHeight) {
				logsEndRef.current.scrollIntoView({ behavior: "smooth" });
			}
		}
	}, [streamingLogs.length, autoScroll]);

	// Detect manual scrolling
	const handleLogsScroll = useCallback(() => {
		const container = logsContainerRef.current;
		if (!container) return;
		const isAtBottom =
			container.scrollHeight -
				container.scrollTop -
				container.clientHeight <
			50;
		setAutoScroll(isAtBottom);
	}, []);

	const getStatusBadge = (status: ExecutionStatus) => {
		switch (status) {
			case "Success":
				return (
					<Badge variant="default" className="bg-green-500">
						<CheckCircle className="mr-1 h-3 w-3" />
						Completed
					</Badge>
				);
			case "Failed":
				return (
					<Badge variant="destructive">
						<XCircle className="mr-1 h-3 w-3" />
						Failed
					</Badge>
				);
			case "Running":
				return (
					<Badge variant="secondary">
						<Loader2 className="mr-1 h-3 w-3 animate-spin" />
						Running
					</Badge>
				);
			case "Pending":
				return (
					<Badge variant="outline">
						<Clock className="mr-1 h-3 w-3" />
						Pending
					</Badge>
				);
			case "Cancelling":
				return (
					<Badge
						variant="secondary"
						className="bg-orange-500 text-white"
					>
						<Loader2 className="mr-1 h-3 w-3 animate-spin" />
						Cancelling
					</Badge>
				);
			case "Cancelled":
				return (
					<Badge
						variant="outline"
						className="border-gray-500 text-gray-600"
					>
						<XCircle className="mr-1 h-3 w-3" />
						Cancelled
					</Badge>
				);
			case "CompletedWithErrors":
				return (
					<Badge variant="secondary" className="bg-yellow-500">
						<XCircle className="mr-1 h-3 w-3" />
						Completed with Errors
					</Badge>
				);
			case "Timeout":
				return (
					<Badge variant="destructive">
						<XCircle className="mr-1 h-3 w-3" />
						Timeout
					</Badge>
				);
			default:
				return null;
		}
	};

	return (
		<Card className={className}>
			<CardContent className="pt-4 space-y-4">
				{/* Header: Status + Live indicator */}
				<div className="flex items-center justify-between">
					<div className="flex items-center gap-2">
						{getStatusBadge(effectiveStatus)}
						{isConnected && !isComplete && (
							<Badge variant="outline" className="text-xs">
								<span className="mr-1 h-2 w-2 rounded-full bg-green-500 inline-block animate-pulse" />
								Live
							</Badge>
						)}
					</div>
					{isComplete && onBack && (
						<Button variant="outline" size="sm" onClick={onBack}>
							<ArrowLeft className="mr-1 h-3 w-3" />
							Submit Another
						</Button>
					)}
				</div>

				{/* Result display (when complete) */}
				{isComplete && execution && (
					<motion.div
						initial={{ opacity: 0, height: 0 }}
						animate={{ opacity: 1, height: "auto" }}
						transition={{ duration: 0.2 }}
					>
						{execution.result === null ? (
							<p className="text-sm text-muted-foreground text-center py-4">
								No result returned
							</p>
						) : (
							<div className="border rounded-md p-3">
								{execution.result_type === "json" &&
									typeof execution.result === "object" && (
										<PrettyInputDisplay
											inputData={
												execution.result as Record<
													string,
													unknown
												>
											}
											showToggle={true}
											defaultView="pretty"
										/>
									)}
								{execution.result_type === "html" &&
									typeof execution.result === "string" && (
										<SafeHTMLRenderer
											html={execution.result}
											title="Execution Result"
										/>
									)}
								{execution.result_type === "text" &&
									typeof execution.result === "string" && (
										<pre className="whitespace-pre-wrap font-mono text-sm">
											{execution.result}
										</pre>
									)}
								{!execution.result_type &&
									typeof execution.result === "object" &&
									execution.result !== null && (
										<PrettyInputDisplay
											inputData={
												execution.result as Record<
													string,
													unknown
												>
											}
											showToggle={true}
											defaultView="pretty"
										/>
									)}
							</div>
						)}
					</motion.div>
				)}

				{/* Error message */}
				{execution?.error_message && (
					<div className="border border-destructive/50 bg-destructive/10 rounded-md p-3">
						<pre className="text-sm text-destructive whitespace-pre-wrap">
							{execution.error_message}
						</pre>
					</div>
				)}

				{/* Logs section (collapsible) */}
				<div className="border rounded-md">
					<button
						type="button"
						className="w-full flex items-center justify-between p-3 hover:bg-muted/50 transition-colors"
						onClick={() => setShowLogs(!showLogs)}
					>
						<span className="text-sm font-medium flex items-center gap-2">
							Logs
							{streamingLogs.length > 0 && (
								<Badge variant="secondary" className="text-xs">
									{streamingLogs.length}
								</Badge>
							)}
						</span>
						{showLogs ? (
							<ChevronUp className="h-4 w-4 text-muted-foreground" />
						) : (
							<ChevronDown className="h-4 w-4 text-muted-foreground" />
						)}
					</button>

					{showLogs && (
						<div
							ref={logsContainerRef}
							onScroll={handleLogsScroll}
							className="max-h-48 overflow-y-auto border-t"
						>
							{streamingLogs.length === 0 ? (
								<div className="text-center text-sm text-muted-foreground py-4">
									{isComplete
										? "No logs captured"
										: "Waiting for logs..."}
								</div>
							) : (
								<div className="p-2 space-y-1">
									{streamingLogs.map((log, index) => {
										const level =
											log.level?.toLowerCase() || "info";
										const levelColor =
											{
												debug: "text-gray-500",
												info: "text-blue-600",
												warning: "text-yellow-600",
												error: "text-red-600",
												traceback: "text-orange-600",
											}[
												level as
													| "debug"
													| "info"
													| "warning"
													| "error"
													| "traceback"
											] || "text-gray-600";

										return (
											<div
												key={index}
												className="flex gap-2 text-xs font-mono"
											>
												<span className="text-muted-foreground whitespace-nowrap">
													{log.timestamp
														? new Date(
																log.timestamp,
															).toLocaleTimeString()
														: ""}
												</span>
												<span
													className={`font-semibold uppercase min-w-[50px] ${levelColor}`}
												>
													{log.level}
												</span>
												<span className="flex-1 whitespace-pre-wrap">
													{log.message}
												</span>
											</div>
										);
									})}
									<div ref={logsEndRef} />
								</div>
							)}
						</div>
					)}
				</div>
			</CardContent>
		</Card>
	);
}

export default ExecutionInlineDisplay;
