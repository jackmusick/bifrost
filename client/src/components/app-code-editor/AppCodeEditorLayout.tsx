/**
 * App Code Editor Layout
 *
 * Complete editor layout for App Builder with:
 * - File tree sidebar (using modular FileTree)
 * - Code editor (Monaco)
 * - Live preview panel
 */

import { useState, useCallback, useMemo, useEffect, useRef } from "react";
import { useLocation } from "react-router-dom";
import { Button } from "@/components/ui/button";
import {
	FileTree,
	createAppCodeOperations,
	appCodeIconResolver,
	validateAppCodePath,
} from "@/components/file-tree";
import { AppCodeEditor } from "./AppCodeEditor";
import { AppCodePreview } from "./AppCodePreview";
import { useAppCodeEditor } from "./useAppCodeEditor";
import { useAppCodeUpdates, type LastUpdate } from "@/hooks/useAppCodeUpdates";
import { authFetch } from "@/lib/api-client";
import { JsxAppShell } from "@/components/jsx-app/JsxAppShell";
import { toast } from "sonner";
import {
	Save,
	Play,
	Code,
	Eye,
	PanelLeftClose,
	PanelLeft,
	LayoutGrid,
	AppWindow,
} from "lucide-react";
import { DependencyPanel } from "./DependencyPanel";
import type { FileNode, FileContent, EditorCallbacks } from "@/components/file-tree/types";

interface AppCodeEditorLayoutProps {
	/** Application UUID */
	appId: string;
	/** Application name for display */
	appName?: string;
	/** Application slug for building base path */
	appSlug?: string;
	/** Callback when files are saved */
	onSave?: (path: string, source: string, compiled: string) => Promise<void>;
}

type ViewMode = "split" | "code" | "preview" | "app";
type SidebarTab = "files" | "packages";

/**
 * App Code Editor Layout
 *
 * Provides a complete IDE-like experience for editing App Builder apps.
 */
