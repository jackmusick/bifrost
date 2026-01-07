/**
 * Action Builder Component
 *
 * Visual builder for configuring actions (navigate, workflow, custom, etc.)
 * Used by Button, DataTable row/header actions, and StatCard onClick.
 */

import { useCallback } from "react";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import {
	Select,
	SelectContent,
	SelectItem,
	SelectTrigger,
	SelectValue,
} from "@/components/ui/select";
import { cn } from "@/lib/utils";
import { WorkflowSelector } from "@/components/forms/WorkflowSelector";
import { KeyValueEditor } from "./KeyValueEditor";

/**
 * Action types supported by the builder
 */
export type ActionType =
	| "navigate"
	| "workflow"
	| "custom"
	| "set-variable"
	| "delete";

/**
 * Action configuration object
 */
export interface ActionConfig {
	type: ActionType;
	/** Navigation path (for navigate type) */
	navigateTo?: string;
	/** Workflow ID (for workflow type) */
	workflowId?: string;
	/** Custom action ID (for custom type) */
	customActionId?: string;
	/** Variable name (for set-variable type) */
	variableName?: string;
	/** Variable value (for set-variable type) */
	variableValue?: string;
	/** Parameters to pass to the action */
	actionParams?: Record<string, unknown>;
	/** Confirmation dialog config */
	confirm?: {
		title: string;
		message: string;
		confirmLabel?: string;
		cancelLabel?: string;
	};
}

export interface ActionBuilderProps {
	/** Current action configuration */
	value: ActionConfig;
	/** Callback when action changes */
	onChange: (value: ActionConfig) => void;
	/** Available action types (defaults to all) */
	allowedTypes?: ActionType[];
	/** Whether to show confirmation dialog options */
	showConfirmation?: boolean;
	/** Hint for parameter values (e.g., "Use {{ row.* }} for row data") */
	parameterHint?: string;
	/** Additional CSS classes */
	className?: string;
}

const ACTION_TYPE_LABELS: Record<ActionType, string> = {
	navigate: "Navigate to Page",
	workflow: "Run Workflow",
	custom: "Custom Action",
	"set-variable": "Set Variable",
	delete: "Delete Record",
};

/**
 * Action Builder
 *
 * Provides a visual interface for configuring actions instead of raw JSON.
 *
 * @example
 * <ActionBuilder
 *   value={{ type: "workflow", workflowId: "my-workflow" }}
 *   onChange={(action) => updateAction(action)}
 *   showConfirmation={true}
 *   parameterHint="Use {{ row.id }} for row data"
 * />
 */
