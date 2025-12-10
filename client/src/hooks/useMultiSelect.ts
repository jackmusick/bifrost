import { useState, useCallback } from "react";

/**
 * Hook for managing multi-selection state in dialogs and lists.
 * Provides toggle, clear, and selection checking functionality.
 *
 * @example
 * ```tsx
 * const { selectedIds, toggle, clear, isSelected, count } = useMultiSelect<string>();
 *
 * // Toggle selection
 * <button onClick={() => toggle(item.id)}>
 *   {isSelected(item.id) ? "Selected" : "Select"}
 * </button>
 *
 * // Clear on dialog close
 * const handleClose = () => {
 *   clear();
 *   onClose();
 * };
 * ```
 */
export function useMultiSelect<T extends string = string>() {
	const [selectedIds, setSelectedIds] = useState<T[]>([]);

	const toggle = useCallback((id: T) => {
		setSelectedIds((prev) =>
			prev.includes(id) ? prev.filter((i) => i !== id) : [...prev, id],
		);
	}, []);

	const clear = useCallback(() => setSelectedIds([]), []);

	const isSelected = useCallback(
		(id: T) => selectedIds.includes(id),
		[selectedIds],
	);

	const selectAll = useCallback((ids: T[]) => {
		setSelectedIds(ids);
	}, []);

	const deselectAll = useCallback((ids: T[]) => {
		setSelectedIds((prev) => prev.filter((id) => !ids.includes(id)));
	}, []);

	return {
		selectedIds,
		toggle,
		clear,
		isSelected,
		selectAll,
		deselectAll,
		count: selectedIds.length,
	};
}
