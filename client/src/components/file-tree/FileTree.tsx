/**
 * Modular File Tree Component
 *
 * A reusable file tree component that works with different backends:
 * - Workspace files (code editor)
 * - JSX files (app builder)
 * - Organization-scoped file trees
 *
 * Dependencies are injected rather than hardcoded, making the component
 * portable across different contexts.
 */

import { useEffect, useCallback, useState, useRef, useMemo } from "react";
import {
	ChevronRight,
	ChevronDown,
	File,
	Folder,
	FilePlus,
	FolderPlus,
	Trash2,
	Edit2,
	RefreshCw,
	Loader2,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";
import {
	ContextMenu,
	ContextMenuContent,
	ContextMenuItem,
	ContextMenuSeparator,
	ContextMenuTrigger,
} from "@/components/ui/context-menu";
import {
	AlertDialog,
	AlertDialogAction,
	AlertDialogCancel,
	AlertDialogContent,
	AlertDialogDescription,
	AlertDialogFooter,
	AlertDialogHeader,
	AlertDialogTitle,
} from "@/components/ui/alert-dialog";

import { useFileTree } from "./useFileTree";
import { defaultIconResolver } from "./icons";
import type {
	FileNode,
	FileTreeNode,
	FileTreeProps,
	FileIconResolver,
	EditorCallbacks,
	FileTreeConfig,
	FileOperations,
	PathValidator,
} from "./types";

type CreatingItemType = "file" | "folder" | null;

/**
 * Resolved config type with pathValidator always present (but possibly undefined)
 */
type ResolvedConfig = Omit<Required<FileTreeConfig>, "pathValidator"> & {
	pathValidator: PathValidator | undefined;
};

/**
 * Default configuration for file tree behavior
 */
const DEFAULT_CONFIG: ResolvedConfig = {
	enableUpload: false, // Disabled by default - workspace adapter enables it
	enableDragMove: true,
	enableCreate: true,
	enableRename: true,
	enableDelete: true,
	emptyMessage: "No files found",
	loadingMessage: "Loading files...",
	pathValidator: undefined,
};

/**
 * Modular File Tree Component
 *
 * @param operations - File operations implementation (required)
 * @param editor - Optional editor integration callbacks
 * @param iconResolver - Optional custom icon resolver
 * @param config - Optional behavior configuration
 * @param className - Optional additional CSS classes
 */
export function FileTree({
	operations,
	editor,
	iconResolver = defaultIconResolver,
	config: userConfig,
	className,
	refreshTrigger,
}: FileTreeProps) {
	// Memoize config to avoid recreating on every render
	const config: ResolvedConfig = useMemo(
		() => ({ ...DEFAULT_CONFIG, ...userConfig }),
		[userConfig],
	);

	const {
		files,
		isLoading,
		loadFiles,
		toggleFolder,
		isFolderExpanded,
		refreshAll,
		removeFromTree,
	} = useFileTree(operations);

	const [creatingItem, setCreatingItem] = useState<CreatingItemType>(null);
	const [newItemName, setNewItemName] = useState("");
	const [creatingInFolder, setCreatingInFolder] = useState<string | null>(null);
	const [renamingFile, setRenamingFile] = useState<FileNode | null>(null);
	const [renameValue, setRenameValue] = useState("");
	const [fileToDelete, setFileToDelete] = useState<FileNode | null>(null);
	const [dragOverFolder, setDragOverFolder] = useState<string | null>(null);
	const [isProcessing, setIsProcessing] = useState(false);
	const [pendingOrgMove, setPendingOrgMove] = useState<{
		file: FileNode;
		targetOrg: FileNode;
	} | null>(null);

	const inputRef = useRef<HTMLInputElement>(null);
	const renameInputRef = useRef<HTMLInputElement>(null);

	// Load root directory on mount
	useEffect(() => {
		loadFiles("");
	}, [loadFiles]);

	// Refresh when refreshTrigger changes (for external refresh requests)
	const prevRefreshTrigger = useRef(refreshTrigger);
	useEffect(() => {
		if (
			refreshTrigger !== undefined &&
			prevRefreshTrigger.current !== undefined &&
			refreshTrigger !== prevRefreshTrigger.current
		) {
			refreshAll();
		}
		prevRefreshTrigger.current = refreshTrigger;
	}, [refreshTrigger, refreshAll]);

	// Notify editor of loading state changes
	useEffect(() => {
		editor?.onLoadingChange?.(isLoading);
	}, [isLoading, editor]);

	const handleFileClick = useCallback(
		async (file: FileNode) => {
			if (file.type === "folder") {
				toggleFolder(file.path);
				return;
			}

			// Auto-expand parent folders
			try {
				const pathParts = file.path.split("/");
				pathParts.pop(); // Remove filename
				let currentPath = "";
				for (const part of pathParts) {
					currentPath = currentPath ? `${currentPath}/${part}` : part;
					if (!isFolderExpanded(currentPath)) {
						await toggleFolder(currentPath);
					}
				}
			} catch {
				// Ignore folder expansion errors
			}

			// Read file and notify editor
			if (editor?.onFileOpen) {
				try {
					const content = await operations.read(file.path);
					editor.onFileOpen(file, content);
				} catch (err) {
					toast.error("Failed to open file", {
						description: err instanceof Error ? err.message : String(err),
					});
				}
			}
		},
		[toggleFolder, isFolderExpanded, editor, operations],
	);

	const handleFolderToggle = useCallback(
		(folder: FileNode) => {
			toggleFolder(folder.path);
		},
		[toggleFolder],
	);

	const handleCancelNewItem = useCallback(() => {
		setCreatingItem(null);
		setNewItemName("");
		setCreatingInFolder(null);
	}, []);

	const handleCreateFile = useCallback((folderPath?: string) => {
		setCreatingItem("file");
		setNewItemName("");
		setCreatingInFolder(folderPath || null);
	}, []);

	const handleCreateFolder = useCallback((folderPath?: string) => {
		setCreatingItem("folder");
		setNewItemName("");
		setCreatingInFolder(folderPath || null);
	}, []);

	const handleInputMouseDown = useCallback((e: React.MouseEvent) => {
		e.stopPropagation();
	}, []);

	const handleRefresh = useCallback(async () => {
		await refreshAll();
	}, [refreshAll]);

	const handleSaveNewItem = useCallback(async () => {
		if (!newItemName.trim() || !creatingItem) return;

		const fullPath = creatingInFolder
			? `${creatingInFolder}/${newItemName}`
			: newItemName;

		// Validate path if validator is configured
		if (config.pathValidator) {
			const validation = config.pathValidator(fullPath);
			if (!validation.valid) {
				toast.error(`Invalid ${creatingItem} path`, {
					description: validation.error,
				});
				return;
			}
		}

		try {
			setIsProcessing(true);

			if (creatingItem === "file") {
				await operations.write(fullPath, "");
			} else {
				await operations.createFolder(fullPath);
			}

			await loadFiles(creatingInFolder || "");

			setCreatingItem(null);
			setNewItemName("");
			setCreatingInFolder(null);
		} catch (err) {
			toast.error(`Failed to create ${creatingItem}`, {
				description: err instanceof Error ? err.message : String(err),
			});
		} finally {
			setIsProcessing(false);
		}
	}, [newItemName, creatingItem, creatingInFolder, loadFiles, operations, config]);

	// Focus input when creating new item
	useEffect(() => {
		if (creatingItem && inputRef.current) {
			inputRef.current.focus();
		}
	}, [creatingItem, creatingInFolder]);

	// Handle clicks outside the input to cancel if empty
	useEffect(() => {
		if (!creatingItem) return;

		const handleClickOutside = (event: MouseEvent) => {
			if (inputRef.current && !inputRef.current.contains(event.target as Node)) {
				if (!newItemName.trim()) {
					handleCancelNewItem();
				}
			}
		};

		document.addEventListener("mousedown", handleClickOutside);
		return () => {
			document.removeEventListener("mousedown", handleClickOutside);
		};
	}, [creatingItem, newItemName, handleCancelNewItem]);

	const handleNewItemKeyDown = useCallback(
		(e: React.KeyboardEvent<HTMLInputElement>) => {
			if (e.key === "Enter") {
				e.preventDefault();
				if (newItemName.trim()) {
					handleSaveNewItem();
				} else {
					handleCancelNewItem();
				}
			} else if (e.key === "Escape") {
				e.preventDefault();
				handleCancelNewItem();
			}
		},
		[handleSaveNewItem, handleCancelNewItem, newItemName],
	);

	const handleDelete = useCallback((file: FileNode) => {
		setFileToDelete(file);
	}, []);

	const handleConfirmDelete = useCallback(async () => {
		if (!fileToDelete) return;

		const isFolder = fileToDelete.type === "folder";
		const deletePath = fileToDelete.path;
		const deleteName = fileToDelete.name;

		try {
			setIsProcessing(true);

			// Notify editor of deletion (for closing tabs)
			editor?.onFileDeleted?.(deletePath, isFolder);

			// Optimistically remove from tree
			removeFromTree(deletePath, isFolder);
			setFileToDelete(null);

			// Delete from server
			await operations.delete(deletePath);

			toast.success(`Deleted ${deleteName}`);
		} catch (err) {
			// On error, reload parent folder to restore correct state
			const parentFolder = deletePath.includes("/")
				? deletePath.substring(0, deletePath.lastIndexOf("/"))
				: "";
			await loadFiles(parentFolder);
			toast.error("Failed to delete", {
				description: err instanceof Error ? err.message : String(err),
			});
		} finally {
			setIsProcessing(false);
		}
	}, [fileToDelete, loadFiles, editor, removeFromTree, operations]);

	const handleRename = useCallback((file: FileNode) => {
		setRenamingFile(file);
		setRenameValue(file.name);
	}, []);

	const handleCancelRename = useCallback(() => {
		setRenamingFile(null);
		setRenameValue("");
	}, []);

	const handleSaveRename = useCallback(async () => {
		if (!renamingFile || !renameValue.trim() || renameValue === renamingFile.name) {
			handleCancelRename();
			return;
		}

		const newPath = renamingFile.path.includes("/")
			? renamingFile.path.replace(/[^/]+$/, renameValue)
			: renameValue;

		// Validate path if validator is configured
		if (config.pathValidator) {
			const validation = config.pathValidator(newPath);
			if (!validation.valid) {
				toast.error("Invalid path", {
					description: validation.error,
				});
				return;
			}
		}

		try {
			setIsProcessing(true);

			const parentFolder = renamingFile.path.includes("/")
				? renamingFile.path.substring(0, renamingFile.path.lastIndexOf("/"))
				: "";

			// Notify editor of rename
			editor?.onFileRenamed?.(renamingFile.path, newPath);

			await operations.rename(renamingFile.path, newPath);
			await loadFiles(parentFolder);
			toast.success(`Renamed to ${renameValue}`);

			handleCancelRename();
		} catch (err) {
			toast.error("Failed to rename", {
				description: err instanceof Error ? err.message : String(err),
			});
		} finally {
			setIsProcessing(false);
		}
	}, [renamingFile, renameValue, loadFiles, handleCancelRename, editor, operations, config]);

	// Focus rename input when renaming starts
	useEffect(() => {
		if (renamingFile && renameInputRef.current) {
			renameInputRef.current.focus();
			const lastDotIndex = renameValue.lastIndexOf(".");
			if (lastDotIndex > 0) {
				renameInputRef.current.setSelectionRange(0, lastDotIndex);
			} else {
				renameInputRef.current.select();
			}
		}
		// eslint-disable-next-line react-hooks/exhaustive-deps
	}, [renamingFile]);

	// Handle clicks outside the rename input to save
	useEffect(() => {
		if (!renamingFile) return;

		const handleClickOutside = (event: MouseEvent) => {
			if (
				renameInputRef.current &&
				!renameInputRef.current.contains(event.target as Node)
			) {
				if (renameValue.trim()) {
					handleSaveRename();
				} else {
					handleCancelRename();
				}
			}
		};

		document.addEventListener("mousedown", handleClickOutside);
		return () => {
			document.removeEventListener("mousedown", handleClickOutside);
		};
	}, [renamingFile, renameValue, handleSaveRename, handleCancelRename]);

	const handleRenameKeyDown = useCallback(
		(e: React.KeyboardEvent<HTMLInputElement>) => {
			if (e.key === "Enter") {
				e.preventDefault();
				if (renameValue.trim()) {
					handleSaveRename();
				} else {
					handleCancelRename();
				}
			} else if (e.key === "Escape") {
				e.preventDefault();
				handleCancelRename();
			}
		},
		[handleSaveRename, handleCancelRename, renameValue],
	);

	const handleRenameInputMouseDown = useCallback((e: React.MouseEvent) => {
		e.stopPropagation();
	}, []);

	const handleDragStart = useCallback((e: React.DragEvent, file: FileNode) => {
		e.dataTransfer.effectAllowed = "move";
		e.dataTransfer.setData("text/plain", file.path);
		e.dataTransfer.setData("application/json", JSON.stringify(file));
	}, []);

	const handleDragOver = useCallback(
		(e: React.DragEvent, targetFolder?: string) => {
			e.preventDefault();
			e.dataTransfer.dropEffect = "move";
			setDragOverFolder(targetFolder || "");
		},
		[],
	);

	const handleDragLeave = useCallback(() => {
		setDragOverFolder(null);
	}, []);

	const handleDrop = useCallback(
		async (e: React.DragEvent, targetFolder?: string, targetFolderNode?: FileNode) => {
			e.preventDefault();
			setDragOverFolder(null);

			if (!config.enableDragMove) return;

			// Internal move operation
			try {
				const draggedPath = e.dataTransfer.getData("text/plain");
				const draggedFileJson = e.dataTransfer.getData("application/json");
				if (!draggedPath) return;

				// Parse dragged file for metadata checks
				let draggedFile: FileNode | null = null;
				try {
					draggedFile = draggedFileJson ? JSON.parse(draggedFileJson) : null;
				} catch {
					// Ignore parse errors
				}

				// Check if this is a cross-org move by comparing org prefixes in paths
				// Paths look like "org:global/..." or "org:uuid/..."
				const getOrgFromPath = (path: string): { id: string | null; name: string } | null => {
					if (!path.startsWith("org:")) return null;
					const withoutPrefix = path.slice(4); // Remove "org:"
					const slashIdx = withoutPrefix.indexOf("/");
					const orgPart = slashIdx === -1 ? withoutPrefix : withoutPrefix.slice(0, slashIdx);
					if (orgPart === "global") {
						return { id: null, name: "Global" };
					}
					return { id: orgPart, name: orgPart }; // Name will be resolved from metadata if available
				};

				const sourceOrg = getOrgFromPath(draggedPath);
				const targetPath = targetFolder || "";
				const targetOrg = getOrgFromPath(targetPath);

				// If both have org prefixes and they differ, it's a cross-org move
				if (sourceOrg && targetOrg && sourceOrg.id !== targetOrg.id) {
					// Check if file is an entity (can be moved between orgs)
					if (!draggedFile?.entityType) {
						toast.error("Only entities can be moved between organizations");
						return;
					}

					// Get target org name from the folder node metadata or use the extracted name
					const targetOrgName = targetFolderNode?.metadata?.isOrgContainer
						? targetFolderNode.name
						: targetOrg.name;

					// Create synthetic org container for the confirmation dialog
					const syntheticTargetOrg: FileNode = {
						path: `org:${targetOrg.id ?? "global"}`,
						name: targetOrgName,
						type: "folder",
						size: null,
						extension: null,
						modified: new Date().toISOString(),
						metadata: {
							isOrgContainer: true,
							organizationId: targetOrg.id,
						},
					};

					// Show confirmation dialog
					setPendingOrgMove({ file: draggedFile, targetOrg: syntheticTargetOrg });
					return;
				}

				// Don't allow dropping on itself
				if (draggedPath === targetFolder) return;

				// Don't allow dropping a folder into its own child
				if (targetFolder && targetFolder.startsWith(draggedPath + "/")) return;

				// Calculate new path
				const fileName = draggedPath.split("/").pop()!;
				const newPath = targetFolder ? `${targetFolder}/${fileName}` : fileName;

				// Don't do anything if the path hasn't changed
				if (draggedPath === newPath) return;

				// Validate path if validator is configured
				if (config.pathValidator) {
					const validation = config.pathValidator(newPath);
					if (!validation.valid) {
						toast.error("Cannot move here", {
							description: validation.error,
						});
						return;
					}
				}

				setIsProcessing(true);

				const sourceFolder = draggedPath.includes("/")
					? draggedPath.substring(0, draggedPath.lastIndexOf("/"))
					: "";
				const targetFolderPath = targetFolder || "";

				// Notify editor of move (same as rename)
				editor?.onFileRenamed?.(draggedPath, newPath);

				await operations.rename(draggedPath, newPath);

				// Reload affected folders
				await loadFiles(sourceFolder);
				if (sourceFolder !== targetFolderPath) {
					await loadFiles(targetFolderPath);
				}

				toast.success(`Moved ${fileName}`);
			} catch (err) {
				toast.error("Failed to move", {
					description: err instanceof Error ? err.message : String(err),
				});
			} finally {
				setIsProcessing(false);
			}
		},
		[loadFiles, editor, operations, config],
	);

	const handleConfirmOrgMove = useCallback(async () => {
		if (!pendingOrgMove) return;

		const { file, targetOrg } = pendingOrgMove;
		setPendingOrgMove(null);

		try {
			setIsProcessing(true);

			// The adapter's rename() handles cross-org moves specially
			await operations.rename(file.path, targetOrg.path);
			toast.success(`Moved to ${targetOrg.name}`);
			await refreshAll();
		} catch (error) {
			toast.error(error instanceof Error ? error.message : "Failed to move");
		} finally {
			setIsProcessing(false);
		}
	}, [pendingOrgMove, operations, refreshAll]);

	return (
		<div className={cn("flex h-full flex-col relative", className)}>
			{/* Loading overlay */}
			{isProcessing && (
				<div className="absolute inset-0 bg-background/80 backdrop-blur-sm z-50 flex items-center justify-center">
					<div className="flex flex-col items-center gap-2">
						<Loader2 className="h-8 w-8 animate-spin text-primary" />
						<p className="text-sm text-muted-foreground">Processing...</p>
					</div>
				</div>
			)}

			{/* Toolbar */}
			<div className="flex items-center gap-1 border-b p-2">
				{config.enableCreate && (
					<>
						<Button
							variant="ghost"
							size="sm"
							onClick={() => handleCreateFile()}
							title="New File"
							className="h-7 px-2"
						>
							<FilePlus className="h-4 w-4" />
						</Button>
						<Button
							variant="ghost"
							size="sm"
							onClick={() => handleCreateFolder()}
							title="New Folder"
							className="h-7 px-2"
						>
							<FolderPlus className="h-4 w-4" />
						</Button>
					</>
				)}
				<Button
					variant="ghost"
					size="sm"
					onClick={handleRefresh}
					title="Refresh"
					className="h-7 px-2"
				>
					<RefreshCw className="h-4 w-4" />
				</Button>
			</div>

			{/* File list */}
			<ContextMenu>
				<ContextMenuTrigger asChild>
					<div
						className={cn(
							"flex-1 overflow-auto",
							dragOverFolder === "" &&
								"bg-primary/10 outline outline-2 outline-primary outline-dashed",
						)}
						onDragOver={(e) => handleDragOver(e)}
						onDragLeave={handleDragLeave}
						onDrop={(e) => handleDrop(e)}
					>
						{isLoading && files.length === 0 && !creatingItem ? (
							<div className="flex h-full items-center justify-center">
								<div className="text-sm text-muted-foreground">
									{config.loadingMessage}
								</div>
							</div>
						) : files.length === 0 && !creatingItem ? (
							<div className="flex h-full items-center justify-center p-4">
								<div className="text-center text-sm text-muted-foreground">
									<p>{config.emptyMessage}</p>
									{config.enableCreate && (
										<p className="mt-2 text-xs">
											Right-click to create files and folders
										</p>
									)}
								</div>
							</div>
						) : (
							<div className="space-y-1 p-2">
								{/* Inline new item editor at root */}
								{creatingItem && !creatingInFolder && (
									<div className="flex items-center gap-2 rounded px-2 py-1 bg-muted/50">
										<div className="w-4" />
										{isProcessing ? (
											<Loader2 className="h-4 w-4 flex-shrink-0 animate-spin text-primary" />
										) : creatingItem === "folder" ? (
											<Folder className="h-4 w-4 flex-shrink-0 text-primary" />
										) : (
											<File className="h-4 w-4 flex-shrink-0 text-muted-foreground" />
										)}
										<input
											ref={inputRef}
											type="text"
											value={newItemName}
											onChange={(e) => setNewItemName(e.target.value)}
											onKeyDown={handleNewItemKeyDown}
											onMouseDown={handleInputMouseDown}
											placeholder={
												creatingItem === "folder" ? "Folder name" : "File name"
											}
											disabled={isProcessing}
											className="flex-1 bg-transparent text-sm outline-none disabled:opacity-50 disabled:cursor-not-allowed"
										/>
									</div>
								)}

								{/* Existing files */}
								{files.map((file) => (
									<FileTreeItem
										key={file.path}
										file={file}
										iconResolver={iconResolver}
										config={config}
										editor={editor}
										onFileClick={handleFileClick}
										onFolderToggle={handleFolderToggle}
										onDelete={handleDelete}
										onRename={handleRename}
										onCreateFile={handleCreateFile}
										onCreateFolder={handleCreateFolder}
										isExpanded={isFolderExpanded(file.path)}
										onDragStart={handleDragStart}
										onDragOver={handleDragOver}
										onDragLeave={handleDragLeave}
										onDrop={handleDrop}
										isDragOver={dragOverFolder === file.path}
										creatingItem={creatingItem}
										creatingInFolder={creatingInFolder}
										newItemName={newItemName}
										setNewItemName={setNewItemName}
										inputRef={inputRef}
										handleNewItemKeyDown={handleNewItemKeyDown}
										handleInputMouseDown={handleInputMouseDown}
										renamingFile={renamingFile}
										renameValue={renameValue}
										setRenameValue={setRenameValue}
										renameInputRef={renameInputRef}
										handleRenameKeyDown={handleRenameKeyDown}
										handleRenameInputMouseDown={handleRenameInputMouseDown}
										isProcessing={isProcessing}
									/>
								))}
							</div>
						)}
					</div>
				</ContextMenuTrigger>
				{config.enableCreate && (
					<ContextMenuContent>
						<ContextMenuItem onClick={() => handleCreateFile()}>
							<FilePlus className="mr-2 h-4 w-4" />
							New File
						</ContextMenuItem>
						<ContextMenuItem onClick={() => handleCreateFolder()}>
							<FolderPlus className="mr-2 h-4 w-4" />
							New Folder
						</ContextMenuItem>
					</ContextMenuContent>
				)}
			</ContextMenu>

			{/* Delete Confirmation Dialog */}
			<AlertDialog
				open={!!fileToDelete}
				onOpenChange={(open) => !open && setFileToDelete(null)}
			>
				<AlertDialogContent>
					<AlertDialogHeader>
						<AlertDialogTitle>
							Delete {fileToDelete?.type === "folder" ? "Folder" : "File"}
						</AlertDialogTitle>
						<AlertDialogDescription>
							Are you sure you want to delete{" "}
							<strong>{fileToDelete?.name}</strong>?
							{fileToDelete?.type === "folder" &&
								" This will delete all contents inside the folder."}{" "}
							This action cannot be undone.
						</AlertDialogDescription>
					</AlertDialogHeader>
					<AlertDialogFooter>
						<AlertDialogCancel>Cancel</AlertDialogCancel>
						<AlertDialogAction
							onClick={handleConfirmDelete}
							className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
						>
							Delete
						</AlertDialogAction>
					</AlertDialogFooter>
				</AlertDialogContent>
			</AlertDialog>

			{/* Cross-Org Move Confirmation Dialog */}
			<AlertDialog
				open={!!pendingOrgMove}
				onOpenChange={(open) => !open && setPendingOrgMove(null)}
			>
				<AlertDialogContent>
					<AlertDialogHeader>
						<AlertDialogTitle>
							Move to {pendingOrgMove?.targetOrg.name}?
						</AlertDialogTitle>
						<AlertDialogDescription>
							Move "{pendingOrgMove?.file.name}" to{" "}
							{pendingOrgMove?.targetOrg.name}? This will change which
							organization has access to this entity.
						</AlertDialogDescription>
					</AlertDialogHeader>
					<AlertDialogFooter>
						<AlertDialogCancel>Cancel</AlertDialogCancel>
						<AlertDialogAction onClick={handleConfirmOrgMove}>
							Move
						</AlertDialogAction>
					</AlertDialogFooter>
				</AlertDialogContent>
			</AlertDialog>
		</div>
	);
}

interface FileTreeItemProps {
	file: FileTreeNode;
	iconResolver: FileIconResolver;
	config: ResolvedConfig;
	editor?: EditorCallbacks;
	onFileClick: (file: FileNode) => void;
	onFolderToggle: (folder: FileNode) => void;
	onDelete: (file: FileNode) => void;
	onRename: (file: FileNode) => void;
	onCreateFile: (folderPath?: string) => void;
	onCreateFolder: (folderPath?: string) => void;
	isExpanded: boolean;
	onDragStart: (e: React.DragEvent, file: FileNode) => void;
	onDragOver: (e: React.DragEvent, targetFolder?: string) => void;
	onDragLeave: () => void;
	onDrop: (e: React.DragEvent, targetFolder?: string, targetFolderNode?: FileNode) => void;
	isDragOver: boolean;
	creatingItem: CreatingItemType;
	creatingInFolder: string | null;
	newItemName: string;
	setNewItemName: (name: string) => void;
	inputRef: React.RefObject<HTMLInputElement | null>;
	handleNewItemKeyDown: (e: React.KeyboardEvent<HTMLInputElement>) => void;
	handleInputMouseDown: (e: React.MouseEvent) => void;
	renamingFile: FileNode | null;
	renameValue: string;
	setRenameValue: (name: string) => void;
	renameInputRef: React.RefObject<HTMLInputElement | null>;
	handleRenameKeyDown: (e: React.KeyboardEvent<HTMLInputElement>) => void;
	handleRenameInputMouseDown: (e: React.MouseEvent) => void;
	isProcessing: boolean;
}

function FileTreeItem({
	file,
	iconResolver,
	config,
	editor,
	onFileClick,
	onFolderToggle,
	onDelete,
	onRename,
	onCreateFile,
	onCreateFolder,
	isExpanded,
	onDragStart,
	onDragOver,
	onDragLeave,
	onDrop,
	isDragOver,
	creatingItem,
	creatingInFolder,
	newItemName,
	setNewItemName,
	inputRef,
	handleNewItemKeyDown,
	handleInputMouseDown,
	renamingFile,
	renameValue,
	setRenameValue,
	renameInputRef,
	handleRenameKeyDown,
	handleRenameInputMouseDown,
	isProcessing,
}: FileTreeItemProps) {
	const isFolder = file.type === "folder";
	const level = file.level;
	const isRenaming = renamingFile?.path === file.path;
	const isSelected = editor?.isFileSelected?.(file.path) ?? false;
	const isOrgContainer = file.metadata?.isOrgContainer === true;

	// Don't allow dragging org containers
	const canDrag = config.enableDragMove && !isOrgContainer;

	// Get icon from resolver
	const { icon: FileIcon, className: iconClassName } = iconResolver(file);

	return (
		<div>
			{isRenaming ? (
				// Inline rename editor
				<div
					className="flex items-center gap-2 rounded px-2 py-1 bg-muted/50"
					style={{ paddingLeft: `${level * 12 + 8}px` }}
				>
					{isFolder ? (
						<>
							{isExpanded ? (
								<ChevronDown className="h-4 w-4 flex-shrink-0 text-muted-foreground" />
							) : (
								<ChevronRight className="h-4 w-4 flex-shrink-0 text-muted-foreground" />
							)}
							<FileIcon className={cn("h-4 w-4 flex-shrink-0", iconClassName)} />
						</>
					) : (
						<>
							<div className="w-4" />
							<FileIcon className={cn("h-4 w-4 flex-shrink-0", iconClassName)} />
						</>
					)}
					<input
						ref={renameInputRef}
						type="text"
						value={renameValue}
						onChange={(e) => setRenameValue(e.target.value)}
						onKeyDown={handleRenameKeyDown}
						onMouseDown={handleRenameInputMouseDown}
						disabled={isProcessing}
						className="flex-1 bg-transparent text-sm outline-none disabled:opacity-50 disabled:cursor-not-allowed"
					/>
				</div>
			) : (
				<ContextMenu>
					<ContextMenuTrigger asChild>
						<button
							draggable={canDrag}
							onClick={() => (isFolder ? onFolderToggle(file) : onFileClick(file))}
							onDragStart={canDrag ? (e) => onDragStart(e, file) : undefined}
							onDragOver={(e) => {
								if (isFolder) {
									e.stopPropagation();
									onDragOver(e, file.path);
								}
							}}
							onDragLeave={onDragLeave}
							onDrop={(e) => {
								if (isFolder) {
									e.stopPropagation();
									onDrop(e, file.path, file);
								}
							}}
							className={cn(
								"flex w-full items-center gap-2 rounded px-2 py-1 text-left text-sm transition-colors outline-none",
								isSelected && !isDragOver ? "bg-accent text-accent-foreground" : "",
								!isDragOver && !isSelected ? "hover:bg-muted" : "",
								isDragOver && isFolder && "bg-primary/30 border-2 border-primary",
							)}
							style={{ paddingLeft: `${level * 12 + 8}px` }}
						>
							{isFolder ? (
								<>
									{isExpanded ? (
										<ChevronDown className="h-4 w-4 flex-shrink-0 text-muted-foreground" />
									) : (
										<ChevronRight className="h-4 w-4 flex-shrink-0 text-muted-foreground" />
									)}
									<FileIcon className={cn("h-4 w-4 flex-shrink-0", iconClassName)} />
								</>
							) : (
								<>
									<div className="w-4" />
									<FileIcon className={cn("h-4 w-4 flex-shrink-0", iconClassName)} />
								</>
							)}
							<span className="flex-1 truncate">{file.name}</span>
						</button>
					</ContextMenuTrigger>
					<ContextMenuContent>
						{isFolder && config.enableCreate && !isOrgContainer && (
							<>
								<ContextMenuItem onClick={() => onCreateFile(file.path)}>
									<FilePlus className="mr-2 h-4 w-4" />
									New File
								</ContextMenuItem>
								<ContextMenuItem onClick={() => onCreateFolder(file.path)}>
									<FolderPlus className="mr-2 h-4 w-4" />
									New Folder
								</ContextMenuItem>
								<ContextMenuSeparator />
							</>
						)}
						{config.enableRename && !isOrgContainer && (
							<ContextMenuItem onClick={() => onRename(file)}>
								<Edit2 className="mr-2 h-4 w-4" />
								Rename
							</ContextMenuItem>
						)}
						{config.enableDelete && !isOrgContainer && (
							<>
								{config.enableRename && !isOrgContainer && <ContextMenuSeparator />}
								<ContextMenuItem
									onClick={() => onDelete(file)}
									className="text-destructive focus:text-destructive"
								>
									<Trash2 className="mr-2 h-4 w-4" />
									Delete
								</ContextMenuItem>
							</>
						)}
					</ContextMenuContent>
				</ContextMenu>
			)}

			{/* Inline new item editor (shown when creating in this folder) */}
			{creatingItem && creatingInFolder === file.path && (
				<div
					className="flex items-center gap-2 rounded px-2 py-1 bg-muted/50 mt-1"
					style={{ paddingLeft: `${(level + 1) * 12 + 8}px` }}
				>
					<div className="w-4" />
					{isProcessing ? (
						<Loader2 className="h-4 w-4 flex-shrink-0 animate-spin text-primary" />
					) : creatingItem === "folder" ? (
						<Folder className="h-4 w-4 flex-shrink-0 text-primary" />
					) : (
						<File className="h-4 w-4 flex-shrink-0 text-muted-foreground" />
					)}
					<input
						ref={inputRef}
						type="text"
						value={newItemName}
						onChange={(e) => setNewItemName(e.target.value)}
						onKeyDown={handleNewItemKeyDown}
						onMouseDown={handleInputMouseDown}
						placeholder={creatingItem === "folder" ? "Folder name" : "File name"}
						disabled={isProcessing}
						className="flex-1 bg-transparent text-sm outline-none disabled:opacity-50 disabled:cursor-not-allowed"
					/>
				</div>
			)}
		</div>
	);
}

// Re-export types for convenience
export type { FileNode, FileTreeNode, FileOperations, EditorCallbacks, FileTreeConfig };
