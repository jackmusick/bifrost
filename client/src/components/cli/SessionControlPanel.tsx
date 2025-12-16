/**
 * SessionControlPanel - Left panel of the CLI Workbench
 *
 * Provides workflow selection, parameter input, and run controls for CLI sessions.
 */

import { useCallback, useMemo, useState, useEffect } from "react";
import { Loader2, Wifi, WifiOff, FileCode } from "lucide-react";
import { Label } from "@/components/ui/label";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import {
	Select,
	SelectContent,
	SelectItem,
	SelectTrigger,
	SelectValue,
} from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import {
	Tooltip,
	TooltipContent,
	TooltipProvider,
	TooltipTrigger,
} from "@/components/ui/tooltip";
import { WorkflowParametersForm } from "@/components/workflows/WorkflowParametersForm";
import { SessionHistoryList } from "./SessionHistoryList";
import type { CLISessionResponse } from "@/services/cli";

interface SessionControlPanelProps {
	session: CLISessionResponse;
	selectedWorkflow: string | null;
	onSelectWorkflow: (name: string) => void;
	onRun: (params: Record<string, unknown>) => Promise<void>;
	isSubmitting: boolean;
	currentExecutionId: string | null;
	onSelectExecution: (executionId: string) => void;
}

export function SessionControlPanel({
	session,
	selectedWorkflow,
	onSelectWorkflow,
	onRun,
	isSubmitting,
	currentExecutionId,
	onSelectExecution,
}: SessionControlPanelProps) {
	const currentWorkflow = useMemo(
		() => session.workflows.find((w) => w.name === selectedWorkflow),
		[session.workflows, selectedWorkflow],
	);

	// Form state lifted from WorkflowParametersForm to prevent reset on session updates
	// This ensures form values persist even if the form component remounts
	const [formValues, setFormValues] = useState<Record<string, unknown>>({});

	// Initialize form values when workflow changes
	useEffect(() => {
		if (currentWorkflow?.parameters) {
			setFormValues(
				currentWorkflow.parameters.reduce(
					(acc: Record<string, unknown>, param) => {
						acc[param.name] =
							param.default_value ?? (param.type === "bool" ? false : "");
						return acc;
					},
					{} as Record<string, unknown>,
				),
			);
		}
	}, [selectedWorkflow]); // Only reset when workflow changes, not on every session update

	// Handle workflow selection
	const handleWorkflowSelect = useCallback(
		(name: string) => {
			onSelectWorkflow(name);
		},
		[onSelectWorkflow],
	);

	// Extract filename from path
	const fileName = session.file_path.split("/").pop() || session.file_path;

	return (
		<div className="flex flex-col h-full overflow-hidden">
			{/* Header */}
			<div className="flex-none px-4 py-2 border-b">
				<div className="flex items-center gap-3">
					<Badge
						variant={session.is_connected ? "default" : "secondary"}
						className="flex items-center gap-1 flex-shrink-0"
					>
						{session.is_connected ? (
							<>
								<Wifi className="h-3 w-3" />
								Connected
							</>
						) : (
							<>
								<WifiOff className="h-3 w-3" />
								Disconnected
							</>
						)}
					</Badge>
					<TooltipProvider>
						<Tooltip>
							<TooltipTrigger asChild>
								<div className="flex items-center gap-2 min-w-0 cursor-default">
									<FileCode className="h-4 w-4 flex-shrink-0 text-muted-foreground" />
									<span className="text-sm font-medium truncate">{fileName}</span>
								</div>
							</TooltipTrigger>
							<TooltipContent side="bottom" align="start" className="max-w-md">
								<p className="font-mono text-xs break-all">{session.file_path}</p>
							</TooltipContent>
						</Tooltip>
					</TooltipProvider>
				</div>
			</div>

			{/* Scrollable content */}
			<div className="flex-1 overflow-y-auto">
				<div className="p-4 space-y-4">
					{/* Workflow selector */}
					<div className="space-y-2">
						<Label htmlFor="workflow-select">Workflow</Label>
						{session.workflows.length === 1 ? (
							<div className="p-2 rounded-md border bg-muted/50">
								<div className="font-medium text-sm">
									{session.workflows[0].name}
								</div>
								{session.workflows[0].description && (
									<p className="text-xs text-muted-foreground mt-0.5">
										{session.workflows[0].description}
									</p>
								)}
							</div>
						) : (
							<Select
								value={selectedWorkflow || ""}
								onValueChange={handleWorkflowSelect}
							>
								<SelectTrigger id="workflow-select">
									<SelectValue placeholder="Select a workflow" />
								</SelectTrigger>
								<SelectContent>
									{session.workflows.map((w) => (
										<SelectItem key={w.name} value={w.name}>
											<div className="flex flex-col items-start">
												<span>{w.name}</span>
												{w.description && (
													<span className="text-xs text-muted-foreground">
														{w.description}
													</span>
												)}
											</div>
										</SelectItem>
									))}
								</SelectContent>
							</Select>
						)}
					</div>

					{/* Workflow description */}
					{currentWorkflow?.description && session.workflows.length > 1 && (
						<p className="text-sm text-muted-foreground">
							{currentWorkflow.description}
						</p>
					)}

					{/* Pending state indicator */}
					{session.pending && (
						<Alert>
							<Loader2 className="h-4 w-4 animate-spin" />
							<AlertTitle>Execution Pending</AlertTitle>
							<AlertDescription>
								Waiting for CLI to pick up the execution...
							</AlertDescription>
						</Alert>
					)}

					{/* Disconnected warning */}
					{!session.is_connected && !session.pending && (
						<Alert variant="destructive">
							<WifiOff className="h-4 w-4" />
							<AlertTitle>CLI Disconnected</AlertTitle>
							<AlertDescription>
								The CLI is not running. Start the CLI to execute workflows.
							</AlertDescription>
						</Alert>
					)}

					{/* Parameter form with Run button */}
					{currentWorkflow && (
						<WorkflowParametersForm
							parameters={currentWorkflow.parameters}
							onExecute={onRun}
							isExecuting={isSubmitting || session.pending}
							executeButtonText="Run"
							values={formValues}
							onChange={setFormValues}
						/>
					)}

					{/* Placeholder if no workflow selected */}
					{!currentWorkflow && session.workflows.length > 1 && (
						<p className="text-sm text-muted-foreground text-center py-4">
							Select a workflow above to configure parameters
						</p>
					)}
				</div>
			</div>

			{/* History section (sticky at bottom) */}
			{session.executions.length > 0 && (
				<div className="flex-none border-t max-h-[200px] overflow-hidden flex flex-col">
					<div className="px-4 py-2 bg-muted/30 border-b">
						<h4 className="text-sm font-medium">
							History ({session.executions.length})
						</h4>
					</div>
					<div className="overflow-y-auto flex-1">
						<SessionHistoryList
							executions={session.executions}
							currentExecutionId={currentExecutionId}
							onSelect={onSelectExecution}
						/>
					</div>
				</div>
			)}
		</div>
	);
}
