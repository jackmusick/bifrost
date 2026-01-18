/**
 * Workspace File Tree Component
 *
 * A specialized version of the modular FileTree for the workspace code editor.
 * Integrates with:
 * - useEditorStore for tab management and file opening
 * - fileService for workspace-specific operations
 *
 * Note: Desktop file upload functionality is handled separately in the
 * original FileTree component. This modular version focuses on the core
 * file tree functionality without the upload features for now.
 */

import { useState, useMemo } from "react";
import { toast } from "sonner";
import { FileTree } from "./FileTree";
import { workspaceOperations } from "./adapters/workspaceOperations";
import { defaultIconResolver } from "./icons";
import { useEditorStore } from "@/stores/editorStore";
import { fileService, type FileMetadata } from "@/services/fileService";
import { WorkflowIdConflictDialog } from "@/components/editor/WorkflowIdConflictDialog";
import type { FileNode, FileContent, EditorCallbacks, FileTreeConfig } from "./types";
import type { components } from "@/lib/v1";

type WorkflowIdConflict = components["schemas"]["WorkflowIdConflict"];

/**
 * Convert a file node to FileMetadata for the editor store
 */
function toFileMetadata(file: FileNode): FileMetadata {
	return {
		path: file.path,
		name: file.name,
		type: file.type,
		size: file.size,
		extension: file.extension,
		modified: file.modified,
		// Cast entityType to the expected union type
		entity_type: (file.entityType as FileMetadata["entity_type"]) ?? null,
		entity_id: file.entityId ?? null,
	};
}

/**
 * Workspace File Tree Component
 *
 * Use this component for the code editor workspace.
 * For other contexts (JSX editor, org-scoped), use the generic FileTree component.
 */
export function WorkspaceFileTree({ className }: { className?: string }) {
	const tabs = useEditorStore((state) => state.tabs);
	const activeTabIndex = useEditorStore((state) => state.activeTabIndex);
	const setOpenFile = useEditorStore((state) => state.setOpenFile);
	const setLoadingFile = useEditorStore((state) => state.setLoadingFile);
	const updateTabPath = useEditorStore((state) => state.updateTabPath);
	const closeTabsByPath = useEditorStore((state) => state.closeTabsByPath);

	// Get the currently open file path
	const openFilePath = useMemo(() => {
		const activeTab =
			activeTabIndex >= 0 && activeTabIndex < tabs.length
				? tabs[activeTabIndex]
				: null;
		return activeTab?.file?.path || null;
	}, [tabs, activeTabIndex]);

	// Workflow ID conflict state for uploads
	const [uploadWorkflowConflicts, setUploadWorkflowConflicts] = useState<{
		conflicts: WorkflowIdConflict[];
		files: Array<{
			filePath: string;
			content: string;
			encoding: "utf-8" | "base64";
			conflictIds: Record<string, string>;
		}>;
	} | null>(null);

	// Editor callbacks to integrate with the editor store
	const editorCallbacks = useMemo<EditorCallbacks>(
		() => ({
			onFileOpen: (file: FileNode, content: FileContent) => {
				const metadata = toFileMetadata(file);
				setOpenFile(metadata, content.content, content.encoding, content.etag);
			},
			onFileDeleted: (path: string, isFolder: boolean) => {
				closeTabsByPath(path, isFolder);
			},
			onFileRenamed: (oldPath: string, newPath: string) => {
				updateTabPath(oldPath, newPath);
			},
			isFileSelected: (path: string) => {
				return openFilePath === path;
			},
			onLoadingChange: (isLoading: boolean) => {
				setLoadingFile(isLoading);
			},
		}),
		[openFilePath, setOpenFile, closeTabsByPath, updateTabPath, setLoadingFile],
	);

	// Configuration for workspace file tree
	const config = useMemo<FileTreeConfig>(
		() => ({
			enableUpload: false, // Upload handled in original FileTree for now
			enableDragMove: true,
			enableCreate: true,
			enableRename: true,
			enableDelete: true,
			emptyMessage: "No files found",
			loadingMessage: "Loading files...",
		}),
		[],
	);

	return (
		<>
			<FileTree
				operations={workspaceOperations}
				iconResolver={defaultIconResolver}
				editor={editorCallbacks}
				config={config}
				className={className}
			/>

			{/* Workflow ID Conflict Dialog for Uploads */}
			<WorkflowIdConflictDialog
				conflicts={uploadWorkflowConflicts?.conflicts ?? []}
				open={uploadWorkflowConflicts !== null}
				onUseExisting={async () => {
					if (!uploadWorkflowConflicts) return;

					try {
						for (const file of uploadWorkflowConflicts.files) {
							await fileService.writeFile(
								file.filePath,
								file.content,
								file.encoding,
								undefined,
								true,
								file.conflictIds,
							);
						}
						toast.success("Existing workflow IDs preserved");
					} catch (error) {
						console.error("Failed to apply existing IDs:", error);
						toast.error("Failed to preserve workflow IDs");
					}

					setUploadWorkflowConflicts(null);
				}}
				onGenerateNew={() => {
					toast.info("New workflow IDs were generated");
					setUploadWorkflowConflicts(null);
				}}
				onCancel={() => {
					setUploadWorkflowConflicts(null);
				}}
			/>
		</>
	);
}
