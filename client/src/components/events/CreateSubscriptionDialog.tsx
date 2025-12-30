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
import {
	Select,
	SelectContent,
	SelectItem,
	SelectTrigger,
	SelectValue,
} from "@/components/ui/select";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { AlertCircle, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { useCreateSubscription } from "@/services/events";
import { useWorkflows } from "@/hooks/useWorkflows";
import type { components } from "@/lib/v1";

type WorkflowMetadata = components["schemas"]["WorkflowMetadata"];

interface CreateSubscriptionDialogProps {
	open: boolean;
	onOpenChange: (open: boolean) => void;
	sourceId: string;
	onSuccess?: () => void;
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
	const [errors, setErrors] = useState<string[]>([]);

	// Fetch available workflows
	const { data: workflowsData, isLoading: isLoadingWorkflows } = useWorkflows();
	const workflows: WorkflowMetadata[] = workflowsData || [];

	const isLoading = createMutation.isPending;

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
			await createMutation.mutateAsync({
				params: {
					path: { source_id: sourceId },
				},
				body: {
					workflow_id: workflowId,
					event_type: eventType.trim() || undefined,
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
					Subscribe a workflow to receive events from this source. The workflow
					will be triggered whenever matching events arrive.
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

				{/* Workflow Select */}
				<div className="space-y-2">
					<Label htmlFor="workflow">Workflow</Label>
					<Select value={workflowId} onValueChange={setWorkflowId}>
						<SelectTrigger id="workflow">
							<SelectValue
								placeholder={
									isLoadingWorkflows
										? "Loading workflows..."
										: "Select a workflow..."
								}
							/>
						</SelectTrigger>
						<SelectContent>
							{workflows.map((workflow) => (
								<SelectItem key={workflow.id} value={workflow.id}>
									{workflow.name}
								</SelectItem>
							))}
						</SelectContent>
					</Select>
					<p className="text-xs text-muted-foreground">
						The workflow will receive the event data as input parameters.
					</p>
				</div>

				{/* Event Type Filter (optional) */}
				<div className="space-y-2">
					<Label htmlFor="event-type">Event Type Filter (optional)</Label>
					<Input
						id="event-type"
						value={eventType}
						onChange={(e) => setEventType(e.target.value)}
						placeholder="e.g., ticket.created"
					/>
					<p className="text-xs text-muted-foreground">
						Only trigger the workflow for events matching this type. Leave empty
						to receive all events.
					</p>
				</div>
			</div>

			<DialogFooter>
				<Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
					Cancel
				</Button>
				<Button type="submit" disabled={isLoading}>
					{isLoading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
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
