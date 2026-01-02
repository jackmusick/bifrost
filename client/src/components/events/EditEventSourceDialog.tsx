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
import { useUpdateEventSource, type EventSource } from "@/services/events";

interface EditEventSourceDialogProps {
	source: EventSource | null;
	open: boolean;
	onOpenChange: (open: boolean) => void;
}

function EditEventSourceDialogContent({
	source,
	onOpenChange,
}: {
	source: EventSource;
	onOpenChange: (open: boolean) => void;
}) {
	const updateMutation = useUpdateEventSource();

	// Form state - initialized from props, component remounts when dialog opens
	const [name, setName] = useState(source.name);

	// Webhook config fields (for generic adapter)
	const [eventTypeHeader, setEventTypeHeader] = useState<string>(
		(source.webhook?.config?.event_type_header as string) ?? "",
	);
	const [eventTypeField, setEventTypeField] = useState<string>(
		(source.webhook?.config?.event_type_field as string) ?? "",
	);
	const [secret, setSecret] = useState<string>(
		(source.webhook?.config?.secret as string) ?? "",
	);

	const [errors, setErrors] = useState<string[]>([]);

	const isLoading = updateMutation.isPending;
	const isWebhook = source.source_type === "webhook";
	const isGenericAdapter =
		!source.webhook?.adapter_name ||
		source.webhook?.adapter_name === "generic";

	const validateForm = (): boolean => {
		const newErrors: string[] = [];

		if (!name.trim()) {
			newErrors.push("Name is required");
		}

		setErrors(newErrors);
		return newErrors.length === 0;
	};

	const handleSubmit = async (e: React.FormEvent) => {
		e.preventDefault();
		if (!validateForm()) return;

		try {
			// Build webhook config only if values are set
			const webhookConfig: Record<string, unknown> = {};
			if (eventTypeHeader.trim()) {
				webhookConfig.event_type_header = eventTypeHeader.trim();
			}
			if (eventTypeField.trim()) {
				webhookConfig.event_type_field = eventTypeField.trim();
			}
			if (secret.trim()) {
				webhookConfig.secret = secret.trim();
			}

			await updateMutation.mutateAsync({
				params: {
					path: { source_id: source.id },
				},
				body: {
					name: name.trim(),
					webhook: isWebhook ? { config: webhookConfig } : undefined,
				},
			});

			toast.success("Event source updated");
			onOpenChange(false);
		} catch (error) {
			console.error("Failed to update event source:", error);
			toast.error("Failed to update event source");
		}
	};

	return (
		<form onSubmit={handleSubmit}>
			<DialogHeader>
				<DialogTitle>Edit Event Source</DialogTitle>
				<DialogDescription>
					Update the event source settings.
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

				{/* Name */}
				<div className="space-y-2">
					<Label htmlFor="name">Name</Label>
					<Input
						id="name"
						value={name}
						onChange={(e) => setName(e.target.value)}
						placeholder="e.g., GitHub Webhooks"
					/>
				</div>

				{/* Webhook Config (Generic Adapter Only) */}
				{isWebhook && isGenericAdapter && (
					<>
						<div className="border-t pt-4">
							<h4 className="text-sm font-medium mb-3">
								Webhook Configuration
							</h4>
						</div>

						<div className="space-y-2">
							<Label htmlFor="event-type-header">
								Event Type Header
							</Label>
							<Input
								id="event-type-header"
								value={eventTypeHeader}
								onChange={(e) =>
									setEventTypeHeader(e.target.value)
								}
								placeholder="e.g., X-Event-Type"
							/>
							<p className="text-xs text-muted-foreground">
								HTTP header containing the event type (optional)
							</p>
						</div>

						<div className="space-y-2">
							<Label htmlFor="event-type-field">
								Event Type Field
							</Label>
							<Input
								id="event-type-field"
								value={eventTypeField}
								onChange={(e) =>
									setEventTypeField(e.target.value)
								}
								placeholder="e.g., type or event"
							/>
							<p className="text-xs text-muted-foreground">
								JSON payload field containing the event type
								(optional, takes precedence over header)
							</p>
						</div>

						<div className="space-y-2">
							<Label htmlFor="secret">Webhook Secret</Label>
							<Input
								id="secret"
								type="password"
								value={secret}
								onChange={(e) => setSecret(e.target.value)}
								placeholder="Leave empty to disable signature verification"
							/>
							<p className="text-xs text-muted-foreground">
								HMAC secret for signature verification
								(optional)
							</p>
						</div>
					</>
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
					Save Changes
				</Button>
			</DialogFooter>
		</form>
	);
}

export function EditEventSourceDialog({
	source,
	open,
	onOpenChange,
}: EditEventSourceDialogProps) {
	return (
		<Dialog open={open} onOpenChange={onOpenChange}>
			<DialogContent className="sm:max-w-[500px]">
				{open && source && (
					<EditEventSourceDialogContent
						source={source}
						onOpenChange={onOpenChange}
					/>
				)}
			</DialogContent>
		</Dialog>
	);
}
