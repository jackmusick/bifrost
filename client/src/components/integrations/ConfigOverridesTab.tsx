import { useState, useMemo } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Checkbox } from "@/components/ui/checkbox";
import {
	DataTable,
	DataTableBody,
	DataTableCell,
	DataTableHead,
	DataTableHeader,
	DataTableRow,
} from "@/components/ui/data-table";
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
import { Settings, Loader2, Check, X, Trash2 } from "lucide-react";
import { toast } from "sonner";
import type {
	ConfigSchemaItem,
	IntegrationMapping,
} from "@/services/integrations";
import { useUpdateMapping } from "@/services/integrations";

interface OrgWithMapping {
	id: string;
	name: string;
	mapping?: IntegrationMapping;
	formData: {
		organization_id: string;
		entity_id: string;
		entity_name: string;
		oauth_token_id?: string;
		config: Record<string, unknown>;
	};
	isDirty: boolean;
}

interface ConfigRow {
	orgId: string;
	orgName: string;
	mappingId: string | null;
	configKey: string;
	value: unknown;
	hasOverride: boolean;
	fieldType: ConfigSchemaItem["type"];
	fieldSchema: ConfigSchemaItem;
	// For saving - we need full mapping data
	mapping: IntegrationMapping | undefined;
	currentConfig: Record<string, unknown>;
}

interface ConfigOverridesTabProps {
	orgsWithMappings: OrgWithMapping[];
	configSchema: ConfigSchemaItem[];
	integrationId: string;
}

interface EditingCell {
	rowKey: string; // orgId:configKey
	value: unknown;
}

