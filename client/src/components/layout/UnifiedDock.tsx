// client/src/components/layout/UnifiedDock.tsx

import { Code, AppWindow } from "lucide-react";
import { WindowDock, type DockItem } from "@/components/window-management";
import { useEditorStore } from "@/stores/editorStore";
import { useAppViewerStore } from "@/stores/appViewerStore";
import { useUploadStore } from "@/stores/uploadStore";
import { useExecutionStreamStore } from "@/stores/executionStreamStore";

/**
 * Unified dock that aggregates all minimized windows.
 * Renders both editor and app viewer dock items.
 */
export function UnifiedDock() {
	// Editor state
	const editorIsOpen = useEditorStore((state) => state.isOpen);
	const editorLayoutMode = useEditorStore((state) => state.layoutMode);
	const editorActiveTab = useEditorStore((state) => {
		const idx = state.activeTabIndex;
		return idx >= 0 && idx < state.tabs.length ? state.tabs[idx] : null;
	});
	const editorSidebarPanel = useEditorStore((state) => state.sidebarPanel);
	const restoreEditor = useEditorStore((state) => state.restoreEditor);

	// Editor activity state
	const isUploading = useUploadStore((state) => state.isUploading);
	const streams = useExecutionStreamStore((state) => state.streams);
	const hasActiveExecution = Object.values(streams).some(
		(s) => s.status === "Running" || s.status === "Pending",
	);
	const editorIsLoading = isUploading || hasActiveExecution;

	// App viewer state
	const appId = useAppViewerStore((state) => state.appId);
	const appName = useAppViewerStore((state) => state.appName);
	const appLayoutMode = useAppViewerStore((state) => state.layoutMode);
	const appIsPreview = useAppViewerStore((state) => state.isPreview);

	// Build dock items
	const items: DockItem[] = [];

	// Add app viewer if minimized
	if (appId && appLayoutMode === "minimized") {
		items.push({
			id: `app-${appId}`,
			icon: <AppWindow className="h-4 w-4" />,
			label: appIsPreview ? `${appName} (Preview)` : appName || "App",
			isLoading: false,
			onRestore: () => {
				useAppViewerStore.setState({ layoutMode: "maximized" });
			},
		});
	}

	// Add editor if minimized
	if (editorIsOpen && editorLayoutMode === "minimized") {
		// Get label for minimized editor
		let editorLabel = "Editor";
		if (editorActiveTab?.file) {
			editorLabel = editorActiveTab.file.name;
		} else if (editorSidebarPanel === "files") {
			editorLabel = "File Browser";
		} else if (editorSidebarPanel === "search") {
			editorLabel = "Search";
		} else if (editorSidebarPanel === "sourceControl") {
			editorLabel = "Source Control";
		} else if (editorSidebarPanel === "run") {
			editorLabel = "Execute";
		} else if (editorSidebarPanel === "packages") {
			editorLabel = "Packages";
		}

		items.push({
			id: "editor",
			icon: <Code className="h-4 w-4" />,
			label: editorLabel,
			isLoading: editorIsLoading,
			onRestore: restoreEditor,
		});
	}

	return <WindowDock items={items} />;
}
