/**
 * Modular File Tree State Management Hook
 *
 * Manages tree state (expand/collapse, loading, caching) independently
 * of the specific file operations implementation.
 */

import { useState, useCallback } from "react";
import type { FileNode, FileTreeNode, FileOperations } from "./types";

interface FileTreeState {
	/** Map of path -> children for lazy loading */
	fileMap: Map<string, FileNode[]>;
	/** Set of expanded folder paths */
	expandedFolders: Set<string>;
	/** Loading state */
	isLoading: boolean;
}

interface UseFileTreeResult {
	/** Flat list of visible files with hierarchy info */
	files: FileTreeNode[];
	/** Whether the tree is loading */
	isLoading: boolean;
	/** Load files at a path */
	loadFiles: (path: string) => Promise<void>;
	/** Toggle folder expand/collapse */
	toggleFolder: (folderPath: string) => Promise<void>;
	/** Check if a folder is expanded */
	isFolderExpanded: (folderPath: string) => boolean;
	/** Refresh all loaded paths */
	refreshAll: () => Promise<void>;
	/** Optimistically add files to tree (for uploads) */
	addFilesOptimistically: (files: FileNode[], targetFolder: string) => void;
	/** Optimistically remove a file/folder from tree */
	removeFromTree: (path: string, isFolder: boolean) => void;
}

/**
 * Sort files with folders first, then alphabetically
 */
function sortFiles(files: FileNode[]): FileNode[] {
	return [...files].sort((a, b) => {
		// Folders first
		if (a.type === "folder" && b.type !== "folder") return -1;
		if (a.type !== "folder" && b.type === "folder") return 1;
		// Then alphabetically (case-insensitive)
		return a.name.toLowerCase().localeCompare(b.name.toLowerCase());
	});
}

/**
 * File tree state management hook
 *
 * @param operations - File operations implementation
 * @returns Tree state and manipulation functions
 */
