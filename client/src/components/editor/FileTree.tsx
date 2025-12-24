import { useEffect, useCallback, useState, useRef } from "react";
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
import { useFileTree, type FileTreeNode } from "@/hooks/useFileTree";
import { useEditorStore } from "@/stores/editorStore";
import { fileService, type FileMetadata } from "@/services/fileService";
import { useUploadProgress } from "@/stores/uploadStore";
import { cn } from "@/lib/utils";
import { isExcludedPath } from "@/lib/file-filter";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";

/**
 * Interface for a file with its relative path from the drop target
 */
interface FileWithPath {
	file: File;
	relativePath: string;
}

/**
 * Recursively traverse a FileSystemEntry to collect all files with their relative paths.
 * Supports both files and folders dropped from the filesystem.
 */
async function traverseFileSystemEntry(
	entry: FileSystemEntry,
	basePath: string = "",
): Promise<FileWithPath[]> {
	const results: FileWithPath[] = [];

	if (entry.isFile) {
		const fileEntry = entry as FileSystemFileEntry;
		const file = await new Promise<File>((resolve, reject) => {
			fileEntry.file(resolve, reject);
		});
		results.push({
			file,
			relativePath: basePath ? `${basePath}/${entry.name}` : entry.name,
		});
	} else if (entry.isDirectory) {
		const dirEntry = entry as FileSystemDirectoryEntry;
		const reader = dirEntry.createReader();

		// readEntries may return partial results, so we need to loop until empty
		const readAllEntries = async (): Promise<FileSystemEntry[]> => {
			const entries: FileSystemEntry[] = [];
			let batch: FileSystemEntry[];
			do {
				batch = await new Promise((resolve, reject) => {
					reader.readEntries(resolve, reject);
				});
				entries.push(...batch);
			} while (batch.length > 0);
			return entries;
		};

		const entries = await readAllEntries();
		const newBasePath = basePath ? `${basePath}/${entry.name}` : entry.name;

		for (const childEntry of entries) {
			const childResults = await traverseFileSystemEntry(
				childEntry,
				newBasePath,
			);
			results.push(...childResults);
		}
	}

	return results;
}

/**
 * Convert a FileContentResponse to a FileMetadata for optimistic updates
 */
function responseToMetadata(
	path: string,
	size: number,
	modified: string,
): FileMetadata {
	const name = path.split("/").pop()!;
	const lastDot = name.lastIndexOf(".");
	return {
		path,
		name,
		type: "file",
		size,
		extension: lastDot > 0 ? name.substring(lastDot + 1) : null,
		modified,
		is_workflow: false,
		is_data_provider: false,
	};
}

/**
 * Detect if a file is text-based (can be read as UTF-8)
 */
function isTextFile(file: File): boolean {
	return (
		file.type.startsWith("text/") ||
		file.type === "application/json" ||
		file.type === "application/javascript" ||
		file.type === "application/xml" ||
		!!file.name.match(
			/\.(txt|md|json|js|jsx|ts|tsx|py|java|c|cpp|h|hpp|css|scss|html|xml|yaml|yml|sh|bash|sql|log|csv)$/i,
		)
	);
}
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

type CreatingItemType = "file" | "folder" | null;

/**
 * File tree component with hierarchical navigation
 */
