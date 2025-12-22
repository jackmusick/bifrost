/**
 * Editor File Operations API service
 * Uses auto-generated types from OpenAPI spec
 */

import type { components } from "@/lib/v1";
import { authFetch } from "@/lib/api-client";

// Auto-generated types from OpenAPI spec
export type FileMetadata = components["schemas"]["FileMetadata"];
export type FileContentRequest = components["schemas"]["FileContentRequest"];
export type FileContentResponse = components["schemas"]["FileContentResponse"];
export type FileConflictResponse = components["schemas"]["FileConflictResponse"];

// Custom error for file conflicts
export class FileConflictError extends Error {
	constructor(public conflictData: FileConflictResponse) {
		super(conflictData.message);
		this.name = "FileConflictError";
	}
}

export const fileService = {
	/**
	 * List files and folders in a directory
	 */
	async listFiles(path: string = ""): Promise<FileMetadata[]> {
		const response = await authFetch(
			`/api/editor/files?path=${encodeURIComponent(path)}`,
		);

		if (!response.ok) {
			throw new Error(`Failed to list files: ${response.statusText}`);
		}

		return response.json();
	},

	/**
	 * Read file content
	 */
	async readFile(path: string): Promise<FileContentResponse> {
		const response = await authFetch(
			`/api/editor/files/content?path=${encodeURIComponent(path)}`,
		);

		if (!response.ok) {
			throw new Error(`Failed to read file: ${response.statusText}`);
		}

		return response.json();
	},

	/**
	 * Write file content
	 *
	 * @param index - If true, inject IDs into decorators. If false (default), detect if IDs needed.
	 */
	async writeFile(
		path: string,
		content: string,
		encoding: "utf-8" | "base64" = "utf-8",
		expectedEtag?: string,
		index: boolean = false,
	): Promise<FileContentResponse> {
		const body: FileContentRequest = {
			path,
			content,
			encoding,
			expected_etag: expectedEtag ?? null,
		};

		const url = index
			? "/api/editor/files/content?index=true"
			: "/api/editor/files/content";

		const response = await authFetch(url, {
			method: "PUT",
			body: JSON.stringify(body),
		});

		// Handle conflict responses
		if (response.status === 409) {
			const conflictData =
				(await response.json()) as FileConflictResponse;
			throw new FileConflictError(conflictData);
		}

		if (!response.ok) {
			throw new Error(`Failed to write file: ${response.statusText}`);
		}

		return response.json();
	},

	/**
	 * Create a new folder
	 */
	async createFolder(path: string): Promise<FileMetadata> {
		const response = await authFetch(
			`/api/editor/files/folder?path=${encodeURIComponent(path)}`,
			{ method: "POST" },
		);

		if (!response.ok) {
			throw new Error(`Failed to create folder: ${response.statusText}`);
		}

		return response.json();
	},

	/**
	 * Delete a file or folder
	 */
	async deletePath(path: string): Promise<void> {
		const response = await authFetch(
			`/api/editor/files?path=${encodeURIComponent(path)}`,
			{ method: "DELETE" },
		);

		if (!response.ok) {
			throw new Error(`Failed to delete: ${response.statusText}`);
		}
	},

	/**
	 * Rename or move a file or folder
	 */
	async renamePath(oldPath: string, newPath: string): Promise<FileMetadata> {
		const response = await authFetch(
			`/api/editor/files/rename?old_path=${encodeURIComponent(oldPath)}&new_path=${encodeURIComponent(newPath)}`,
			{ method: "POST" },
		);

		if (!response.ok) {
			throw new Error(`Failed to rename: ${response.statusText}`);
		}

		return response.json();
	},
};
