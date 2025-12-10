import { $api } from "@/lib/api-client";
import { useAuth } from "@/contexts/AuthContext";
import type { components } from "@/lib/v1";

// Re-export types for convenience
export type SystemLog = components["schemas"]["SystemLog"];
export type SystemLogsListResponse =
	components["schemas"]["SystemLogsListResponse"];

export interface GetSystemLogsParams {
	category?: string;
	level?: string;
	startDate?: string;
	endDate?: string;
	limit?: number;
	continuationToken?: string;
}

export function useSystemLogs(params: GetSystemLogsParams = {}) {
	const { user } = useAuth();

	return $api.useQuery("get", "/api/logs",
		{ params: { query: params as Record<string, string | number | undefined> } },
		{
			queryKey: ["systemLogs", params],
			enabled: !!user,
			staleTime: 30000, // 30 seconds
		}
	);
}
