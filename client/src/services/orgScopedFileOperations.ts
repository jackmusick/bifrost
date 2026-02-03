/**
 * Org-Scoped File Operations Adapter
 *
 * Wraps the workspace fileService and provides organization-scoped filtering.
 * Files are displayed in a flat VS Code-style folder hierarchy with organization
 * scope shown as metadata on each file.
 *
 * Unlike the previous version, this no longer uses virtual "org:xxx" path prefixes.
 * Instead, paths are the real file paths and organization info is in metadata.
 */

import type {
	FileNode,
	FileContent,
	FileOperations,
} from "@/components/file-tree/types";
import { fileService, type FileMetadata } from "./fileService";
import { authFetch } from "@/lib/api-client";

export interface Organization {
	id: string;
	name: string;
}

export interface OrgScopedFilterOptions {
	/** Selected organization ID to filter by, null for global only, undefined for all */
	selectedOrgId?: string | null;
	/** Whether to include global-scoped files when filtering by org (default true) */
	includeGlobal?: boolean;
}

/**
 * Convert FileMetadata to FileNode with organization metadata
 */
function toFileNode(
	file: FileMetadata,
	orgId: string | null,
	orgName: string | null,
): FileNode {
	return {
		path: file.path,
		name: file.name,
		type: file.type,
		size: file.size ?? null,
		extension: file.extension ?? null,
		modified: file.modified,
		entityType: file.entity_type,
		entityId: file.entity_id,
		metadata: {
			organizationId: orgId,
			organizationName: orgName,
		},
	};
}

/**
 * Update entity organization via API
 */
async function updateEntityOrganization(
	entityType: string,
	entityId: string,
	organizationId: string | null,
): Promise<void> {
	const endpoints: Record<string, string> = {
		workflow: `/api/workflows/${entityId}`,
		form: `/api/forms/${entityId}`,
		agent: `/api/agents/${entityId}`,
	};

	const endpoint = endpoints[entityType];
	if (!endpoint) {
		throw new Error(`Unknown entity type: ${entityType}`);
	}

	// Use PATCH for workflows/forms, PUT for agents
	const method = entityType === "agent" ? "PUT" : "PATCH";

	const response = await authFetch(endpoint, {
		method,
		headers: { "Content-Type": "application/json" },
		body: JSON.stringify({ organization_id: organizationId }),
	});

	if (!response.ok) {
		throw new Error(
			`Failed to update ${entityType} organization: ${response.statusText}`,
		);
	}
}

/**
 * Create org-scoped file operations adapter
 *
 * @param organizations - List of available organizations
 * @param filterOptions - Optional filter options for org filtering
 * @returns FileOperations implementation with org filtering
 */
export function createOrgScopedFileOperations(
	organizations: Organization[],
	filterOptions?: OrgScopedFilterOptions,
): FileOperations {
	// Build org name lookup
	const orgNames = new Map<string, string>(
		organizations.map((org) => [org.id, org.name]),
	);

	// Get filter settings with defaults
	const selectedOrgId = filterOptions?.selectedOrgId;
	const includeGlobal = filterOptions?.includeGlobal ?? true;

	/**
	 * Check if a file's organization matches the current filter
	 */
	function matchesOrgFilter(fileOrgId: string | null): boolean {
		// If no filter is set (undefined), show all files
		if (selectedOrgId === undefined) {
			return true;
		}

		// If filtering by global (null), only show global files
		if (selectedOrgId === null) {
			return fileOrgId === null;
		}

		// Filtering by a specific org
		if (fileOrgId === selectedOrgId) {
			return true;
		}

		// Include global files if includeGlobal is true
		if (includeGlobal && fileOrgId === null) {
			return true;
		}

		return false;
	}

	/**
	 * Get the display name for an organization
	 */
	function getOrgName(orgId: string | null): string | null {
		if (orgId === null) {
			return "Global";
		}
		return orgNames.get(orgId) ?? null;
	}

	return {
		async list(path: string): Promise<FileNode[]> {
			// Fetch all files recursively to determine which folders have content
			const allFilesRecursive = await fileService.listFiles("", true);

			// Build a set of folder paths that contain files matching the filter
			const foldersWithContent = new Set<string>();

			for (const file of allFilesRecursive) {
				if (file.type === "folder") continue;
				const fileOrgId = file.organization_id ?? null;
				if (!matchesOrgFilter(fileOrgId)) continue;

				// Add all parent folder paths
				const parts = file.path.split("/");
				for (let i = 1; i < parts.length; i++) {
					foldersWithContent.add(parts.slice(0, i).join("/"));
				}
			}

			// Fetch files at this path
			const files = await fileService.listFiles(path);

			// Filter files based on org filter
			const filteredFiles = files.filter((file) => {
				if (file.type === "folder") {
					// Include folders that have files matching the filter
					return foldersWithContent.has(file.path);
				}
				// For files, check org filter match
				const fileOrgId = file.organization_id ?? null;
				return matchesOrgFilter(fileOrgId);
			});

			return filteredFiles.map((f) => {
				const fileOrgId = f.organization_id ?? null;
				return toFileNode(f, fileOrgId, getOrgName(fileOrgId));
			});
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
			encoding?: "utf-8" | "base64",
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
}

/**
 * Change an entity's organization scope via the API
 *
 * @param entityType - The type of entity (workflow, form, agent)
 * @param entityId - The entity's ID
 * @param organizationId - The target organization ID (null for global)
 */
export async function changeEntityOrganization(
	entityType: string,
	entityId: string,
	organizationId: string | null,
): Promise<void> {
	await updateEntityOrganization(entityType, entityId, organizationId);
}
