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
export type FileConflictResponse =
	components["schemas"]["FileConflictResponse"];

// Deactivation protection types
export type PendingDeactivation = components["schemas"]["PendingDeactivation"];
export type AvailableReplacement =
	components["schemas"]["AvailableReplacement"];
export type AffectedEntity = components["schemas"]["AffectedEntity"];

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
	 * @param path - Directory path relative to workspace root
	 * @param recursive - If true, return all files recursively (not just direct children)
	 */
	async listFiles(
		path: string = "",
		recursive: boolean = false,
	): Promise<FileMetadata[]> {
		const params = new URLSearchParams({ path });
		if (recursive) {
			params.set("recursive", "true");
		}
		const response = await authFetch(`/api/files/editor?${params}`);

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
			`/api/files/editor/content?path=${encodeURIComponent(path)}`,
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
	 * @param forceIds - Map of function_name -> ID to inject. Used when user chooses "Use Existing IDs".
	 * @param forceDeactivation - If true, skip deactivation protection and allow removing functions with dependencies.
	 * @param replacements - Map of workflow_id -> new_function_name for identity transfer during deactivation.
	 */
	async writeFile(
		path: string,
		content: string,
		encoding: "utf-8" | "base64" = "utf-8",
		expectedEtag?: string,
		index: boolean = false,
		forceIds?: Record<string, string>,
		forceDeactivation?: boolean,
		replacements?: Record<string, string>,
		workflowsToDeactivate?: string[],
	): Promise<FileContentResponse> {
		const body: FileContentRequest & {
			force_ids?: Record<string, string> | null;
			force_deactivation?: boolean;
			replacements?: Record<string, string> | null;
			workflows_to_deactivate?: string[] | null;
		} = {
			path,
			content,
			encoding,
			expected_etag: expectedEtag ?? null,
			force_ids: forceIds ?? null,
			force_deactivation: forceDeactivation ?? false,
			replacements: replacements ?? null,
			workflows_to_deactivate: workflowsToDeactivate ?? null,
		};

		const url = index
			? "/api/files/editor/content?index=true"
			: "/api/files/editor/content";

		const response = await authFetch(url, {
			method: "PUT",
			body: JSON.stringify(body),
		});

		// Handle conflict responses
		if (response.status === 409) {
			const responseBody = await response.json();
			// FastAPI's HTTPException wraps the response in { detail: {...} }
			const conflictData = (responseBody.detail ??
				responseBody) as FileConflictResponse;
			throw new FileConflictError(conflictData);
		}

		if (!response.ok) {
			// Try to extract detail from JSON error response (e.g., 403 for .bifrost/ files)
			let detail = response.statusText;
			try {
				const errorBody = await response.json();
				if (errorBody.detail) {
					detail = typeof errorBody.detail === "string"
						? errorBody.detail
						: JSON.stringify(errorBody.detail);
				}
			} catch {
				// Ignore JSON parse errors, fall back to statusText
			}
			throw new Error(detail);
		}

		return response.json();
	},

	/**
	 * Create a new folder
	 */
	async createFolder(path: string): Promise<FileMetadata> {
		const response = await authFetch(
			`/api/files/editor/folder?path=${encodeURIComponent(path)}`,
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
			`/api/files/editor?path=${encodeURIComponent(path)}`,
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
			`/api/files/editor/rename?old_path=${encodeURIComponent(oldPath)}&new_path=${encodeURIComponent(newPath)}`,
			{ method: "POST" },
		);

		if (!response.ok) {
			throw new Error(`Failed to rename: ${response.statusText}`);
		}

		return response.json();
	},
};
