/**
 * Workspace File Tree Component
 *
 * A specialized version of the modular FileTree for the workspace code editor.
 * Integrates with:
 * - useEditorStore for tab management and file opening
 * - fileService for workspace-specific operations
 * - Organization-scoped file filtering (flat folder hierarchy with org filter)
 *
 * Note: Desktop file upload functionality is handled separately in the
 * original FileTree component. This modular version focuses on the core
 * file tree functionality without the upload features for now.
 */

import { useState, useMemo, useCallback, useEffect } from "react";
import { toast } from "sonner";
import { cn } from "@/lib/utils";
import { FileTree } from "./FileTree";
import { defaultIconResolver } from "./icons";
import { useEditorStore } from "@/stores/editorStore";
import { fileService, type FileMetadata } from "@/services/fileService";
import {
	createOrgScopedFileOperations,
	changeEntityOrganization,
} from "@/services/orgScopedFileOperations";
import { useOrganizations } from "@/hooks/useOrganizations";
import { WorkflowIdConflictDialog } from "@/components/editor/WorkflowIdConflictDialog";
import { OrganizationSelect } from "@/components/forms/OrganizationSelect";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import {
	Dialog,
	DialogContent,
	DialogDescription,
	DialogFooter,
	DialogHeader,
	DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
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
		// Include organization_id from metadata if present
		organization_id: (file.metadata?.organizationId as string | undefined) ?? null,
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

	// Fetch organizations for org-scoped file filtering
	const { data: organizationsData } = useOrganizations();
	const organizations = useMemo(
		() =>
			(organizationsData ?? []).map((org) => ({
				id: org.id,
				name: org.name,
			})),
		[organizationsData],
	);

	// Filter state - undefined means "All", null means "Global only", string is org ID
	const [selectedOrgId, setSelectedOrgId] = useState<string | null | undefined>(
		undefined,
	);
	const [includeGlobal, setIncludeGlobal] = useState(true);

	// Refresh trigger to force file tree reload after scope changes
	const [refreshTrigger, setRefreshTrigger] = useState(0);

	// Create org-scoped file operations adapter with current filter settings
	const operations = useMemo(
		() =>
			createOrgScopedFileOperations(organizations, {
				selectedOrgId,
				includeGlobal,
			}),
		[organizations, selectedOrgId, includeGlobal],
	);

	// Refresh tree when filter changes to clear cached data in expanded folders
	useEffect(() => {
		setRefreshTrigger((prev) => prev + 1);
	}, [selectedOrgId, includeGlobal]);

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

	// Change Scope dialog state
	const [changeScopeFile, setChangeScopeFile] = useState<FileNode | null>(null);
	const [newScopeOrgId, setNewScopeOrgId] = useState<string | null | undefined>(
		undefined,
	);
	const [isChangingScope, setIsChangingScope] = useState(false);

	// Handle scope change request from context menu
	const handleChangeScope = useCallback((file: FileNode) => {
		setChangeScopeFile(file);
		// Initialize with current org
		const currentOrgId = file.metadata?.organizationId as string | null | undefined;
		setNewScopeOrgId(currentOrgId ?? null);
	}, []);

	// Handle scope change confirmation
	const handleConfirmScopeChange = useCallback(async () => {
		if (!changeScopeFile || !changeScopeFile.entityType || !changeScopeFile.entityId) {
			return;
		}

		const currentOrgId = changeScopeFile.metadata?.organizationId as
			| string
			| null
			| undefined;
		// Don't do anything if scope hasn't changed
		if (newScopeOrgId === currentOrgId) {
			setChangeScopeFile(null);
			return;
		}

		try {
			setIsChangingScope(true);
			await changeEntityOrganization(
				changeScopeFile.entityType,
				changeScopeFile.entityId,
				newScopeOrgId ?? null,
			);
			toast.success(`Changed scope to ${newScopeOrgId === null ? "Global" : organizations.find((o) => o.id === newScopeOrgId)?.name ?? "organization"}`);
			setChangeScopeFile(null);
			// Trigger refresh
			setRefreshTrigger((prev) => prev + 1);
		} catch (error) {
			toast.error(
				error instanceof Error ? error.message : "Failed to change scope",
			);
		} finally {
			setIsChangingScope(false);
		}
	}, [changeScopeFile, newScopeOrgId, organizations]);

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
		<div className={cn("flex h-full flex-col", className)}>
			{/* Organization filter controls */}
			<div className="border-b">
				<OrganizationSelect
					value={selectedOrgId}
					onChange={setSelectedOrgId}
					showAll={true}
					showGlobal={true}
					triggerClassName="rounded-none border-0 border-b"
					contentClassName="z-[101] rounded-none"
				/>
				{/* Show "Include Global" checkbox when filtering by a specific org */}
				{selectedOrgId !== undefined && selectedOrgId !== null && (
					<div className="flex items-center gap-2 px-3 py-2 border-t">
						<Checkbox
							id="include-global"
							checked={includeGlobal}
							onCheckedChange={(checked) =>
								setIncludeGlobal(checked === true)
							}
						/>
						<Label
							htmlFor="include-global"
							className="text-sm text-muted-foreground cursor-pointer"
						>
							Include Global
						</Label>
					</div>
				)}
			</div>

			{/* File tree */}
			<FileTree
				operations={operations}
				iconResolver={defaultIconResolver}
				editor={editorCallbacks}
				config={config}
				className="flex-1 min-h-0"
				refreshTrigger={refreshTrigger}
				onChangeScope={handleChangeScope}
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

			{/* Change Scope Dialog */}
			<Dialog
				open={!!changeScopeFile}
				onOpenChange={(open) => !open && setChangeScopeFile(null)}
			>
				<DialogContent className="z-[101]">
					<DialogHeader>
						<DialogTitle>Change Scope</DialogTitle>
						<DialogDescription>
							Change the organization scope for "{changeScopeFile?.name}".
							This will change which organization has access to this{" "}
							{changeScopeFile?.entityType}.
						</DialogDescription>
					</DialogHeader>
					<div className="py-4">
						<OrganizationSelect
							value={newScopeOrgId}
							onChange={setNewScopeOrgId}
							showAll={false}
							showGlobal={true}
							contentClassName="z-[102]"
						/>
					</div>
					<DialogFooter>
						<Button
							variant="outline"
							onClick={() => setChangeScopeFile(null)}
							disabled={isChangingScope}
						>
							Cancel
						</Button>
						<Button
							onClick={handleConfirmScopeChange}
							disabled={isChangingScope}
						>
							{isChangingScope ? "Changing..." : "Change Scope"}
						</Button>
					</DialogFooter>
				</DialogContent>
			</Dialog>
		</div>
	);
}
