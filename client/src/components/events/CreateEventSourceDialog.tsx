import { useState, useMemo } from "react";
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
import { OrganizationSelect } from "@/components/forms/OrganizationSelect";
import { useAuth } from "@/contexts/AuthContext";
import {
	useCreateEventSource,
	useWebhookAdapters,
	type EventSourceType,
} from "@/services/events";
import { useIntegrations } from "@/services/integrations";
import { DynamicConfigForm, type ConfigSchema } from "./DynamicConfigForm";

interface CreateEventSourceDialogProps {
	open: boolean;
	onOpenChange: (open: boolean) => void;
	onSuccess?: () => void;
}

function CreateEventSourceDialogContent({
	onOpenChange,
	onSuccess,
}: Omit<CreateEventSourceDialogProps, "open">) {
	const { isPlatformAdmin } = useAuth();
	const createMutation = useCreateEventSource();

	// Form state
	const [name, setName] = useState("");
	const [sourceType, setSourceType] = useState<EventSourceType>("webhook");
	const [organizationId, setOrganizationId] = useState<string | null>(null);
	const [adapterName, setAdapterName] = useState<string>("");
	const [integrationId, setIntegrationId] = useState<string>("");
	const [errors, setErrors] = useState<string[]>([]);

	// Dynamic config for adapters with config_schema
	const [webhookConfig, setWebhookConfig] = useState<Record<string, unknown>>(
		{},
	);

	// Fetch available adapters
	const { data: adaptersData } = useWebhookAdapters();
	const adapters = adaptersData?.adapters || [];

	// Fetch integrations for OAuth-based adapters
	const { data: integrationsData } = useIntegrations();
	const integrations = integrationsData?.items || [];

	// Get selected adapter info
	const selectedAdapter = adapters.find((a) => a.name === adapterName);

	// Filter integrations if adapter requires specific OAuth
	const filteredIntegrations = selectedAdapter?.requires_integration
		? integrations.filter(
				(i) => i.name === selectedAdapter.requires_integration,
			)
		: integrations;

	// Check if adapter has dynamic config schema (non-empty properties)
	const hasDynamicConfig = useMemo(() => {
		if (!selectedAdapter?.config_schema) return false;
		const schema = selectedAdapter.config_schema as {
			properties?: Record<string, unknown>;
		};
		return schema.properties && Object.keys(schema.properties).length > 0;
	}, [selectedAdapter]);

	// Reset config when adapter changes
	const handleAdapterChange = (newAdapter: string) => {
		setAdapterName(newAdapter);
		setWebhookConfig({});
		setIntegrationId("");
	};

	const isLoading = createMutation.isPending;

	const validateForm = (): boolean => {
		const newErrors: string[] = [];

		if (!name.trim()) {
			newErrors.push("Name is required");
		}

		if (sourceType === "webhook" && !adapterName) {
			newErrors.push("Please select a webhook adapter");
		}

		if (selectedAdapter?.requires_integration && !integrationId) {
			newErrors.push(
				`This adapter requires a ${selectedAdapter.requires_integration} integration`,
			);
		}

		setErrors(newErrors);
		return newErrors.length === 0;
	};

	const handleSubmit = async (e: React.FormEvent) => {
		e.preventDefault();
		if (!validateForm()) return;

		try {
			await createMutation.mutateAsync({
				body: {
					name: name.trim(),
					source_type: sourceType,
					organization_id: organizationId || undefined,
					webhook:
						sourceType === "webhook"
							? {
									adapter_name: adapterName || undefined,
									integration_id: integrationId || undefined,
									config: webhookConfig,
								}
							: undefined,
				},
			});

			toast.success("Event source created successfully");
			onOpenChange(false);
			onSuccess?.();
		} catch (error) {
			console.error("Failed to create event source:", error);
			toast.error("Failed to create event source");
		}
	};

	return (
		<form onSubmit={handleSubmit}>
			<DialogHeader>
				<DialogTitle>Create Event Source</DialogTitle>
				<DialogDescription>
					Create a new event source to receive webhooks and trigger
					workflows.
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

				{/* Organization (Platform Admin Only) */}
				{isPlatformAdmin && (
					<div className="space-y-2">
						<Label htmlFor="organization">Organization</Label>
						<OrganizationSelect
							value={organizationId}
							onChange={(value) =>
								setOrganizationId(value ?? null)
							}
							showGlobal
						/>
						<p className="text-xs text-muted-foreground">
							Leave as Global to make this source available to all
							organizations.
						</p>
					</div>
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

				{/* Source Type */}
				<div className="space-y-2">
					<Label htmlFor="source-type">Source Type</Label>
					<Select
						value={sourceType}
						onValueChange={(value) =>
							setSourceType(value as EventSourceType)
						}
					>
						<SelectTrigger id="source-type">
							<SelectValue />
						</SelectTrigger>
						<SelectContent>
							<SelectItem value="webhook">Webhook</SelectItem>
							<SelectItem value="schedule" disabled>
								Schedule (Coming Soon)
							</SelectItem>
							<SelectItem value="internal" disabled>
								Internal (Coming Soon)
							</SelectItem>
						</SelectContent>
					</Select>
				</div>

				{/* Webhook Adapter */}
				{sourceType === "webhook" && (
					<div className="space-y-2">
						<Label htmlFor="adapter">Webhook Adapter</Label>
						<Select
							value={adapterName}
							onValueChange={handleAdapterChange}
						>
							<SelectTrigger id="adapter">
								<SelectValue placeholder="Select an adapter..." />
							</SelectTrigger>
							<SelectContent>
								{adapters.map((adapter) => (
									<SelectItem
										key={adapter.name}
										value={adapter.name}
									>
										{adapter.display_name}
									</SelectItem>
								))}
							</SelectContent>
						</Select>
						{selectedAdapter?.description && (
							<p className="text-xs text-muted-foreground">
								{selectedAdapter.description}
							</p>
						)}
					</div>
				)}

				{/* Integration (if required by adapter) */}
				{selectedAdapter?.requires_integration && (
					<div className="space-y-2">
						<Label htmlFor="integration">Integration</Label>
						<Select
							value={integrationId}
							onValueChange={setIntegrationId}
						>
							<SelectTrigger id="integration">
								<SelectValue placeholder="Select an integration..." />
							</SelectTrigger>
							<SelectContent>
								{filteredIntegrations.map((integration) => (
									<SelectItem
										key={integration.id}
										value={integration.id}
									>
										{integration.name}
									</SelectItem>
								))}
							</SelectContent>
						</Select>
						<p className="text-xs text-muted-foreground">
							This adapter requires a{" "}
							{selectedAdapter.requires_integration} integration
							for authentication.
						</p>
					</div>
				)}

				{/* Dynamic Config Form - For adapters with config_schema */}
				{sourceType === "webhook" &&
					hasDynamicConfig &&
					selectedAdapter && (
						<>
							<div className="border-t pt-4">
								<h4 className="text-sm font-medium mb-3">
									Configuration
								</h4>
							</div>
							<DynamicConfigForm
								adapterName={selectedAdapter.name}
								integrationId={integrationId || undefined}
								configSchema={
									selectedAdapter.config_schema as unknown as ConfigSchema
								}
								config={webhookConfig}
								onChange={setWebhookConfig}
							/>
						</>
					)}

				{/* Generic adapter config - fallback for adapters without config_schema */}
				{sourceType === "webhook" &&
					adapterName === "generic" &&
					!hasDynamicConfig && (
						<>
							<div className="border-t pt-4">
								<h4 className="text-sm font-medium mb-3">
									Webhook Configuration
								</h4>
								<p className="text-xs text-muted-foreground mb-3">
									Configure how event types are extracted from
									incoming webhooks.
								</p>
							</div>

							<div className="space-y-2">
								<Label htmlFor="event-type-header">
									Event Type Header
								</Label>
								<Input
									id="event-type-header"
									value={
										(webhookConfig.event_type_header as string) ||
										""
									}
									onChange={(e) =>
										setWebhookConfig((prev) => ({
											...prev,
											event_type_header:
												e.target.value || undefined,
										}))
									}
									placeholder="e.g., X-Event-Type"
								/>
								<p className="text-xs text-muted-foreground">
									HTTP header containing the event type
									(optional)
								</p>
							</div>

							<div className="space-y-2">
								<Label htmlFor="event-type-field">
									Event Type Field
								</Label>
								<Input
									id="event-type-field"
									value={
										(webhookConfig.event_type_field as string) ||
										""
									}
									onChange={(e) =>
										setWebhookConfig((prev) => ({
											...prev,
											event_type_field:
												e.target.value || undefined,
										}))
									}
									placeholder="e.g., type or event"
								/>
								<p className="text-xs text-muted-foreground">
									JSON payload field containing the event type
									(optional)
								</p>
							</div>

							<div className="space-y-2">
								<Label htmlFor="secret">Webhook Secret</Label>
								<Input
									id="secret"
									type="password"
									value={
										(webhookConfig.secret as string) || ""
									}
									onChange={(e) =>
										setWebhookConfig((prev) => ({
											...prev,
											secret: e.target.value || undefined,
										}))
									}
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
					Create Event Source
				</Button>
			</DialogFooter>
		</form>
	);
}

export function CreateEventSourceDialog({
	open,
	onOpenChange,
	onSuccess,
}: CreateEventSourceDialogProps) {
	return (
		<Dialog open={open} onOpenChange={onOpenChange}>
			<DialogContent className="sm:max-w-[500px]">
				{open && (
					<CreateEventSourceDialogContent
						onOpenChange={onOpenChange}
						onSuccess={onSuccess}
					/>
				)}
			</DialogContent>
		</Dialog>
	);
}
