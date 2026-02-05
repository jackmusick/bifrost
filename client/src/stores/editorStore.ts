import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { FileMetadata, FileContentResponse } from "@/services/fileService";
import { fileService } from "@/services/fileService";
import type { components } from "@/lib/v1";

type WorkflowIdConflict = components["schemas"]["WorkflowIdConflict"];
type PendingDeactivation = components["schemas"]["PendingDeactivation"];
type AvailableReplacement = components["schemas"]["AvailableReplacement"];

/**
 * Editor state store using Zustand with persistence
 * Manages open files with tabs, cursor position, unsaved changes, and sidebar panel
 * State is persisted to localStorage so editor session survives navigation
 */

export type SidebarPanel =
	| "files"
	| "search"
	| "run"
	| "packages"
	| "sourceControl";
export type LayoutMode = "fullscreen" | "minimized";

export interface CursorPosition {
	line: number;
	column: number;
}

export interface ExecutionResult {
	timestamp: string;
	executionId?: string;
	loggerOutput: Array<{
		level: string;
		message: string;
		source: string;
		timestamp?: string;
	}>;
	variables: Record<string, unknown>;
	status: string;
	error: string | undefined;
}

export interface TerminalOutput {
	executions: ExecutionResult[];
}

export type SaveState = "clean" | "dirty" | "saving" | "saved" | "conflict";
export type ConflictReason =
	| "content_changed"
	| "path_not_found"
	| "workflows_would_deactivate";

// Define ConflictInfo locally since it's not in the OpenAPI spec
interface ConflictInfo {
	current_content: string;
	incoming_content: string;
	current_etag: string;
	message: string;
	base_content?: string;
}

// Diagnostic from file save response
export interface FileDiagnostic {
	severity: "error" | "warning" | "info";
	message: string;
	line?: number;
	column?: number;
	source?: string;
}

// Diff preview state for sync UI
export interface DiffPreviewState {
	path: string;
	displayName: string;
	entityType: string;
	localContent: string | null;
	remoteContent: string | null;
	isConflict: boolean;
	isLoading?: boolean;
	resolution?: "keep_local" | "keep_remote";
	onResolve?: (resolution: "keep_local" | "keep_remote") => void;
}

export interface EditorTab {
	file: FileMetadata;
	content: string;
	encoding: "utf-8" | "base64";
	unsavedChanges: boolean;
	saveState?: SaveState; // Visual save state for cloud icons
	conflictReason?: ConflictReason; // Type of conflict (when saveState === "conflict")
	serverContentDiffers?: boolean; // True if server has different content
	cursorPosition?: CursorPosition;
	selectedLanguage?: string;
	etag?: string | undefined; // File version identifier for change detection
	gitConflict?: ConflictInfo; // Git merge conflict data from API (current/incoming content)
	diagnostics?: FileDiagnostic[]; // Diagnostics from last save (syntax errors, etc.)
}

interface EditorState {
	// Editor visibility
	isOpen: boolean;
	layoutMode: LayoutMode;

	// Tabs
	tabs: EditorTab[];
	activeTabIndex: number;
	isLoadingFile: boolean;

	// Indexing state (blocks editor during ID injection)
	isIndexing: boolean;
	indexingMessage: string | null;

	// Layout state
	sidebarPanel: SidebarPanel;
	terminalHeight: number;

	// Terminal output
	terminalOutput: TerminalOutput | null;

	// Currently streaming execution ID (for terminal display)
	currentStreamingExecutionId: string | null;

	// Workflow ID conflict resolution state
	pendingWorkflowConflict: {
		conflicts: WorkflowIdConflict[];
		filePath: string;
		content: string;
		encoding: "utf-8" | "base64";
		etag?: string;
		tabIndex: number;
	} | null;

	// Workflow deactivation protection state
	pendingDeactivationConflict: {
		pendingDeactivations: PendingDeactivation[];
		availableReplacements: AvailableReplacement[];
		filePath: string;
		content: string;
		encoding: "utf-8" | "base64";
		etag?: string;
		tabIndex: number;
	} | null;

	// Diff preview state for sync UI
	diffPreview: DiffPreviewState | null;

	// Computed properties helpers
	get activeTab(): EditorTab | null;
	get openFile(): FileMetadata | null;
	get fileContent(): string;
	get fileEncoding(): "utf-8" | "base64";
	get unsavedChanges(): boolean;

