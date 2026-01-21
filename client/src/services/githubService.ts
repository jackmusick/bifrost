/**
 * GitHub Sync service functions
 *
 * Provides API calls for GitHub synchronization features including
 * fetching content for diff previews.
 */

import { apiClient } from "@/lib/api-client";
import type { components } from "@/lib/v1";

// Auto-generated types from OpenAPI spec
export type SyncContentRequest = components["schemas"]["SyncContentRequest"];
export type SyncContentResponse = components["schemas"]["SyncContentResponse"];

/**
 * Fetch file content for diff preview
 *
 * Retrieves the content of a file from either the local (database) or remote
 * (GitHub) source for displaying in a diff viewer.
 *
 * @param path - File path to fetch content for
 * @param source - Which side to fetch: "local" (database) or "remote" (GitHub)
 * @returns The file content, or null if not found
 */
export async function fetchSyncContent(
	path: string,
	source: "local" | "remote",
): Promise<string | null> {
	const { data, error } = await apiClient.POST("/api/github/sync/content", {
		body: { path, source },
	});

	if (error) {
		console.error("Failed to fetch sync content:", error);
		return null;
	}

	return data?.content ?? null;
}