export function useFileTree(operations: FileOperations): UseFileTreeResult {
	const [state, setState] = useState<FileTreeState>({
		fileMap: new Map([["", []]]),
		expandedFolders: new Set<string>(),
		isLoading: false,
	});

	/**
	 * Load files at a given path
	 */
	const loadFiles = useCallback(
		async (path: string = "") => {
			setState((prev) => ({ ...prev, isLoading: true }));

			try {
				const allFiles = await operations.list(path);

				// Synthesize folder structure from flat file list
				// The API may return a flat list with full paths
				const directChildren: FileNode[] = [];
				const seenFolders = new Set<string>();

				for (const file of allFiles) {
					// Get the relative path from current directory
					const relativePath = path
						? file.path.slice(path.length + 1)
						: file.path;

					// Skip if the file path doesn't start with the current path
					if (path && !file.path.startsWith(path + "/")) {
						continue;
					}

					// Check if this is a direct child or nested deeper
					const slashIndex = relativePath.indexOf("/");

					if (slashIndex === -1) {
						// Direct child - add as-is
						directChildren.push(file);
					} else {
						// Nested file - extract the immediate folder name
						const folderName = relativePath.slice(0, slashIndex);
						const folderPath = path ? `${path}/${folderName}` : folderName;

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
							});
						}
					}
				}

				const sortedFiles = sortFiles(directChildren);
				setState((prev) => {
					const newFileMap = new Map(prev.fileMap);
					newFileMap.set(path, sortedFiles);
					return {
						...prev,
						fileMap: newFileMap,
						isLoading: false,
					};
				});
			} catch {
				setState((prev) => ({ ...prev, isLoading: false }));
			}
		},
		[operations],
	);

	/**
	 * Toggle folder expand/collapse
	 */
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

	/**
	 * Check if a folder is expanded
	 */
	const isFolderExpanded = useCallback(
		(folderPath: string) => {
			return state.expandedFolders.has(folderPath);
		},
		[state.expandedFolders],
	);

	/**
	 * Refresh all loaded paths
	 */
	const refreshAll = useCallback(async () => {
		let foldersToReload: string[] = [];
		setState((prev) => {
			foldersToReload = Array.from(prev.expandedFolders);
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
	 * Optimistically add files to the tree without refetching
	 */
	const addFilesOptimistically = useCallback(
		(newFiles: FileNode[], targetFolder: string) => {
			setState((prev) => {
				const newFileMap = new Map(prev.fileMap);
				const newExpandedFolders = new Set(prev.expandedFolders);

				// Track all items by parent path
				const itemsByParent = new Map<string, FileNode[]>();
				const foldersQueued = new Set<string>();

				for (const file of newFiles) {
					const parentPath = file.path.includes("/")
						? file.path.substring(0, file.path.lastIndexOf("/"))
						: "";

					// Create intermediate folder entries
					const pathParts = file.path.split("/");
					for (let i = 0; i < pathParts.length - 1; i++) {
						const folderPath = pathParts.slice(0, i + 1).join("/");
						const folderParentPath =
							i === 0 ? "" : pathParts.slice(0, i).join("/");

						const existingInParent = newFileMap.get(folderParentPath) || [];
						const folderExistsInMap = existingInParent.some(
							(f) => f.path === folderPath,
						);
						const folderAlreadyQueued = foldersQueued.has(folderPath);

						if (!folderExistsInMap && !folderAlreadyQueued) {
							const folderEntry: FileNode = {
								path: folderPath,
								name: pathParts[i],
								type: "folder",
								size: null,
								extension: null,
								modified: new Date().toISOString(),
							};

							if (!itemsByParent.has(folderParentPath)) {
								itemsByParent.set(folderParentPath, []);
							}
							itemsByParent.get(folderParentPath)!.push(folderEntry);
							foldersQueued.add(folderPath);
							newExpandedFolders.add(folderPath);
						} else {
							newExpandedFolders.add(folderPath);
						}

						if (!newFileMap.has(folderPath)) {
							newFileMap.set(folderPath, []);
						}
					}

					// Add the file itself
					if (!itemsByParent.has(parentPath)) {
						itemsByParent.set(parentPath, []);
					}
					itemsByParent.get(parentPath)!.push(file);
				}

				// Merge items into fileMap
				for (const [parentPath, items] of itemsByParent) {
					const existing = newFileMap.get(parentPath) || [];
					const existingPaths = new Set(existing.map((f) => f.path));
					const newItems = items.filter((item) => !existingPaths.has(item.path));
					const combined = [...existing, ...newItems];
					newFileMap.set(parentPath, sortFiles(combined));
				}

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
	 * Optimistically remove a file or folder from the tree
	 */
	const removeFromTree = useCallback((path: string, isFolder: boolean) => {
		setState((prev) => {
			const newFileMap = new Map(prev.fileMap);
			const newExpandedFolders = new Set(prev.expandedFolders);

			const parentPath = path.includes("/")
				? path.substring(0, path.lastIndexOf("/"))
				: "";

			// Remove from parent's children
			const parentFiles = newFileMap.get(parentPath) || [];
			newFileMap.set(
				parentPath,
				parentFiles.filter((f) => f.path !== path),
			);

			if (isFolder) {
				newExpandedFolders.delete(path);

				// Remove all cached children
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

	/**
	 * Build flat list of visible files with hierarchy info
	 */
	const buildVisibleFiles = useCallback((): FileTreeNode[] => {
		const result: FileTreeNode[] = [];

		const addFilesRecursively = (path: string, level: number) => {
			const files = state.fileMap.get(path) || [];

			for (const file of files) {
				const node: FileTreeNode = { ...file, level };
				result.push(node);

				if (file.type === "folder" && state.expandedFolders.has(file.path)) {
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
		loadFiles,
		toggleFolder,
		isFolderExpanded,
		refreshAll,
		addFilesOptimistically,
		removeFromTree,
	};
}
