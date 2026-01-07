/**
 * App Builder Editor Store
 *
 * Zustand store for managing App Builder editing state:
 * - Dirty tracking: which components and pages have unsaved changes
 * - UUID mapping: frontend component IDs to backend UUIDs
 * - Save state: pending operations and save status
 *
 * This is separate from app-builder.store.ts which handles runtime execution.
 */

import { create } from "zustand";
import { subscribeWithSelector } from "zustand/middleware";

/**
 * Component dirty state
 */
export type ComponentDirtyStatus = "new" | "modified" | "deleted" | "clean";

/**
 * Original props for rollback on error
 */
interface ComponentSnapshot {
	status: ComponentDirtyStatus;
	originalProps?: Record<string, unknown>;
}

/**
 * App Builder editor state
 */
interface AppBuilderEditorState {
	// Context - which app/page we're editing
	appId: string | null;
	pageId: string | null;

	// Dirty tracking: component_id -> status
	dirtyComponents: Map<string, ComponentSnapshot>;

	// Dirty tracking: page_id set (pages are simpler, just dirty or not)
	dirtyPages: Set<string>;

	// Frontend component ID -> Backend UUID mapping
	// Populated when components are fetched or created
	uuidMap: Map<string, string>;

	// Save status
	isSaving: boolean;
	lastSaveError: string | null;

	// Actions: Context
	setContext: (appId: string | null, pageId: string | null) => void;
	clearContext: () => void;

	// Actions: Component dirty tracking
	markNew: (componentId: string) => void;
	markModified: (
		componentId: string,
		originalProps?: Record<string, unknown>,
	) => void;
	markDeleted: (componentId: string) => void;
	markClean: (componentId: string) => void;
	clearAllDirty: () => void;

	// Actions: Page dirty tracking
	markPageDirty: (pageId: string) => void;
	markPageClean: (pageId: string) => void;

	// Actions: UUID mapping
	setUUID: (componentId: string, uuid: string) => void;
	getUUID: (componentId: string) => string | undefined;
	setUUIDs: (mapping: Record<string, string>) => void;
	clearUUIDs: () => void;

	// Actions: Save status
	setSaving: (isSaving: boolean) => void;
	setSaveError: (error: string | null) => void;

	// Computed: has unsaved changes
	hasUnsavedChanges: () => boolean;
	getDirtyCount: () => number;

	// Rollback support
	getSnapshot: (componentId: string) => ComponentSnapshot | undefined;
	rollbackComponent: (
		componentId: string,
	) => Record<string, unknown> | undefined;

	// Reset all state
	reset: () => void;
}

/**
 * Initial state values
 */
const initialState = {
	appId: null as string | null,
	pageId: null as string | null,
	dirtyComponents: new Map<string, ComponentSnapshot>(),
	dirtyPages: new Set<string>(),
	uuidMap: new Map<string, string>(),
	isSaving: false,
	lastSaveError: null as string | null,
};

/**
 * App Builder editor store
 *
 * Manages editing state including dirty tracking and UUID resolution.
 * Separate from runtime store to keep concerns isolated.
 */