export function AppCodeEditorLayout({
	appId,
	appName = "App",
	appSlug,
	onSave,
}: AppCodeEditorLayoutProps) {
	const location = useLocation();

	// Layout state
	const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
	const [viewMode, setViewMode] = useState<ViewMode>("split");
	const [sidebarTab, setSidebarTab] = useState<SidebarTab>("files");

	// Compute base path for the app preview
	// The editor is now at /apps/{slug}/edit/* so we need to extract that base
	const basePath = useMemo(() => {
		if (appSlug) {
			return `/apps/${appSlug}/edit`;
		}
		// Fallback: extract from current location
		// Pattern: /apps/{slug}/edit/...
		const match = location.pathname.match(/^(\/apps\/[^/]+\/edit)/);
		return match ? match[1] : "/";
	}, [appSlug, location.pathname]);

	// Get the current route within the app (for display)
	const currentAppRoute = useMemo(() => {
		const prefix = basePath;
		if (location.pathname.startsWith(prefix)) {
			const route = location.pathname.slice(prefix.length) || "/";
			return route;
		}
		return "/";
	}, [basePath, location.pathname]);

	// File state
	const [currentFile, setCurrentFile] = useState<{
		path: string;
		name: string;
		source: string;
		compiled: string | null;
	} | null>(null);

	// Create app code operations for the file tree
	const operations = useMemo(
		() => createAppCodeOperations(appId),
		[appId],
	);

	// Track file tree refresh counter - increments to trigger refresh
	const [fileTreeRefresh, setFileTreeRefresh] = useState(0);

	// Use a ref to track current file path so the callback can access it
	const currentFilePathRef = useRef<string | null>(null);
	useEffect(() => {
		currentFilePathRef.current = currentFile?.path ?? null;
	}, [currentFile?.path]);

	// Handle real-time updates from WebSocket via callback
	const handleWebSocketUpdate = useCallback(
		(update: LastUpdate) => {
			const { action, path, userName } = update;

			// Show toast for external changes (not from this editor session)
			if (action === "create") {
				toast.info(`${userName} created ${path.split("/").pop()}`, {
					duration: 2000,
				});
				// Trigger file tree refresh
				setFileTreeRefresh((n) => n + 1);
			} else if (action === "delete") {
				toast.info(`${userName} deleted ${path.split("/").pop()}`, {
					duration: 2000,
				});
				// If the deleted file was open, close it
				if (currentFilePathRef.current === path) {
					setCurrentFile(null);
				}
				// Trigger file tree refresh
				setFileTreeRefresh((n) => n + 1);
			} else if (action === "update") {
				// If the updated file is currently open, show a toast with reload option
				if (currentFilePathRef.current === path) {
					toast.info(`${userName} updated this file`, {
						duration: 2000,
						action: {
							label: "Reload",
							onClick: async () => {
								// Re-fetch the file content
								try {
									const content = await operations.read(path);
									if (content) {
										setCurrentFile((prev) =>
											prev
												? { ...prev, source: content.content }
												: null,
										);
									}
								} catch (error) {
									console.error("[AppCodeEditorLayout] Failed to reload file:", error);
								}
							},
						},
					});
				}
			}
		},
		[operations],
	);

	// Real-time updates via WebSocket
	useAppCodeUpdates({
		appId,
		enabled: true,
		onUpdate: handleWebSocketUpdate,
	});

	// App code editor hook for managing source, compilation, etc.
	const {
		state: editorState,
		setSource,
		setCompiled,
		save: triggerSave,
	} = useAppCodeEditor({
		initialSource: currentFile?.source ?? "",
		initialCompiled: currentFile?.compiled ?? undefined,
		compileDelay: 300,
		onSave: async (source, compiled) => {
			if (!currentFile) return;

			try {
				// Save to API and get compiled code back
				const response = await authFetch(
					`/api/applications/${appId}/files/${encodeURIComponent(currentFile.path)}`,
					{
						method: "PUT",
						headers: { "Content-Type": "application/json" },
						body: JSON.stringify({ source }),
					},
				);

				if (!response.ok) {
					throw new Error(`Failed to save: ${response.statusText}`);
				}

				const data = await response.json();

				// Update compiled code from server response
				if (data.compiled) {
					setCompiled(data.compiled);
				}

				// Call external save handler if provided
				await onSave?.(currentFile.path, source, data.compiled ?? compiled);

				toast.success("File saved", { description: currentFile.name });
			} catch (error) {
				toast.error("Failed to save file", {
					description: error instanceof Error ? error.message : "Unknown error",
				});
				throw error;
			}
		},
	});

	// Handle file open from file tree
	const handleFileOpen = useCallback(
		(file: FileNode, content: FileContent) => {
			// Get compiled from metadata, ensuring it's a string or null
			const compiledValue = file.metadata?.compiled;
			const compiled = typeof compiledValue === "string" ? compiledValue : null;

			setCurrentFile({
				path: file.path,
				name: file.name,
				source: content.content,
				compiled,
			});
		},
		[],
	);

	// Update editor source when file changes
	// We intentionally only reset on path change, not content change
	const currentPath = currentFile?.path;
	const currentSource = currentFile?.source;
	useEffect(() => {
		if (currentSource !== undefined) {
			setSource(currentSource);
		}
	}, [currentPath, currentSource, setSource]);

	// Editor callbacks for file tree integration
	const editorCallbacks = useMemo<EditorCallbacks>(
		() => ({
			onFileOpen: handleFileOpen,
			onFileDeleted: (path: string) => {
				if (currentFile?.path === path) {
					setCurrentFile(null);
				}
			},
			onFileRenamed: (oldPath: string, newPath: string) => {
				if (currentFile?.path === oldPath) {
					setCurrentFile((prev) =>
						prev
							? {
									...prev,
									path: newPath,
									name: newPath.split("/").pop() || newPath,
								}
							: null,
					);
				}
			},
			isFileSelected: (path: string) => currentFile?.path === path,
		}),
		[currentFile, handleFileOpen],
	);

	// Handle manual save
	const handleSave = useCallback(async () => {
		if (!currentFile || editorState.errors.length > 0) {
			if (editorState.errors.length > 0) {
				toast.error("Cannot save with errors");
			}
			return;
		}

		await triggerSave();
	}, [currentFile, editorState.errors, triggerSave]);

	// Handle run/preview
	const handleRun = useCallback(() => {
		if (viewMode === "code") {
			setViewMode("split");
		}
	}, [viewMode]);

	return (
		<div className="h-full flex flex-col bg-background">
			{/* Toolbar */}
			<div className="flex items-center justify-between h-10 px-2 border-b bg-muted/30">
				<div className="flex items-center gap-2">
					{/* Sidebar toggle */}
					<Button
						variant="ghost"
						size="icon"
						className="h-7 w-7"
						onClick={() => setSidebarCollapsed(!sidebarCollapsed)}
						title={sidebarCollapsed ? "Show sidebar" : "Hide sidebar"}
					>
						{sidebarCollapsed ? (
							<PanelLeft className="h-4 w-4" />
						) : (
							<PanelLeftClose className="h-4 w-4" />
						)}
					</Button>

					{/* File name */}
					<span className="text-sm font-medium truncate max-w-[200px]">
						{currentFile?.name || appName}
					</span>

					{/* Unsaved indicator */}
					{editorState.hasUnsavedChanges && (
						<span className="text-xs text-muted-foreground">
							(unsaved)
						</span>
					)}
				</div>

				<div className="flex items-center gap-1">
					{/* Current app route indicator (in app view) */}
					{viewMode === "app" && (
						<span className="text-xs text-muted-foreground mr-2 font-mono">
							{currentAppRoute}
						</span>
					)}

					{/* View mode toggles */}
					<div className="flex items-center gap-0.5 mr-2">
						<Button
							variant={viewMode === "code" ? "secondary" : "ghost"}
							size="icon"
							className="h-7 w-7"
							onClick={() => setViewMode("code")}
							title="Code only"
						>
							<Code className="h-4 w-4" />
						</Button>
						<Button
							variant={viewMode === "split" ? "secondary" : "ghost"}
							size="icon"
							className="h-7 w-7"
							onClick={() => setViewMode("split")}
							title="Split view (code + file preview)"
						>
							<LayoutGrid className="h-4 w-4" />
						</Button>
						<Button
							variant={viewMode === "preview" ? "secondary" : "ghost"}
							size="icon"
							className="h-7 w-7"
							onClick={() => setViewMode("preview")}
							title="File preview only"
						>
							<Eye className="h-4 w-4" />
						</Button>
						<Button
							variant={viewMode === "app" ? "secondary" : "ghost"}
							size="icon"
							className="h-7 w-7"
							onClick={() => setViewMode("app")}
							title="Full app preview (with navigation)"
						>
							<AppWindow className="h-4 w-4" />
						</Button>
					</div>

					{/* Run button */}
					<Button
						variant="ghost"
						size="sm"
						onClick={handleRun}
						className="gap-1"
						title="Run preview (Cmd+Enter)"
					>
						<Play className="h-4 w-4" />
						Run
					</Button>

					{/* Save button */}
					<Button
						variant="ghost"
						size="sm"
						onClick={handleSave}
						disabled={
							!currentFile ||
							!editorState.hasUnsavedChanges ||
							editorState.errors.length > 0
						}
						className="gap-1"
						title="Save (Cmd+S)"
					>
						<Save className="h-4 w-4" />
						Save
					</Button>
				</div>
			</div>

			{/* Main content */}
			<div className="flex-1 min-h-0 flex">
				{/* Sidebar */}
				{!sidebarCollapsed && (
					<div className="w-60 border-r flex-shrink-0 flex flex-col">
						{/* Tab switcher */}
						<div className="flex border-b">
							<button
								className={`flex-1 px-3 py-1.5 text-xs font-medium ${
									sidebarTab === "files"
										? "border-b-2 border-primary text-foreground"
										: "text-muted-foreground hover:text-foreground"
								}`}
								onClick={() => setSidebarTab("files")}
							>
								Files
							</button>
							<button
								className={`flex-1 px-3 py-1.5 text-xs font-medium ${
									sidebarTab === "packages"
										? "border-b-2 border-primary text-foreground"
										: "text-muted-foreground hover:text-foreground"
								}`}
								onClick={() => setSidebarTab("packages")}
							>
								Packages
							</button>
						</div>

						{/* Tab content */}
						{sidebarTab === "files" ? (
							<div className="flex-1 overflow-auto">
								<FileTree
									operations={operations}
									iconResolver={appCodeIconResolver}
									editor={editorCallbacks}
									refreshTrigger={fileTreeRefresh}
									config={{
										enableUpload: false,
										enableDragMove: true,
										enableCreate: true,
										enableRename: true,
										enableDelete: true,
										emptyMessage: "No files yet",
										loadingMessage: "Loading files...",
										pathValidator: validateAppCodePath,
									}}
								/>
							</div>
						) : (
							<DependencyPanel appId={appId} />
						)}
					</div>
				)}

				{/* Editor and Preview */}
				<div className="flex-1 min-h-0 flex">
					{viewMode === "split" ? (
						<>
							{/* Code Editor */}
							<div className="flex-1 min-w-0 border-r">
								{currentFile ? (
									<AppCodeEditor
										value={editorState.source}
										onChange={setSource}
										onSave={handleSave}
										errors={editorState.errors}
										path={currentFile.path}
									/>
								) : (
									<div className="h-full flex items-center justify-center text-muted-foreground">
										<p className="text-sm">
											Select a file to edit
										</p>
									</div>
								)}
							</div>

							{/* File Preview */}
							<div className="flex-1 min-w-0 overflow-auto">
								<AppCodePreview
									compiled={editorState.compiled}
									errors={editorState.errors}
									isCompiling={editorState.isCompiling}
									bordered={false}
								/>
							</div>
						</>
					) : viewMode === "code" ? (
						<div className="flex-1 min-w-0">
							{currentFile ? (
								<AppCodeEditor
									value={editorState.source}
									onChange={setSource}
									onSave={handleSave}
									errors={editorState.errors}
									path={currentFile.path}
								/>
							) : (
								<div className="h-full flex items-center justify-center text-muted-foreground">
									<p className="text-sm">Select a file to edit</p>
								</div>
							)}
						</div>
					) : viewMode === "preview" ? (
						<div className="flex-1 min-w-0 overflow-auto">
							<AppCodePreview
								compiled={editorState.compiled}
								errors={editorState.errors}
								isCompiling={editorState.isCompiling}
								bordered={false}
							/>
						</div>
					) : (
						/* App preview - full app with navigation */
						<div className="flex-1 min-h-0 overflow-hidden">
							<JsxAppShell
								appId={appId}
								appSlug={appSlug || ""}
								isPreview={true}
							/>
						</div>
					)}
				</div>
			</div>

			{/* Status bar */}
			<div className="flex items-center justify-between h-6 px-2 border-t bg-muted/30 text-xs text-muted-foreground">
				<div className="flex items-center gap-4">
					{currentFile && <span>{currentFile.path}</span>}
				</div>
				<div className="flex items-center gap-4">
					{editorState.errors.length > 0 && (
						<span className="text-red-500">
							{editorState.errors.length} error
							{editorState.errors.length > 1 ? "s" : ""}
						</span>
					)}
					{editorState.isCompiling && (
						<span className="text-yellow-500">Compiling...</span>
					)}
				</div>
			</div>
		</div>
	);
}
