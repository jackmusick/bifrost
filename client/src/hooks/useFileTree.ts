import { useState, useCallback } from "react";
import { fileService, type FileMetadata } from "@/services/fileService";

export interface FileTreeNode extends FileMetadata {
	children?: FileTreeNode[];
	level: number;
}

interface FileTreeState {
	fileMap: Map<string, FileMetadata[]>; // path -> children mapping
	expandedFolders: Set<string>;
	loadingFolders: Set<string>;
	isLoading: boolean;
}

/**
 * File tree state management hook
 * Handles loading files, expand/collapse state, and hierarchical tree structure
 */
export function useFileTree() {
	const [state, setState] = useState<FileTreeState>({
		fileMap: new Map([["", []]]), // Initialize with root
		expandedFolders: new Set<string>(),
		loadingFolders: new Set<string>(),
		isLoading: false,
	});

	const sortFiles = (files: FileMetadata[]): FileMetadata[] => {
		return [...files].sort((a, b) => {
			// Folders first
			if (a.type === "folder" && b.type !== "folder") return -1;
			if (a.type !== "folder" && b.type === "folder") return 1;

			// Then alphabetically (case-insensitive)
			return a.name.toLowerCase().localeCompare(b.name.toLowerCase());
		});
	};

	const loadFiles = useCallback(async (path: string = "") => {
		setState((prev) => {
			const newLoadingFolders = new Set(prev.loadingFolders);
			newLoadingFolders.add(path);
			return { ...prev, isLoading: true, loadingFolders: newLoadingFolders };
		});

		try {
			const allFiles = await fileService.listFiles(path);

			// Synthesize folder structure from flat file list
			// The API returns a flat list of files with full paths, but no folder entries
			const directChildren: FileMetadata[] = [];
			const seenFolders = new Set<string>();

			for (const file of allFiles) {
				// Get the relative path from current directory
				const relativePath = path
					? file.path.slice(path.length + 1)
					: file.path;

				// Skip if the file path doesn't start with the current path
				// (shouldn't happen, but safety check)
				if (path && !file.path.startsWith(path + "/")) {
					continue;
				}

				// Check if this is a direct child or nested deeper
				const slashIndex = relativePath.indexOf("/");

				if (slashIndex === -1) {
					// Direct child file - add as-is
					directChildren.push(file);
				} else {
					// Nested file - extract the immediate folder name
					const folderName = relativePath.slice(0, slashIndex);
					const folderPath = path
						? `${path}/${folderName}`
						: folderName;

					if (!seenFolders.has(folderPath)) {
						seenFolders.add(folderPath);
						// Create synthetic folder entry
						directChildren.push({
							path: folderPath,
							name: folderName,
							type: "folder",
							size: null,
							extension: null,
							modified: new Date().toISOString(),
							entity_type: null,
							entity_id: null,
						});
					}
				}
			}

			const sortedFiles = sortFiles(directChildren);
			setState((prev) => {
				const newFileMap = new Map(prev.fileMap);
				newFileMap.set(path, sortedFiles);
				const newLoadingFolders = new Set(prev.loadingFolders);
				newLoadingFolders.delete(path);
				return {
					...prev,
					fileMap: newFileMap,
					isLoading: newLoadingFolders.size > 0,
					loadingFolders: newLoadingFolders,
				};
			});
		} catch {
			setState((prev) => {
				const newLoadingFolders = new Set(prev.loadingFolders);
				newLoadingFolders.delete(path);
				return { ...prev, isLoading: newLoadingFolders.size > 0, loadingFolders: newLoadingFolders };
			});
		}
	}, []);

	const toggleFolder = useCallback(
		async (folderPath: string) => {
			setState((prev) => {
				const newExpandedFolders = new Set(prev.expandedFolders);
				const wasExpanded = newExpandedFolders.has(folderPath);

				if (wasExpanded) {
					newExpandedFolders.delete(folderPath);
				} else {
					newExpandedFolders.add(folderPath);
				}

				return {
					...prev,
					expandedFolders: newExpandedFolders,
				};
			});

			// Load folder contents if not already loaded and expanding
			if (
				!state.expandedFolders.has(folderPath) &&
				!state.fileMap.has(folderPath)
			) {
				await loadFiles(folderPath);
			}
		},
		[state.expandedFolders, state.fileMap, loadFiles],
	);

	const isFolderExpanded = useCallback(
		(folderPath: string) => {
			return state.expandedFolders.has(folderPath);
		},
		[state.expandedFolders],
	);

	const isFolderLoading = useCallback(
		(folderPath: string) => {
			return state.loadingFolders.has(folderPath);
		},
		[state.loadingFolders],
	);

	const refreshAll = useCallback(async () => {
		// Get current expanded folders using functional setState to avoid stale closure
		let foldersToReload: string[] = [];
		setState((prev) => {
			foldersToReload = Array.from(prev.expandedFolders);
			// Clear fileMap to force fresh data, but keep expandedFolders
			return {
				...prev,
				fileMap: new Map([["", []]]),
				isLoading: true,
			};
		});

		// Reload root
		await loadFiles("");

		// Reload all expanded folders
		for (const folderPath of foldersToReload) {
			await loadFiles(folderPath);
		}

		setState((prev) => ({ ...prev, isLoading: false }));
	}, [loadFiles]);

	/**
	 * Optimistically add files to the tree without refetching from the server.
	 * Creates intermediate folders as needed for nested paths.
	 *
	 * @param newFiles - Array of FileMetadata to add
	 * @param targetFolder - Base folder where files were dropped (empty string for root)
	 */
	const addFilesOptimistically = useCallback(
		(newFiles: FileMetadata[], targetFolder: string) => {
			setState((prev) => {
				const newFileMap = new Map(prev.fileMap);
				const newExpandedFolders = new Set(prev.expandedFolders);

				// Track all folders we need to create and files to add by parent path
				const itemsByParent = new Map<string, FileMetadata[]>();
				// Track folders we've already queued for creation in this batch
				const foldersQueued = new Set<string>();

				for (const file of newFiles) {
					// Get the parent path for this file
					const parentPath = file.path.includes("/")
						? file.path.substring(0, file.path.lastIndexOf("/"))
						: "";

					// Create intermediate folder entries for nested paths
					// For path "a/b/c/file.txt", create entries for "a", "a/b", "a/b/c"
					const pathParts = file.path.split("/");
					for (let i = 0; i < pathParts.length - 1; i++) {
						const folderPath = pathParts.slice(0, i + 1).join("/");
						const folderParentPath =
							i === 0 ? "" : pathParts.slice(0, i).join("/");

						// Check if folder already exists in fileMap OR already queued in this batch
						const existingInParent =
							newFileMap.get(folderParentPath) || [];
						const folderExistsInMap = existingInParent.some(
							(f) => f.path === folderPath,
						);
						const folderAlreadyQueued =
							foldersQueued.has(folderPath);

						if (!folderExistsInMap && !folderAlreadyQueued) {
							// Create folder entry
							const folderEntry: FileMetadata = {
								path: folderPath,
								name: pathParts[i],
								type: "folder",
								size: null,
								extension: null,
								modified: new Date().toISOString(),
								entity_type: null,
								entity_id: null,
							};

							if (!itemsByParent.has(folderParentPath)) {
								itemsByParent.set(folderParentPath, []);
							}
							itemsByParent
								.get(folderParentPath)!
								.push(folderEntry);
							foldersQueued.add(folderPath);

							// Auto-expand folders that contain new files
							newExpandedFolders.add(folderPath);
						} else {
							// Folder exists, just expand it
							newExpandedFolders.add(folderPath);
						}

						// Initialize folder's children array if not present
						if (!newFileMap.has(folderPath)) {
							newFileMap.set(folderPath, []);
						}
					}

					// Add the file itself to its parent folder
					if (!itemsByParent.has(parentPath)) {
						itemsByParent.set(parentPath, []);
					}
					itemsByParent.get(parentPath)!.push(file);
				}

				// Merge items into fileMap
				for (const [parentPath, items] of itemsByParent) {
					const existing = newFileMap.get(parentPath) || [];
					const existingPaths = new Set(existing.map((f) => f.path));

					// Filter out duplicates
					const newItems = items.filter(
						(item) => !existingPaths.has(item.path),
					);

					// Combine and sort
					const combined = [...existing, ...newItems];
					const sorted = sortFiles(combined);
					newFileMap.set(parentPath, sorted);
				}

				// Expand target folder if not root
				if (targetFolder) {
					newExpandedFolders.add(targetFolder);
				}

				return {
					...prev,
					fileMap: newFileMap,
					expandedFolders: newExpandedFolders,
				};
			});
		},
		[],
	);

	/**
	 * Optimistically remove a file or folder from the tree.
	 * Cleans up all related state including cached children and expanded folder state.
	 *
	 * @param path - Path of the file or folder to remove
	 * @param isFolder - Whether the item is a folder
	 */
	const removeFromTree = useCallback((path: string, isFolder: boolean) => {
		setState((prev) => {
			const newFileMap = new Map(prev.fileMap);
			const newExpandedFolders = new Set(prev.expandedFolders);

			// Get parent path
			const parentPath = path.includes("/")
				? path.substring(0, path.lastIndexOf("/"))
				: "";

			// Remove from parent's children list
			const parentFiles = newFileMap.get(parentPath) || [];
			newFileMap.set(
				parentPath,
				parentFiles.filter((f) => f.path !== path),
			);

			if (isFolder) {
				// Remove from expanded folders
				newExpandedFolders.delete(path);

				// Remove all cached children (any path starting with this folder)
				for (const key of newFileMap.keys()) {
					if (key === path || key.startsWith(path + "/")) {
						newFileMap.delete(key);
					}
				}

				// Remove any expanded subfolders
				for (const folderPath of newExpandedFolders) {
					if (folderPath.startsWith(path + "/")) {
						newExpandedFolders.delete(folderPath);
					}
				}
			}

			return {
				...prev,
				fileMap: newFileMap,
				expandedFolders: newExpandedFolders,
			};
		});
	}, []);

	// Build flat list of visible files with proper hierarchy
	const buildVisibleFiles = useCallback((): FileTreeNode[] => {
		const result: FileTreeNode[] = [];

		const addFilesRecursively = (path: string, level: number) => {
			const files = state.fileMap.get(path) || [];

			for (const file of files) {
				const node: FileTreeNode = { ...file, level };
				result.push(node);

				// If it's a folder and it's expanded, add its children
				if (
					file.type === "folder" &&
					state.expandedFolders.has(file.path)
				) {
					addFilesRecursively(file.path, level + 1);
				}
			}
		};

		addFilesRecursively("", 0);
		return result;
	}, [state.fileMap, state.expandedFolders]);

	return {
		files: buildVisibleFiles(),
		isLoading: state.isLoading,
		isFolderLoading,
		loadFiles,
		toggleFolder,
		isFolderExpanded,
		refreshAll,
		addFilesOptimistically,
		removeFromTree,
	};
}