	// Actions
	openEditor: () => void;
	closeEditor: () => void;
	minimizeEditor: () => void;
	restoreEditor: () => void;

	// Tab management
	openFileInTab: (
		file: FileMetadata,
		content?: string,
		encoding?: "utf-8" | "base64",
		etag?: string,
		gitConflict?: ConflictInfo,
	) => void;
	closeTab: (index: number) => void;
	closeAllTabs: () => void;
	closeOtherTabs: (index: number) => void;
	setActiveTab: (index: number) => void;
	reorderTabs: (fromIndex: number, toIndex: number) => void;

	// Active tab operations
	setFileContent: (content: string) => void;
	setLoadingFile: (loading: boolean) => void;
	markSaved: () => void;
	setSaveState: (tabIndex: number, state: SaveState) => void;
	setConflictState: (tabIndex: number, reason: ConflictReason) => void;
	setDiagnostics: (
		tabIndex: number,
		diagnostics: FileDiagnostic[] | undefined,
	) => void;
	resolveConflict: (
		tabIndex: number,
		action: "keep_mine" | "use_server" | "recreate" | "close",
	) => Promise<void>;
	setCursorPosition: (position: CursorPosition) => void;
	setSelectedLanguage: (language: string) => void;

	// File operations
	updateTabPath: (oldPath: string, newPath: string) => void;
	closeTabsByPath: (pathOrPrefix: string, isFolder?: boolean) => number;

	// Legacy compatibility (deprecated, use openFileInTab)
	setOpenFile: (
		file: FileMetadata | null,
		content?: string,
		encoding?: "utf-8" | "base64",
		etag?: string,
	) => void;

	setSidebarPanel: (panel: SidebarPanel) => void;
	setTerminalHeight: (height: number) => void;
	appendTerminalOutput: (result: Omit<ExecutionResult, "timestamp">) => void;
	clearTerminalOutput: () => void;
	setCurrentStreamingExecutionId: (executionId: string | null) => void;

	// Indexing state (blocks editor during ID injection)
	setIndexing: (isIndexing: boolean, message?: string | null) => void;

	// Line reveal (scroll to specific line after file loads)
	pendingLineReveal: number | null;
	revealLine: (line: number) => void;
	clearPendingLineReveal: () => void;

	// Update tab content from server (for ID injection)
	updateTabContent: (tabIndex: number, content: string, etag: string) => void;

	// Workflow ID conflict resolution
	setPendingWorkflowConflict: (
		conflict: {
			conflicts: WorkflowIdConflict[];
			filePath: string;
			content: string;
			encoding: "utf-8" | "base64";
			etag?: string;
			tabIndex: number;
		} | null,
	) => void;
	resolveWorkflowIdConflict: (
		action: "use_existing" | "generate_new" | "cancel",
	) => Promise<FileContentResponse | null>;

	// Deactivation protection
	setPendingDeactivationConflict: (
		conflict: {
			pendingDeactivations: PendingDeactivation[];
			availableReplacements: AvailableReplacement[];
			filePath: string;
			content: string;
			encoding: "utf-8" | "base64";
			etag?: string;
			tabIndex: number;
		} | null,
	) => void;
	resolveDeactivationConflict: (
		action: "force_deactivate" | "apply_replacements" | "cancel",
		replacements?: Record<string, string>,
	) => Promise<FileContentResponse | null>;

	// Diff preview actions
	setDiffPreview: (
		preview:
			| DiffPreviewState
			| null
			| ((prev: DiffPreviewState | null) => DiffPreviewState | null),
	) => void;
	clearDiffPreview: () => void;
}

