/**
 * Org-Scoped File Operations Adapter
 *
 * Wraps the workspace fileService and transforms the flat file list into
 * an org-grouped structure with virtual org containers at the root.
 *
 * Path convention:
 * - Root lists org containers: "org:global", "org:{uuid}"
 * - Within org: "org:global/workflows/file.py" -> real path "workflows/file.py"
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

const ORG_PREFIX = "org:";
const GLOBAL_ORG_ID = "global";

/**
 * Extract org ID from virtual path
 * "org:global/workflows/file.py" -> "global"
 * "org:abc123/forms/test.json" -> "abc123"
 */
function extractOrgId(path: string): string | null {
	if (!path.startsWith(ORG_PREFIX)) return null;
	const withoutPrefix = path.slice(ORG_PREFIX.length);
	const slashIdx = withoutPrefix.indexOf("/");
	return slashIdx === -1 ? withoutPrefix : withoutPrefix.slice(0, slashIdx);
}

/**
 * Extract real path from virtual path
 * "org:global/workflows/file.py" -> "workflows/file.py"
 * "org:abc123" -> ""
 */
function extractRealPath(path: string): string {
	if (!path.startsWith(ORG_PREFIX)) return path;
	const withoutPrefix = path.slice(ORG_PREFIX.length);
	const slashIdx = withoutPrefix.indexOf("/");
	return slashIdx === -1 ? "" : withoutPrefix.slice(slashIdx + 1);
}

/**
 * Build virtual path from org ID and real path
 */
function buildVirtualPath(orgId: string | null, realPath: string): string {
	const orgPart = orgId ?? GLOBAL_ORG_ID;
	return realPath
		? `${ORG_PREFIX}${orgPart}/${realPath}`
		: `${ORG_PREFIX}${orgPart}`;
}

/**
 * Convert FileMetadata to FileNode with virtual path
 */
function toFileNode(file: FileMetadata, orgId: string | null): FileNode {
	return {
		path: buildVirtualPath(orgId, file.path),
		name: file.name,
		type: file.type,
		size: file.size ?? null,
		extension: file.extension ?? null,
		modified: file.modified,
		entityType: file.entity_type,
		entityId: file.entity_id,
		metadata: {
			realPath: file.path,
			organizationId: orgId,
		},
	};
}

/**
 * Create org container FileNode
 */
function createOrgContainer(orgId: string | null, orgName: string): FileNode {
	return {
		path: `${ORG_PREFIX}${orgId ?? GLOBAL_ORG_ID}`,
		name: orgName,
		type: "folder",
		size: null,
		extension: null,
		modified: new Date().toISOString(),
		metadata: {
			isOrgContainer: true,
			organizationId: orgId,
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
 * @returns FileOperations implementation with org grouping
 */
export function createOrgScopedFileOperations(
	organizations: Organization[],
): FileOperations {
	// Build org name lookup
	const orgNames = new Map<string, string>(
		organizations.map((org) => [org.id, org.name]),
	);
	orgNames.set(GLOBAL_ORG_ID, "Global");

	return {
		async list(path: string): Promise<FileNode[]> {
			// Root: return org containers
			if (path === "") {
				// Fetch all files recursively to determine which orgs have content
				const allFiles = await fileService.listFiles("", true);

				// Group files by organization
				const orgHasContent = new Set<string>();
				orgHasContent.add(GLOBAL_ORG_ID); // Always show Global

				for (const file of allFiles) {
					const orgId = file.organization_id ?? GLOBAL_ORG_ID;
					orgHasContent.add(orgId);
				}

				// Build org containers (Global first, then others alphabetically)
				const containers: FileNode[] = [
					createOrgContainer(null, "Global"),
				];

				const sortedOrgs = organizations
					.filter((org) => orgHasContent.has(org.id))
					.sort((a, b) => a.name.localeCompare(b.name));

				for (const org of sortedOrgs) {
					containers.push(createOrgContainer(org.id, org.name));
				}

				return containers;
			}

			// Within an org container
			const orgId = extractOrgId(path);
			if (orgId === null) {
				// Shouldn't happen, but fallback to direct listing
				const files = await fileService.listFiles(path);
				return files.map((f) => toFileNode(f, null));
			}

			const realPath = extractRealPath(path);
			const dbOrgId = orgId === GLOBAL_ORG_ID ? null : orgId;

			// Fetch files at this real path
			const files = await fileService.listFiles(realPath);

			// Filter to only files belonging to this org
			// For folders, include if any descendant belongs to this org
			const filteredFiles = files.filter((file) => {
				if (file.type === "folder") {
					// Folders are always included - they'll be empty if no matching files
					return true;
				}
				// For files, check org match (null org = global)
				const fileOrgId = file.organization_id ?? null;
				return fileOrgId === dbOrgId;
			});

			return filteredFiles.map((f) => toFileNode(f, dbOrgId));
		},

		async read(path: string): Promise<FileContent> {
			const realPath = extractRealPath(path);
			const response = await fileService.readFile(realPath);
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
			const realPath = extractRealPath(path);
			await fileService.writeFile(realPath, content, encoding, etag);
		},

		async createFolder(path: string): Promise<void> {
			const realPath = extractRealPath(path);
			await fileService.createFolder(realPath);
		},

		async delete(path: string): Promise<void> {
			const realPath = extractRealPath(path);
			await fileService.deletePath(realPath);
		},

		async rename(oldPath: string, newPath: string): Promise<void> {
			const oldOrgId = extractOrgId(oldPath);
			const newOrgId = extractOrgId(newPath);
			const oldRealPath = extractRealPath(oldPath);
			const newRealPath = extractRealPath(newPath);

			// Check if this is a cross-org move (drag to different org container)
			if (oldOrgId !== newOrgId && newRealPath === "") {
				// This is a drop onto an org container - need to update entity org
				// The file's metadata should have entityType and entityId
				// We'll need to refetch the file info to get these
				const files = await fileService.listFiles("", true);
				const file = files.find((f) => f.path === oldRealPath);

				if (file?.entity_type && file?.entity_id) {
					const targetOrgId =
						newOrgId === GLOBAL_ORG_ID ? null : newOrgId;
					await updateEntityOrganization(
						file.entity_type,
						file.entity_id,
						targetOrgId,
					);
					return;
				}

				throw new Error(
					"Cannot move non-entity files between organizations",
				);
			}

			// Regular rename/move within same org
			await fileService.renamePath(oldRealPath, newRealPath);
		},
	};
}
