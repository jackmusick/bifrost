import { Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
	Dialog,
	DialogContent,
	DialogDescription,
	DialogFooter,
	DialogHeader,
	DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

interface ConfigSchemaField {
	key: string;
	type: string;
	required?: boolean;
}

export interface IntegrationDefaultsDialogProps {
	open: boolean;
	onOpenChange: (open: boolean) => void;
	configSchema: ConfigSchemaField[];
	formValues: Record<string, unknown>;
	onFormValuesChange: (values: Record<string, unknown>) => void;
	onSave: () => void;
	isSaving: boolean;
}

export function IntegrationDefaultsDialog({
	open,
	onOpenChange,
	configSchema,
	formValues,
	onFormValuesChange,
	onSave,
	isSaving,
}: IntegrationDefaultsDialogProps) {
	return (
		<Dialog
			open={open}
			onOpenChange={onOpenChange}
		>
			<DialogContent className="max-w-md">
				<form
					onSubmit={(e) => {
						e.preventDefault();
						onSave();
					}}
				>
					<DialogHeader>
						<DialogTitle>
							Edit Configuration Defaults
						</DialogTitle>
						<DialogDescription>
							Set default values for new organization mappings
						</DialogDescription>
					</DialogHeader>
					<div className="space-y-4 py-4">
						{configSchema?.map((field) => (
							<div key={field.key} className="space-y-2">
								<Label htmlFor={`default-${field.key}`}>
									{field.key}
									{field.required && (
										<span className="text-destructive ml-1">
											*
										</span>
									)}
									<span className="text-muted-foreground text-xs ml-2">
										({field.type})
									</span>
								</Label>
								{field.type === "bool" ? (
									<select
										id={`default-${field.key}`}
										value={String(
											formValues[field.key] ??
												"",
										)}
										onChange={(e) =>
											onFormValuesChange({
												...formValues,
												[field.key]:
													e.target.value ===
													"true",
											})
										}
										className="flex h-8 w-full rounded-2xl border border-transparent bg-input/50 px-2.5 text-sm transition-[color,box-shadow] duration-200 outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/30 disabled:cursor-not-allowed disabled:opacity-50"
									>
										<option value="">
											— Not set —
										</option>
										<option value="true">True</option>
										<option value="false">False</option>
									</select>
								) : (
									<Input
										id={`default-${field.key}`}
										type={
											field.type === "secret"
												? "password"
												: "text"
										}
										placeholder={`Default ${field.key}`}
										value={String(
											formValues[field.key] ??
												"",
										)}
										onChange={(e) =>
											onFormValuesChange({
												...formValues,
												[field.key]:
													field.type === "int"
														? parseInt(
																e.target
																	.value,
															) || ""
														: e.target
																.value,
											})
										}
									/>
								)}
							</div>
						))}
					</div>
					<DialogFooter>
						<Button
							type="button"
							variant="outline"
							onClick={() => onOpenChange(false)}
							disabled={isSaving}
						>
							Cancel
						</Button>
						<Button
							type="submit"
							disabled={isSaving}
						>
							{isSaving ? (
								<>
									<Loader2 className="h-4 w-4 mr-2 animate-spin" />
									Saving...
								</>
							) : (
								"Save Defaults"
							)}
						</Button>
					</DialogFooter>
				</form>
			</DialogContent>
		</Dialog>
	);
}
