/**
 * Column Builder Component
 *
 * Visual editor for DataTable column definitions.
 * Allows add/remove/reorder of columns with proper field configuration.
 */

import { useCallback } from "react";
import { Plus, Trash2, GripVertical } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
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
import type { TableColumn } from "@/lib/app-builder-types";

export interface ColumnBuilderProps {
	/** Current column definitions */
	value: TableColumn[];
	/** Callback when columns change */
	onChange: (value: TableColumn[]) => void;
	/** Additional CSS classes */
	className?: string;
}

const COLUMN_TYPES = [
	{ value: "text", label: "Text" },
	{ value: "number", label: "Number" },
	{ value: "date", label: "Date" },
	{ value: "badge", label: "Badge" },
];

/**
 * Column Builder
 *
 * Provides a visual interface for configuring DataTable columns.
 *
 * @example
 * <ColumnBuilder
 *   value={props.columns}
 *   onChange={(columns) => onChange({ props: { ...props, columns } })}
 * />
 */
export function ColumnBuilder({
	value,
	onChange,
	className,
}: ColumnBuilderProps) {
	const handleAddColumn = useCallback(() => {
		const newColumn: TableColumn = {
			key: "",
			header: "",
			type: "text",
			sortable: false,
		};
		onChange([...value, newColumn]);
	}, [value, onChange]);

	const handleRemoveColumn = useCallback(
		(index: number) => {
			onChange(value.filter((_, i) => i !== index));
		},
		[value, onChange],
	);

	const handleUpdateColumn = useCallback(
		(index: number, updates: Partial<TableColumn>) => {
			onChange(
				value.map((col, i) =>
					i === index ? { ...col, ...updates } : col,
				),
			);
		},
		[value, onChange],
	);

	const handleMoveColumn = useCallback(
		(index: number, direction: "up" | "down") => {
			const newIndex = direction === "up" ? index - 1 : index + 1;
			if (newIndex < 0 || newIndex >= value.length) return;

			const newValue = [...value];
			[newValue[index], newValue[newIndex]] = [
				newValue[newIndex],
				newValue[index],
			];
			onChange(newValue);
		},
		[value, onChange],
	);

	return (
		<div className={cn("space-y-3", className)}>
			{value.length === 0 ? (
				<div className="text-sm text-muted-foreground italic py-4 text-center border border-dashed rounded-md">
					No columns defined. Add a column to get started.
				</div>
			) : (
				<Accordion type="multiple" className="space-y-2">
					{value.map((column, index) => (
						<AccordionItem
							key={index}
							value={`column-${index}`}
							className="border rounded-md px-3"
						>
							<div className="flex items-center gap-2">
								<GripVertical className="h-4 w-4 text-muted-foreground cursor-move" />
								<AccordionTrigger className="flex-1 hover:no-underline py-3">
									<div className="flex items-center gap-2 text-left">
										<span className="font-medium">
											{column.header ||
												column.key ||
												`Column ${index + 1}`}
										</span>
										{column.key && (
											<span className="text-xs text-muted-foreground font-mono">
												{column.key}
											</span>
										)}
									</div>
								</AccordionTrigger>
								<div className="flex items-center gap-1">
									<Button
										type="button"
										variant="ghost"
										size="icon"
										className="h-8 w-8"
										onClick={(e) => {
											e.stopPropagation();
											handleMoveColumn(index, "up");
										}}
										disabled={index === 0}
									>
										<span className="text-xs">↑</span>
									</Button>
									<Button
										type="button"
										variant="ghost"
										size="icon"
										className="h-8 w-8"
										onClick={(e) => {
											e.stopPropagation();
											handleMoveColumn(index, "down");
										}}
										disabled={index === value.length - 1}
									>
										<span className="text-xs">↓</span>
									</Button>
									<Button
										type="button"
										variant="ghost"
										size="icon"
										className="h-8 w-8 text-muted-foreground hover:text-destructive"
										onClick={(e) => {
											e.stopPropagation();
											handleRemoveColumn(index);
										}}
									>
										<Trash2 className="h-4 w-4" />
									</Button>
								</div>
							</div>

							<AccordionContent className="space-y-4 pb-4">
								<div className="grid grid-cols-2 gap-3">
									<div className="space-y-2">
										<Label className="text-sm">
											Data Key
										</Label>
										<Input
											value={column.key}
											onChange={(e) =>
												handleUpdateColumn(index, {
													key: e.target.value,
												})
											}
											placeholder="field_name"
											className="font-mono text-sm"
										/>
										<p className="text-xs text-muted-foreground">
											Field path in the data (e.g.,
											user.name)
										</p>
									</div>

									<div className="space-y-2">
										<Label className="text-sm">
											Header Label
										</Label>
										<Input
											value={column.header}
											onChange={(e) =>
												handleUpdateColumn(index, {
													header: e.target.value,
												})
											}
											placeholder="Column Header"
										/>
									</div>
								</div>

								<div className="grid grid-cols-2 gap-3">
									<div className="space-y-2">
										<Label className="text-sm">Type</Label>
										<Select
											value={column.type ?? "text"}
											onValueChange={(type) =>
												handleUpdateColumn(index, {
													type: type as TableColumn["type"],
												})
											}
										>
											<SelectTrigger>
												<SelectValue />
											</SelectTrigger>
											<SelectContent>
												{COLUMN_TYPES.map((type) => (
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

									<div className="space-y-2">
										<Label className="text-sm">Width</Label>
										<Input
											value={
												column.width === "auto"
													? ""
													: String(column.width ?? "")
											}
											onChange={(e) => {
												const val = e.target.value;
												handleUpdateColumn(index, {
													width: val
														? Number(val) || "auto"
														: undefined,
												});
											}}
											placeholder="auto"
											type="number"
											min={50}
										/>
									</div>
								</div>

								<div className="flex items-center justify-between">
									<div>
										<Label className="text-sm">
											Sortable
										</Label>
										<p className="text-xs text-muted-foreground">
											Allow sorting by this column
										</p>
									</div>
									<Switch
										checked={column.sortable ?? false}
										onCheckedChange={(sortable) =>
											handleUpdateColumn(index, {
												sortable,
											})
										}
									/>
								</div>

								{column.type === "badge" && (
									<div className="space-y-2">
										<Label className="text-sm">
											Badge Colors
										</Label>
										<p className="text-xs text-muted-foreground mb-2">
											Map values to colors (e.g., active →
											green)
										</p>
										<Input
											value={
												column.badgeColors
													? JSON.stringify(
															column.badgeColors,
														)
													: ""
											}
											onChange={(e) => {
												try {
													const badgeColors = e.target
														.value
														? JSON.parse(
																e.target.value,
															)
														: undefined;
													handleUpdateColumn(index, {
														badgeColors,
													});
												} catch {
													// Invalid JSON, ignore
												}
											}}
											placeholder='{"active": "green", "inactive": "gray"}'
											className="font-mono text-xs"
										/>
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
				onClick={handleAddColumn}
			>
				<Plus className="h-4 w-4 mr-2" />
				Add Column
			</Button>
		</div>
	);
}

export default ColumnBuilder;
