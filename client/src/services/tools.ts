/**
 * Tools Service
 *
 * Provides access to the unified tools endpoint.
 * Returns both system tools and workflow tools.
 */

import { apiClient } from "@/lib/api-client";
import type { components } from "@/lib/v1";

// Re-export types for convenience
export type ToolInfo = components["schemas"]["ToolInfo"];
export type ToolsResponse = components["schemas"]["ToolsResponse"];

/**
 * Options for fetching tools
 */
export interface GetToolsOptions {
	type?: "system" | "workflow";
	include_inactive?: boolean;
}

/**
 * Fetch all available tools
 * @param options - Filter options for tools
 */
export async function getTools(
	options?: GetToolsOptions | "system" | "workflow",
): Promise<ToolsResponse> {
	// Support legacy signature where just type was passed
	const opts: GetToolsOptions =
		typeof options === "string" ? { type: options } : options ?? {};

	const query: { type?: "system" | "workflow"; include_inactive?: boolean } =
		{};
	if (opts.type) query.type = opts.type;
	if (opts.include_inactive) query.include_inactive = opts.include_inactive;

	const { data, error } = await apiClient.GET("/api/tools", {
		params: { query },
	});

	if (error) {
		throw new Error("Failed to fetch tools");
	}

	return data;
}

/**
 * Fetch system tools only
 */
export async function getSystemTools(): Promise<ToolsResponse> {
	const { data, error } = await apiClient.GET("/api/tools/system");

	if (error) {
		throw new Error("Failed to fetch system tools");
	}

	return data;
}