export function ActionBuilder({
	value,
	onChange,
	allowedTypes = ["navigate", "workflow", "custom", "set-variable"],
	showConfirmation = false,
	parameterHint,
	className,
}: ActionBuilderProps) {
	const handleTypeChange = useCallback(
		(type: ActionType) => {
			// Reset type-specific fields when type changes
			onChange({
				type,
				actionParams: value.actionParams,
				confirm: value.confirm,
			});
		},
		[value, onChange],
	);

	const handleConfirmToggle = useCallback(
		(enabled: boolean) => {
			if (enabled) {
				onChange({
					...value,
					confirm: {
						title: "Confirm Action",
						message: "Are you sure you want to proceed?",
						confirmLabel: "Confirm",
						cancelLabel: "Cancel",
					},
				});
			} else {
				const { confirm: _, ...rest } = value;
				onChange(rest);
			}
		},
		[value, onChange],
	);

	return (
		<div className={cn("space-y-4", className)}>
			{/* Action Type Selector */}
			<div className="space-y-2">
				<Label className="text-sm font-medium">Action Type</Label>
				<Select value={value.type} onValueChange={handleTypeChange}>
					<SelectTrigger>
						<SelectValue />
					</SelectTrigger>
					<SelectContent>
						{allowedTypes.map((type) => (
							<SelectItem key={type} value={type}>
								{ACTION_TYPE_LABELS[type]}
							</SelectItem>
						))}
					</SelectContent>
				</Select>
			</div>

			{/* Navigate Fields */}
			{value.type === "navigate" && (
				<div className="space-y-2">
					<Label className="text-sm font-medium">Navigate To</Label>
					<Input
						value={value.navigateTo ?? ""}
						onChange={(e) =>
							onChange({ ...value, navigateTo: e.target.value })
						}
						placeholder="/page/path or {{ expression }}"
					/>
					<p className="text-xs text-muted-foreground">
						Path to navigate. Supports expressions like{" "}
						{"{{ row.id }}"}
					</p>
				</div>
			)}

			{/* Workflow Fields */}
			{value.type === "workflow" && (
				<div className="space-y-4">
					<div className="space-y-2">
						<Label className="text-sm font-medium">Workflow</Label>
						<WorkflowSelector
							value={value.workflowId}
							onChange={(workflowId) =>
								onChange({ ...value, workflowId })
							}
							placeholder="Select a workflow"
						/>
					</div>

					<div className="space-y-2">
						<Label className="text-sm font-medium">
							Parameters
						</Label>
						<KeyValueEditor
							value={value.actionParams ?? {}}
							onChange={(actionParams) =>
								onChange({ ...value, actionParams })
							}
							hint={parameterHint}
						/>
					</div>
				</div>
			)}

			{/* Custom Action Fields */}
			{value.type === "custom" && (
				<div className="space-y-4">
					<div className="space-y-2">
						<Label className="text-sm font-medium">Action ID</Label>
						<Input
							value={value.customActionId ?? ""}
							onChange={(e) =>
								onChange({
									...value,
									customActionId: e.target.value,
								})
							}
							placeholder="my-custom-action"
						/>
					</div>

					<div className="space-y-2">
						<Label className="text-sm font-medium">
							Parameters
						</Label>
						<KeyValueEditor
							value={value.actionParams ?? {}}
							onChange={(actionParams) =>
								onChange({ ...value, actionParams })
							}
							hint={parameterHint}
						/>
					</div>
				</div>
			)}

			{/* Set Variable Fields */}
			{value.type === "set-variable" && (
				<div className="space-y-4">
					<div className="space-y-2">
						<Label className="text-sm font-medium">
							Variable Name
						</Label>
						<Input
							value={value.variableName ?? ""}
							onChange={(e) =>
								onChange({
									...value,
									variableName: e.target.value,
								})
							}
							placeholder="selectedItem"
						/>
						<p className="text-xs text-muted-foreground">
							Access via {"{{ variables.variableName }}"}
						</p>
					</div>

					<div className="space-y-2">
						<Label className="text-sm font-medium">Value</Label>
						<Input
							value={value.variableValue ?? ""}
							onChange={(e) =>
								onChange({
									...value,
									variableValue: e.target.value,
								})
							}
							placeholder="{{ row }} or static value"
						/>
					</div>
				</div>
			)}

			{/* Delete Action - typically just needs confirmation */}
			{value.type === "delete" && (
				<div className="rounded-md bg-destructive/10 border border-destructive/20 p-3">
					<p className="text-sm text-destructive">
						This action will delete the record. Consider enabling
						confirmation below.
					</p>
				</div>
			)}

			{/* Confirmation Dialog Toggle */}
			{showConfirmation && (
				<div className="space-y-3 pt-2 border-t">
					<div className="flex items-center justify-between">
						<div>
							<Label className="text-sm font-medium">
								Require Confirmation
							</Label>
							<p className="text-xs text-muted-foreground">
								Show a dialog before executing
							</p>
						</div>
						<Switch
							checked={!!value.confirm}
							onCheckedChange={handleConfirmToggle}
						/>
					</div>

					{value.confirm && (
						<div className="space-y-3 pl-4 border-l-2 border-muted">
							<div className="space-y-2">
								<Label className="text-sm">Dialog Title</Label>
								<Input
									value={value.confirm.title}
									onChange={(e) =>
										onChange({
											...value,
											confirm: {
												...value.confirm!,
												title: e.target.value,
											},
										})
									}
								/>
							</div>

							<div className="space-y-2">
								<Label className="text-sm">Message</Label>
								<Textarea
									value={value.confirm.message}
									onChange={(e) =>
										onChange({
											...value,
											confirm: {
												...value.confirm!,
												message: e.target.value,
											},
										})
									}
									rows={2}
								/>
							</div>

							<div className="grid grid-cols-2 gap-2">
								<div className="space-y-2">
									<Label className="text-sm">
										Confirm Button
									</Label>
									<Input
										value={
											value.confirm.confirmLabel ??
											"Confirm"
										}
										onChange={(e) =>
											onChange({
												...value,
												confirm: {
													...value.confirm!,
													confirmLabel:
														e.target.value,
												},
											})
										}
									/>
								</div>
								<div className="space-y-2">
									<Label className="text-sm">
										Cancel Button
									</Label>
									<Input
										value={
											value.confirm.cancelLabel ??
											"Cancel"
										}
										onChange={(e) =>
											onChange({
												...value,
												confirm: {
													...value.confirm!,
													cancelLabel: e.target.value,
												},
											})
										}
									/>
								</div>
							</div>
						</div>
					)}
				</div>
			)}
		</div>
	);
}

export default ActionBuilder;