export function FileTree() {
	const {
		files,
		isLoading,
		loadFiles,
		toggleFolder,
		isFolderExpanded,
		refreshAll,
		addFilesOptimistically,
		removeFromTree,
	} = useFileTree();
	const {
		startUpload,
		updateProgress,
		recordFailure,
		finishUpload,
		shouldContinueUpload,
	} = useUploadProgress();
	const tabs = useEditorStore((state) => state.tabs);
	const activeTabIndex = useEditorStore((state) => state.activeTabIndex);
	const setOpenFile = useEditorStore((state) => state.setOpenFile);
	const setLoadingFile = useEditorStore((state) => state.setLoadingFile);
	const updateTabPath = useEditorStore((state) => state.updateTabPath);
	const closeTabsByPath = useEditorStore((state) => state.closeTabsByPath);

	// Compute active tab from state
	const activeTab =
		activeTabIndex >= 0 && activeTabIndex < tabs.length
			? tabs[activeTabIndex]
			: null;
	const openFile = activeTab?.file || null;
	const [creatingItem, setCreatingItem] = useState<CreatingItemType>(null);
	const [newItemName, setNewItemName] = useState("");
	const [creatingInFolder, setCreatingInFolder] = useState<string | null>(
		null,
	); // Folder path where item is being created
	const [renamingFile, setRenamingFile] = useState<FileMetadata | null>(null); // File being renamed
	const [renameValue, setRenameValue] = useState(""); // New name for rename
	const [fileToDelete, setFileToDelete] = useState<FileMetadata | null>(null);
	const [dragOverFolder, setDragOverFolder] = useState<string | null>(null); // Folder being dragged over
	const [isProcessing, setIsProcessing] = useState(false); // Loading overlay for operations
	const [uploadConflict, setUploadConflict] = useState<{
		count: number;
		onCancel: () => void;
		onReplaceAll: () => void;
	} | null>(null); // Upload conflict dialog state
	const inputRef = useRef<HTMLInputElement>(null);
	const renameInputRef = useRef<HTMLInputElement>(null);

	// Load root directory on mount
	useEffect(() => {
		loadFiles("");
	}, [loadFiles]);

	const handleFileClick = useCallback(
		async (file: FileMetadata) => {
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
					// Load folder contents if not already loaded
					if (!isFolderExpanded(currentPath)) {
						await toggleFolder(currentPath);
					}
				}
			} catch {
				// Ignore folder expansion errors
			}

			// Load file directly - no conflict checking on explicit user click
			try {
				setLoadingFile(true);
				const response = await fileService.readFile(file.path);
				setOpenFile(
					file,
					response.content,
					response.encoding as "utf-8" | "base64",
					response.etag,
				);
			} catch {
				setLoadingFile(false);
			}
		},
		[toggleFolder, isFolderExpanded, setOpenFile, setLoadingFile],
	);

	const handleFolderToggle = useCallback(
		(folder: FileMetadata) => {
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
		// Prevent this click from triggering the click-outside handler
		e.stopPropagation();
	}, []);

	const handleRefresh = useCallback(async () => {
		await refreshAll();
	}, [refreshAll]);

	const handleSaveNewItem = useCallback(async () => {
		if (!newItemName.trim() || !creatingItem) return;

		try {
			setIsProcessing(true);

			// Construct the full path (folder path + new item name)
			const fullPath = creatingInFolder
				? `${creatingInFolder}/${newItemName}`
				: newItemName;

			if (creatingItem === "file") {
				// Create an empty file
				await fileService.writeFile(fullPath, "");
			} else {
				await fileService.createFolder(fullPath);
			}

			// Reload the parent folder (or root if no parent)
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
	}, [newItemName, creatingItem, creatingInFolder, loadFiles]);

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
			if (
				inputRef.current &&
				!inputRef.current.contains(event.target as Node)
			) {
				// Clicked outside - cancel if empty, otherwise keep it
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
					// Cancel if trying to save with empty name
					handleCancelNewItem();
				}
			} else if (e.key === "Escape") {
				e.preventDefault();
				handleCancelNewItem();
			}
		},
		[handleSaveNewItem, handleCancelNewItem, newItemName],
	);

	const handleDelete = useCallback((file: FileMetadata) => {
		setFileToDelete(file);
	}, []);

	const handleConfirmDelete = useCallback(async () => {
		if (!fileToDelete) return;

		const isFolder = fileToDelete.type === "folder";
		const deletePath = fileToDelete.path;
		const deleteName = fileToDelete.name;

		try {
			setIsProcessing(true);

			// Close any open tabs for this file/folder
			const closedCount = closeTabsByPath(deletePath, isFolder);

			// Optimistically remove from tree (immediate UI update)
			removeFromTree(deletePath, isFolder);
			setFileToDelete(null);

			// Delete from server
			await fileService.deletePath(deletePath);

			// Show appropriate message
			if (closedCount > 0) {
				toast.success(
					isFolder
						? `Deleted folder ${deleteName} and closed ${closedCount} open ${closedCount === 1 ? "file" : "files"}`
						: `Deleted ${deleteName} and closed the tab`,
				);
			} else {
				toast.success(`Deleted ${deleteName}`);
			}
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
	}, [fileToDelete, loadFiles, closeTabsByPath, removeFromTree]);

	const handleRename = useCallback((file: FileMetadata) => {
		setRenamingFile(file);
		setRenameValue(file.name);
	}, []);

	const handleCancelRename = useCallback(() => {
		setRenamingFile(null);
		setRenameValue("");
	}, []);

	const handleSaveRename = useCallback(async () => {
		if (
			!renamingFile ||
			!renameValue.trim() ||
			renameValue === renamingFile.name
		) {
			handleCancelRename();
			return;
		}

		try {
			setIsProcessing(true);
			const newPath = renamingFile.path.includes("/")
				? renamingFile.path.replace(/[^/]+$/, renameValue)
				: renameValue;

			// Get parent folder path
			const parentFolder = renamingFile.path.includes("/")
				? renamingFile.path.substring(
						0,
						renamingFile.path.lastIndexOf("/"),
					)
				: "";

			// Update tab paths if any tabs have this file/folder open
			updateTabPath(renamingFile.path, newPath);

			await fileService.renamePath(renamingFile.path, newPath);
			await loadFiles(parentFolder); // Refresh parent folder
			toast.success(`Renamed to ${renameValue}`);

			handleCancelRename();
		} catch (err) {
			toast.error("Failed to rename", {
				description: err instanceof Error ? err.message : String(err),
			});
		} finally {
			setIsProcessing(false);
		}
	}, [
		renamingFile,
		renameValue,
		loadFiles,
		handleCancelRename,
		updateTabPath,
	]);

	// Focus rename input when renaming starts
	useEffect(() => {
		if (renamingFile && renameInputRef.current) {
			renameInputRef.current.focus();
			// Select the filename without extension
			const lastDotIndex = renameValue.lastIndexOf(".");
			if (lastDotIndex > 0) {
				renameInputRef.current.setSelectionRange(0, lastDotIndex);
			} else {
				renameInputRef.current.select();
			}
		}
		// eslint-disable-next-line react-hooks/exhaustive-deps
	}, [renamingFile]); // Only run when renamingFile changes, not renameValue

	// Handle clicks outside the rename input to save
	useEffect(() => {
		if (!renamingFile) return;

		const handleClickOutside = (event: MouseEvent) => {
			if (
				renameInputRef.current &&
				!renameInputRef.current.contains(event.target as Node)
			) {
				// Clicked outside - save if has value, otherwise cancel
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
		// Prevent this click from triggering the click-outside handler
		e.stopPropagation();
	}, []);

	const handleDragStart = useCallback(
		(e: React.DragEvent, file: FileMetadata) => {
			e.dataTransfer.effectAllowed = "move";
			e.dataTransfer.setData("text/plain", file.path);
			e.dataTransfer.setData("application/json", JSON.stringify(file));
		},
		[],
	);

	const handleDragOver = useCallback(
		(e: React.DragEvent, targetFolder?: string) => {
			e.preventDefault();

			// Check if dragging files from outside (not internal move)
			const hasFiles = e.dataTransfer.types.includes("Files");
			const hasInternalData = e.dataTransfer.types.includes("text/plain");

			if (hasFiles && !hasInternalData) {
				// External file upload
				e.dataTransfer.dropEffect = "copy";
			} else {
				// Internal move
				e.dataTransfer.dropEffect = "move";
			}

			setDragOverFolder(targetFolder || "");
		},
		[],
	);

	const handleDragLeave = useCallback(() => {
		setDragOverFolder(null);
	}, []);

	const handleDrop = useCallback(
		async (e: React.DragEvent, targetFolder?: string) => {
			e.preventDefault();
			setDragOverFolder(null);

			const targetPath = targetFolder || "";

			// Check if this is an external file drop (not internal move)
			// Use DataTransferItemList to support folder uploads via webkitGetAsEntry
			const items = e.dataTransfer.items;
			const hasExternalFiles =
				items &&
				items.length > 0 &&
				Array.from(items).some((item) => item.kind === "file");

			if (hasExternalFiles) {
				// External file upload - collect all files including from folders
				const allFiles: FileWithPath[] = [];

				// IMPORTANT: Extract all entries SYNCHRONOUSLY first!
				// The DataTransferItemList is cleared by the browser after any await,
				// so we must call webkitGetAsEntry() on all items before any async work.
				// See: https://developer.mozilla.org/en-US/docs/Web/API/DataTransferItem/webkitGetAsEntry
				const entries: Array<{
					entry: FileSystemEntry | null;
					fallbackFile: File | null;
				}> = [];

				for (let i = 0; i < items.length; i++) {
					const item = items[i];
					if (item.kind !== "file") continue;

					// Get entry synchronously - must happen before any await
					const entry = item.webkitGetAsEntry?.() ?? null;
					// Also get fallback file synchronously in case entry processing fails
					const fallbackFile = item.getAsFile();
					entries.push({ entry, fallbackFile });
				}

				// Now process entries asynchronously - the DataTransferItemList may be
				// cleared after this point, but we've already extracted what we need
				for (const { entry, fallbackFile } of entries) {
					if (entry) {
						if (entry.isDirectory) {
							// Traverse directory recursively
							try {
								const filesFromEntry =
									await traverseFileSystemEntry(entry);
								allFiles.push(...filesFromEntry);
							} catch {
								console.warn(
									`Failed to traverse directory: ${entry.name}`,
								);
							}
						} else if (entry.isFile) {
							// Handle file entry - need to use file() method
							try {
								const fileEntry = entry as FileSystemFileEntry;
								const file = await new Promise<File>(
									(resolve, reject) => {
										fileEntry.file(resolve, reject);
									},
								);
								allFiles.push({
									file,
									relativePath: file.name,
								});
							} catch {
								// Fallback to getAsFile (already extracted synchronously)
								if (fallbackFile) {
									allFiles.push({
										file: fallbackFile,
										relativePath: fallbackFile.name,
									});
								}
							}
						}
					} else if (fallbackFile) {
						// Browser doesn't support webkitGetAsEntry, use fallback
						allFiles.push({
							file: fallbackFile,
							relativePath: fallbackFile.name,
						});
					}
				}

				if (allFiles.length === 0) return;

				// Filter out excluded files (system files, caches, metadata, etc.)
				const filteredFiles = allFiles.filter(({ relativePath }) => {
					const fullPath = targetPath
						? `${targetPath}/${relativePath}`
						: relativePath;
					return !isExcludedPath(fullPath);
				});

				// Note: Silently filter excluded files (system files, caches, etc.)
				// No need to log - this is expected behavior

				// Use filtered list from here on
				const filesToUpload = filteredFiles;
				if (filesToUpload.length === 0) {
					toast.info(
						"No files to upload (all files were filtered out)",
					);
					return;
				}

				// Check for existing files that would be overwritten
				try {
					// Get all existing files recursively from the target path
					const existingFiles =
						await fileService.listFiles(targetPath);
					const existingPaths = new Set(
						existingFiles
							.filter((f) => f.type === "file")
							.map((f) => f.path),
					);

					// Find files that already exist
					const conflictCount = filesToUpload.filter(
						({ relativePath }) => {
							const fullPath = targetPath
								? `${targetPath}/${relativePath}`
								: relativePath;
							return existingPaths.has(fullPath);
						},
					).length;

					// Show conflict dialog if any files would be overwritten
					if (conflictCount > 0) {
						const shouldReplace = await new Promise<boolean>(
							(resolve) => {
								setUploadConflict({
									count: conflictCount,
									onCancel: () => {
										setUploadConflict(null);
										resolve(false);
									},
									onReplaceAll: () => {
										setUploadConflict(null);
										resolve(true);
									},
								});
							},
						);

						if (!shouldReplace) {
							return; // User cancelled
						}
					}
				} catch {
					// If we can't check for existing files, proceed with upload
					// (the upload will fail individually if there are issues)
				}

				// Start upload progress tracking
				startUpload(filesToUpload.length);
				const uploadedFiles: FileMetadata[] = [];

				for (let i = 0; i < filesToUpload.length; i++) {
					// Check for cancellation before each file
					if (!shouldContinueUpload()) {
						toast.info(
							`Upload cancelled (${i} of ${filesToUpload.length} files uploaded)`,
						);
						break;
					}

					const { file, relativePath } = filesToUpload[i];
					const filePath = targetPath
						? `${targetPath}/${relativePath}`
						: relativePath;

					updateProgress(file.name, i);

					try {
						let content: string;
						let encoding: "utf-8" | "base64";

						if (isTextFile(file)) {
							// Read as text
							content = await file.text();
							encoding = "utf-8";
						} else {
							// Read as binary and encode to base64
							// Use chunked encoding to avoid stack overflow with large files
							const arrayBuffer = await file.arrayBuffer();
							const bytes = new Uint8Array(arrayBuffer);
							const chunkSize = 8192;
							let binary = "";
							for (let i = 0; i < bytes.length; i += chunkSize) {
								const chunk = bytes.subarray(
									i,
									Math.min(i + chunkSize, bytes.length),
								);
								binary += String.fromCharCode(...chunk);
							}
							content = btoa(binary);
							encoding = "base64";
						}

						// Upload file (backend creates parent directories automatically)
						const response = await fileService.writeFile(
							filePath,
							content,
							encoding,
						);

						// Convert response to FileMetadata for optimistic update
						const metadata = responseToMetadata(
							response.path,
							response.size,
							response.modified,
						);
						uploadedFiles.push(metadata);
					} catch (err) {
						recordFailure(
							filePath,
							err instanceof Error ? err.message : String(err),
						);
						// Continue with next file
					}
				}

				// Optimistically add all uploaded files to tree
				if (uploadedFiles.length > 0) {
					addFilesOptimistically(uploadedFiles, targetPath);
				}

				finishUpload();
				return;
			}

			// Internal move operation
			try {
				const draggedPath = e.dataTransfer.getData("text/plain");
				if (!draggedPath) return;

				// Don't allow dropping on itself
				if (draggedPath === targetFolder) return;

				// Don't allow dropping a folder into its own child
				if (targetFolder && targetFolder.startsWith(draggedPath + "/"))
					return;

				// Calculate new path
				const fileName = draggedPath.split("/").pop()!;
				const newPath = targetFolder
					? `${targetFolder}/${fileName}`
					: fileName;

				// Don't do anything if the path hasn't changed
				if (draggedPath === newPath) return;

				setIsProcessing(true);

				// Get source and target folders
				const sourceFolder = draggedPath.includes("/")
					? draggedPath.substring(0, draggedPath.lastIndexOf("/"))
					: "";
				const targetFolderPath = targetFolder || "";

				// Update tab paths if any tabs have this file/folder open
				updateTabPath(draggedPath, newPath);

				await fileService.renamePath(draggedPath, newPath);

				// Reload affected folders
				await loadFiles(sourceFolder); // Reload source folder
				if (sourceFolder !== targetFolderPath) {
					await loadFiles(targetFolderPath); // Reload target folder if different
				}

				toast.success(`Moved ${fileName}`);
			} catch (err) {
				toast.error("Failed to move", {
					description:
						err instanceof Error ? err.message : String(err),
				});
			} finally {
				setIsProcessing(false);
			}
		},
		[
			loadFiles,
			updateTabPath,
			startUpload,
			updateProgress,
			recordFailure,
			finishUpload,
			addFilesOptimistically,
			shouldContinueUpload,
		],
	);

	return (
		<div className="flex h-full flex-col relative">
			{/* Loading overlay */}
			{isProcessing && (
				<div className="absolute inset-0 bg-background/80 backdrop-blur-sm z-50 flex items-center justify-center">
					<div className="flex flex-col items-center gap-2">
						<Loader2 className="h-8 w-8 animate-spin text-primary" />
						<p className="text-sm text-muted-foreground">
							Processing...
						</p>
					</div>
				</div>
			)}

			{/* Toolbar */}
			<div className="flex items-center gap-1 border-b p-2">
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
									Loading files...
								</div>
							</div>
						) : files.length === 0 && !creatingItem ? (
							<div className="flex h-full items-center justify-center p-4">
								<div className="text-center text-sm text-muted-foreground">
									<p>No files found</p>
									<p className="mt-2 text-xs">
										Right-click to create files and folders
									</p>
								</div>
							</div>
						) : (
							<div className="space-y-1 p-2">
								{/* Inline new item editor */}
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
											onChange={(e) =>
												setNewItemName(e.target.value)
											}
											onKeyDown={handleNewItemKeyDown}
											onMouseDown={handleInputMouseDown}
											placeholder={
												creatingItem === "folder"
													? "Folder name"
													: "File name"
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
										onFileClick={handleFileClick}
										onFolderToggle={handleFolderToggle}
										onDelete={handleDelete}
										onRename={handleRename}
										onCreateFile={handleCreateFile}
										onCreateFolder={handleCreateFolder}
										isExpanded={isFolderExpanded(file.path)}
										isSelected={
											openFile?.path === file.path
										}
										onDragStart={handleDragStart}
										onDragOver={handleDragOver}
										onDragLeave={handleDragLeave}
										onDrop={handleDrop}
										isDragOver={
											dragOverFolder === file.path
										}
										creatingItem={creatingItem}
										creatingInFolder={creatingInFolder}
										newItemName={newItemName}
										setNewItemName={setNewItemName}
										inputRef={inputRef}
										handleNewItemKeyDown={
											handleNewItemKeyDown
										}
										handleInputMouseDown={
											handleInputMouseDown
										}
										handleCancelNewItem={
											handleCancelNewItem
										}
										renamingFile={renamingFile}
										renameValue={renameValue}
										setRenameValue={setRenameValue}
										renameInputRef={renameInputRef}
										handleRenameKeyDown={
											handleRenameKeyDown
										}
										handleRenameInputMouseDown={
											handleRenameInputMouseDown
										}
										isProcessing={isProcessing}
									/>
								))}
							</div>
						)}
					</div>
				</ContextMenuTrigger>
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
			</ContextMenu>

			{/* Delete Confirmation Dialog */}
			<AlertDialog
				open={!!fileToDelete}
				onOpenChange={(open) => !open && setFileToDelete(null)}
			>
				<AlertDialogContent>
					<AlertDialogHeader>
						<AlertDialogTitle>
							Delete{" "}
							{fileToDelete?.type === "folder"
								? "Folder"
								: "File"}
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

			{/* Upload Conflict Dialog */}
			<AlertDialog
				open={!!uploadConflict}
				onOpenChange={(open) => {
					if (!open && uploadConflict) {
						uploadConflict.onCancel();
					}
				}}
			>
				<AlertDialogContent>
					<AlertDialogHeader>
						<AlertDialogTitle>
							Replace existing files?
						</AlertDialogTitle>
						<AlertDialogDescription>
							{uploadConflict?.count === 1
								? "1 file already exists and will be replaced."
								: `${uploadConflict?.count} files already exist and will be replaced.`}
						</AlertDialogDescription>
					</AlertDialogHeader>
					<AlertDialogFooter>
						<AlertDialogCancel onClick={uploadConflict?.onCancel}>
							Cancel
						</AlertDialogCancel>
						<AlertDialogAction
							onClick={uploadConflict?.onReplaceAll}
						>
							Replace All
						</AlertDialogAction>
					</AlertDialogFooter>
				</AlertDialogContent>
			</AlertDialog>
		</div>
	);
}

