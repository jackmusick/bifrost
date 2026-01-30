/**
 * React Query hooks for unified tools
 */

import { useQuery } from "@tanstack/react-query";
import { getTools, getSystemTools } from "@/services/tools";
import type { ToolInfo } from "@/services/tools";

/**
 * Fetch all available tools (system + workflow)
 */
export function useTools(type?: "system" | "workflow") {
	return useQuery({
		queryKey: ["tools", type],
		queryFn: () => getTools(type),
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
 * Get tools grouped by type
 */
export function useToolsGrouped() {
	const { data, ...rest } = useTools();

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
