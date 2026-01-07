/**
 * Table Action Builder Component
 *
 * Visual editor for DataTable row and header actions.
 * Supports multiple actions with add/remove and full action configuration.
 */

import { useCallback } from "react";
import { Plus, Trash2, GripVertical } from "lucide-react";
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
import {
	Accordion,
	AccordionContent,
	AccordionItem,
	AccordionTrigger,
} from "@/components/ui/accordion";
import { cn } from "@/lib/utils";
import { WorkflowSelector } from "@/components/forms/WorkflowSelector";
import { WorkflowParameterEditor } from "./WorkflowParameterEditor";
import type { TableAction } from "@/lib/app-builder-types";

export interface TableActionBuilderProps {
	/** Current actions */
	value: TableAction[];
	/** Callback when actions change */
	onChange: (value: TableAction[]) => void;
	/** Whether this is for row actions (enables {{ row.* }} hints) */
	isRowAction?: boolean;
	/** Additional CSS classes */
	className?: string;
}

const ACTION_TYPES = [
	{ value: "navigate", label: "Navigate" },
	{ value: "workflow", label: "Run Workflow" },
	{ value: "set-variable", label: "Set Variable" },
	{ value: "delete", label: "Delete" },
];

const BUTTON_VARIANTS = [
	{ value: "default", label: "Default" },
	{ value: "destructive", label: "Destructive" },
	{ value: "outline", label: "Outline" },
	{ value: "ghost", label: "Ghost" },
];

/**
 * Table Action Builder
 *
 * Visual interface for configuring DataTable row and header actions.
 *
 * @example
 * <TableActionBuilder
 *   value={props.rowActions ?? []}
 *   onChange={(actions) => onChange({ props: { ...props, rowActions: actions } })}
 *   isRowAction={true}
 * />
 */