interface FileTreeItemProps {
	file: FileTreeNode;
	onFileClick: (file: FileMetadata) => void;
	onFolderToggle: (folder: FileMetadata) => void;
	onDelete: (file: FileMetadata) => void;
	onRename: (file: FileMetadata) => void;
	onCreateFile: (folderPath?: string) => void;
	onCreateFolder: (folderPath?: string) => void;
	isExpanded: boolean;
	isSelected: boolean;
	onDragStart: (e: React.DragEvent, file: FileMetadata) => void;
	onDragOver: (e: React.DragEvent, targetFolder?: string) => void;
	onDragLeave: () => void;
	onDrop: (e: React.DragEvent, targetFolder?: string) => void;
	isDragOver: boolean;
	creatingItem: CreatingItemType;
	creatingInFolder: string | null;
	newItemName: string;
	setNewItemName: (name: string) => void;
	inputRef: React.RefObject<HTMLInputElement | null>;
	handleNewItemKeyDown: (e: React.KeyboardEvent<HTMLInputElement>) => void;
	handleInputMouseDown: (e: React.MouseEvent) => void;
	handleCancelNewItem: () => void;
	renamingFile: FileMetadata | null;
	renameValue: string;
	setRenameValue: (name: string) => void;
	renameInputRef: React.RefObject<HTMLInputElement | null>;
	handleRenameKeyDown: (e: React.KeyboardEvent<HTMLInputElement>) => void;
	handleRenameInputMouseDown: (e: React.MouseEvent) => void;
	isProcessing: boolean;
}

