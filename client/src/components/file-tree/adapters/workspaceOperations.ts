/**
 * Workspace File Operations Adapter
 *
 * Wraps the existing fileService to conform to the FileOperations interface.
 * Used by the code editor for workspace files.
 */

import { fileService } from "@/services/fileService";
import type { FileNode, FileContent, FileOperations } from "../types";

/**
 * Convert FileMetadata from API to FileNode
 */
function toFileNode(file: {
	path: string;
	name: string;
	type: "file" | "folder";
	size?: number | null;
	extension?: string | null;
	modified: string;
	entity_type?: string | null;
	entity_id?: string | null;
}): FileNode {
	return {
		path: file.path,
		name: file.name,
		type: file.type,
		size: file.size ?? null,
		extension: file.extension ?? null,
		modified: file.modified,
		entityType: file.entity_type ?? null,
		entityId: file.entity_id ?? null,
	};
}

/**
 * Workspace file operations implementation
 *
 * This adapter wraps the existing fileService to work with
 * the modular file tree component.
 */
export const workspaceOperations: FileOperations = {
	async list(path: string): Promise<FileNode[]> {
		const files = await fileService.listFiles(path);
		return files.map(toFileNode);
	},

	async read(path: string): Promise<FileContent> {
		const response = await fileService.readFile(path);
		return {
			content: response.content,
			encoding: response.encoding as "utf-8" | "base64",
			etag: response.etag,
		};
	},

	async write(
		path: string,
		content: string,
		encoding: "utf-8" | "base64" = "utf-8",
		etag?: string,
	): Promise<void> {
		await fileService.writeFile(path, content, encoding, etag);
	},

	async createFolder(path: string): Promise<void> {
		await fileService.createFolder(path);
	},

	async delete(path: string): Promise<void> {
		await fileService.deletePath(path);
	},

	async rename(oldPath: string, newPath: string): Promise<void> {
		await fileService.renamePath(oldPath, newPath);
	},
};
