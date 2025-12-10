import { useState, useCallback } from "react";
import type { FormField } from "@/lib/client-types";

interface UseFieldManagerOptions {
	fields: FormField[];
	setFields: (fields: FormField[]) => void;
}

interface UseFieldManagerReturn {
	// Dialog state
	selectedField: FormField | undefined;
	isDialogOpen: boolean;
	editingIndex: number | undefined;

	// Delete dialog state
	isDeleteDialogOpen: boolean;
	deletingIndex: number | undefined;
	deletingFieldLabel: string | undefined;

	// Actions
	openAddDialog: () => void;
	openEditDialog: (index: number) => void;
	closeDialog: () => void;
	saveField: (field: FormField, insertAtIndex?: number) => void;

	// Delete actions
	openDeleteDialog: (index: number) => void;
	closeDeleteDialog: () => void;
	confirmDelete: () => void;

	// Reorder actions
	moveUp: (index: number) => void;
	moveDown: (index: number) => void;
}

/**
 * Hook for managing form field CRUD operations.
 * Extracts common logic from FieldsPanel and FieldsPanelDnD components.
 *
 * @example
 * ```tsx
 * const {
 *   selectedField,
 *   isDialogOpen,
 *   openAddDialog,
 *   openEditDialog,
 *   saveField,
 *   openDeleteDialog,
 *   confirmDelete,
 * } = useFieldManager({ fields, setFields });
 *
 * // Open dialog for new field
 * <Button onClick={openAddDialog}>Add Field</Button>
 *
 * // Open dialog to edit existing field
 * <Button onClick={() => openEditDialog(index)}>Edit</Button>
 *
 * // Save field from dialog
 * <FieldConfigDialog onSave={saveField} />
 * ```
 */
export function useFieldManager({
	fields,
	setFields,
}: UseFieldManagerOptions): UseFieldManagerReturn {
	const [selectedField, setSelectedField] = useState<FormField | undefined>();
	const [isDialogOpen, setIsDialogOpen] = useState(false);
	const [editingIndex, setEditingIndex] = useState<number | undefined>();

	const [isDeleteDialogOpen, setIsDeleteDialogOpen] = useState(false);
	const [deletingIndex, setDeletingIndex] = useState<number | undefined>();

	const deletingFieldLabel =
		deletingIndex !== undefined
			? (fields[deletingIndex]?.label ?? undefined)
			: undefined;

	const openAddDialog = useCallback(() => {
		setSelectedField(undefined);
		setEditingIndex(undefined);
		setIsDialogOpen(true);
	}, []);

	const openEditDialog = useCallback(
		(index: number) => {
			setSelectedField(fields[index]);
			setEditingIndex(index);
			setIsDialogOpen(true);
		},
		[fields],
	);

	const closeDialog = useCallback(() => {
		setIsDialogOpen(false);
	}, []);

	const saveField = useCallback(
		(field: FormField, insertAtIndex?: number) => {
			if (editingIndex !== undefined) {
				// Update existing field
				const newFields = [...fields];
				newFields[editingIndex] = field;
				setFields(newFields);
			} else if (insertAtIndex !== undefined) {
				// Insert at specific index (for drag-and-drop)
				const newFields = [...fields];
				newFields.splice(insertAtIndex, 0, field);
				setFields(newFields);
			} else {
				// Add new field at the end
				setFields([...fields, field]);
			}
			setIsDialogOpen(false);
		},
		[fields, setFields, editingIndex],
	);

	const openDeleteDialog = useCallback((index: number) => {
		setDeletingIndex(index);
		setIsDeleteDialogOpen(true);
	}, []);

	const closeDeleteDialog = useCallback(() => {
		setIsDeleteDialogOpen(false);
		setDeletingIndex(undefined);
	}, []);

	const confirmDelete = useCallback(() => {
		if (deletingIndex !== undefined) {
			setFields(fields.filter((_, i) => i !== deletingIndex));
		}
		setIsDeleteDialogOpen(false);
		setDeletingIndex(undefined);
	}, [fields, setFields, deletingIndex]);

	const moveUp = useCallback(
		(index: number) => {
			if (index === 0) return;
			const newFields = [...fields];
			const temp = newFields[index]!;
			newFields[index] = newFields[index - 1]!;
			newFields[index - 1] = temp;
			setFields(newFields);
		},
		[fields, setFields],
	);

	const moveDown = useCallback(
		(index: number) => {
			if (index === fields.length - 1) return;
			const newFields = [...fields];
			const temp = newFields[index]!;
			newFields[index] = newFields[index + 1]!;
			newFields[index + 1] = temp;
			setFields(newFields);
		},
		[fields, setFields],
	);

	return {
		selectedField,
		isDialogOpen,
		editingIndex,
		isDeleteDialogOpen,
		deletingIndex,
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
	};
}
