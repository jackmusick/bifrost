import { useState, useEffect, useRef } from "react";
import {
	Pencil,
	Trash2,
	GripVertical,
	Plus,
	Type,
	Mail,
	Hash,
	ChevronDown,
	CheckSquare,
	TextCursorInput,
	Star,
	Workflow as WorkflowIcon,
	CircleDot,
	Calendar,
	FileText,
	Code,
	Upload,
} from "lucide-react";
import {
	Card,
	CardContent,
	CardDescription,
	CardHeader,
	CardTitle,
} from "@/components/ui/card";
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
import { Badge } from "@/components/ui/badge";
import { FieldConfigDialog } from "./FieldConfigDialog";
import type { components } from "@/lib/v1";
import type { FormField } from "@/lib/client-types";
type WorkflowMetadata = components["schemas"]["WorkflowMetadata"];
type WorkflowParameter = components["schemas"]["WorkflowParameter"];
import {
	draggable,
	dropTargetForElements,
} from "@atlaskit/pragmatic-drag-and-drop/element/adapter";
import { combine } from "@atlaskit/pragmatic-drag-and-drop/combine";
import { reorder } from "@atlaskit/pragmatic-drag-and-drop/reorder";
import { autoScrollForElements } from "@atlaskit/pragmatic-drag-and-drop-auto-scroll/element";
import { useWorkflowsMetadata } from "@/hooks/useWorkflows";

interface FieldsPanelProps {
	fields: FormField[];
	setFields: (fields: FormField[]) => void;
	linkedWorkflow?: string;
	previewContext?: {
		workflow: Record<string, unknown>;
		query: Record<string, string>;
		field: Record<string, unknown>;
	};
}

// Field type templates for the palette
const FIELD_TEMPLATES = [
	{ type: "text", icon: Type, label: "Text Input", color: "bg-blue-500" },
	{ type: "email", icon: Mail, label: "Email", color: "bg-purple-500" },
	{ type: "number", icon: Hash, label: "Number", color: "bg-green-500" },
	{
		type: "select",
		icon: ChevronDown,
		label: "Dropdown",
		color: "bg-orange-500",
	},
	{
		type: "checkbox",
		icon: CheckSquare,
		label: "Checkbox",
		color: "bg-pink-500",
	},
	{
		type: "textarea",
		icon: TextCursorInput,
		label: "Text Area",
		color: "bg-indigo-500",
	},
	{
		type: "radio",
		icon: CircleDot,
		label: "Radio Buttons",
		color: "bg-cyan-500",
	},
	{
		type: "datetime",
		icon: Calendar,
		label: "Date & Time",
		color: "bg-amber-500",
	},
	{
		type: "markdown",
		icon: FileText,
		label: "Markdown",
		color: "bg-slate-500",
	},
	{ type: "html", icon: Code, label: "HTML Content", color: "bg-red-500" },
	{
		type: "file",
		icon: Upload,
		label: "File Upload",
		color: "bg-emerald-500",
	},
];

interface FieldItemProps {
	field: FormField;
	index: number;
	onEdit: () => void;
	onDelete: () => void;
	isDraggingNew: boolean;
}