function FileTreeItem({
	file,
	onFileClick,
	onFolderToggle,
	onDelete,
	onRename,
	onCreateFile,
	onCreateFolder,
	isExpanded,
	isSelected,
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
	handleCancelNewItem: _handleCancelNewItem,
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
							<Folder className="h-4 w-4 flex-shrink-0 text-primary" />
						</>
					) : (
						<>
							<div className="w-4" />
							<File className="h-4 w-4 flex-shrink-0 text-muted-foreground" />
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
							draggable
							onClick={() =>
								isFolder
									? onFolderToggle(file)
									: onFileClick(file)
							}
							onDragStart={(e) => onDragStart(e, file)}
							onDragOver={(e) => {
								if (isFolder) {
									e.stopPropagation(); // Prevent highlighting the container
									onDragOver(e, file.path);
								}
							}}
							onDragLeave={onDragLeave}
							onDrop={(e) => {
								if (isFolder) {
									e.stopPropagation(); // Prevent container from handling the drop
									onDrop(e, file.path);
								}
							}}
							className={cn(
								"flex w-full items-center gap-2 rounded px-2 py-1 text-left text-sm transition-colors outline-none",
								isSelected && !isDragOver
									? "bg-accent text-accent-foreground"
									: "",
								!isDragOver && !isSelected
									? "hover:bg-muted"
									: "",
								isDragOver &&
									isFolder &&
									"bg-primary/30 border-2 border-primary",
							)}
							style={{ paddingLeft: `${level * 12 + 8}px` }}
						>
							{isFolder && (
								<>
									{isExpanded ? (
										<ChevronDown className="h-4 w-4 flex-shrink-0 text-muted-foreground" />
									) : (
										<ChevronRight className="h-4 w-4 flex-shrink-0 text-muted-foreground" />
									)}
									<Folder className="h-4 w-4 flex-shrink-0 text-primary" />
								</>
							)}
							{!isFolder && (
								<>
									<div className="w-4" />
									<File className="h-4 w-4 flex-shrink-0 text-muted-foreground" />
								</>
							)}
							<span className="flex-1 truncate">{file.name}</span>
						</button>
					</ContextMenuTrigger>
					<ContextMenuContent>
						{isFolder && (
							<>
								<ContextMenuItem
									onClick={() => onCreateFile(file.path)}
								>
									<FilePlus className="mr-2 h-4 w-4" />
									New File
								</ContextMenuItem>
								<ContextMenuItem
									onClick={() => onCreateFolder(file.path)}
								>
									<FolderPlus className="mr-2 h-4 w-4" />
									New Folder
								</ContextMenuItem>
								<ContextMenuSeparator />
							</>
						)}
						<ContextMenuItem onClick={() => onRename(file)}>
							<Edit2 className="mr-2 h-4 w-4" />
							Rename
						</ContextMenuItem>
						<ContextMenuSeparator />
						<ContextMenuItem
							onClick={() => onDelete(file)}
							className="text-destructive focus:text-destructive"
						>
							<Trash2 className="mr-2 h-4 w-4" />
							Delete
						</ContextMenuItem>
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
						placeholder={
							creatingItem === "folder"
								? "Folder name"
								: "File name"
						}
						disabled={isProcessing}
						className="flex-1 bg-transparent text-sm outline-none disabled:opacity-50 disabled:cursor-not-allowed"
					/>
				</div>
			)}
		</div>
	);
}
