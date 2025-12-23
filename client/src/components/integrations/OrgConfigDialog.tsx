import { useState } from "react";
import { Button } from "@/components/ui/button";
import {
	Dialog,
	DialogContent,
	DialogDescription,
	DialogFooter,
	DialogHeader,
	DialogTitle,
} from "@/components/ui/dialog";
import { Loader2 } from "lucide-react";
import { ConfigFieldInput } from "./ConfigFieldInput";
import type { ConfigSchemaItem } from "@/services/integrations";

interface OrgConfigDialogProps {
	open: boolean;
	onOpenChange: (open: boolean) => void;
	orgId: string;
	orgName: string;
	configSchema: ConfigSchemaItem[];
	/** The org's current config overrides (only keys that have explicit overrides) */
	currentConfig: Record<string, unknown>;
	onSave: (config: Record<string, unknown>) => Promise<void>;
}

function OrgConfigDialogContent({
	orgName,
	configSchema,
	currentConfig,
	onSave,
	onOpenChange,
}: Omit<OrgConfigDialogProps, "open" | "orgId">) {
	// Track which keys have overrides (start with what's in currentConfig)
	// We use a separate Set to track this because we need to distinguish
	// between "value is undefined because no override" vs "value is explicitly set to empty"
	const [overrideKeys, setOverrideKeys] = useState<Set<string>>(
		() => new Set(Object.keys(currentConfig)),
	);

	// Form values - only contains values for fields that have overrides
	const [formValues, setFormValues] = useState<Record<string, unknown>>(
		() => ({ ...currentConfig }),
	);
	const [isSaving, setIsSaving] = useState(false);

	const handleFieldChange = (key: string, value: unknown) => {
		setFormValues((prev) => ({ ...prev, [key]: value }));
		// Mark as having an override when user types
		if (value !== undefined && value !== null && value !== "") {
			setOverrideKeys((prev) => new Set(prev).add(key));
		}
	};

	const handleReset = (key: string) => {
		// Remove the override - this will cause the integration default to be used
		setFormValues((prev) => {
			const next = { ...prev };
			delete next[key];
			return next;
		});
		setOverrideKeys((prev) => {
			const next = new Set(prev);
			next.delete(key);
			return next;
		});
	};

	const handleSubmit = async (e: React.FormEvent) => {
		e.preventDefault();
		setIsSaving(true);
		try {
			// Build config to save:
			// - Keys with non-empty values: send the value
			// - Keys that were in currentConfig but now empty/removed: send null to delete
			const configToSave: Record<string, unknown> = {};

			// Check all keys that were originally set OR are in overrideKeys
			const allKeys = new Set([
				...Object.keys(currentConfig),
				...overrideKeys,
			]);

			for (const key of allKeys) {
				const value = formValues[key];
				const hasValue = value !== undefined && value !== null && value !== "";

				if (hasValue) {
					// Has a value - send it
					configToSave[key] = value;
				} else if (key in currentConfig) {
					// Was previously set but now empty - send null to delete
					configToSave[key] = null;
				}
				// If not in currentConfig and no value, skip (nothing to do)
			}

			await onSave(configToSave);
			onOpenChange(false);
		} finally {
			setIsSaving(false);
		}
	};

	const handleCancel = () => {
		onOpenChange(false);
	};

	return (
		<form onSubmit={handleSubmit}>
			<DialogHeader>
				<DialogTitle>Configure {orgName}</DialogTitle>
				<DialogDescription>
					Set organization-specific configuration overrides. Empty fields use
					the integration default.
				</DialogDescription>
			</DialogHeader>

			<div className="space-y-4 py-4">
				{configSchema.length > 0 ? (
					configSchema.map((field) => (
						<ConfigFieldInput
							key={field.key}
							field={field}
							value={formValues[field.key]}
							onChange={(value) => handleFieldChange(field.key, value)}
							onReset={() => handleReset(field.key)}
							hasOverride={overrideKeys.has(field.key)}
						/>
					))
				) : (
					<p className="text-sm text-muted-foreground text-center py-4">
						No configuration fields defined
					</p>
				)}
			</div>

			<DialogFooter>
				<Button
					variant="outline"
					onClick={handleCancel}
					type="button"
					disabled={isSaving}
				>
					Cancel
				</Button>
				<Button type="submit" disabled={isSaving}>
					{isSaving ? (
						<>
							<Loader2 className="mr-2 h-4 w-4 animate-spin" />
							Saving...
						</>
					) : (
						"Save"
					)}
				</Button>
			</DialogFooter>
		</form>
	);
}

export function OrgConfigDialog({
	open,
	onOpenChange,
	orgId,
	orgName,
	configSchema,
	currentConfig,
	onSave,
}: OrgConfigDialogProps) {
	return (
		<Dialog open={open} onOpenChange={onOpenChange}>
			<DialogContent className="max-w-2xl max-h-[80vh] overflow-y-auto">
				{/* Key resets form state when switching between orgs */}
				<OrgConfigDialogContent
					key={orgId}
					orgName={orgName}
					configSchema={configSchema}
					currentConfig={currentConfig}
					onSave={onSave}
					onOpenChange={onOpenChange}
				/>
			</DialogContent>
		</Dialog>
	);
}
