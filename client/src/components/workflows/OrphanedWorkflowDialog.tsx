/**
 * OrphanedWorkflowDialog Component
 *
 * Dialog for managing orphaned workflows. Shows when a workflow's backing file
 * no longer exists. Provides options to:
 * - Replace with a compatible function from another file
 * - Recreate the file from the stored code snapshot
 * - Deactivate the workflow
 */

import { useState, useEffect, useCallback } from "react";
import {
	Dialog,
	DialogContent,
	DialogDescription,
	DialogHeader,
	DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import {
	Select,
	SelectContent,
	SelectItem,
	SelectTrigger,
	SelectValue,
} from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import {
	AlertTriangle,
	FileCode,
	RefreshCw,
	XCircle,
	ArrowRightLeft,
	Loader2,
} from "lucide-react";
import { toast } from "sonner";
import { authFetch } from "@/lib/api-client";
import type { components } from "@/lib/v1";

// Type for workflow from the API
type Workflow = components["schemas"]["WorkflowMetadata"];

// Types for orphan management API (may not be in generated types yet)
interface WorkflowReference {
	type: "form" | "app" | "agent";
	id: string;
	name: string;
}

interface CompatibleReplacement {
	path: string;
	function_name: string;
	signature: string;
	compatibility: "exact" | "compatible";
}

interface OrphanedWorkflowDialogProps {
	/** Whether the dialog is open */
	open: boolean;
	/** Callback when dialog should close */
	onClose: () => void;
	/** The orphaned workflow to manage */
	workflow: Workflow;
	/** Callback after successful action (to refresh data) */
	onSuccess?: () => void;
}

/**
 * Dialog for resolving orphaned workflows.
 *
 * An orphaned workflow is one whose backing file has been deleted or no longer
 * contains the workflow function. The workflow continues to work using its
 * stored code snapshot, but cannot be edited via files.
 */
export function OrphanedWorkflowDialog({
	open,
	onClose,
	workflow,
	onSuccess,
}: OrphanedWorkflowDialogProps) {
	const [replacements, setReplacements] = useState<CompatibleReplacement[]>(
		[],
	);
	const [usedBy, setUsedBy] = useState<WorkflowReference[]>([]);
	const [selectedReplacement, setSelectedReplacement] = useState<
		string | null
	>(null);
	const [isLoadingReplacements, setIsLoadingReplacements] = useState(false);
	const [isActionLoading, setIsActionLoading] = useState(false);
	const [error, setError] = useState<string | null>(null);

	// Fetch compatible replacements when dialog opens
	const fetchReplacements = useCallback(async () => {
		if (!open || !workflow.id) return;

		setIsLoadingReplacements(true);
		setError(null);

		try {
			const response = await authFetch(
				`/api/workflows/${workflow.id}/compatible-replacements`,
			);

			if (!response.ok) {
				throw new Error("Failed to fetch compatible replacements");
			}

			const data = await response.json();
			setReplacements(data.replacements || []);
		} catch (err) {
			console.error("Error fetching replacements:", err);
			setError("Failed to load compatible replacements");
		} finally {
			setIsLoadingReplacements(false);
		}
	}, [open, workflow.id]);

	// Fetch workflow references (what entities use this workflow)
	const fetchReferences = useCallback(async () => {
		if (!open || !workflow.id) return;

		try {
			const response = await authFetch(
				`/api/workflows/${workflow.id}/references`,
			);

			if (response.ok) {
				const data = await response.json();
				setUsedBy(data.references || []);
			}
		} catch (err) {
			// Non-critical, just log
			console.error("Error fetching references:", err);
		}
	}, [open, workflow.id]);

	// Reset state and load data when dialog opens. State is set inside the
	// async functions only after awaited fetches resolve — the rule fires on
	// synchronous setState in effects, which we avoid via the void-promise
	// kick-off. Reset of selectedReplacement is also wrapped so it does not
	// run synchronously within the effect body.
	useEffect(() => {
		if (!open) return;
		void (async () => {
			setSelectedReplacement(null);
			await Promise.all([fetchReplacements(), fetchReferences()]);
		})();
	}, [open, fetchReplacements, fetchReferences]);

	// Handle replace action
	const handleReplace = async () => {
		if (!selectedReplacement) return;

		setIsActionLoading(true);
		setError(null);

		try {
			const [path, funcName] = selectedReplacement.split("::");

			const response = await authFetch(
				`/api/workflows/${workflow.id}/replace`,
				{
					method: "POST",
					body: JSON.stringify({
						source_path: path,
						function_name: funcName,
					}),
				},
			);

			if (!response.ok) {
				const errorData = await response.json().catch(() => ({}));
				throw new Error(
					errorData.detail || "Failed to replace workflow",
				);
			}

			toast.success(
				`Workflow "${workflow.name}" replaced successfully`,
			);
			onSuccess?.();
			onClose();
		} catch (err) {
			const message =
				err instanceof Error ? err.message : "Failed to replace workflow";
			setError(message);
			toast.error(message);
		} finally {
			setIsActionLoading(false);
		}
	};

	// Handle recreate file action
	const handleRecreate = async () => {
		setIsActionLoading(true);
		setError(null);

		try {
			const response = await authFetch(
				`/api/workflows/${workflow.id}/recreate`,
				{
					method: "POST",
				},
			);

			if (!response.ok) {
				const errorData = await response.json().catch(() => ({}));
				throw new Error(
					errorData.detail || "Failed to recreate file",
				);
			}

			toast.success(
				`File recreated for workflow "${workflow.name}"`,
			);
			onSuccess?.();
			onClose();
		} catch (err) {
			const message =
				err instanceof Error ? err.message : "Failed to recreate file";
			setError(message);
			toast.error(message);
		} finally {
			setIsActionLoading(false);
		}
	};

	// Handle deactivate action
	const handleDeactivate = async () => {
		setIsActionLoading(true);
		setError(null);

		try {
			const response = await authFetch(
				`/api/workflows/${workflow.id}/deactivate`,
				{
					method: "POST",
				},
			);

			if (!response.ok) {
				const errorData = await response.json().catch(() => ({}));
				throw new Error(
					errorData.detail || "Failed to deactivate workflow",
				);
			}

			const data = await response.json();
			if (data.warning) {
				toast.warning(data.warning);
			} else {
				toast.success(
					`Workflow "${workflow.name}" deactivated`,
				);
			}
			onSuccess?.();
			onClose();
		} catch (err) {
			const message =
				err instanceof Error
					? err.message
					: "Failed to deactivate workflow";
			setError(message);
			toast.error(message);
		} finally {
			setIsActionLoading(false);
		}
	};

	// Get the last known path from the workflow
	const lastPath = workflow.relative_file_path || workflow.source_file_path || "Unknown";

	return (
		<Dialog open={open} onOpenChange={(isOpen) => !isOpen && onClose()}>
			<DialogContent className="max-w-lg">
				<DialogHeader>
					<DialogTitle className="flex items-center gap-2">
						<AlertTriangle className="h-5 w-5 text-yellow-500" />
						Orphaned Workflow
					</DialogTitle>
					<DialogDescription>
						This workflow's file no longer exists or no longer
						contains the workflow function. Replacing will update
						every form, app, and agent that uses this workflow
						automatically.
					</DialogDescription>
				</DialogHeader>

				<div className="space-y-4">
					{/* Workflow Info */}
					<div className="text-sm space-y-1.5 bg-muted/50 rounded-lg p-3">
						<div className="flex items-center justify-between">
							<span className="text-muted-foreground">
								Workflow:
							</span>
							<span className="font-medium">{workflow.name}</span>
						</div>
						<div className="flex items-center justify-between">
							<span className="text-muted-foreground">
								Function:
							</span>
							<code className="text-xs bg-muted px-1.5 py-0.5 rounded">
								{workflow.name}
							</code>
						</div>
						<div className="flex items-center justify-between">
							<span className="text-muted-foreground">
								Last path:
							</span>
							<code className="text-xs bg-muted px-1.5 py-0.5 rounded max-w-[200px] truncate">
								{lastPath}
							</code>
						</div>
						{usedBy.length > 0 && (
							<div className="flex items-start justify-between pt-1">
								<span className="text-muted-foreground">
									Used by:
								</span>
								<div className="flex flex-wrap gap-1 justify-end max-w-[200px]">
									{usedBy.map((ref) => (
										<Badge
											key={`${ref.type}-${ref.id}`}
											variant="secondary"
											className="text-xs"
										>
											{ref.name}
										</Badge>
									))}
								</div>
							</div>
						)}
					</div>

					{error && (
						<div className="text-sm text-destructive bg-destructive/10 rounded-lg p-3">
							{error}
						</div>
					)}

					{/* Replace Option */}
					<div className="border rounded-lg p-4 space-y-3">
						<div className="flex items-center gap-2">
							<ArrowRightLeft className="h-4 w-4 text-muted-foreground" />
							<h4 className="font-medium">
								Replace with existing file
							</h4>
						</div>
						<p className="text-sm text-muted-foreground">
							Link this workflow to a function in an existing
							file.
						</p>

						{isLoadingReplacements ? (
							<div className="space-y-2">
								<Skeleton className="h-9 w-full" />
							</div>
						) : replacements.length > 0 ? (
							<>
								<Select
									value={selectedReplacement || ""}
									onValueChange={setSelectedReplacement}
								>
									<SelectTrigger>
										<SelectValue placeholder="Select a replacement..." />
									</SelectTrigger>
									<SelectContent>
										{replacements.map((r) => (
											<SelectItem
												key={`${r.path}::${r.function_name}`}
												value={`${r.path}::${r.function_name}`}
											>
												<div className="flex items-center gap-2">
													<FileCode className="h-3 w-3 text-muted-foreground" />
													<span className="font-mono text-xs truncate max-w-[150px]">
														{r.path}
													</span>
													<span>::</span>
													<span className="font-mono text-xs">
														{r.function_name}
													</span>
													<Badge
														variant={
															r.compatibility ===
															"exact"
																? "default"
																: "secondary"
														}
														className="text-xs ml-auto"
													>
														{r.compatibility}
													</Badge>
												</div>
											</SelectItem>
										))}
									</SelectContent>
								</Select>
								<Button
									className="w-full"
									onClick={handleReplace}
									disabled={
										!selectedReplacement || isActionLoading
									}
								>
									{isActionLoading ? (
										<Loader2 className="mr-2 h-4 w-4 animate-spin" />
									) : (
										<ArrowRightLeft className="mr-2 h-4 w-4" />
									)}
									Replace
								</Button>
							</>
						) : (
							<p className="text-sm text-muted-foreground italic">
								No compatible replacements found
							</p>
						)}
					</div>

					{/* Recreate File Option */}
					<div className="border rounded-lg p-4 space-y-3">
						<div className="flex items-center gap-2">
							<RefreshCw className="h-4 w-4 text-muted-foreground" />
							<h4 className="font-medium">Recreate file</h4>
						</div>
						<p className="text-sm text-muted-foreground">
							Restore the file at{" "}
							<code className="text-xs bg-muted px-1 py-0.5 rounded">
								{lastPath}
							</code>{" "}
							with the workflow's saved code.
						</p>
						<Button
							variant="outline"
							className="w-full"
							onClick={handleRecreate}
							disabled={isActionLoading}
						>
							{isActionLoading ? (
								<Loader2 className="mr-2 h-4 w-4 animate-spin" />
							) : (
								<RefreshCw className="mr-2 h-4 w-4" />
							)}
							Recreate File
						</Button>
					</div>

					{/* Deactivate Option */}
					<div className="border border-destructive/30 rounded-lg p-4 space-y-3">
						<div className="flex items-center gap-2">
							<XCircle className="h-4 w-4 text-destructive" />
							<h4 className="font-medium">Deactivate</h4>
						</div>
						<p className="text-sm text-muted-foreground">
							Mark this workflow as inactive. Forms and apps using
							it will need to be updated.
						</p>
						{usedBy.length > 0 && (
							<p className="text-xs text-yellow-600">
								Warning: {usedBy.length}{" "}
								{usedBy.length === 1 ? "entity" : "entities"}{" "}
								still {usedBy.length === 1 ? "uses" : "use"}{" "}
								this workflow.
							</p>
						)}
						<Button
							variant="destructive"
							className="w-full"
							onClick={handleDeactivate}
							disabled={isActionLoading}
						>
							{isActionLoading ? (
								<Loader2 className="mr-2 h-4 w-4 animate-spin" />
							) : (
								<XCircle className="mr-2 h-4 w-4" />
							)}
							Deactivate
						</Button>
					</div>
				</div>
			</DialogContent>
		</Dialog>
	);
}

export default OrphanedWorkflowDialog;
