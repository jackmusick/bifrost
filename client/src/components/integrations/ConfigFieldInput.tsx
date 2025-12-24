import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { RotateCcw, CheckCircle2 } from "lucide-react";
import type { ConfigSchemaItem } from "@/services/integrations";

interface ConfigFieldInputProps {
	field: ConfigSchemaItem;
	value: unknown;
	onChange: (value: unknown) => void;
	/** If provided, shows a reset button that clears to undefined (uses integration default) */
	onReset?: () => void;
	/** Whether this field has a value different from integration default */
	hasOverride?: boolean;
}

export function ConfigFieldInput({
	field,
	value,
	onChange,
	onReset,
	hasOverride,
}: ConfigFieldInputProps) {
	// Secrets should never be displayed - only allow setting new values
	if (field.type === "secret") {
		const hasSecretValue = Boolean(value);

		return (
			<div className="space-y-2">
				<div className="flex items-center justify-between">
					<Label className="flex items-center gap-2">
						{field.key}
						{field.required && (
							<span className="text-destructive">*</span>
						)}
						{hasSecretValue && (
							<Badge
								variant="secondary"
								className="text-xs font-normal"
							>
								<CheckCircle2 className="h-3 w-3 mr-1" />
								Secret configured
							</Badge>
						)}
					</Label>
					{onReset && hasOverride && (
						<Button
							type="button"
							variant="ghost"
							size="sm"
							onClick={onReset}
							className="h-6 px-2 text-muted-foreground hover:text-foreground"
							title="Reset to integration default"
						>
							<RotateCcw className="h-3 w-3 mr-1" />
							Reset
						</Button>
					)}
				</div>
				{field.description && (
					<p className="text-sm text-muted-foreground">
						{field.description}
					</p>
				)}
				<Input
					type="password"
					value={(value as string) || ""}
					onChange={(e) => onChange(e.target.value)}
					placeholder={
						hasOverride
							? "••••••••  (override set)"
							: hasSecretValue
								? "••••••••"
								: "Enter new value..."
					}
				/>
				{hasOverride && !value && (
					<p className="text-xs text-muted-foreground">
						An override is set. Enter a new value to change it, or
						reset to use the integration default.
					</p>
				)}
			</div>
		);
	}

	const renderInput = () => {
		switch (field.type) {
			case "bool":
				return (
					<Checkbox
						checked={Boolean(value)}
						onCheckedChange={(checked) => onChange(checked)}
					/>
				);

			case "int":
				return (
					<Input
						type="number"
						value={
							value !== undefined && value !== null
								? (value as number)
								: ""
						}
						onChange={(e) => {
							const val = e.target.value;
							onChange(
								val === "" ? undefined : parseInt(val) || 0,
							);
						}}
						placeholder={field.description || field.key}
					/>
				);

			case "json":
				return (
					<textarea
						value={
							value === undefined || value === null
								? ""
								: typeof value === "string"
									? value
									: JSON.stringify(value, null, 2)
						}
						onChange={(e) => {
							const val = e.target.value;
							if (val === "") {
								onChange(undefined);
								return;
							}
							try {
								onChange(JSON.parse(val));
							} catch {
								// Keep as string if invalid JSON
								onChange(val);
							}
						}}
						placeholder={field.description || field.key}
						className="flex min-h-[80px] w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
					/>
				);

			case "string":
			default:
				return (
					<Input
						type="text"
						value={(value as string) ?? ""}
						onChange={(e) => {
							const val = e.target.value;
							onChange(val === "" ? undefined : val);
						}}
						placeholder={field.description || field.key}
					/>
				);
		}
	};

	return (
		<div className="space-y-2">
			<div className="flex items-center justify-between">
				<Label className="flex items-center gap-1">
					{field.key}
					{field.required && (
						<span className="text-destructive">*</span>
					)}
				</Label>
				{onReset && hasOverride && (
					<Button
						type="button"
						variant="ghost"
						size="sm"
						onClick={onReset}
						className="h-6 px-2 text-muted-foreground hover:text-foreground"
						title="Reset to integration default"
					>
						<RotateCcw className="h-3 w-3 mr-1" />
						Reset
					</Button>
				)}
			</div>
			{field.description && (
				<p className="text-sm text-muted-foreground">
					{field.description}
				</p>
			)}
			{renderInput()}
		</div>
	);
}