function FieldItem({ field, index, onEdit, onDelete }: FieldItemProps) {
	const ref = useRef<HTMLDivElement>(null);
	const [dragging, setDragging] = useState(false);
	const [isDraggedOver, setIsDraggedOver] = useState(false);
	const [dropPosition, setDropPosition] = useState<
		"none" | "before" | "after"
	>("none");

	useEffect(() => {
		const el = ref.current;
		if (!el) return;

		return combine(
			draggable({
				element: el,
				getInitialData: () => ({ type: "field", index, field }),
				onDragStart: () => setDragging(true),
				onDrop: () => setDragging(false),
			}),
			dropTargetForElements({
				element: el,
				getData: ({ input, element }) => {
					const rect = element.getBoundingClientRect();
					const midpoint = rect.top + rect.height / 2;
					const position =
						input.clientY < midpoint ? "before" : "after";
					return { index, position };
				},
				canDrop: ({ source }) =>
					source.data["type"] === "field" ||
					source.data["type"] === "template" ||
					source.data["type"] === "workflow-input",
				onDragEnter: ({ source }) => {
					if (
						source.data["type"] === "template" ||
						source.data["type"] === "workflow-input"
					) {
						setIsDraggedOver(true);
					} else {
						setIsDraggedOver(true);
					}
				},
				onDrag: ({ self, source }) => {
					if (
						source.data["type"] === "template" ||
						source.data["type"] === "workflow-input"
					) {
						const position = self.data["position"] as
							| "before"
							| "after";
						setDropPosition(position);
					}
				},
				onDragLeave: () => {
					setIsDraggedOver(false);
					setDropPosition("none");
				},
				onDrop: () => {
					setIsDraggedOver(false);
					setDropPosition("none");
				},
			}),
		);
	}, [index, field]);

	const getFieldTypeBadge = (type: string) => {
		const colors: Record<string, string> = {
			text: "bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200",
			email: "bg-purple-100 text-purple-800 dark:bg-purple-900 dark:text-purple-200",
			number: "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200",
			select: "bg-orange-100 text-orange-800 dark:bg-orange-900 dark:text-orange-200",
			checkbox:
				"bg-pink-100 text-pink-800 dark:bg-pink-900 dark:text-pink-200",
			textarea:
				"bg-indigo-100 text-indigo-800 dark:bg-indigo-900 dark:text-indigo-200",
			radio: "bg-cyan-100 text-cyan-800 dark:bg-cyan-900 dark:text-cyan-200",
			datetime:
				"bg-amber-100 text-amber-800 dark:bg-amber-900 dark:text-amber-200",
			markdown:
				"bg-slate-100 text-slate-800 dark:bg-slate-900 dark:text-slate-200",
			html: "bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200",
			file: "bg-emerald-100 text-emerald-800 dark:bg-emerald-900 dark:text-emerald-200",
		};
		return (
			<span
				className={`px-2 py-1 text-xs font-medium rounded ${colors[type] || "bg-gray-100 text-gray-800"}`}
			>
				{type}
			</span>
		);
	};

	return (
		<div className="relative">
			{/* Drop indicator line */}
			{dropPosition === "before" && (
				<div className="absolute -top-1 left-0 right-0 h-0.5 bg-primary z-10" />
			)}

			<div
				ref={ref}
				className={`flex items-center gap-3 rounded-lg border p-3 transition-all ${
					dragging ? "opacity-50 scale-95" : ""
				} ${isDraggedOver ? "border-primary bg-accent" : "bg-card"} hover:border-primary/50 cursor-move`}
			>
				<GripVertical className="h-5 w-5 text-muted-foreground flex-shrink-0" />

				<div className="flex-1 min-w-0">
					<div className="flex items-center gap-2">
						<p className="font-medium truncate">{field.label}</p>
						{field.required && (
							<Badge variant="destructive" className="text-xs">
								Required
							</Badge>
						)}
					</div>
					<div className="mt-1 flex items-center gap-2">
						<p className="font-mono text-xs text-muted-foreground truncate">
							{field.name}
						</p>
						{getFieldTypeBadge(field.type)}
					</div>
				</div>

				<div className="flex gap-1 flex-shrink-0">
					<Button
						variant="ghost"
						size="icon"
						onClick={onEdit}
						className="h-8 w-8"
					>
						<Pencil className="h-4 w-4" />
					</Button>
					<Button
						variant="ghost"
						size="icon"
						onClick={onDelete}
						className="h-8 w-8"
					>
						<Trash2 className="h-4 w-4" />
					</Button>
				</div>
			</div>

			{/* Drop indicator line after */}
			{dropPosition === "after" && (
				<div className="absolute -bottom-1 left-0 right-0 h-0.5 bg-primary z-10" />
			)}
		</div>
	);
}

interface PaletteItemProps {
	template: (typeof FIELD_TEMPLATES)[0];
}

function PaletteItem({ template }: PaletteItemProps) {
	const ref = useRef<HTMLDivElement>(null);
	const [dragging, setDragging] = useState(false);
	const Icon = template.icon;

	useEffect(() => {
		const el = ref.current;
		if (!el) return;

		return draggable({
			element: el,
			getInitialData: () => ({
				type: "template",
				fieldType: template.type,
			}),
			onDragStart: () => setDragging(true),
			onDrop: () => setDragging(false),
		});
	}, [template.type]);

	return (
		<div
			ref={ref}
			className={`flex items-center gap-3 rounded-lg border p-3 cursor-grab active:cursor-grabbing transition-all hover:border-primary hover:shadow-sm ${
				dragging ? "opacity-50 scale-95" : ""
			}`}
		>
			<div className={`${template.color} p-2 rounded`}>
				<Icon className="h-4 w-4 text-white" />
			</div>
			<span className="text-sm font-medium">{template.label}</span>
		</div>
	);
}

interface WorkflowInputItemProps {
	param: {
		name?: string;
		type?: string;
		required?: boolean;
		label?: string | null;
		helpText?: string | null;
		defaultValue?: unknown;
		dataProvider?: string | null;
	};
}

