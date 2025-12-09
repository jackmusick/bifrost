import { useEffect, useMemo, useRef } from "react";
import { Terminal as TerminalIcon, Trash2 } from "lucide-react";
import { useEditorStore } from "@/stores/editorStore";
import { useExecutionStreamStore } from "@/stores/executionStreamStore";
import { Button } from "@/components/ui/button";
import { TerminalLogMessage } from "./TerminalLogMessage";
import { TerminalExecutionResult } from "./TerminalExecutionResult";

interface TerminalPanelProps {
	onResizeStart?: (e: React.MouseEvent) => void;
}

/**
 * Terminal panel for viewing execution logs
 * Displays output from script/workflow/data provider executions
 */
export function TerminalPanel({ onResizeStart }: TerminalPanelProps) {
	const terminalOutput = useEditorStore((state) => state.terminalOutput);
	const clearTerminalOutput = useEditorStore(
		(state) => state.clearTerminalOutput,
	);
	const currentStreamingExecutionId = useEditorStore(
		(state) => state.currentStreamingExecutionId,
	);

	// Get streaming logs from execution stream store
	// Use stable selector to only re-render when logs actually change
	const streamState = useExecutionStreamStore((state) =>
		currentStreamingExecutionId
			? state.streams[currentStreamingExecutionId]
			: undefined,
	);
	const streamingLogs = useMemo(
		() => streamState?.streamingLogs ?? [],
		[streamState?.streamingLogs],
	);

	const scrollRef = useRef<HTMLDivElement>(null);

	const formatTimestamp = (isoString: string) => {
		const date = new Date(isoString);
		return date.toLocaleTimeString("en-US", {
			hour12: false,
			hour: "2-digit",
			minute: "2-digit",
			second: "2-digit",
		});
	};

	const getLogColor = (level: string) => {
		const upperLevel = level.toUpperCase();
		switch (upperLevel) {
			case "ERROR":
				return "text-destructive";
			case "WARNING":
				return "text-yellow-600 dark:text-yellow-500";
			case "TRACEBACK":
				return "text-orange-600 dark:text-orange-500";
			case "SUCCESS":
				return "text-green-600 dark:text-green-500";
			case "INFO":
			case "DEBUG":
			default:
				return "text-foreground";
		}
	};

	// Auto-scroll to bottom when new logs or executions are added
	useEffect(() => {
		if (
			scrollRef.current &&
			(streamingLogs.length > 0 ||
				(terminalOutput && terminalOutput.executions.length > 0))
		) {
			scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
		}
	}, [terminalOutput, streamingLogs]);

	return (
		<div className="flex h-full flex-col overflow-hidden relative bg-background">
			{/* Resize handle */}
			<div
				className="absolute top-0 left-0 right-0 h-1 cursor-row-resize hover:bg-primary/50 active:bg-primary transition-colors z-20"
				onMouseDown={onResizeStart}
			/>

			{/* Loading bar - shown when execution is in progress */}
			{streamingLogs.length > 0 && (
				<div className="absolute top-1 left-0 right-0 h-0.5 bg-muted overflow-hidden z-10">
					<div className="h-full bg-primary animate-[loading_1.5s_ease-in-out_infinite]" />
				</div>
			)}

			{/* Header with clear button */}
			{(streamingLogs.length > 0 ||
				(terminalOutput && terminalOutput.executions.length > 0)) && (
				<div className="flex items-center justify-between px-3 py-1 border-b bg-muted/30">
					<div className="flex items-center gap-2">
						<TerminalIcon className="h-3 w-3 text-muted-foreground" />
						<span className="text-xs font-medium text-muted-foreground">
							Terminal
						</span>
					</div>
					<Button
						variant="ghost"
						size="sm"
						onClick={clearTerminalOutput}
						className="h-6 px-2"
						title="Clear terminal"
					>
						<Trash2 className="h-3 w-3" />
					</Button>
				</div>
			)}

			{/* Terminal content */}
			{streamingLogs.length === 0 &&
			(!terminalOutput || terminalOutput.executions.length === 0) ? (
				<div className="flex flex-1 items-center justify-center p-4">
					<div className="text-center">
						<TerminalIcon className="h-12 w-12 mx-auto mb-3 text-muted-foreground" />
						<p className="text-muted-foreground mb-2">Terminal</p>
						<p className="text-xs text-muted-foreground max-w-md">
							Execution logs will appear here when you run
							scripts, workflows, or data providers.
						</p>
					</div>
				</div>
			) : (
				<div
					ref={scrollRef}
					className="flex-1 overflow-auto p-3 font-mono text-xs bg-black/5 dark:bg-black/20 leading-tight"
				>
					{/* Completed executions */}
					{terminalOutput?.executions.map((execution, execIndex) => {
						// Check if this is a Git operation (single log entry with source "git")
						const isGitOperation =
							execution.loggerOutput.length === 1 &&
							execution.loggerOutput[0]?.source === "git";

						return (
							<div key={execIndex}>
								{/* Separator for subsequent executions (skip for git operations) */}
								{execIndex > 0 && !isGitOperation && (
									<div className="border-t border-border/50 my-2" />
								)}

								{/* Logs with inline timestamps - no spacing between lines */}
								{execution.loggerOutput.map((log, logIndex) => (
									<div
										key={logIndex}
										className={getLogColor(log.level)}
									>
										<span className="text-muted-foreground">
											[
											{log.timestamp
												? formatTimestamp(log.timestamp)
												: formatTimestamp(
														execution.timestamp,
													)}
											]
										</span>{" "}
										[{log.level.toUpperCase()}]{" "}
										<TerminalLogMessage
											message={log.message}
										/>
									</div>
								))}

								{/* Error Display */}
								{execution.error && (
									<div className="text-destructive">
										Error: {execution.error}
									</div>
								)}

								{/* Execution Result Display */}
								{execution.executionId && (
									<TerminalExecutionResult
										executionId={execution.executionId}
										status={execution.status}
									/>
								)}
							</div>
						);
					})}

					{/* Streaming logs - shown in real-time */}
					{streamingLogs.length > 0 && (
						<>
							{/* Separator between completed executions and streaming logs */}
							{terminalOutput &&
								terminalOutput.executions.length > 0 && (
									<div className="border-t border-border/50 my-2" />
								)}

							{streamingLogs.map((log, logIndex) => (
								<div
									key={`streaming-${logIndex}`}
									className={getLogColor(log.level)}
								>
									<span className="text-muted-foreground">
										[{formatTimestamp(log.timestamp)}]
									</span>{" "}
									[{log.level.toUpperCase()}]{" "}
									<TerminalLogMessage message={log.message} />
								</div>
							))}
						</>
					)}
				</div>
			)}
		</div>
	);
}