export const useAppBuilderEditorStore = create<AppBuilderEditorState>()(
	subscribeWithSelector((set, get) => ({
		// Initial state
		...initialState,

		// Context management
		setContext: (appId, pageId) =>
			set({
				appId,
				pageId,
				// Clear dirty state when switching pages
				dirtyComponents: new Map(),
				dirtyPages: new Set(),
			}),

		clearContext: () =>
			set({
				appId: null,
				pageId: null,
				dirtyComponents: new Map(),
				dirtyPages: new Set(),
			}),

		// Dirty tracking
		markNew: (componentId) =>
			set((state) => {
				const newMap = new Map(state.dirtyComponents);
				newMap.set(componentId, { status: "new" });
				return { dirtyComponents: newMap };
			}),

		markModified: (componentId, originalProps) =>
			set((state) => {
				const newMap = new Map(state.dirtyComponents);
				const existing = newMap.get(componentId);

				// Don't downgrade from "new" to "modified"
				if (existing?.status === "new") {
					return state;
				}

				// Keep original props from first modification for rollback
				newMap.set(componentId, {
					status: "modified",
					originalProps: existing?.originalProps ?? originalProps,
				});
				return { dirtyComponents: newMap };
			}),

		markDeleted: (componentId) =>
			set((state) => {
				const newMap = new Map(state.dirtyComponents);
				const existing = newMap.get(componentId);

				// If it was "new", just remove it entirely (never saved to backend)
				if (existing?.status === "new") {
					newMap.delete(componentId);
					return { dirtyComponents: newMap };
				}

				newMap.set(componentId, { status: "deleted" });
				return { dirtyComponents: newMap };
			}),

		markClean: (componentId) =>
			set((state) => {
				const newMap = new Map(state.dirtyComponents);
				newMap.delete(componentId);
				return { dirtyComponents: newMap };
			}),

		clearAllDirty: () =>
			set({ dirtyComponents: new Map(), dirtyPages: new Set() }),

		// Page dirty tracking
		markPageDirty: (pageId) =>
			set((state) => {
				const newSet = new Set(state.dirtyPages);
				newSet.add(pageId);
				return { dirtyPages: newSet };
			}),

		markPageClean: (pageId) =>
			set((state) => {
				const newSet = new Set(state.dirtyPages);
				newSet.delete(pageId);
				return { dirtyPages: newSet };
			}),

		// UUID mapping
		setUUID: (componentId, uuid) =>
			set((state) => {
				const newMap = new Map(state.uuidMap);
				newMap.set(componentId, uuid);
				return { uuidMap: newMap };
			}),

		getUUID: (componentId) => {
			return get().uuidMap.get(componentId);
		},

		setUUIDs: (mapping) =>
			set((state) => {
				const newMap = new Map(state.uuidMap);
				for (const [componentId, uuid] of Object.entries(mapping)) {
					newMap.set(componentId, uuid);
				}
				return { uuidMap: newMap };
			}),

		clearUUIDs: () => set({ uuidMap: new Map() }),

		// Save status
		setSaving: (isSaving) => set({ isSaving }),

		setSaveError: (error) => set({ lastSaveError: error }),

		// Computed
		hasUnsavedChanges: () => {
			const { dirtyComponents, dirtyPages, isSaving } = get();
			return dirtyComponents.size > 0 || dirtyPages.size > 0 || isSaving;
		},

		getDirtyCount: () => {
			const { dirtyComponents, dirtyPages } = get();
			return dirtyComponents.size + dirtyPages.size;
		},

		// Rollback support
		getSnapshot: (componentId) => {
			return get().dirtyComponents.get(componentId);
		},

		rollbackComponent: (componentId) => {
			const state = get();
			const snapshot = state.dirtyComponents.get(componentId);

			if (!snapshot) return undefined;

			// Remove from dirty tracking
			const newMap = new Map(state.dirtyComponents);
			newMap.delete(componentId);
			set({ dirtyComponents: newMap });

			// Return original props for restoration
			return snapshot.originalProps;
		},

		// Reset
		reset: () =>
			set({
				...initialState,
				dirtyComponents: new Map(),
				dirtyPages: new Set(),
				uuidMap: new Map(),
			}),
	})),
);

/**
 * Hook to get dirty component IDs by status
 */
export function useDirtyComponentsByStatus(status: ComponentDirtyStatus) {
	return useAppBuilderEditorStore((state) => {
		const result: string[] = [];
		for (const [id, snapshot] of state.dirtyComponents) {
			if (snapshot.status === status) {
				result.push(id);
			}
		}
		return result;
	});
}

/**
 * Hook to check if a specific component is dirty
 */
export function useIsComponentDirty(componentId: string) {
	return useAppBuilderEditorStore((state) =>
		state.dirtyComponents.has(componentId),
	);
}
