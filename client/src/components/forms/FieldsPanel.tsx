import {
	Plus,
	Pencil,
	Trash2,
	GripVertical,
	ArrowUp,
	ArrowDown,
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
import { useFieldManager } from "@/hooks/useFieldManager";
import type { FormField } from "@/lib/client-types";

interface FieldsPanelProps {
	fields: FormField[];
	setFields: (fields: FormField[]) => void;
}

export function FieldsPanel({ fields, setFields }: FieldsPanelProps) {
	const {
		selectedField,
		isDialogOpen,
		isDeleteDialogOpen,
		deletingFieldLabel,
		openAddDialog,
		openEditDialog,
		closeDialog,
		saveField,
		openDeleteDialog,
		closeDeleteDialog,
		confirmDelete,
		moveUp,
		moveDown,
	} = useFieldManager({ fields, setFields });

	const getFieldTypeBadge = (type: string) => {
		const colors: Record<string, "default" | "secondary" | "outline"> = {
			text: "default",
			email: "secondary",
			number: "secondary",
			select: "outline",
			checkbox: "outline",
			textarea: "default",
		};
		return <Badge variant={colors[type] || "default"}>{type}</Badge>;
	};

	return (
		<>
			<Card>
				<CardHeader>
					<div className="flex items-center justify-between">
						<div>
							<CardTitle>Form Fields</CardTitle>
							<CardDescription>
								Add and configure fields for your form
							</CardDescription>
						</div>
						<Button onClick={openAddDialog}>
							<Plus className="mr-2 h-4 w-4" />
							Add Field
						</Button>
					</div>
				</CardHeader>
				<CardContent>
					{fields.length > 0 ? (
						<div className="space-y-2">
							{fields.map((field, index) => (
								<div
									key={index}
									className="flex items-center gap-3 rounded-lg border p-3"
								>
									<div className="flex items-center gap-2">
										<GripVertical className="h-4 w-4 text-muted-foreground" />
										<div className="flex flex-col gap-1">
											<Button
												variant="ghost"
												size="icon"
												className="h-6 w-6"
												onClick={() => moveUp(index)}
												disabled={index === 0}
											>
												<ArrowUp className="h-3 w-3" />
											</Button>
											<Button
												variant="ghost"
												size="icon"
												className="h-6 w-6"
												onClick={() => moveDown(index)}
												disabled={
													index === fields.length - 1
												}
											>
												<ArrowDown className="h-3 w-3" />
											</Button>
										</div>
									</div>

									<div className="flex-1">
										<div className="flex items-center gap-2">
											<p className="font-medium">
												{field.label}
											</p>
											{field.required && (
												<Badge
													variant="destructive"
													className="text-xs"
												>
													Required
												</Badge>
											)}
										</div>
										<div className="mt-1 flex items-center gap-2">
											<p className="font-mono text-xs text-muted-foreground">
												{field.name}
											</p>
											{getFieldTypeBadge(field.type)}
										</div>
									</div>

									<div className="flex gap-2">
										<Button
											variant="ghost"
											size="icon"
											onClick={() => openEditDialog(index)}
										>
											<Pencil className="h-4 w-4" />
										</Button>
										<Button
											variant="ghost"
											size="icon"
											onClick={() => openDeleteDialog(index)}
										>
											<Trash2 className="h-4 w-4" />
										</Button>
									</div>
								</div>
							))}
						</div>
					) : (
						<div className="flex flex-col items-center justify-center py-12 text-center">
							<p className="text-sm text-muted-foreground">
								No fields added yet. Click "Add Field" to get
								started.
							</p>
						</div>
					)}
				</CardContent>
			</Card>

			<FieldConfigDialog
				field={selectedField}
				open={isDialogOpen}
				onClose={closeDialog}
				onSave={saveField}
			/>

			{/* Delete Confirmation Dialog */}
			<AlertDialog
				open={isDeleteDialogOpen}
				onOpenChange={closeDeleteDialog}
			>
				<AlertDialogContent>
					<AlertDialogHeader>
						<AlertDialogTitle>Remove Field</AlertDialogTitle>
						<AlertDialogDescription>
							Are you sure you want to remove the field "
							{deletingFieldLabel ?? ""}"? This action cannot be
							undone.
						</AlertDialogDescription>
					</AlertDialogHeader>
					<AlertDialogFooter>
						<AlertDialogCancel>Cancel</AlertDialogCancel>
						<AlertDialogAction
							onClick={confirmDelete}
							className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
						>
							Remove Field
						</AlertDialogAction>
					</AlertDialogFooter>
				</AlertDialogContent>
			</AlertDialog>
		</>
	);
}