function WorkflowInputItem({ param }: WorkflowInputItemProps) {
	const ref = useRef<HTMLDivElement>(null);
	const [dragging, setDragging] = useState(false);

	// Map Python types to field types
	const getFieldType = (pythonType: string): string => {
		const typeMap: Record<string, string> = {
			str: "text",
			string: "text",
			int: "number",
			float: "number",
			number: "number",
			bool: "checkbox",
			boolean: "checkbox",
			email: "email",
			select: "select",
		};
		return typeMap[pythonType.toLowerCase()] || "text";
	};

	const fieldType = getFieldType(param.type ?? "text");
	const template = FIELD_TEMPLATES.find((t) => t.type === fieldType);
	const Icon = param.dataProvider ? ChevronDown : (template?.icon ?? Type);

	useEffect(() => {
		const el = ref.current;
		if (!el) return;

		return draggable({
			element: el,
			getInitialData: () => ({
				type: "workflow-input",
				fieldType,
				fieldName: param.name ?? "",
				required: param.required ?? false,
				description: param.helpText ?? undefined,
				dataProvider: param.dataProvider ?? undefined,
			}),
			onDragStart: () => setDragging(true),
			onDrop: () => setDragging(false),
		});
	}, [fieldType, param]);

	return (
		<div
			ref={ref}
			className={`flex items-center gap-2 rounded-lg border border-primary/50 bg-primary/5 p-3 cursor-grab active:cursor-grabbing transition-all hover:border-primary hover:shadow-sm ${
				dragging ? "opacity-50 scale-95" : ""
			}`}
		>
			<div className={`${template?.color ?? "bg-blue-500"} p-2 rounded`}>
				<Icon className="h-4 w-4 text-white" />
			</div>
			<div className="flex-1 min-w-0">
				<div className="flex items-center gap-1">
					<span className="text-xs font-mono font-semibold">
						{param.name ?? "unnamed"}
					</span>
					{param.required && (
						<Star className="h-3 w-3 text-amber-500 fill-amber-500" />
					)}
				</div>
				{param.helpText && (
					<p className="text-[10px] text-muted-foreground truncate">
						{param.helpText}
					</p>
				)}
			</div>
		</div>
	);
}

