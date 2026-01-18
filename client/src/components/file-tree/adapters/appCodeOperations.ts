/**
 * App Code File Operations Adapter
 *
 * Provides FileOperations for the App Code Builder editor.
 * Works with the /api/applications/{app_id}/versions/{version_id}/files endpoints.
 */

import { authFetch } from "@/lib/api-client";
import type { FileNode, FileContent, FileOperations } from "../types";

/**
 * App code file from API response
 */
interface AppCodeFileResponse {
	id: string;
	app_version_id: string;
	path: string;
	source: string;
	compiled: string | null;
	created_at: string;
	updated_at: string;
}

/**
 * Convert app code file response to FileNode
 */
function toFileNode(file: AppCodeFileResponse): FileNode {
	const pathParts = file.path.split("/");
	const name = pathParts[pathParts.length - 1];

	return {
		path: file.path,
		name,
		type: "file", // App code API only has files, folders are virtual
		size: file.source.length,
		extension: null, // App code files don't have extensions in path
		modified: file.updated_at,
		metadata: {
			id: file.id,
			compiled: file.compiled,
		},
	};
}

/**
 * Create app code file operations for a specific app version
 *
 * @param appId - Application UUID
 * @param versionId - Version UUID (draft or active)
 * @returns FileOperations implementation for app code files
 */
export function createAppCodeOperations(appId: string, versionId: string): FileOperations {
	const baseUrl = `/api/applications/${appId}/versions/${versionId}/files`;

	return {
		async list(path: string): Promise<FileNode[]> {
			const response = await authFetch(baseUrl);

			if (!response.ok) {
				throw new Error(`Failed to list files: ${response.statusText}`);
			}

			const data = await response.json();
			const files: AppCodeFileResponse[] = data.files || [];

			// Filter to files under the requested path
			// The API returns all files, so we filter client-side
			const filteredFiles = path
				? files.filter((f) => f.path.startsWith(path + "/") || f.path === path)
				: files;

			return filteredFiles.map(toFileNode);
		},

		async read(path: string): Promise<FileContent> {
			const response = await authFetch(`${baseUrl}/${encodeURIComponent(path)}`);

			if (!response.ok) {
				throw new Error(`Failed to read file: ${response.statusText}`);
			}

			const file: AppCodeFileResponse = await response.json();

			return {
				content: file.source,
				encoding: "utf-8",
				// Use updated_at as etag for optimistic locking
				etag: file.updated_at,
			};
		},

		async write(
			path: string,
			content: string,
			_encoding: "utf-8" | "base64" = "utf-8",
			_etag?: string,
		): Promise<void> {
			// Check if file exists first
			const checkResponse = await authFetch(`${baseUrl}/${encodeURIComponent(path)}`);

			if (checkResponse.ok) {
				// File exists, update it
				const response = await authFetch(`${baseUrl}/${encodeURIComponent(path)}`, {
					method: "PATCH",
					headers: { "Content-Type": "application/json" },
					body: JSON.stringify({ source: content }),
				});

				if (!response.ok) {
					throw new Error(`Failed to update file: ${response.statusText}`);
				}
			} else if (checkResponse.status === 404) {
				// File doesn't exist, create it
				const response = await authFetch(baseUrl, {
					method: "POST",
					headers: { "Content-Type": "application/json" },
					body: JSON.stringify({ path, source: content }),
				});

				if (!response.ok) {
					throw new Error(`Failed to create file: ${response.statusText}`);
				}
			} else {
				throw new Error(`Failed to check file: ${checkResponse.statusText}`);
			}
		},

		async createFolder(_path: string): Promise<void> {
			// App code files don't have real folders - they're virtual based on paths
			// Creating a folder is a no-op, files will create the path structure
		},

		async delete(path: string): Promise<void> {
			const response = await authFetch(`${baseUrl}/${encodeURIComponent(path)}`, {
				method: "DELETE",
			});

			if (!response.ok && response.status !== 404) {
				throw new Error(`Failed to delete file: ${response.statusText}`);
			}
		},

		async rename(oldPath: string, newPath: string): Promise<void> {
			// Read the old file
			const content = await this.read(oldPath);

			// Create at new path
			await this.write(newPath, content.content);

			// Delete old file
			await this.delete(oldPath);
		},
	};
}
