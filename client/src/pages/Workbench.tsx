/**
 * Workbench - CLI Session Workbench with split-panel layout
 *
 * Provides a unified experience for workflow selection, parameter input,
 * execution viewing, and history - all on one page.
 */

import { useState, useEffect, useCallback, useRef } from "react";
import { useNavigate, useParams, Link } from "react-router-dom";
import {
	AlertCircle,
	ArrowLeft,
	PanelLeftClose,
	PanelLeft,
} from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";
import { webSocketService } from "@/services/websocket";
import { Button } from "@/components/ui/button";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Skeleton } from "@/components/ui/skeleton";
import { toast } from "sonner";
import {
	getCLISession,
	continueCLISession,
	type CLISessionResponse,
} from "@/services/cli";
import { SessionControlPanel } from "@/components/cli/SessionControlPanel";
import { ExecutionDetails } from "@/pages/ExecutionDetails";

// Minimum sidebar width
const MIN_SIDEBAR_WIDTH = 280;
const MAX_SIDEBAR_WIDTH = 600;
const DEFAULT_SIDEBAR_WIDTH = 360;

export function Workbench() {
	const { sessionId } = useParams<{ sessionId: string }>();
	const navigate = useNavigate();
	const { user } = useAuth();

	// Session state
	const [session, setSession] = useState<CLISessionResponse | null>(null);
	const [isLoading, setIsLoading] = useState(true);
	const [error, setError] = useState<string | null>(null);

	// UI state
	const [selectedWorkflow, setSelectedWorkflow] = useState<string | null>(
		null,
	);
	const [isSubmitting, setIsSubmitting] = useState(false);
	const [currentExecutionId, setCurrentExecutionId] = useState<string | null>(
		null,
	);

	// Resizable sidebar state
	const [sidebarWidth, setSidebarWidth] = useState(DEFAULT_SIDEBAR_WIDTH);
	const [sidebarVisible, setSidebarVisible] = useState(true);
	const [isResizing, setIsResizing] = useState(false);
	const containerRef = useRef<HTMLDivElement>(null);

	// Fetch session data - only depends on sessionId to avoid re-fetching when
	// selectedWorkflow or currentExecutionId change (which would cause loading
	// skeleton to flash and unmount SessionControlPanel, losing form state)
	const fetchSession = useCallback(async () => {
		if (!sessionId) return;

		try {
			setIsLoading(true);
			const data = await getCLISession(sessionId);
			if (!data) {
				setError("Session not found");
				return;
			}
			setSession(data);
			setError(null);

			// Initialize selected workflow (use functional update to avoid stale closure)
			setSelectedWorkflow((current) => {
				if (current) return current; // Already set, don't override
				if (data.selected_workflow) return data.selected_workflow;
				if (data.workflows.length === 1) return data.workflows[0].name;
				return null;
			});

			// Track latest execution (use functional update to avoid stale closure)
			setCurrentExecutionId((current) => {
				if (current) return current; // Already set, don't override
				if (data.executions && data.executions.length > 0) return data.executions[0].id;
				return null;
			});
		} catch (err) {
			setError(
				err instanceof Error ? err.message : "Failed to load session",
			);
		} finally {
			setIsLoading(false);
		}
	}, [sessionId]);

	useEffect(() => {
		fetchSession();
	}, [fetchSession]);

	// Subscribe to websocket for session updates
	useEffect(() => {
		if (!user?.id || !sessionId) return;

		const channel = `cli-session:${sessionId}`;
		webSocketService.connect([channel]);

		// Subscribe to CLI session updates using proper callback mechanism
		// This survives WebSocket reconnections unlike raw message listeners
		const unsubscribe = webSocketService.onCLISessionUpdate(
			sessionId,
			(update) => {
				if (update.state) {
					setSession(update.state);
					// Update current execution if new one started
					if (update.state.executions && update.state.executions.length > 0) {
						const latestExecution = update.state.executions[0];
						// Only auto-switch if the new execution is running/pending
						if (
							latestExecution.status === "Running" ||
							latestExecution.status === "Pending"
						) {
							setCurrentExecutionId(latestExecution.id);
						}
					}
				}
			},
		);

		return () => {
			unsubscribe();
			webSocketService.unsubscribe(channel);
		};
	}, [user?.id, sessionId]);

	// Handle workflow execution
	const handleRun = useCallback(
		async (params: Record<string, unknown>) => {
			if (!selectedWorkflow || !sessionId) {
				toast.error("Please select a workflow");
				return;
			}

			setIsSubmitting(true);
			try {
				const response = await continueCLISession(sessionId, {
					workflow_name: selectedWorkflow,
					params,
				});

				// Subscribe to execution channel BEFORE mounting ExecutionDetails
				// This ensures we receive completion events even for fast CLI executions
				// (CLI polls for pending executions and can complete very quickly)
				await webSocketService.connect([
					`execution:${response.execution_id}`,
				]);

				setCurrentExecutionId(response.execution_id);
				toast.success("Workflow execution started");
			} catch (err) {
				toast.error(
					err instanceof Error
						? err.message
						: "Failed to start execution",
				);
			} finally {
				setIsSubmitting(false);
			}
		},
		[selectedWorkflow, sessionId],
	);

	// Resize handlers
	const handleMouseDown = useCallback((e: React.MouseEvent) => {
		e.preventDefault();
		setIsResizing(true);
	}, []);

	const handleMouseMove = useCallback(
		(e: MouseEvent) => {
			if (!isResizing || !containerRef.current) return;

			const containerRect = containerRef.current.getBoundingClientRect();
			const newWidth = e.clientX - containerRect.left;
			const constrainedWidth = Math.max(
				MIN_SIDEBAR_WIDTH,
				Math.min(MAX_SIDEBAR_WIDTH, newWidth),
			);
			setSidebarWidth(constrainedWidth);
		},
		[isResizing],
	);

	const handleMouseUp = useCallback(() => {
		setIsResizing(false);
	}, []);

	useEffect(() => {
		if (isResizing) {
			document.addEventListener("mousemove", handleMouseMove);
			document.addEventListener("mouseup", handleMouseUp);
			return () => {
				document.removeEventListener("mousemove", handleMouseMove);
				document.removeEventListener("mouseup", handleMouseUp);
			};
		}
		return undefined;
	}, [isResizing, handleMouseMove, handleMouseUp]);

	// Loading state
	if (isLoading) {
		return (
			<div className="flex h-[calc(100vh-4rem)]">
				<div className="w-[360px] border-r p-4 space-y-4">
					<Skeleton className="h-16 w-full" />
					<Skeleton className="h-10 w-full" />
					<Skeleton className="h-32 w-full" />
				</div>
				<div className="flex-1 p-4">
					<Skeleton className="h-full w-full" />
				</div>
			</div>
		);
	}

	// Error state
	if (error || !session) {
		return (
			<div className="p-6 space-y-4 max-w-lg mx-auto mt-12">
				<Alert variant="destructive">
					<AlertCircle className="h-4 w-4" />
					<AlertTitle>Error</AlertTitle>
					<AlertDescription>
						{error || "Session not found"}
					</AlertDescription>
				</Alert>
				<Button onClick={() => navigate("/cli")} variant="outline">
					<ArrowLeft className="mr-2 h-4 w-4" />
					Back to Sessions
				</Button>
			</div>
		);
	}

	return (
		<div
			ref={containerRef}
			className="flex h-[calc(100vh-4rem)] overflow-hidden"
			style={{ cursor: isResizing ? "col-resize" : undefined }}
		>
			{/* Top bar for mobile / toggle */}
			<div className="absolute top-2 left-2 z-10 lg:hidden">
				<Button
					variant="outline"
					size="icon"
					onClick={() => setSidebarVisible(!sidebarVisible)}
				>
					{sidebarVisible ? (
						<PanelLeftClose className="h-4 w-4" />
					) : (
						<PanelLeft className="h-4 w-4" />
					)}
				</Button>
			</div>

			{/* Left panel: Control panel */}
			{sidebarVisible && (
				<div
					className="relative flex-none border-r bg-background"
					style={{ width: `${sidebarWidth}px` }}
				>
					{/* Back link */}
					<div className="absolute top-2 left-2 z-10">
						<Button variant="ghost" size="sm" asChild>
							<Link to="/cli">
								<ArrowLeft className="h-4 w-4 mr-1" />
								Sessions
							</Link>
						</Button>
					</div>

					<div className="h-full pt-10">
						<SessionControlPanel
							session={session}
							selectedWorkflow={selectedWorkflow}
							onSelectWorkflow={setSelectedWorkflow}
							onRun={handleRun}
							isSubmitting={isSubmitting}
							currentExecutionId={currentExecutionId}
							onSelectExecution={setCurrentExecutionId}
						/>
					</div>

					{/* Resize handle */}
					<div
						className="absolute top-0 right-0 bottom-0 w-1 cursor-col-resize hover:bg-primary/50 active:bg-primary transition-colors"
						onMouseDown={handleMouseDown}
					/>
				</div>
			)}

			{/* Toggle button when sidebar is hidden */}
			{!sidebarVisible && (
				<div className="absolute top-2 left-2 z-10">
					<Button
						variant="outline"
						size="icon"
						onClick={() => setSidebarVisible(true)}
					>
						<PanelLeft className="h-4 w-4" />
					</Button>
				</div>
			)}

			{/* Right panel: Execution viewer */}
			<div className="flex-1 overflow-hidden bg-muted/20">
				{currentExecutionId ? (
					<ExecutionDetails
						executionId={currentExecutionId}
						embedded
					/>
				) : (
					<div className="flex flex-col items-center justify-center h-full text-center p-8">
						<div className="text-muted-foreground space-y-2">
							<h3 className="text-lg font-medium">
								No Execution Selected
							</h3>
							<p className="text-sm">
								Select a workflow and click Run to start an
								execution,
								<br />
								or select a previous execution from the history.
							</p>
						</div>
					</div>
				)}
			</div>
		</div>
	);
}