export function FieldsPanelDnD({
	fields,
	setFields,
	linkedWorkflow,
	previewContext,
}: FieldsPanelProps) {
	const [selectedField, setSelectedField] = useState<FormField | undefined>();
	const [isDialogOpen, setIsDialogOpen] = useState(false);
	const [isDeleteDialogOpen, setIsDeleteDialogOpen] = useState(false);
	const [editingIndex, setEditingIndex] = useState<number | undefined>();
	const [deletingIndex, setDeletingIndex] = useState<number | undefined>();
	const [newFieldType, setNewFieldType] = useState<string | undefined>();
	const [workflowInputData, setWorkflowInputData] = useState<{
		name: string;
		required: boolean;
		helpText?: string;
		dataProvider?: string;
	}>();
	const [insertAtIndex, setInsertAtIndex] = useState<number | undefined>();
	const [isDraggingNew, setIsDraggingNew] = useState(false);
	const [isWorkflowInput, setIsWorkflowInput] = useState(false);
	const dropZoneRef = useRef<HTMLDivElement>(null);

	const { data: metadata } = useWorkflowsMetadata() as {
		data?: { workflows?: WorkflowMetadata[]; dataProviders?: unknown[] };
	};

	// Get the current workflow's parameters, filtering out ones already in the form
	const workflowParams = linkedWorkflow
		? (
				metadata?.workflows?.find(
					(w: WorkflowMetadata) => w.name === linkedWorkflow,
				)?.parameters || []
			).filter(
				(param: WorkflowParameter) =>
					!fields.some((field) => field.name === param.name),
			)
		: [];

	useEffect(() => {
		const el = dropZoneRef.current;
		if (!el) return;

		return combine(
			dropTargetForElements({
				element: el,
				getData: () => ({ type: "dropzone" }),
				canDrop: ({ source }) =>
					source.data["type"] === "template" ||
					source.data["type"] === "field" ||
					source.data["type"] === "workflow-input",
				onDragStart: ({ source }) => {
					if (
						source.data["type"] === "template" ||
						source.data["type"] === "workflow-input"
					) {
						setIsDraggingNew(true);
					}
				},
				onDrop: ({ source, location }) => {
					setIsDraggingNew(false);

					if (source.data["type"] === "template") {
						// Dropped a template - determine insert index and open dialog
						const target = location.current.dropTargets.find(
							(t) => t.data["index"] !== undefined,
						);
						if (target?.data["index"] !== undefined) {
							const position = target.data["position"] as
								| "before"
								| "after";
							const dropIndex =
								position === "before"
									? (target.data["index"] as number)
									: (target.data["index"] as number) + 1;
							setInsertAtIndex(dropIndex);
						} else {
							setInsertAtIndex(fields.length);
						}
						setNewFieldType(source.data["fieldType"] as string);
						setSelectedField(undefined);
						setEditingIndex(undefined);
						setWorkflowInputData(undefined);
						setIsWorkflowInput(false);
						setIsDialogOpen(true);
					} else if (source.data["type"] === "workflow-input") {
						// Dropped a workflow input - determine insert index and pre-fill field data
						const target = location.current.dropTargets.find(
							(t) => t.data["index"] !== undefined,
						);
						if (target?.data["index"] !== undefined) {
							const position = target.data["position"] as
								| "before"
								| "after";
							const dropIndex =
								position === "before"
									? (target.data["index"] as number)
									: (target.data["index"] as number) + 1;
							setInsertAtIndex(dropIndex);
						} else {
							setInsertAtIndex(fields.length);
						}
						setNewFieldType(source.data["fieldType"] as string);
						setSelectedField(undefined);
						setEditingIndex(undefined);
						const description = source.data["description"] as
							| string
							| undefined;
						const dataProvider = source.data["dataProvider"] as
							| string
							| undefined;
						setWorkflowInputData({
							name: source.data["fieldName"] as string,
							required: source.data["required"] as boolean,
							...(description !== undefined && {
								helpText: description,
							}),
							...(dataProvider !== undefined && { dataProvider }),
						});
						setIsWorkflowInput(true);
						setIsDialogOpen(true);
					} else if (source.data["type"] === "field") {
						// Reordering existing fields
						const startIndex = source.data["index"] as number;
						const target = location.current.dropTargets[0];
						if (target?.data["index"] !== undefined) {
							const endIndex = target.data["index"] as number;
							if (startIndex !== endIndex) {
								setFields(
									reorder({
										list: fields,
										startIndex,
										finishIndex: endIndex,
									}),
								);
							}
						}
					}
				},
			}),
			autoScrollForElements({
				element: el,
			}),
		);
	}, [fields, setFields]);

	const handleEditField = (index: number) => {
		setSelectedField(fields[index]);
		setEditingIndex(index);
		setNewFieldType(undefined);
		setWorkflowInputData(undefined);
		setIsWorkflowInput(false);
		setIsDialogOpen(true);
	};

	const handleSaveField = (field: FormField) => {
		if (editingIndex !== undefined) {
			// Update existing field
			const newFields = [...fields];
			newFields[editingIndex] = field;
			setFields(newFields);
		} else {
			// Add new field at the specified index (or at the end if not specified)
			const newFields = [...fields];
			const index =
				insertAtIndex !== undefined ? insertAtIndex : fields.length;
			newFields.splice(index, 0, field);
			setFields(newFields);
		}
		setIsDialogOpen(false);
		setNewFieldType(undefined);
		setInsertAtIndex(undefined);
	};

	const handleDeleteField = (index: number) => {
		setDeletingIndex(index);
		setIsDeleteDialogOpen(true);
	};

	const handleConfirmDelete = () => {
		if (deletingIndex !== undefined) {
			setFields(fields.filter((_, i) => i !== deletingIndex));
		}
		setIsDeleteDialogOpen(false);
		setDeletingIndex(undefined);
	};

	return (
		<div className="grid grid-cols-1 lg:grid-cols-4 gap-6 w-full h-full">
			{/* Field Palette */}
			<Card className="lg:col-span-1 flex flex-col h-full overflow-hidden">
				<CardHeader className="pb-3 flex-shrink-0">
					<div className="flex items-center gap-2">
						<WorkflowIcon className="h-4 w-4 text-primary" />
						<CardTitle className="text-base">
							Field Palette
						</CardTitle>
					</div>
					<CardDescription className="text-xs">
						Drag fields into the form builder
					</CardDescription>
				</CardHeader>
				<CardContent className="space-y-4 overflow-y-auto flex-1 min-h-0">
					{/* Workflow Inputs Section */}
					{workflowParams.length > 0 && (
						<div className="space-y-2">
							<div className="flex items-center gap-1 mb-2">
								<h4 className="text-xs font-semibold uppercase tracking-wide text-primary">
									Workflow Inputs
								</h4>
								<Star className="h-3 w-3 text-amber-500 fill-amber-500" />
							</div>
							<p className="text-[10px] text-muted-foreground mb-2">
								Required inputs are marked by{" "}
								<Star className="h-2.5 w-2.5 text-amber-500 fill-amber-500 inline" />
							</p>
							<div className="space-y-2">
								{workflowParams.map(
									(
										param: WorkflowParameter,
										index: number,
									) => (
										<WorkflowInputItem
											key={
												param.name ??
												`workflow-param-${index}`
											}
											param={param}
										/>
									),
								)}
							</div>
						</div>
					)}

					{/* Divider */}
					{workflowParams.length > 0 && (
						<div className="relative">
							<div className="absolute inset-0 flex items-center">
								<span className="w-full border-t" />
							</div>
							<div className="relative flex justify-center text-xs uppercase">
								<span className="bg-card px-2 text-muted-foreground">
									or
								</span>
							</div>
						</div>
					)}

					{/* All Field Types Section */}
					<div className="space-y-2">
						<div className="flex items-center gap-1 mb-2">
							<h4 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
								All Field Types
							</h4>
						</div>
						<p className="text-[10px] text-muted-foreground mb-2">
							Additional fields not used by workflow
						</p>
						<div className="space-y-2">
							{FIELD_TEMPLATES.map((template) => (
								<PaletteItem
									key={template.type}
									template={template}
								/>
							))}
						</div>
					</div>
				</CardContent>
			</Card>

			{/* Drop Zone */}
			<Card className="lg:col-span-3 flex flex-col h-full overflow-hidden">
				<CardHeader className="flex-shrink-0">
					<div className="flex items-center justify-between">
						<div>
							<CardTitle>Form Fields</CardTitle>
							<CardDescription>
								Drag and drop to reorder fields
							</CardDescription>
						</div>
						<Button
							onClick={() => {
								setNewFieldType(undefined);
								setSelectedField(undefined);
								setEditingIndex(undefined);
								setInsertAtIndex(undefined);
								setIsWorkflowInput(false);
								setIsDialogOpen(true);
							}}
							variant="outline"
							size="icon"
							title="Add Field"
						>
							<Plus className="h-4 w-4" />
						</Button>
					</div>
				</CardHeader>
				<CardContent className="overflow-y-auto flex-1 min-h-0">
					<div ref={dropZoneRef} className="min-h-full">
						{fields.length > 0 ? (
							<div className="space-y-2">
								{fields.map((field, index) => (
									<FieldItem
										key={`${field.name}-${index}`}
										field={field}
										index={index}
										onEdit={() => handleEditField(index)}
										onDelete={() =>
											handleDeleteField(index)
										}
										isDraggingNew={isDraggingNew}
									/>
								))}
							</div>
						) : (
							<div className="flex flex-col items-center justify-center py-16 text-center border-2 border-dashed rounded-lg">
								<div className="max-w-sm">
									<h3 className="text-lg font-semibold mb-2">
										Drop fields here
									</h3>
									<p className="text-sm text-muted-foreground">
										Drag field types from the left palette
										or click the + button to get started
									</p>
								</div>
							</div>
						)}
					</div>
				</CardContent>
			</Card>

			<FieldConfigDialog
				field={selectedField ?? undefined}
				open={isDialogOpen}
				onClose={() => {
					setIsDialogOpen(false);
					setNewFieldType(undefined);
					setWorkflowInputData(undefined);
					setInsertAtIndex(undefined);
					setIsWorkflowInput(false);
				}}
				onSave={handleSaveField}
				allFieldNames={fields.map((f) => f.name)}
				{...(previewContext && { previewContext })}
				{...(newFieldType && { defaultType: newFieldType })}
				{...(workflowInputData && { workflowInputData })}
				{...(isWorkflowInput && { isWorkflowInput })}
			/>

			{/* Delete Confirmation Dialog */}
			<AlertDialog
				open={isDeleteDialogOpen}
				onOpenChange={setIsDeleteDialogOpen}
			>
				<AlertDialogContent>
					<AlertDialogHeader>
						<AlertDialogTitle>Remove Field</AlertDialogTitle>
						<AlertDialogDescription>
							Are you sure you want to remove the field "
							{deletingIndex !== undefined
								? fields[deletingIndex]?.label
								: ""}
							"? This action cannot be undone.
						</AlertDialogDescription>
					</AlertDialogHeader>
					<AlertDialogFooter>
						<AlertDialogCancel>Cancel</AlertDialogCancel>
						<AlertDialogAction
							onClick={handleConfirmDelete}
							className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
						>
							Remove Field
						</AlertDialogAction>
					</AlertDialogFooter>
				</AlertDialogContent>
			</AlertDialog>
		</div>
	);
}
