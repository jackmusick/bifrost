/**
 * App Code Editor Layout
 *
 * Complete editor layout for App Builder with:
 * - File tree sidebar (using modular FileTree)
 * - Code editor (Monaco)
 * - Live preview panel
 */

import { useState, useCallback, useMemo, useEffect } from "react";
import { Button } from "@/components/ui/button";
import {
	FileTree,
	createAppCodeOperations,
	appCodeIconResolver,
} from "@/components/file-tree";
import { AppCodeEditor } from "./AppCodeEditor";
import { AppCodePreview } from "./AppCodePreview";
import { useAppCodeEditor } from "./useAppCodeEditor";
import { toast } from "sonner";
import {
	Save,
	Play,
	Code,
	Eye,
	PanelLeftClose,
	PanelLeft,
	LayoutGrid,
} from "lucide-react";
import type { FileNode, FileContent, EditorCallbacks } from "@/components/file-tree/types";

interface AppCodeEditorLayoutProps {
	/** Application UUID */
	appId: string;
	/** Version UUID (draft or active) */
	versionId: string;
	/** Application name for display */
	appName?: string;
	/** Callback when files are saved */
	onSave?: (path: string, source: string, compiled: string) => Promise<void>;
}

type ViewMode = "split" | "code" | "preview";

/**
 * App Code Editor Layout
 *
 * Provides a complete IDE-like experience for editing App Builder apps.
 */
export function AppCodeEditorLayout({
	appId,
	versionId,
	appName = "App",
	onSave,
}: AppCodeEditorLayoutProps) {
	// Layout state
	const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
	const [viewMode, setViewMode] = useState<ViewMode>("split");

	// File state
	const [currentFile, setCurrentFile] = useState<{
		path: string;
		name: string;
		source: string;
		compiled: string | null;
	} | null>(null);

	// Create app code operations for the file tree
	const operations = useMemo(
		() => createAppCodeOperations(appId, versionId),
		[appId, versionId],
	);

	// App code editor hook for managing source, compilation, etc.
	const {
		state: editorState,
		setSource,
		save: triggerSave,
	} = useAppCodeEditor({
		initialSource: currentFile?.source ?? "",
		initialCompiled: currentFile?.compiled ?? undefined,
		compileDelay: 300,
		onSave: async (source, compiled) => {
			if (!currentFile) return;

			try {
				// Save to API
				await operations.write(currentFile.path, source);

				// Call external save handler if provided
				await onSave?.(currentFile.path, source, compiled);

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
							title="Split view"
						>
							<LayoutGrid className="h-4 w-4" />
						</Button>
						<Button
							variant={viewMode === "preview" ? "secondary" : "ghost"}
							size="icon"
							className="h-7 w-7"
							onClick={() => setViewMode("preview")}
							title="Preview only"
						>
							<Eye className="h-4 w-4" />
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
				{/* Sidebar - File Tree */}
				{!sidebarCollapsed && (
					<div className="w-60 border-r flex-shrink-0 overflow-auto">
						<FileTree
							operations={operations}
							iconResolver={appCodeIconResolver}
							editor={editorCallbacks}
							config={{
								enableUpload: false,
								enableDragMove: true,
								enableCreate: true,
								enableRename: true,
								enableDelete: true,
								emptyMessage: "No files yet",
								loadingMessage: "Loading files...",
							}}
						/>
					</div>
				)}

				{/* Editor and Preview */}
				<div className="flex-1 min-w-0 flex">
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
										language="javascript"
									/>
								) : (
									<div className="h-full flex items-center justify-center text-muted-foreground">
										<p className="text-sm">
											Select a file to edit
										</p>
									</div>
								)}
							</div>

							{/* Preview */}
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
									language="javascript"
								/>
							) : (
								<div className="h-full flex items-center justify-center text-muted-foreground">
									<p className="text-sm">Select a file to edit</p>
								</div>
							)}
						</div>
					) : (
						<div className="flex-1 min-w-0 overflow-auto">
							<AppCodePreview
								compiled={editorState.compiled}
								errors={editorState.errors}
								isCompiling={editorState.isCompiling}
								bordered={false}
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