export function ConfigOverridesTab({
	orgsWithMappings,
	configSchema,
	integrationId,
}: ConfigOverridesTabProps) {
	const [editingCell, setEditingCell] = useState<EditingCell | null>(null);
	const [savingRows, setSavingRows] = useState<Set<string>>(new Set());
	const [deleteConfirm, setDeleteConfirm] = useState<ConfigRow | null>(null);

	const updateMutation = useUpdateMapping();

	// Filter out secret fields - they should never be shown in this view
	const visibleSchema = useMemo(
		() => configSchema.filter((field) => field.type !== "secret"),
		[configSchema],
	);

	// Flatten data: one row per org + config key that HAS an override (excluding secrets)
	const rows = useMemo((): ConfigRow[] => {
		const result: ConfigRow[] = [];

		// Only include orgs that have mappings
		const orgsWithMappingsOnly = orgsWithMappings.filter((org) => org.mapping);

		for (const org of orgsWithMappingsOnly) {
			for (const field of visibleSchema) {
				const currentValue = org.mapping?.config?.[field.key];
				// Only include rows that have an actual override
				const hasOverride =
					currentValue !== undefined && currentValue !== null;

				if (hasOverride) {
					result.push({
						orgId: org.id,
						orgName: org.name,
						mappingId: org.mapping?.id || null,
						configKey: field.key,
						value: currentValue,
						hasOverride: true,
						fieldType: field.type,
						fieldSchema: field,
						mapping: org.mapping,
						currentConfig: org.mapping?.config || {},
					});
				}
			}
		}

		return result;
	}, [orgsWithMappings, visibleSchema]);

	const getRowKey = (row: ConfigRow) => `${row.orgId}:${row.configKey}`;

	const handleCellClick = (row: ConfigRow) => {
		if (savingRows.has(getRowKey(row))) return;
		// Start with current value or empty - never show defaults
		setEditingCell({
			rowKey: getRowKey(row),
			value: row.value ?? "",
		});
	};

	const handleSave = async (row: ConfigRow, newValue: unknown) => {
		if (!row.mappingId || !row.mapping) {
			toast.error("No mapping exists - create a mapping first");
			return;
		}

		const rowKey = getRowKey(row);
		setSavingRows((prev) => new Set(prev).add(rowKey));

		try {
			// Build updated config - merge current with new value
			const updatedConfig = { ...row.currentConfig };

			// If value is empty, remove the key (fall back to integration default)
			if (newValue === "" || newValue === null || newValue === undefined) {
				delete updatedConfig[row.configKey];
			} else {
				updatedConfig[row.configKey] = newValue;
			}

			await updateMutation.mutateAsync({
				params: {
					path: {
						integration_id: integrationId,
						mapping_id: row.mappingId,
					},
				},
				body: {
					entity_id: row.mapping.entity_id,
					entity_name: row.mapping.entity_name || undefined,
					oauth_token_id: row.mapping.oauth_token_id || undefined,
					config:
						Object.keys(updatedConfig).length > 0 ? updatedConfig : undefined,
				},
			});

			setEditingCell(null);
			// Query invalidation in useUpdateMapping handles refresh
		} catch (error) {
			console.error("Failed to save config:", error);
			toast.error(`Failed to save ${row.configKey} for ${row.orgName}`);
		} finally {
			setSavingRows((prev) => {
				const next = new Set(prev);
				next.delete(rowKey);
				return next;
			});
		}
	};

	const handleDeleteClick = (row: ConfigRow) => {
		// Show confirmation dialog
		setDeleteConfirm(row);
	};

	const handleDeleteConfirm = async () => {
		const row = deleteConfirm;
		if (!row) return;

		// Delete the override by sending null for the key
		if (!row.mappingId || !row.mapping) {
			toast.error("No mapping exists");
			setDeleteConfirm(null);
			return;
		}

		const rowKey = getRowKey(row);
		setSavingRows((prev) => new Set(prev).add(rowKey));
		setDeleteConfirm(null);

		try {
			// Send null for the key to delete it from the database
			const configToSave = {
				...row.currentConfig,
				[row.configKey]: null, // This tells backend to delete this key
			};

			await updateMutation.mutateAsync({
				params: {
					path: {
						integration_id: integrationId,
						mapping_id: row.mappingId,
					},
				},
				body: {
					entity_id: row.mapping.entity_id,
					entity_name: row.mapping.entity_name || undefined,
					oauth_token_id: row.mapping.oauth_token_id || undefined,
					config: configToSave,
				},
			});

			toast.success(`Removed ${row.configKey} override for ${row.orgName}`);
			// Query invalidation in useUpdateMapping handles refresh
		} catch (error) {
			console.error("Failed to delete config:", error);
			toast.error(`Failed to delete ${row.configKey} for ${row.orgName}`);
		} finally {
			setSavingRows((prev) => {
				const next = new Set(prev);
				next.delete(rowKey);
				return next;
			});
		}
	};

	const handleCancel = () => {
		setEditingCell(null);
	};

	const handleKeyDown = (
		e: React.KeyboardEvent,
		row: ConfigRow,
		value: unknown,
	) => {
		if (e.key === "Enter" && !e.shiftKey) {
			e.preventDefault();
			handleSave(row, value);
		} else if (e.key === "Escape") {
			handleCancel();
		}
	};

	const formatDisplayValue = (
		value: unknown,
		fieldType: ConfigSchemaItem["type"],
		hasOverride: boolean,
	): string => {
		// If no override, show placeholder
		if (!hasOverride) {
			return "—";
		}
		if (value === undefined || value === null || value === "") {
			return "—";
		}
		if (fieldType === "bool") {
			return value ? "True" : "False";
		}
		if (fieldType === "json") {
			return typeof value === "string" ? value : JSON.stringify(value);
		}
		return String(value);
	};

	const renderEditInput = (row: ConfigRow, currentValue: unknown) => {
		const rowKey = getRowKey(row);
		const isSaving = savingRows.has(rowKey);

		switch (row.fieldType) {
			case "bool":
				return (
					<div className="flex items-center gap-2">
						<Checkbox
							checked={Boolean(currentValue)}
							onCheckedChange={(checked) => {
								setEditingCell({ rowKey, value: checked });
							}}
							disabled={isSaving}
							autoFocus
						/>
						<span className="text-sm">
							{currentValue ? "True" : "False"}
						</span>
						<div className="flex gap-1 ml-auto">
							<button
								type="button"
								onClick={() => handleSave(row, currentValue)}
								disabled={isSaving}
								className="p-1 rounded hover:bg-green-100 dark:hover:bg-green-900 text-green-600"
							>
								{isSaving ? (
									<Loader2 className="h-4 w-4 animate-spin" />
								) : (
									<Check className="h-4 w-4" />
								)}
							</button>
							<button
								type="button"
								onClick={handleCancel}
								disabled={isSaving}
								className="p-1 rounded hover:bg-red-100 dark:hover:bg-red-900 text-red-600"
							>
								<X className="h-4 w-4" />
							</button>
						</div>
					</div>
				);

			case "int":
				return (
					<div className="flex items-center gap-2">
						<Input
							type="number"
							value={
								currentValue !== undefined && currentValue !== null
									? (currentValue as number)
									: ""
							}
							onChange={(e) => {
								const val = e.target.value;
								setEditingCell({
									rowKey,
									value: val === "" ? undefined : parseInt(val) || 0,
								});
							}}
							onKeyDown={(e) => handleKeyDown(e, row, currentValue)}
							onBlur={() => handleSave(row, currentValue)}
							disabled={isSaving}
							className="h-8 w-24"
							autoFocus
						/>
						{isSaving && <Loader2 className="h-4 w-4 animate-spin" />}
					</div>
				);

			case "json":
				return (
					<div className="flex flex-col gap-2">
						<textarea
							value={
								currentValue === undefined || currentValue === null
									? ""
									: typeof currentValue === "string"
										? currentValue
										: JSON.stringify(currentValue, null, 2)
							}
							onChange={(e) => {
								const val = e.target.value;
								if (val === "") {
									setEditingCell({ rowKey, value: undefined });
									return;
								}
								try {
									setEditingCell({
										rowKey,
										value: JSON.parse(val),
									});
								} catch {
									setEditingCell({ rowKey, value: val });
								}
							}}
							onKeyDown={(e) => {
								if (e.key === "Escape") handleCancel();
							}}
							disabled={isSaving}
							className="min-h-[60px] w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
							autoFocus
						/>
						<div className="flex gap-1 justify-end">
							<button
								type="button"
								onClick={() => handleSave(row, currentValue)}
								disabled={isSaving}
								className="p-1 rounded hover:bg-green-100 dark:hover:bg-green-900 text-green-600"
							>
								{isSaving ? (
									<Loader2 className="h-4 w-4 animate-spin" />
								) : (
									<Check className="h-4 w-4" />
								)}
							</button>
							<button
								type="button"
								onClick={handleCancel}
								disabled={isSaving}
								className="p-1 rounded hover:bg-red-100 dark:hover:bg-red-900 text-red-600"
							>
								<X className="h-4 w-4" />
							</button>
						</div>
					</div>
				);

			case "string":
			default:
				return (
					<div className="flex items-center gap-2">
						<Input
							type="text"
							value={(currentValue as string) ?? ""}
							onChange={(e) => {
								const val = e.target.value;
								setEditingCell({
									rowKey,
									value: val === "" ? undefined : val,
								});
							}}
							onKeyDown={(e) => handleKeyDown(e, row, currentValue)}
							onBlur={() => handleSave(row, currentValue)}
							disabled={isSaving}
							className="h-8"
							autoFocus
						/>
						{isSaving && <Loader2 className="h-4 w-4 animate-spin" />}
					</div>
				);
		}
	};

	if (visibleSchema.length === 0) {
		return (
			<div className="flex flex-col items-center justify-center py-12 text-center">
				<Settings className="h-12 w-12 text-muted-foreground" />
				<h3 className="mt-4 text-lg font-semibold">
					No configuration schema
				</h3>
				<p className="mt-2 text-sm text-muted-foreground max-w-md">
					Add configuration fields to the integration to enable per-org
					configuration.
				</p>
			</div>
		);
	}

	if (rows.length === 0) {
		return (
			<div className="flex flex-col items-center justify-center py-12 text-center">
				<Settings className="h-12 w-12 text-muted-foreground" />
				<h3 className="mt-4 text-lg font-semibold">
					No configuration overrides
				</h3>
				<p className="mt-2 text-sm text-muted-foreground max-w-md">
					All organizations are using integration defaults. Use the Configure
					button in the Mappings tab to set organization-specific values.
				</p>
			</div>
		);
	}

	return (
		<div className="space-y-4">
			<p className="text-sm text-muted-foreground">
				Organization-specific configuration overrides. Click to edit, or delete
				to revert to integration default.
			</p>
			<div className="rounded-md border overflow-x-auto">
				<DataTable>
					<DataTableHeader>
						<DataTableRow>
							<DataTableHead className="w-48">Organization</DataTableHead>
							<DataTableHead className="w-48">Config Key</DataTableHead>
							<DataTableHead>Value</DataTableHead>
							<DataTableHead className="w-16"></DataTableHead>
						</DataTableRow>
					</DataTableHeader>
					<DataTableBody>
						{rows.map((row) => {
							const rowKey = getRowKey(row);
							const isEditing = editingCell?.rowKey === rowKey;
							const isSaving = savingRows.has(rowKey);

							return (
								<DataTableRow key={rowKey}>
									<DataTableCell className="font-medium">
										{row.orgName}
									</DataTableCell>
									<DataTableCell>
										<div className="flex items-center gap-2">
											<span className="font-mono text-sm">
												{row.configKey}
											</span>
											<span className="text-muted-foreground text-xs">
												({row.fieldType})
											</span>
										</div>
									</DataTableCell>
									<DataTableCell
										className={`cursor-pointer transition-colors ${
											isEditing ? "" : "hover:bg-muted/50"
										} ${isSaving ? "opacity-70" : ""}`}
										onClick={() => !isEditing && handleCellClick(row)}
									>
										{isEditing ? (
											renderEditInput(row, editingCell.value)
										) : (
											<span>
												{formatDisplayValue(
													row.value,
													row.fieldType,
													row.hasOverride,
												)}
											</span>
										)}
									</DataTableCell>
									<DataTableCell>
										{!isEditing && (
											<Button
												variant="ghost"
												size="sm"
												onClick={() => handleDeleteClick(row)}
												disabled={isSaving}
												className="h-7 w-7 p-0 text-destructive hover:text-destructive"
												title="Delete override (revert to default)"
											>
												{isSaving ? (
													<Loader2 className="h-3 w-3 animate-spin" />
												) : (
													<Trash2 className="h-3 w-3" />
												)}
											</Button>
										)}
									</DataTableCell>
								</DataTableRow>
							);
						})}
					</DataTableBody>
				</DataTable>
			</div>

			{/* Delete Confirmation Dialog */}
			<AlertDialog
				open={deleteConfirm !== null}
				onOpenChange={(open) => !open && setDeleteConfirm(null)}
			>
				<AlertDialogContent>
					<AlertDialogHeader>
						<AlertDialogTitle>Delete Configuration Override</AlertDialogTitle>
						<AlertDialogDescription>
							Are you sure you want to delete the{" "}
							<span className="font-mono font-semibold">
								{deleteConfirm?.configKey}
							</span>{" "}
							override for {deleteConfirm?.orgName}? This will revert to the
							integration default value.
						</AlertDialogDescription>
					</AlertDialogHeader>
					<AlertDialogFooter>
						<AlertDialogCancel>Cancel</AlertDialogCancel>
						<AlertDialogAction
							onClick={handleDeleteConfirm}
							className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
						>
							Delete
						</AlertDialogAction>
					</AlertDialogFooter>
				</AlertDialogContent>
			</AlertDialog>
		</div>
	);
}
