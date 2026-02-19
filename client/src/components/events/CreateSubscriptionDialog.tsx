import { useState } from "react";
import {
	Dialog,
	DialogContent,
	DialogDescription,
	DialogFooter,
	DialogHeader,
	DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { AlertCircle, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { useCreateSubscription } from "@/services/events";
import { useWorkflows } from "@/hooks/useWorkflows";
import { WorkflowSelectorDialog } from "@/components/workflows/WorkflowSelectorDialog";
import { WorkflowParametersForm } from "@/components/workflows/WorkflowParametersForm";
import type { components } from "@/lib/v1";

type WorkflowMetadata = components["schemas"]["WorkflowMetadata"];

interface CreateSubscriptionDialogProps {
	open: boolean;
	onOpenChange: (open: boolean) => void;
	sourceId: string;
	onSuccess?: () => void;
}

/**
 * Remove entries where value is undefined, null, or empty string.
 * Returns undefined if no non-empty values remain.
 */
function cleanInputMapping(
	mapping: Record<string, unknown>,
): Record<string, unknown> | undefined {
	const cleaned = Object.fromEntries(
		Object.entries(mapping).filter(
			([, v]) => v !== undefined && v !== null && v !== "",
		),
	);
	return Object.keys(cleaned).length > 0 ? cleaned : undefined;
}

function CreateSubscriptionDialogContent({
	onOpenChange,
	sourceId,
	onSuccess,
}: Omit<CreateSubscriptionDialogProps, "open">) {
	const createMutation = useCreateSubscription();

	// Form state
	const [workflowId, setWorkflowId] = useState("");
	const [eventType, setEventType] = useState("");
	const [inputMapping, setInputMapping] = useState<Record<string, unknown>>(
		{},
	);
	const [errors, setErrors] = useState<string[]>([]);
	const [workflowDialogOpen, setWorkflowDialogOpen] = useState(false);

	// Fetch available workflows for display name lookup
	const { data: workflowsData } = useWorkflows();
	const workflows: WorkflowMetadata[] = workflowsData || [];

	// Get selected workflow for display and parameter info
	const selectedWorkflow = workflows.find((w) => w.id === workflowId);

	const isLoading = createMutation.isPending;

	const handleWorkflowSelect = (ids: string[]) => {
		const newId = ids[0] || "";
		setWorkflowId(newId);
		// Reset input mapping when workflow changes
		setInputMapping({});
	};

	const validateForm = (): boolean => {
		const newErrors: string[] = [];

		if (!workflowId) {
			newErrors.push("Please select a workflow");
		}

		setErrors(newErrors);
		return newErrors.length === 0;
	};

	const handleSubmit = async (e: React.FormEvent) => {
		e.preventDefault();
		if (!validateForm()) return;

		try {
			const cleanedMapping = cleanInputMapping(inputMapping);

			await createMutation.mutateAsync({
				params: {
					path: { source_id: sourceId },
				},
				body: {
					workflow_id: workflowId,
					event_type: eventType.trim() || undefined,
					input_mapping: cleanedMapping,
				},
			});

			toast.success("Subscription created");
			onOpenChange(false);
			onSuccess?.();
		} catch (error) {
			console.error("Failed to create subscription:", error);
			toast.error("Failed to create subscription");
		}
	};

	return (
		<form onSubmit={handleSubmit}>
			<DialogHeader>
				<DialogTitle>Add Workflow Subscription</DialogTitle>
				<DialogDescription>
					Subscribe a workflow to receive events from this source. The
					workflow will be triggered whenever matching events arrive.
				</DialogDescription>
			</DialogHeader>

			<div className="space-y-4 py-4">
				{errors.length > 0 && (
					<Alert variant="destructive">
						<AlertCircle className="h-4 w-4" />
						<AlertDescription>
							<ul className="list-disc list-inside">
								{errors.map((error, i) => (
									<li key={i}>{error}</li>
								))}
							</ul>
						</AlertDescription>
					</Alert>
				)}

				{/* Workflow Selector */}
				<div className="space-y-2">
					<Label>Workflow</Label>
					<Button
						type="button"
						variant="outline"
						className="w-full justify-start font-normal"
						onClick={() => setWorkflowDialogOpen(true)}
					>
						{selectedWorkflow?.name || "Select a workflow..."}
					</Button>
					<WorkflowSelectorDialog
						open={workflowDialogOpen}
						onOpenChange={setWorkflowDialogOpen}
						entityRoles={[]}
						mode="single"
						selectedWorkflowIds={workflowId ? [workflowId] : []}
						onSelect={handleWorkflowSelect}
						title="Select Workflow"
						description="Choose a workflow to receive events from this source."
					/>
					<p className="text-xs text-muted-foreground">
						The workflow will receive the event data as input
						parameters.
					</p>
				</div>

				{/* Event Type Filter (optional) */}
				<div className="space-y-2">
					<Label htmlFor="event-type">
						Event Type Filter (optional)
					</Label>
					<Input
						id="event-type"
						value={eventType}
						onChange={(e) => setEventType(e.target.value)}
						placeholder="e.g., ticket.created"
					/>
					<p className="text-xs text-muted-foreground">
						Only trigger the workflow for events matching this type.
						Leave empty to receive all events.
					</p>
				</div>

				{/* Input Mapping (shown when workflow has parameters) */}
				{selectedWorkflow?.parameters &&
					selectedWorkflow.parameters.length > 0 && (
						<div className="space-y-3">
							<div className="border-t pt-3">
								<Label className="text-sm font-medium">
									Input Mapping (Optional)
								</Label>
								<p className="text-xs text-muted-foreground mt-1">
									Pre-fill workflow parameters with static
									values or template expressions. Use{" "}
									<code className="bg-muted px-1 py-0.5 rounded text-xs">
										{"{{ scheduled_time }}"}
									</code>{" "}
									for the schedule trigger time.
								</p>
							</div>
							<WorkflowParametersForm
								key={workflowId}
								parameters={selectedWorkflow.parameters}
								onExecute={() => {}}
								showExecuteButton={false}
								renderAsDiv
								disableRequired
								values={inputMapping}
								onChange={setInputMapping}
							/>
						</div>
					)}
			</div>

			<DialogFooter>
				<Button
					type="button"
					variant="outline"
					onClick={() => onOpenChange(false)}
				>
					Cancel
				</Button>
				<Button type="submit" disabled={isLoading}>
					{isLoading && (
						<Loader2 className="mr-2 h-4 w-4 animate-spin" />
					)}
					Add Subscription
				</Button>
			</DialogFooter>
		</form>
	);
}

export function CreateSubscriptionDialog({
	open,
	onOpenChange,
	sourceId,
	onSuccess,
}: CreateSubscriptionDialogProps) {
	return (
		<Dialog open={open} onOpenChange={onOpenChange}>
			<DialogContent className="sm:max-w-[450px]">
				{open && (
					<CreateSubscriptionDialogContent
						onOpenChange={onOpenChange}
						sourceId={sourceId}
						onSuccess={onSuccess}
					/>
				)}
			</DialogContent>
		</Dialog>
	);
}
