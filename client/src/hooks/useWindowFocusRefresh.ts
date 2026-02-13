import { useEffect, useCallback } from "react";
import { useFileTree, workspaceOperations } from "@/components/file-tree";
import { useEditorStore } from "@/stores/editorStore";
import { fileService } from "@/services/fileService";

/**
 * Hook that handles window focus events to refresh the file tree
 * When the window regains focus:
 * - Refreshes the file tree to show any external changes
 * - Checks active file for conflicts
 */
export function useWindowFocusRefresh() {
	const { refreshAll } = useFileTree(workspaceOperations);
	const setConflictState = useEditorStore((state) => state.setConflictState);

	// Handle window focus event
	const handleFocus = useCallback(async () => {
		// Refresh directory tree to show any external changes
		try {
			await refreshAll();
		} catch (error) {
			console.error("[WindowFocus] Failed to refresh file tree:", error);
		}

		// Check active file for conflicts (get fresh state)
		const state = useEditorStore.getState();
		const activeTab = state.tabs[state.activeTabIndex];

		if (
			!activeTab ||
			!activeTab.etag ||
			activeTab.saveState === "conflict" ||
			activeTab.saveState === "saving" ||
			state.isIndexing
		) {
			return; // Skip if no active file, no etag, already in conflict, saving, or indexing
		}

		try {
			const serverFile = await fileService.readFile(activeTab.file.path);

			// Check if server content changed
			if (serverFile.etag !== activeTab.etag) {
				// If there are no unsaved changes, just accept the server version silently
				if (!activeTab.unsavedChanges) {
					const newTabs = [...state.tabs];
					newTabs[state.activeTabIndex] = {
						...activeTab,
						content: serverFile.content,
						etag: serverFile.etag,
						encoding: serverFile.encoding as "utf-8" | "base64",
					};
					useEditorStore.setState({ tabs: newTabs });
				} else {
					// Only show conflict if we have unsaved local changes
					setConflictState(state.activeTabIndex, "content_changed");
				}
			}
		} catch (error: unknown) {
			// Check if file was deleted (404)
			if (error instanceof Error && error.message.includes("404")) {
				const state = useEditorStore.getState();
				setConflictState(state.activeTabIndex, "path_not_found");
			}
			// Ignore other errors (network issues, etc.)
		}
	}, [refreshAll, setConflictState]);

	// Set up window focus listener
	useEffect(() => {
		window.addEventListener("focus", handleFocus);
		return () => window.removeEventListener("focus", handleFocus);
	}, [handleFocus]);
}
