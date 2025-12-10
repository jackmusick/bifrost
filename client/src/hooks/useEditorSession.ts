import { useShallow } from "zustand/react/shallow";
import { useEditorStore } from "@/stores/editorStore";

/**
 * Hook for accessing editor session state with optimized re-renders.
 * Uses useShallow to prevent unnecessary re-renders when unrelated state changes.
 *
 * Use this instead of multiple individual useEditorStore() calls:
 *
 * @example
 * ```tsx
 * // ❌ Before: Multiple subscriptions (causes re-renders on any state change)
 * const tabs = useEditorStore((state) => state.tabs);
 * const activeTabIndex = useEditorStore((state) => state.activeTabIndex);
 * const isLoadingFile = useEditorStore((state) => state.isLoadingFile);
 * const setFileContent = useEditorStore((state) => state.setFileContent);
 *
 * // ✅ After: Single subscription with shallow comparison
 * const { tabs, activeTabIndex, isLoadingFile, setFileContent } = useEditorSession();
 * ```
 */
export function useEditorSession() {
	return useEditorStore(
		useShallow((state) => {
			// Compute active tab here to avoid recomputing in components
			const activeTab =
				state.activeTabIndex >= 0 &&
				state.activeTabIndex < state.tabs.length
					? state.tabs[state.activeTabIndex]
					: null;

			return {
				// Tab state
				tabs: state.tabs,
				activeTabIndex: state.activeTabIndex,
				activeTab,

				// Derived values from active tab
				openFile: activeTab?.file ?? null,
				fileContent: activeTab?.content ?? "",
				fileEncoding: activeTab?.encoding ?? "utf-8",
				unsavedChanges: activeTab?.unsavedChanges ?? false,
				cursorPosition: activeTab?.cursorPosition,
				selectedLanguage: activeTab?.selectedLanguage,
				saveState: activeTab?.saveState,
				gitConflict: activeTab?.gitConflict,
				etag: activeTab?.etag,

				// Editor visibility
				isOpen: state.isOpen,
				layoutMode: state.layoutMode,
				isLoadingFile: state.isLoadingFile,

				// Layout
				sidebarPanel: state.sidebarPanel,
				terminalHeight: state.terminalHeight,

				// Terminal
				terminalOutput: state.terminalOutput,
				currentStreamingExecutionId: state.currentStreamingExecutionId,

				// Actions - tab management
				openFileInTab: state.openFileInTab,
				closeTab: state.closeTab,
				closeAllTabs: state.closeAllTabs,
				closeOtherTabs: state.closeOtherTabs,
				setActiveTab: state.setActiveTab,
				reorderTabs: state.reorderTabs,

				// Actions - editor visibility
				openEditor: state.openEditor,
				closeEditor: state.closeEditor,
				minimizeEditor: state.minimizeEditor,
				restoreEditor: state.restoreEditor,

				// Actions - active tab operations
				setFileContent: state.setFileContent,
				setLoadingFile: state.setLoadingFile,
				markSaved: state.markSaved,
				setSaveState: state.setSaveState,
				setConflictState: state.setConflictState,
				resolveConflict: state.resolveConflict,
				setCursorPosition: state.setCursorPosition,
				setSelectedLanguage: state.setSelectedLanguage,

				// Actions - file operations
				updateTabPath: state.updateTabPath,
				closeTabsByPath: state.closeTabsByPath,

				// Actions - layout
				setSidebarPanel: state.setSidebarPanel,
				setTerminalHeight: state.setTerminalHeight,

				// Actions - terminal
				appendTerminalOutput: state.appendTerminalOutput,
				clearTerminalOutput: state.clearTerminalOutput,
				setCurrentStreamingExecutionId:
					state.setCurrentStreamingExecutionId,
			};
		}),
	);
}

/**
 * Lightweight hook for components that only need to open/close the editor.
 * Minimizes re-renders by only subscribing to visibility state.
 */
export function useEditorVisibility() {
	return useEditorStore(
		useShallow((state) => ({
			isOpen: state.isOpen,
			layoutMode: state.layoutMode,
			openEditor: state.openEditor,
			closeEditor: state.closeEditor,
			minimizeEditor: state.minimizeEditor,
			restoreEditor: state.restoreEditor,
		})),
	);
}

/**
 * Hook for components that need terminal/output state.
 */
export function useEditorTerminal() {
	return useEditorStore(
		useShallow((state) => ({
			terminalOutput: state.terminalOutput,
			currentStreamingExecutionId: state.currentStreamingExecutionId,
			appendTerminalOutput: state.appendTerminalOutput,
			clearTerminalOutput: state.clearTerminalOutput,
			setCurrentStreamingExecutionId: state.setCurrentStreamingExecutionId,
		})),
	);
}
