/**
 * React Query hooks for unified tools
 */

import { useQuery } from "@tanstack/react-query";
import { getTools, getSystemTools } from "@/services/tools";
import type { ToolInfo, GetToolsOptions } from "@/services/tools";

/**
 * Fetch all available tools (system + workflow)
 */
export function useTools(options?: GetToolsOptions | "system" | "workflow") {
	// Normalize options for query key
	const opts: GetToolsOptions =
		typeof options === "string" ? { type: options } : options ?? {};

	return useQuery({
		queryKey: ["tools", opts.type, opts.include_inactive],
		queryFn: () => getTools(opts),
		staleTime: 5 * 60 * 1000, // 5 minutes
	});
}

/**
 * Fetch system tools only
 */
export function useSystemTools() {
	return useQuery({
		queryKey: ["tools", "system"],
		queryFn: getSystemTools,
		staleTime: 10 * 60 * 1000, // 10 minutes (system tools rarely change)
	});
}

/**
 * Options for useToolsGrouped hook
 */
export interface UseToolsGroupedOptions {
	/** Include deactivated workflow tools (for agent editor to show orphaned refs) */
	include_inactive?: boolean;
}

/**
 * Get tools grouped by type
 */
export function useToolsGrouped(options?: UseToolsGroupedOptions) {
	const { data, ...rest } = useTools({
		include_inactive: options?.include_inactive,
	});

	const grouped = {
		system: [] as ToolInfo[],
		workflow: [] as ToolInfo[],
	};

	if (data?.tools) {
		for (const tool of data.tools) {
			if (tool.type === "system") {
				grouped.system.push(tool);
			} else if (tool.type === "workflow") {
				grouped.workflow.push(tool);
			}
		}
	}

	return { data: grouped, ...rest };
}