export const useEditorStore = create<EditorState>()(
	persist(
		(set, get) => ({
			// Initial state
			isOpen: false,
			layoutMode: "fullscreen",

			tabs: [],
			activeTabIndex: -1,
			isLoadingFile: false,

			// Indexing state (blocks editor during ID injection)
			isIndexing: false,
			indexingMessage: null,

			sidebarPanel: "files",
			terminalHeight: 300,

			terminalOutput: null,
			currentStreamingExecutionId: null,

			// Workflow ID conflict resolution state
			pendingWorkflowConflict: null,

			// Workflow deactivation protection state
			pendingDeactivationConflict: null,

			// Diff preview state for sync UI
			diffPreview: null,

			// Line reveal state (for scrolling to specific line after file loads)
			pendingLineReveal: null,

			// Computed properties
			get activeTab(): EditorTab | null {
				const state = get();
				return state.activeTabIndex >= 0 &&
					state.activeTabIndex < state.tabs.length
					? (state.tabs[state.activeTabIndex] ?? null)
					: null;
			},

			get openFile() {
				return get().activeTab?.file || null;
			},

			get fileContent() {
				return get().activeTab?.content || "";
			},

			get fileEncoding() {
				return get().activeTab?.encoding || "utf-8";
			},

			get unsavedChanges() {
				return get().activeTab?.unsavedChanges || false;
			},

			// Actions
			openEditor: () => set({ isOpen: true, layoutMode: "fullscreen" }),

			closeEditor: () =>
				set({
					isOpen: false,
					// Clear all tabs and context when closing
					tabs: [],
					activeTabIndex: -1,
					terminalOutput: null,
				}),

			minimizeEditor: () => set({ layoutMode: "minimized" }),

			restoreEditor: () => set({ layoutMode: "fullscreen" }),

			// Tab management
			openFileInTab: (
				file,
				content = "",
				encoding = "utf-8",
				etag,
				gitConflict,
			) => {
				const state = get();

				// Check if file is already open in a tab
				const existingTabIndex = state.tabs.findIndex(
					(tab) => tab.file.path === file.path,
				);

				if (existingTabIndex >= 0) {
					// File already open - only update if content is provided (preserve in-memory state)
					const existingTab = state.tabs[existingTabIndex];
					if (existingTab) {
						const newTabs = [...state.tabs];
						// Only update if new content provided (from server load)
						// Otherwise just switch tabs (preserve existing content)
						if (content !== undefined && content !== "") {
							newTabs[existingTabIndex] = {
								...existingTab,
								content,
								encoding,
								etag: etag,
								...(gitConflict !== undefined
									? { gitConflict }
									: {}),
								unsavedChanges: false, // Reset since we're loading fresh content
							};
						}
						set({
							tabs: newTabs,
							activeTabIndex: existingTabIndex,
							isLoadingFile: false,
						});
					}
				} else {
					// Open new tab
					const newTab: EditorTab = {
						file,
						content,
						encoding,
						etag: etag,
						...(gitConflict !== undefined ? { gitConflict } : {}),
						unsavedChanges: false,
						cursorPosition: { line: 1, column: 1 },
						selectedLanguage: "plaintext",
					};

					set({
						tabs: [...state.tabs, newTab],
						activeTabIndex: state.tabs.length,
						isLoadingFile: false,
					});
				}
			},

			closeTab: (index) => {
				const state = get();
				if (index < 0 || index >= state.tabs.length) return;

				const newTabs = state.tabs.filter((_, i) => i !== index);
				let newActiveIndex = state.activeTabIndex;

				// Adjust active tab index
				if (newTabs.length === 0) {
					newActiveIndex = -1;
				} else if (index === state.activeTabIndex) {
					// Closing active tab, switch to previous or next
					newActiveIndex = Math.min(index, newTabs.length - 1);
				} else if (index < state.activeTabIndex) {
					// Closing a tab before active, decrease active index
					newActiveIndex = state.activeTabIndex - 1;
				}

				set({ tabs: newTabs, activeTabIndex: newActiveIndex });
			},

			closeAllTabs: () => set({ tabs: [], activeTabIndex: -1 }),

			closeOtherTabs: (index) => {
				const state = get();
				if (index < 0 || index >= state.tabs.length) return;

				const tabToKeep = state.tabs[index];
				if (tabToKeep) {
					set({ tabs: [tabToKeep], activeTabIndex: 0 });
				}
			},

			setActiveTab: (index) => {
				const state = get();
				if (index >= 0 && index < state.tabs.length) {
					set({ activeTabIndex: index });
				}
			},

			reorderTabs: (fromIndex, toIndex) => {
				const state = get();
				if (
					fromIndex < 0 ||
					fromIndex >= state.tabs.length ||
					toIndex < 0 ||
					toIndex >= state.tabs.length ||
					fromIndex === toIndex
				) {
					return;
				}

				const newTabs = [...state.tabs];
				const [movedTab] = newTabs.splice(fromIndex, 1);
				if (movedTab) {
					newTabs.splice(toIndex, 0, movedTab);
				}

				// Adjust active tab index if needed
				let newActiveIndex = state.activeTabIndex;
				if (fromIndex === state.activeTabIndex) {
					// The active tab was moved
					newActiveIndex = toIndex;
				} else if (
					fromIndex < state.activeTabIndex &&
					toIndex >= state.activeTabIndex
				) {
					// Tab moved from before active to after/at active
					newActiveIndex--;
				} else if (
					fromIndex > state.activeTabIndex &&
					toIndex <= state.activeTabIndex
				) {
					// Tab moved from after active to before/at active
					newActiveIndex++;
				}

				set({ tabs: newTabs, activeTabIndex: newActiveIndex });
			},

			// Active tab operations
			setFileContent: (content) => {
				const state = get();
				if (state.activeTabIndex < 0) return;

				const newTabs = [...state.tabs];
				const activeTab = newTabs[state.activeTabIndex];
				if (activeTab) {
					newTabs[state.activeTabIndex] = {
						...activeTab,
						content,
						unsavedChanges: activeTab.content !== content,
					};
					set({ tabs: newTabs });
				}
			},

			setLoadingFile: (loading) => set({ isLoadingFile: loading }),

			markSaved: () => {
				const state = get();
				if (state.activeTabIndex < 0) return;

				const newTabs = [...state.tabs];
				const activeTab = newTabs[state.activeTabIndex];
				if (activeTab) {
					newTabs[state.activeTabIndex] = {
						...activeTab,
						unsavedChanges: false,
					};
					set({ tabs: newTabs });
				}
			},

			setSaveState: (tabIndex, saveState) => {
				const state = get();
				if (tabIndex < 0 || tabIndex >= state.tabs.length) return;

				const newTabs = [...state.tabs];
				const tab = newTabs[tabIndex];
				if (tab) {
					newTabs[tabIndex] = {
						...tab,
						saveState,
					};
					set({ tabs: newTabs });
				}
			},

			setConflictState: (tabIndex, reason) => {
				const state = get();
				if (tabIndex < 0 || tabIndex >= state.tabs.length) return;

				const newTabs = [...state.tabs];
				const tab = newTabs[tabIndex];
				if (tab) {
					newTabs[tabIndex] = {
						...tab,
						saveState: "conflict",
						conflictReason: reason,
					};
					set({ tabs: newTabs });
				}
			},

			setDiagnostics: (tabIndex, diagnostics) => {
				const state = get();
				if (tabIndex < 0 || tabIndex >= state.tabs.length) return;

				const newTabs = [...state.tabs];
				const tab = newTabs[tabIndex];
				if (tab) {
					newTabs[tabIndex] = {
						...tab,
						diagnostics,
					};
					set({ tabs: newTabs });
				}
			},

			resolveConflict: async (tabIndex, action) => {
				const state = get();
				if (tabIndex < 0 || tabIndex >= state.tabs.length) return;

				const tab = state.tabs[tabIndex];
				if (!tab || tab.saveState !== "conflict") return;

				switch (action) {
					case "keep_mine":
					case "recreate":
						// Force write to server (no etag check)
						try {
							const response = await fileService.writeFile(
								tab.file.path,
								tab.content,
								tab.encoding,
							);
							// Clear conflict state and mark as saved with new etag
							const newTabs = [...state.tabs];
							const { conflictReason, ...tabWithoutConflict } =
								tab;
							void conflictReason; // Intentionally discard
							newTabs[tabIndex] = {
								...tabWithoutConflict,
								etag: response.etag,
								saveState: "saved",
								unsavedChanges: false,
							};
							set({ tabs: newTabs });

							// Show green cloud briefly
							setTimeout(() => {
								const currentState = get();
								const currentTabs = [...currentState.tabs];
								if (
									currentTabs[tabIndex]?.saveState === "saved"
								) {
									currentTabs[tabIndex] = {
										...currentTabs[tabIndex]!,
										saveState: "clean",
									};
									set({ tabs: currentTabs });
								}
							}, 2500);
						} catch (error) {
							console.error("Failed to resolve conflict:", error);
						}
						break;

					case "use_server":
						// Reload from server
						try {
							const serverFile = await fileService.readFile(
								tab.file.path,
							);
							const newTabs = [...state.tabs];
							const { conflictReason, ...tabWithoutConflict } =
								tab;
							void conflictReason; // Intentionally discard
							newTabs[tabIndex] = {
								...tabWithoutConflict,
								content: serverFile.content,
								encoding: serverFile.encoding as
									| "utf-8"
									| "base64",
								etag: serverFile.etag,
								saveState: "clean",
								unsavedChanges: false,
							};
							set({ tabs: newTabs });
						} catch (error) {
							console.error(
								"Failed to reload from server:",
								error,
							);
						}
						break;

					case "close":
						// Close the tab
						get().closeTab(tabIndex);
						break;
				}
			},

			setCursorPosition: (position) => {
				const state = get();
				if (state.activeTabIndex < 0) return;

				const newTabs = [...state.tabs];
				const activeTab = newTabs[state.activeTabIndex];
				if (activeTab) {
					newTabs[state.activeTabIndex] = {
						...activeTab,
						cursorPosition: position,
					};
					set({ tabs: newTabs });
				}
			},

			setSelectedLanguage: (language) => {
				const state = get();
				if (state.activeTabIndex < 0) return;

				const newTabs = [...state.tabs];
				const activeTab = newTabs[state.activeTabIndex];
				if (activeTab) {
					newTabs[state.activeTabIndex] = {
						...activeTab,
						selectedLanguage: language,
					};
					set({ tabs: newTabs });
				}
			},

			// Legacy compatibility - opens file in new tab
			setOpenFile: (file, content = "", encoding = "utf-8", etag) => {
				if (file) {
					get().openFileInTab(file, content, encoding, etag);
				}
			},

			setSidebarPanel: (panel) => set({ sidebarPanel: panel }),

			setTerminalHeight: (height) => set({ terminalHeight: height }),

			appendTerminalOutput: (result) => {
				const state = get();
				const newExecution: ExecutionResult = {
					...result,
					timestamp: new Date().toISOString(),
				};

				const currentOutput = state.terminalOutput || {
					executions: [],
				};
				set({
					terminalOutput: {
						executions: [...currentOutput.executions, newExecution],
					},
				});
			},

			clearTerminalOutput: () => set({ terminalOutput: null }),

			setCurrentStreamingExecutionId: (executionId) =>
				set({ currentStreamingExecutionId: executionId }),

			// Indexing state (blocks editor during ID injection)
			setIndexing: (isIndexing, message = null) =>
				set({ isIndexing, indexingMessage: message }),

			// Line reveal actions (scroll to specific line after file loads)
			revealLine: (line) => set({ pendingLineReveal: line }),
			clearPendingLineReveal: () => set({ pendingLineReveal: null }),

			// Update tab content from server (for ID injection)
			updateTabContent: (tabIndex, content, etag) => {
				const state = get();
				if (tabIndex < 0 || tabIndex >= state.tabs.length) return;

				const newTabs = [...state.tabs];
				const tab = newTabs[tabIndex];
				if (tab) {
					newTabs[tabIndex] = {
						...tab,
						content,
						etag,
						unsavedChanges: false,
						saveState: "saved",
					};
					set({ tabs: newTabs });
				}
			},

			// Update tab path after file/folder rename
			updateTabPath: (oldPath, newPath) => {
				const state = get();
				const newTabs = state.tabs.map((tab) => {
					if (tab.file.path === oldPath) {
						// Direct match - update the path
						return {
							...tab,
							file: {
								...tab.file,
								path: newPath,
								name: newPath.split("/").pop() || newPath,
							},
						};
					}
					// Check if it's inside a renamed folder
					if (tab.file.path.startsWith(oldPath + "/")) {
						const newFilePath = tab.file.path.replace(
							oldPath,
							newPath,
						);
						return {
							...tab,
							file: {
								...tab.file,
								path: newFilePath,
							},
						};
					}
					return tab;
				});

				// Check if active tab was affected
				let newActiveIndex = state.activeTabIndex;
				if (
					state.activeTabIndex >= 0 &&
					state.activeTabIndex < state.tabs.length
				) {
					const activeTab = state.tabs[state.activeTabIndex];
					if (
						activeTab &&
						(activeTab.file.path === oldPath ||
							activeTab.file.path.startsWith(oldPath + "/"))
					) {
						// Active tab path changed, keep it active
						newActiveIndex = state.tabs.findIndex(
							(tab) =>
								tab.file.path === oldPath ||
								tab.file.path.startsWith(oldPath + "/"),
						);
					}
				}

				set({ tabs: newTabs, activeTabIndex: newActiveIndex });
			},

			// Close tabs by path (for delete operations)
			closeTabsByPath: (pathOrPrefix, isFolder = false) => {
				const state = get();
				const closedCount = state.tabs.filter((tab) =>
					isFolder
						? tab.file.path.startsWith(pathOrPrefix + "/") ||
							tab.file.path === pathOrPrefix
						: tab.file.path === pathOrPrefix,
				).length;

				const newTabs = state.tabs.filter((tab) =>
					isFolder
						? !(
								tab.file.path.startsWith(pathOrPrefix + "/") ||
								tab.file.path === pathOrPrefix
							)
						: tab.file.path !== pathOrPrefix,
				);

				// Adjust active index if needed
				let newActiveIndex = state.activeTabIndex;
				if (newActiveIndex >= newTabs.length) {
					newActiveIndex = newTabs.length - 1;
				}

				set({ tabs: newTabs, activeTabIndex: newActiveIndex });
				return closedCount;
			},

			// Workflow ID conflict resolution
			setPendingWorkflowConflict: (conflict) =>
				set({ pendingWorkflowConflict: conflict }),

			resolveWorkflowIdConflict: async (action) => {
				const state = get();
				const conflict = state.pendingWorkflowConflict;
				if (!conflict) return null;

				// Clear the pending conflict first
				set({ pendingWorkflowConflict: null });

				if (action === "cancel") {
					return null;
				}

				try {
					if (action === "use_existing") {
						// Build the force_ids map from conflicts
						const forceIds: Record<string, string> = {};
						for (const c of conflict.conflicts) {
							forceIds[c.function_name] = c.existing_id;
						}

						// Re-save with force_ids to inject existing IDs
						const response = await fileService.writeFile(
							conflict.filePath,
							conflict.content,
							conflict.encoding,
							conflict.etag,
							true, // index=true to inject IDs
							forceIds,
						);

						return response;
					} else {
						// generate_new: Just save normally, IDs will be auto-generated
						const response = await fileService.writeFile(
							conflict.filePath,
							conflict.content,
							conflict.encoding,
							conflict.etag,
							true, // index=true to inject new IDs
						);

						return response;
					}
				} catch (error) {
					console.error(
						"Failed to resolve workflow ID conflict:",
						error,
					);
					return null;
				}
			},

			// Deactivation protection
			setPendingDeactivationConflict: (conflict) =>
				set({ pendingDeactivationConflict: conflict }),

			resolveDeactivationConflict: async (action, replacements) => {
				const state = get();
				const conflict = state.pendingDeactivationConflict;
				if (!conflict) return null;

				// Clear the pending conflict first
				set({ pendingDeactivationConflict: null });

				if (action === "cancel") {
					return null;
				}

				try {
					if (action === "force_deactivate") {
						// Re-save with force_deactivation=true
						const response = await fileService.writeFile(
							conflict.filePath,
							conflict.content,
							conflict.encoding,
							conflict.etag,
							false, // index
							undefined, // forceIds
							true, // forceDeactivation
						);
						return response;
					} else {
						// apply_replacements: Save with replacements map
						const response = await fileService.writeFile(
							conflict.filePath,
							conflict.content,
							conflict.encoding,
							conflict.etag,
							false, // index
							undefined, // forceIds
							false, // forceDeactivation
							replacements,
						);
						return response;
					}
				} catch (error) {
					console.error(
						"Failed to resolve deactivation conflict:",
						error,
					);
					return null;
				}
			},

			// Diff preview actions
			setDiffPreview: (previewOrUpdater) => {
				if (typeof previewOrUpdater === "function") {
					const currentPreview = get().diffPreview;
					set({ diffPreview: previewOrUpdater(currentPreview) });
				} else {
					set({ diffPreview: previewOrUpdater });
				}
			},
			clearDiffPreview: () => set({ diffPreview: null }),
		}),
		{
			name: "editor-storage", // localStorage key
			// Only persist these fields
			partialize: (state) => ({
				tabs: state.tabs.map((tab) => ({
					...tab,
					content: "", // Don't persist content, reload from server
					unsavedChanges: false, // Reset unsaved changes on reload
				})),
				activeTabIndex: state.activeTabIndex,
				sidebarPanel: state.sidebarPanel,
				terminalHeight: state.terminalHeight,
				layoutMode: state.layoutMode,
				// Do NOT persist isLoadingFile
			}),
		},
	),
);