export function TableActionBuilder({
	value,
	onChange,
	isRowAction = false,
	className,
}: TableActionBuilderProps) {
	const handleAddAction = useCallback(() => {
		const newAction: TableAction = {
			label: "Action",
			variant: "default",
			onClick: {
				type: "workflow",
			},
		};
		onChange([...value, newAction]);
	}, [value, onChange]);

	const handleRemoveAction = useCallback(
		(index: number) => {
			onChange(value.filter((_, i) => i !== index));
		},
		[value, onChange],
	);

	const handleUpdateAction = useCallback(
		(index: number, updates: Partial<TableAction>) => {
			onChange(
				value.map((action, i) =>
					i === index ? { ...action, ...updates } : action,
				),
			);
		},
		[value, onChange],
	);

	const handleUpdateOnClick = useCallback(
		(index: number, updates: Partial<TableAction["onClick"]>) => {
			onChange(
				value.map((action, i) =>
					i === index
						? {
								...action,
								onClick: { ...action.onClick, ...updates },
							}
						: action,
				),
			);
		},
		[value, onChange],
	);

	return (
		<div className={cn("space-y-3", className)}>
			{value.length === 0 ? (
				<div className="text-sm text-muted-foreground italic py-4 text-center border border-dashed rounded-md">
					No actions defined
				</div>
			) : (
				<Accordion type="multiple" className="space-y-2">
					{value.map((action, index) => (
						<AccordionItem
							key={index}
							value={`action-${index}`}
							className="border rounded-md px-3"
						>
							<div className="flex items-center gap-2">
								<GripVertical className="h-4 w-4 text-muted-foreground" />
								<AccordionTrigger className="flex-1 hover:no-underline py-3">
									<div className="flex items-center gap-2 text-left">
										<span className="font-medium">
											{action.label}
										</span>
										<span className="text-xs text-muted-foreground">
											(
											{
												ACTION_TYPES.find(
													(t) =>
														t.value ===
														action.onClick.type,
												)?.label
											}
											)
										</span>
									</div>
								</AccordionTrigger>
								<Button
									type="button"
									variant="ghost"
									size="icon"
									className="h-8 w-8 text-muted-foreground hover:text-destructive"
									onClick={(e) => {
										e.stopPropagation();
										handleRemoveAction(index);
									}}
								>
									<Trash2 className="h-4 w-4" />
								</Button>
							</div>

							<AccordionContent className="space-y-4 pb-4">
								{/* Basic Properties */}
								<div className="grid grid-cols-2 gap-3">
									<div className="space-y-2">
										<Label className="text-sm">Label</Label>
										<Input
											value={action.label}
											onChange={(e) =>
												handleUpdateAction(index, {
													label: e.target.value,
												})
											}
											placeholder="Button label"
										/>
									</div>

									<div className="space-y-2">
										<Label className="text-sm">Style</Label>
										<Select
											value={action.variant ?? "default"}
											onValueChange={(variant) =>
												handleUpdateAction(index, {
													variant:
														variant as TableAction["variant"],
												})
											}
										>
											<SelectTrigger>
												<SelectValue />
											</SelectTrigger>
											<SelectContent>
												{BUTTON_VARIANTS.map((v) => (
													<SelectItem
														key={v.value}
														value={v.value}
													>
														{v.label}
													</SelectItem>
												))}
											</SelectContent>
										</Select>
									</div>
								</div>

								{/* Icon */}
								<div className="space-y-2">
									<Label className="text-sm">
										Icon (optional)
									</Label>
									<Input
										value={action.icon ?? ""}
										onChange={(e) =>
											handleUpdateAction(index, {
												icon:
													e.target.value || undefined,
											})
										}
										placeholder="e.g., edit, trash, eye"
									/>
								</div>

								{/* Action Type */}
								<div className="space-y-2">
									<Label className="text-sm">
										Action Type
									</Label>
									<Select
										value={action.onClick.type}
										onValueChange={(type) =>
											handleUpdateOnClick(index, {
												type: type as TableAction["onClick"]["type"],
											})
										}
									>
										<SelectTrigger>
											<SelectValue />
										</SelectTrigger>
										<SelectContent>
											{ACTION_TYPES.map((type) => (
												<SelectItem
													key={type.value}
													value={type.value}
												>
													{type.label}
												</SelectItem>
											))}
										</SelectContent>
									</Select>
								</div>

								{/* Navigate Fields */}
								{action.onClick.type === "navigate" && (
									<div className="space-y-2">
										<Label className="text-sm">
											Navigate To
										</Label>
										<Input
											value={
												action.onClick.navigateTo ?? ""
											}
											onChange={(e) =>
												handleUpdateOnClick(index, {
													navigateTo: e.target.value,
												})
											}
											placeholder={
												isRowAction
													? "/details/{{ row.id }}"
													: "/page/path"
											}
										/>
										{isRowAction && (
											<p className="text-xs text-muted-foreground">
												Use {"{{ row.id }}"} or{" "}
												{"{{ row.fieldName }}"} for
												dynamic paths
											</p>
										)}
									</div>
								)}

								{/* Workflow Fields */}
								{action.onClick.type === "workflow" && (
									<div className="space-y-4">
										<div className="space-y-2">
											<Label className="text-sm">
												Workflow
											</Label>
											<WorkflowSelector
												value={
													action.onClick.workflowId
												}
												onChange={(workflowId) =>
													handleUpdateOnClick(index, {
														workflowId,
														actionParams: {},
													})
												}
											/>
										</div>

										{action.onClick.workflowId && (
											<div className="space-y-2">
												<Label className="text-sm">
													Parameters
												</Label>
												<WorkflowParameterEditor
													workflowId={
														action.onClick
															.workflowId
													}
													value={
														action.onClick
															.actionParams ?? {}
													}
													onChange={(actionParams) =>
														handleUpdateOnClick(
															index,
															{ actionParams },
														)
													}
													isRowAction={isRowAction}
												/>
											</div>
										)}
									</div>
								)}

								{/* Set Variable Fields */}
								{action.onClick.type === "set-variable" && (
									<div className="space-y-4">
										<div className="space-y-2">
											<Label className="text-sm">
												Variable Name
											</Label>
											<Input
												value={
													action.onClick
														.variableName ?? ""
												}
												onChange={(e) =>
													handleUpdateOnClick(index, {
														variableName:
															e.target.value,
													})
												}
												placeholder="selectedRow"
											/>
										</div>

										<div className="space-y-2">
											<Label className="text-sm">
												Value
											</Label>
											<Input
												value={
													action.onClick
														.variableValue ?? ""
												}
												onChange={(e) =>
													handleUpdateOnClick(index, {
														variableValue:
															e.target.value,
													})
												}
												placeholder={
													isRowAction
														? "{{ row }}"
														: "value"
												}
											/>
											{isRowAction && (
												<p className="text-xs text-muted-foreground">
													Use {"{{ row }}"} to store
													the entire row
												</p>
											)}
										</div>
									</div>
								)}

								{/* Delete Type Notice */}
								{action.onClick.type === "delete" && (
									<div className="rounded-md bg-destructive/10 border border-destructive/20 p-3">
										<p className="text-sm text-destructive">
											Delete actions should have
											confirmation enabled below.
										</p>
									</div>
								)}

								{/* Visibility Expression */}
								<div className="space-y-2">
									<Label className="text-sm">
										Visible When (optional)
									</Label>
									<Input
										value={action.visible ?? ""}
										onChange={(e) =>
											handleUpdateAction(index, {
												visible:
													e.target.value || undefined,
											})
										}
										placeholder={
											isRowAction
												? "{{ row.status != 'deleted' }}"
												: "{{ user.role == 'admin' }}"
										}
									/>
								</div>

								{/* Disabled Expression */}
								<div className="space-y-2">
									<Label className="text-sm">
										Disabled When (optional)
									</Label>
									<Input
										value={action.disabled ?? ""}
										onChange={(e) =>
											handleUpdateAction(index, {
												disabled:
													e.target.value || undefined,
											})
										}
										placeholder={
											isRowAction
												? "{{ row.status == 'completed' }}"
												: ""
										}
									/>
								</div>

								{/* Confirmation */}
								{(action.onClick.type === "delete" ||
									action.onClick.type === "workflow") && (
									<div className="space-y-3 pt-2 border-t">
										<Label className="text-sm font-medium">
											Confirmation Dialog
										</Label>
										<div className="space-y-3">
											<div className="space-y-2">
												<Label className="text-sm">
													Title
												</Label>
												<Input
													value={
														action.confirm?.title ??
														""
													}
													onChange={(e) =>
														handleUpdateAction(
															index,
															{
																confirm: {
																	...action.confirm,
																	title: e
																		.target
																		.value,
																	message:
																		action
																			.confirm
																			?.message ??
																		"",
																},
															},
														)
													}
													placeholder="Confirm Action"
												/>
											</div>

											<div className="space-y-2">
												<Label className="text-sm">
													Message
												</Label>
												<Input
													value={
														action.confirm
															?.message ?? ""
													}
													onChange={(e) =>
														handleUpdateAction(
															index,
															{
																confirm: {
																	...action.confirm,
																	title:
																		action
																			.confirm
																			?.title ??
																		"",
																	message:
																		e.target
																			.value,
																},
															},
														)
													}
													placeholder="Are you sure?"
												/>
											</div>
										</div>
									</div>
								)}
							</AccordionContent>
						</AccordionItem>
					))}
				</Accordion>
			)}

			<Button
				type="button"
				variant="outline"
				size="sm"
				className="w-full"
				onClick={handleAddAction}
			>
				<Plus className="h-4 w-4 mr-2" />
				Add Action
			</Button>

			{isRowAction && value.length > 0 && (
				<p className="text-xs text-muted-foreground">
					Row actions have access to {"{{ row.* }}"} for the current
					row's data.
				</p>
			)}
		</div>
	);
}

export default TableActionBuilder;
