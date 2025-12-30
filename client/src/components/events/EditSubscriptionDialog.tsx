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
import {
	useUpdateSubscription,
	type EventSubscription,
} from "@/services/events";

interface EditSubscriptionDialogProps {
	subscription: EventSubscription | null;
	sourceId: string;
	open: boolean;
	onOpenChange: (open: boolean) => void;
}

function EditSubscriptionDialogContent({
	subscription,
	sourceId,
	onOpenChange,
}: {
	subscription: EventSubscription;
	sourceId: string;
	onOpenChange: (open: boolean) => void;
}) {
	const updateMutation = useUpdateSubscription();

	// Form state - initialized from props, component remounts when dialog opens
	const [eventType, setEventType] = useState<string>(
		subscription.event_type ?? ""
	);
	const [errors, setErrors] = useState<string[]>([]);

	const isLoading = updateMutation.isPending;

	const validateForm = (): boolean => {
		const newErrors: string[] = [];
		// Event type is optional, no validation needed
		setErrors(newErrors);
		return newErrors.length === 0;
	};

	const handleSubmit = async () => {
		if (!subscription || !validateForm()) return;

		try {
			await updateMutation.mutateAsync({
				params: {
					path: {
						source_id: sourceId,
						subscription_id: subscription.id,
					},
				},
				body: {
					event_type: eventType.trim() || null,
				},
			});

			toast.success("Subscription updated");
			onOpenChange(false);
		} catch (error) {
			console.error("Failed to update subscription:", error);
			toast.error("Failed to update subscription");
		}
	};

	return (
		<>
			<DialogHeader>
				<DialogTitle>Edit Subscription</DialogTitle>
				<DialogDescription>
					Update the event type filter for this subscription.
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

				{/* Workflow (read-only) */}
				<div className="space-y-2">
					<Label>Workflow</Label>
					<div className="text-sm font-medium">
						{subscription.workflow_name || subscription.workflow_id}
					</div>
					<p className="text-xs text-muted-foreground">
						The workflow cannot be changed. Create a new subscription to use a
						different workflow.
					</p>
				</div>

				{/* Event Type Filter */}
				<div className="space-y-2">
					<Label htmlFor="event-type">Event Type Filter</Label>
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
				<Button variant="outline" onClick={() => onOpenChange(false)}>
					Cancel
				</Button>
				<Button onClick={handleSubmit} disabled={isLoading}>
					{isLoading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
					Save Changes
				</Button>
			</DialogFooter>
		</>
	);
}

export function EditSubscriptionDialog({
	subscription,
	sourceId,
	open,
	onOpenChange,
}: EditSubscriptionDialogProps) {
	return (
		<Dialog open={open} onOpenChange={onOpenChange}>
			<DialogContent className="sm:max-w-[450px]">
				{open && subscription && (
					<EditSubscriptionDialogContent
						subscription={subscription}
						sourceId={sourceId}
						onOpenChange={onOpenChange}
					/>
				)}
			</DialogContent>
		</Dialog>
	);
}
