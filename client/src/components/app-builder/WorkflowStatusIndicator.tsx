/**
 * Workflow Status Indicator for App Shell Header
 *
 * Shows workflow execution status inline in the header:
 * - Running: Spinner with workflow name
 * - Success: Brief checkmark message that fades
 * - Error: Clickable error message that opens details dialog
 */

import { useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Loader2, CheckCircle2, XCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
	Dialog,
	DialogContent,
	DialogHeader,
	DialogTitle,
	DialogDescription,
} from "@/components/ui/dialog";
import type { WorkflowResult } from "@/lib/app-builder-types";

interface WorkflowStatusIndicatorProps {
	/** Map of execution ID to workflow name for currently running workflows */
	activeWorkflowNames: Map<string, string>;
	/** Result of the last completed workflow (for success/error display) */
	lastCompletedResult?: WorkflowResult;
	/** Callback to clear the last result after it's been displayed */
	onClearResult?: () => void;
}

/**
 * Displays workflow execution status in the app header
 *
 * @example
 * <WorkflowStatusIndicator
 *   activeWorkflowNames={activeWorkflowNames}
 *   lastCompletedResult={lastCompletedResult}
 *   onClearResult={() => setLastCompletedResult(undefined)}
 * />
 */
export function WorkflowStatusIndicator({
	activeWorkflowNames,
	lastCompletedResult,
	onClearResult,
}: WorkflowStatusIndicatorProps) {
	const [showSuccess, setShowSuccess] = useState(false);
	const [showError, setShowError] = useState(false);
	const [errorDialogOpen, setErrorDialogOpen] = useState(false);

	// Get first running workflow name for display
	const runningName = activeWorkflowNames.values().next().value;
	const isRunning = activeWorkflowNames.size > 0;
	const runningCount = activeWorkflowNames.size;

	// Handle completed workflow display
	useEffect(() => {
		if (!lastCompletedResult) {
			setShowSuccess(false);
			setShowError(false);
			return undefined;
		}

		if (lastCompletedResult.status === "completed") {
			// Show success briefly, then fade
			setShowSuccess(true);
			setShowError(false);
			const timer = setTimeout(() => {
				setShowSuccess(false);
				onClearResult?.();
			}, 2000);
			return () => clearTimeout(timer);
		}

		if (lastCompletedResult.status === "failed") {
			// Show error until dismissed
			setShowError(true);
			setShowSuccess(false);
		}

		return undefined;
	}, [lastCompletedResult, onClearResult]);

	// Clear error when dialog closes
	const handleErrorDismiss = () => {
		setErrorDialogOpen(false);
		setShowError(false);
		onClearResult?.();
	};

	// Nothing to show
	if (!isRunning && !showSuccess && !showError) {
		return null;
	}

	return (
		<>
			<AnimatePresence mode="wait">
				{/* Running State */}
				{isRunning && (
					<motion.div
						key="running"
						initial={{ opacity: 0, x: 10 }}
						animate={{ opacity: 1, x: 0 }}
						exit={{ opacity: 0, x: -10 }}
						transition={{ duration: 0.15 }}
						className="flex items-center gap-2 text-sm text-muted-foreground"
					>
						<Loader2 className="h-4 w-4 animate-spin text-primary" />
						<span>
							{runningCount > 1
								? `Running ${runningCount} workflows...`
								: `Running ${runningName || "workflow"}...`}
						</span>
					</motion.div>
				)}

				{/* Success State */}
				{!isRunning && showSuccess && lastCompletedResult && (
					<motion.div
						key="success"
						initial={{ opacity: 0, x: 10 }}
						animate={{ opacity: 1, x: 0 }}
						exit={{ opacity: 0 }}
						transition={{ duration: 0.15 }}
						className="flex items-center gap-2 text-sm text-green-600 dark:text-green-500"
					>
						<CheckCircle2 className="h-4 w-4" />
						<span>
							{lastCompletedResult.workflowName} completed
						</span>
					</motion.div>
				)}

				{/* Error State */}
				{!isRunning &&
					showError &&
					lastCompletedResult?.status === "failed" && (
						<motion.div
							key="error"
							initial={{ opacity: 0, x: 10 }}
							animate={{ opacity: 1, x: 0 }}
							transition={{ duration: 0.15 }}
						>
							<Button
								variant="ghost"
								size="sm"
								className="h-auto py-1 px-2 text-destructive hover:text-destructive hover:bg-destructive/10"
								onClick={() => setErrorDialogOpen(true)}
							>
								<XCircle className="h-4 w-4 mr-1.5" />
								<span className="text-sm">
									{lastCompletedResult.workflowName} failed -
									Click for details
								</span>
							</Button>
						</motion.div>
					)}
			</AnimatePresence>

			{/* Error Details Dialog */}
			<Dialog open={errorDialogOpen} onOpenChange={handleErrorDismiss}>
				<DialogContent className="max-w-lg">
					<DialogHeader>
						<DialogTitle className="text-destructive flex items-center gap-2">
							<XCircle className="h-5 w-5" />
							Workflow Failed
						</DialogTitle>
						<DialogDescription>
							{lastCompletedResult?.workflowName || "Workflow"}{" "}
							encountered an error
						</DialogDescription>
					</DialogHeader>
					<div className="mt-2 p-4 bg-muted rounded-md max-h-64 overflow-auto">
						<pre className="text-sm whitespace-pre-wrap font-mono">
							{lastCompletedResult?.error ||
								"Unknown error occurred"}
						</pre>
					</div>
				</DialogContent>
			</Dialog>
		</>
	);
}

export default WorkflowStatusIndicator;
