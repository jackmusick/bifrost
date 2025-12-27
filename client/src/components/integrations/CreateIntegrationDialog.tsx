import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import {
	Dialog,
	DialogContent,
	DialogDescription,
	DialogFooter,
	DialogHeader,
	DialogTitle,
} from "@/components/ui/dialog";
import {
	AlertDialog,
	AlertDialogAction,
	AlertDialogCancel,
	AlertDialogContent,
	AlertDialogDescription,
	AlertDialogFooter,
	AlertDialogHeader,
	AlertDialogTitle,
} from "@/components/ui/alert-dialog";
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
import { OrganizationSelect } from "@/components/forms/OrganizationSelect";
import { useAuth } from "@/contexts/AuthContext";

// Extended type to include organization_id (supported by backend, pending type regeneration)
type IntegrationDetailWithOrg = IntegrationDetail & {
	organization_id?: string | null;
};

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

// Inner component that gets remounted when the dialog opens or when editing a different integration
function CreateIntegrationDialogContent({
	onOpenChange,
	editIntegrationId,
	initialData,
}: Omit<CreateIntegrationDialogProps, "open">) {
	const queryClient = useQueryClient();
	const { isPlatformAdmin } = useAuth();

	// Only fetch if we don't have initialData and we're editing
	const { data: fetchedIntegration } = useIntegration(
		initialData ? "" : editIntegrationId || "",
	);

	// Use initialData if provided, otherwise use fetched data
	// Cast to extended type that includes organization_id
	const existingIntegration = (initialData ||
		fetchedIntegration) as IntegrationDetailWithOrg | undefined;

	// Fetch available data providers
	const { data: dataProviders, isLoading: isLoadingProviders } =
		useDataProviders();

	const createMutation = useCreateIntegration();
	const updateMutation = useUpdateIntegration();

	const isEditing = Boolean(editIntegrationId);
	const isLoading = createMutation.isPending || updateMutation.isPending;

	// Initialize state from existing integration (or empty for new)
	const [organizationId, setOrganizationId] = useState<string | null | undefined>(() => {
		return existingIntegration?.organization_id ?? null;
	});
	const [name, setName] = useState(() => {
		return existingIntegration?.name || "";
	});
	const [description, setDescription] = useState(() => {
		const integrationWithDesc =
			existingIntegration as typeof existingIntegration & {
				description?: string;
			};
		return integrationWithDesc?.description || "";
	});
	const [dataProviderId, setDataProviderId] = useState<string | null>(() => {
		return existingIntegration?.list_entities_data_provider_id || null;
	});
	const [configSchema, setConfigSchema] = useState<ConfigSchemaItem[]>(() => {
		return existingIntegration?.config_schema || [];
	});
	const [defaultEntityId, setDefaultEntityId] = useState<string>(() => {
		return existingIntegration?.default_entity_id || "";
	});

	// Track original values for confirmation dialogs
	const originalName = existingIntegration?.name || "";
	const originalDataProviderId =
		existingIntegration?.list_entities_data_provider_id || null;
	const originalConfigSchemaKeys = new Set(
		existingIntegration?.config_schema?.map((f) => f.key) || [],
	);

	// Confirmation dialog states
	const [showDataProviderConfirm, setShowDataProviderConfirm] =
		useState(false);
	const [showNameChangeConfirm, setShowNameChangeConfirm] = useState(false);
	const [showConfigFieldRemovalConfirm, setShowConfigFieldRemovalConfirm] =
		useState(false);
	const [removedFieldNames, setRemovedFieldNames] = useState<string[]>([]);

	const handleSubmit = async (e: React.FormEvent) => {
		e.preventDefault();

		if (!name.trim()) {
			toast.error("Integration name is required");
			return;
		}

		// In edit mode, check for confirmations needed
		if (isEditing) {
			// Check 1: Name change confirmation
			if (name !== originalName) {
				setShowNameChangeConfirm(true);
				return;
			}

			// Check 2: Data provider swap confirmation
			if (dataProviderId !== originalDataProviderId) {
				// Count affected mappings (those with entity_id values)
				const affectedMappingsCount =
					initialData?.mappings?.filter((m) => m.entity_id).length ||
					0;
				if (affectedMappingsCount > 0) {
					setShowDataProviderConfirm(true);
					return;
				}
			}

			// Check 3: Config field removal warning
			const currentKeys = new Set(
				configSchema.map((f) => f.key).filter((k) => k.trim()),
			);
			const removedKeys = Array.from(originalConfigSchemaKeys).filter(
				(k) => !currentKeys.has(k),
			);
			if (removedKeys.length > 0) {
				setRemovedFieldNames(removedKeys);
				setShowConfigFieldRemovalConfirm(true);
				return;
			}
		}

		// Proceed with save
		await performSave();
	};

	const performSave = async () => {
		try {
			if (isEditing && editIntegrationId) {
				await updateMutation.mutateAsync({
					params: { path: { integration_id: editIntegrationId } },
					body: {
						name,
						list_entities_data_provider_id:
							dataProviderId || undefined,
						config_schema:
							configSchema.length > 0 ? configSchema : undefined,
						default_entity_id: defaultEntityId || undefined,
					},
				});
				toast.success("Integration updated successfully");
			} else {
				await createMutation.mutateAsync({
					body: {
						name,
						config_schema:
							configSchema.length > 0 ? configSchema : undefined,
						default_entity_id: defaultEntityId || undefined,
						// organization_id is supported by backend, pending type regeneration
						...(organizationId && { organization_id: organizationId }),
					} as Parameters<typeof createMutation.mutateAsync>[0]["body"],
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
		<>
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
					{/* Organization (platform admins only) */}
					{isPlatformAdmin && (
						<div className="space-y-2">
							<Label htmlFor="organization">Organization</Label>
							<OrganizationSelect
								value={organizationId}
								onChange={setOrganizationId}
								showGlobal={true}
								disabled={isEditing}
							/>
							<p className="text-xs text-muted-foreground">
								{isEditing
									? "Organization cannot be changed after creation"
									: "Select Global for platform-wide integration or choose a specific organization"}
							</p>
						</div>
					)}

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

					{/* Default Entity ID */}
					<div className="space-y-2">
						<Label htmlFor="defaultEntityId">
							Default Entity ID
						</Label>
						<Input
							id="defaultEntityId"
							placeholder="e.g., common"
							value={defaultEntityId}
							onChange={(e) => setDefaultEntityId(e.target.value)}
						/>
						<p className="text-xs text-muted-foreground">
							Default value for entity_id in URL templates (used
							when org mapping doesn't specify one)
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
														updateConfigField(
															index,
															{
																required:
																	e.target
																		.checked,
															},
														)
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

			{/* Data Provider Change Confirmation */}
			<AlertDialog
				open={showDataProviderConfirm}
				onOpenChange={setShowDataProviderConfirm}
			>
				<AlertDialogContent>
					<AlertDialogHeader>
						<AlertDialogTitle>
							Change Data Provider?
						</AlertDialogTitle>
						<AlertDialogDescription>
							Changing the data provider may orphan{" "}
							{initialData?.mappings?.filter((m) => m.entity_id)
								.length || 0}{" "}
							existing entity mapping(s). The entity IDs will be
							preserved but may not match entities from the new
							provider.
						</AlertDialogDescription>
					</AlertDialogHeader>
					<AlertDialogFooter>
						<AlertDialogCancel>Cancel</AlertDialogCancel>
						<AlertDialogAction
							onClick={() => {
								setShowDataProviderConfirm(false);
								performSave();
							}}
						>
							Keep Mappings
						</AlertDialogAction>
					</AlertDialogFooter>
				</AlertDialogContent>
			</AlertDialog>

			{/* Name Change Confirmation */}
			<AlertDialog
				open={showNameChangeConfirm}
				onOpenChange={setShowNameChangeConfirm}
			>
				<AlertDialogContent>
					<AlertDialogHeader>
						<AlertDialogTitle>Rename Integration?</AlertDialogTitle>
						<AlertDialogDescription>
							Renaming this integration will break any SDK calls
							using the name '{originalName}'. Workflows and
							scripts will need to be updated to use '{name}'.
						</AlertDialogDescription>
					</AlertDialogHeader>
					<AlertDialogFooter>
						<AlertDialogCancel>Cancel</AlertDialogCancel>
						<AlertDialogAction
							onClick={() => {
								setShowNameChangeConfirm(false);
								performSave();
							}}
						>
							Rename Anyway
						</AlertDialogAction>
					</AlertDialogFooter>
				</AlertDialogContent>
			</AlertDialog>

			{/* Config Field Removal Confirmation */}
			<AlertDialog
				open={showConfigFieldRemovalConfirm}
				onOpenChange={setShowConfigFieldRemovalConfirm}
			>
				<AlertDialogContent>
					<AlertDialogHeader>
						<AlertDialogTitle>
							Remove Configuration Fields?
						</AlertDialogTitle>
						<AlertDialogDescription>
							Removing config field(s) will delete all stored
							values for: {removedFieldNames.join(", ")}. This
							cannot be undone.
						</AlertDialogDescription>
					</AlertDialogHeader>
					<AlertDialogFooter>
						<AlertDialogCancel>Cancel</AlertDialogCancel>
						<AlertDialogAction
							onClick={() => {
								setShowConfigFieldRemovalConfirm(false);
								performSave();
							}}
							className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
						>
							Delete Fields
						</AlertDialogAction>
					</AlertDialogFooter>
				</AlertDialogContent>
			</AlertDialog>
		</>
	);
}

// Outer component that uses key to remount content when dialog opens or integration changes
export function CreateIntegrationDialog({
	open,
	onOpenChange,
	editIntegrationId,
	initialData,
}: CreateIntegrationDialogProps) {
	// Create a stable key that changes when dialog opens or when editing a different integration
	// This forces a remount of the inner component, resetting all form state
	const dialogKey = open ? `open-${editIntegrationId || "new"}` : "closed";

	return (
		<Dialog open={open} onOpenChange={onOpenChange}>
			<DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
				{open && (
					<CreateIntegrationDialogContent
						key={dialogKey}
						onOpenChange={onOpenChange}
						editIntegrationId={editIntegrationId}
						initialData={initialData}
					/>
				)}
			</DialogContent>
		</Dialog>
	);
}
