import { useState, useEffect } from "react";
import { useQueryClient } from "@tanstack/react-query";
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
import { Loader2, Plus, Trash2 } from "lucide-react";
import { toast } from "sonner";
import {
	useCreateIntegration,
	useUpdateIntegration,
	useIntegration,
	type ConfigSchemaItem,
	type IntegrationDetail,
} from "@/services/integrations";
import { useDataProviders } from "@/services/dataProviders";

interface CreateIntegrationDialogProps {
	open: boolean;
	onOpenChange: (open: boolean) => void;
	editIntegrationId?: string;
	/**
	 * If provided, use this data instead of fetching.
	 * This avoids duplicate API calls when the parent already has the data.
	 */
	initialData?: IntegrationDetail;
}

export function CreateIntegrationDialog({
	open,
	onOpenChange,
	editIntegrationId,
	initialData,
}: CreateIntegrationDialogProps) {
	const queryClient = useQueryClient();
	const [name, setName] = useState("");
	const [description, setDescription] = useState("");
	const [dataProviderId, setDataProviderId] = useState<string | null>(null);
	const [configSchema, setConfigSchema] = useState<ConfigSchemaItem[]>([]);

	// Only fetch if we don't have initialData
	const { data: fetchedIntegration } = useIntegration(
		initialData ? "" : (editIntegrationId || ""),
	);

	// Use initialData if provided, otherwise use fetched data
	const existingIntegration = initialData || fetchedIntegration;

	// Fetch available data providers
	const { data: dataProviders, isLoading: isLoadingProviders } =
		useDataProviders();

	const createMutation = useCreateIntegration();
	const updateMutation = useUpdateIntegration();

	const isEditing = Boolean(editIntegrationId);
	const isLoading = createMutation.isPending || updateMutation.isPending;

	// Populate form when editing
	useEffect(() => {
		if (existingIntegration && isEditing) {
			setName(existingIntegration.name);
			// Cast to access description field (available after types regenerated)
			const integrationWithDesc = existingIntegration as typeof existingIntegration & {
				description?: string;
			};
			setDescription(integrationWithDesc.description || "");
			setDataProviderId(
				existingIntegration.list_entities_data_provider_id || null,
			);
			setConfigSchema(existingIntegration.config_schema || []);
		}
	}, [existingIntegration, isEditing]);

	// Reset form when dialog closes
	useEffect(() => {
		if (!open) {
			setName("");
			setDescription("");
			setDataProviderId(null);
			setConfigSchema([]);
		}
	}, [open]);

	const handleSubmit = async (e: React.FormEvent) => {
		e.preventDefault();

		if (!name.trim()) {
			toast.error("Integration name is required");
			return;
		}

		try {
			if (isEditing && editIntegrationId) {
				// Use type assertion for fields not yet in generated types
				await updateMutation.mutateAsync({
					params: { path: { integration_id: editIntegrationId } },
					body: {
						name,
						list_entities_data_provider_id: dataProviderId || undefined,
						config_schema:
							configSchema.length > 0 ? configSchema : undefined,
					} as Parameters<typeof updateMutation.mutateAsync>[0]["body"] & {
						description?: string;
					},
				});
				toast.success("Integration updated successfully");
			} else {
				// Use type assertion for fields not yet in generated types
				await createMutation.mutateAsync({
					body: {
						name,
						list_entities_data_provider_id: dataProviderId || undefined,
						config_schema:
							configSchema.length > 0 ? configSchema : undefined,
					} as Parameters<typeof createMutation.mutateAsync>[0]["body"] & {
						description?: string;
					},
				});
				toast.success("Integration created successfully");
			}

			// Invalidate queries to refresh the list
			queryClient.invalidateQueries({ queryKey: ["integrations"] });
			onOpenChange(false);
		} catch (error: unknown) {
			console.error("Failed to save integration:", error);
			toast.error(
				isEditing
					? "Failed to update integration"
					: "Failed to create integration",
			);
		}
	};

	const addConfigField = () => {
		setConfigSchema([
			...configSchema,
			{
				key: "",
				type: "string",
				required: false,
				default: null,
			},
		]);
	};

	const removeConfigField = (index: number) => {
		setConfigSchema(configSchema.filter((_, i) => i !== index));
	};

	const updateConfigField = (
		index: number,
		field: Partial<ConfigSchemaItem>,
	) => {
		const updated = [...configSchema];
		updated[index] = { ...updated[index], ...field };
		setConfigSchema(updated);
	};

	return (
		<Dialog open={open} onOpenChange={onOpenChange}>
			<DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
				<form onSubmit={handleSubmit}>
					<DialogHeader>
						<DialogTitle>
							{isEditing ? "Edit Integration" : "Create Integration"}
						</DialogTitle>
						<DialogDescription>
							{isEditing
								? "Update integration settings and configuration schema"
								: "Create a new integration to map organizations to external entities"}
						</DialogDescription>
					</DialogHeader>

					<div className="space-y-4 py-4">
						{/* Name */}
						<div className="space-y-2">
							<Label htmlFor="name">Integration Name *</Label>
							<Input
								id="name"
								placeholder="e.g., Microsoft 365, Google Workspace"
								value={name}
								onChange={(e) => setName(e.target.value)}
								required
							/>
						</div>

						{/* Description */}
						<div className="space-y-2">
							<Label htmlFor="description">Description</Label>
							<Input
								id="description"
								placeholder="Brief description of this integration"
								value={description}
								onChange={(e) => setDescription(e.target.value)}
							/>
						</div>

						{/* Data Provider Selection */}
						<div className="space-y-2">
							<Label htmlFor="dataProvider">
								Entity Data Provider
							</Label>
							<Select
								value={dataProviderId || "none"}
								onValueChange={(value) =>
									setDataProviderId(
										value === "none" ? null : value,
									)
								}
							>
								<SelectTrigger id="dataProvider">
									<SelectValue placeholder="Select a data provider..." />
								</SelectTrigger>
								<SelectContent>
									<SelectItem value="none">None</SelectItem>
									{isLoadingProviders ? (
										<SelectItem value="loading" disabled>
											Loading...
										</SelectItem>
									) : (
										(
											dataProviders as Array<{
												id?: string | null;
												name: string;
											}>
										)?.map(
											(provider) =>
												provider.id && (
													<SelectItem
														key={provider.id}
														value={provider.id}
													>
														{provider.name}
													</SelectItem>
												),
										)
									)}
								</SelectContent>
							</Select>
							<p className="text-xs text-muted-foreground">
								Select a data provider to populate entity options
								for organization mappings
							</p>
						</div>

						{/* Config Schema */}
						<div className="space-y-2">
							<div className="flex items-center justify-between">
								<Label>Configuration Schema</Label>
								<Button
									type="button"
									variant="outline"
									size="sm"
									onClick={addConfigField}
								>
									<Plus className="h-4 w-4 mr-1" />
									Add Field
								</Button>
							</div>
							<p className="text-xs text-muted-foreground">
								Define configuration fields required for each
								organization mapping
							</p>

							<div className="space-y-3">
								{configSchema.map((field, index) => (
									<div
										key={index}
										className="flex gap-2 items-start p-3 border rounded-md"
									>
										<div className="flex-1 space-y-2">
											<Input
												placeholder="Field key (e.g., tenant_id)"
												value={field.key}
												onChange={(e) =>
													updateConfigField(index, {
														key: e.target.value,
													})
												}
												required
											/>
											<div className="flex gap-2">
												<Select
													value={field.type}
													onValueChange={(value) =>
														updateConfigField(index, {
															type: value as ConfigSchemaItem["type"],
														})
													}
												>
													<SelectTrigger className="w-32">
														<SelectValue />
													</SelectTrigger>
													<SelectContent>
														<SelectItem value="string">
															String
														</SelectItem>
														<SelectItem value="int">
															Integer
														</SelectItem>
														<SelectItem value="bool">
															Boolean
														</SelectItem>
														<SelectItem value="json">
															JSON
														</SelectItem>
														<SelectItem value="secret">
															Secret
														</SelectItem>
													</SelectContent>
												</Select>
												<label className="flex items-center gap-2 text-sm">
													<input
														type="checkbox"
														checked={field.required}
														onChange={(e) =>
															updateConfigField(index, {
																required: e.target.checked,
															})
														}
														className="rounded"
													/>
													Required
												</label>
											</div>
										</div>
										<Button
											type="button"
											variant="ghost"
											size="icon"
											onClick={() => removeConfigField(index)}
											className="text-destructive"
										>
											<Trash2 className="h-4 w-4" />
										</Button>
									</div>
								))}
							</div>
						</div>
					</div>

					<DialogFooter>
						<Button
							type="button"
							variant="outline"
							onClick={() => onOpenChange(false)}
							disabled={isLoading}
						>
							Cancel
						</Button>
						<Button type="submit" disabled={isLoading}>
							{isLoading ? (
								<>
									<Loader2 className="mr-2 h-4 w-4 animate-spin" />
									{isEditing ? "Updating..." : "Creating..."}
								</>
							) : isEditing ? (
								"Update Integration"
							) : (
								"Create Integration"
							)}
						</Button>
					</DialogFooter>
				</form>
			</DialogContent>
		</Dialog>
	);
}
