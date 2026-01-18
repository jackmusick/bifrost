/**
 * Modular File Tree Types
 *
 * These types define the interfaces for a reusable file tree component
 * that can work with different backends (workspace files, JSX files, etc.)
 */

import type { LucideIcon } from "lucide-react";

/**
 * Represents a file or folder in the tree
 */
export interface FileNode {
	/** Full path relative to root (e.g., "pages/clients/[id]") */
	path: string;
	/** Display name (last segment of path) */
	name: string;
	/** Whether this is a file or folder */
	type: "file" | "folder";
	/** File size in bytes (null for folders) */
	size: number | null;
	/** File extension without dot (null for folders) */
	extension: string | null;
	/** Last modified timestamp (ISO string) */
	modified: string;
	/** Platform entity type (workflow, form, app, agent) - for icon display */
	entityType?: string | null;
	/** Platform entity ID */
	entityId?: string | null;
	/** Custom metadata for specific implementations */
	metadata?: Record<string, unknown>;
}

/**
 * FileNode with tree hierarchy information
 */
export interface FileTreeNode extends FileNode {
	/** Nesting level (0 = root) */
	level: number;
	/** Child nodes (for folders) */
	children?: FileTreeNode[];
}

/**
 * File content with optional ETag for conflict detection
 */
export interface FileContent {
	content: string;
	encoding: "utf-8" | "base64";
	etag?: string;
}

/**
 * Abstract file operations interface
 *
 * Implementations provide the actual API calls for different backends:
 * - WorkspaceFileOperations: Workspace editor files
 * - JsxFileOperations: App Builder JSX files
 * - OrgScopedFileOperations: Organization-scoped file trees
 */
export interface FileOperations {
	/**
	 * List files and folders at a path
	 * @param path - Directory path (empty string for root)
	 * @returns Array of files/folders at that path
	 */
	list(path: string): Promise<FileNode[]>;

	/**
	 * Read file content
	 * @param path - File path
	 * @returns File content with encoding and optional etag
	 */
	read(path: string): Promise<FileContent>;

	/**
	 * Create or update a file
	 * @param path - File path
	 * @param content - File content
	 * @param encoding - Content encoding
	 * @param etag - Expected etag for conflict detection
	 */
	write(
		path: string,
		content: string,
		encoding?: "utf-8" | "base64",
		etag?: string,
	): Promise<void>;

	/**
	 * Create a folder
	 * @param path - Folder path
	 */
	createFolder(path: string): Promise<void>;

	/**
	 * Delete a file or folder
	 * @param path - Path to delete
	 */
	delete(path: string): Promise<void>;

	/**
	 * Rename or move a file/folder
	 * @param oldPath - Current path
	 * @param newPath - New path
	 */
	rename(oldPath: string, newPath: string): Promise<void>;
}

/**
 * Icon configuration for file tree items
 */
export interface FileIconConfig {
	icon: LucideIcon;
	className: string;
}

/**
 * Function to resolve icons for file tree items
 *
 * Implementations can customize icons based on:
 * - Entity type (workflow, form, app)
 * - File extension
 * - Path patterns (pages/, components/)
 * - Custom metadata
 */
export type FileIconResolver = (file: FileNode) => FileIconConfig;

/**
 * Callbacks for editor integration (optional)
 *
 * These allow the file tree to communicate with an editor component
 * without being tightly coupled to a specific editor implementation.
 */
export interface EditorCallbacks {
	/** Called when user clicks a file to open it */
	onFileOpen?: (file: FileNode, content: FileContent) => void;
	/** Called when a file is deleted (to close tabs) */
	onFileDeleted?: (path: string, isFolder: boolean) => void;
	/** Called when a file is renamed (to update tabs) */
	onFileRenamed?: (oldPath: string, newPath: string) => void;
	/** Check if a file is currently selected/active */
	isFileSelected?: (path: string) => boolean;
	/** Called when loading state changes */
	onLoadingChange?: (isLoading: boolean) => void;
}

/**
 * Configuration for file tree behavior
 */
export interface FileTreeConfig {
	/** Enable drag-and-drop file uploads from desktop */
	enableUpload?: boolean;
	/** Enable drag-and-drop reordering/moving */
	enableDragMove?: boolean;
	/** Enable create file/folder operations */
	enableCreate?: boolean;
	/** Enable rename operations */
	enableRename?: boolean;
	/** Enable delete operations */
	enableDelete?: boolean;
	/** Custom empty state message */
	emptyMessage?: string;
	/** Custom loading message */
	loadingMessage?: string;
}

/**
 * Props for the modular FileTree component
 */
export interface FileTreeProps {
	/** File operations implementation */
	operations: FileOperations;
	/** Optional editor integration callbacks */
	editor?: EditorCallbacks;
	/** Custom icon resolver (falls back to default) */
	iconResolver?: FileIconResolver;
	/** Behavior configuration */
	config?: FileTreeConfig;
	/** Additional CSS classes */
	className?: string;
}
