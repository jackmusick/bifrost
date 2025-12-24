import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";

export interface DashboardMetrics {
	workflow_count: number;
	data_provider_count: number;
	form_count: number;
	execution_stats: {
		total_executions: number;
		success_count: number;
		failed_count: number;
		running_count: number;
		pending_count: number;
		success_rate: number;
		avg_duration_seconds: number;
	};
	recent_failures: Array<{
		execution_id: string;
		workflow_name: string;
		error_message: string | null;
		started_at: string | null;
	}>;
	roi_24h?: {
		total_time_saved: number;
		total_value: number;
		time_saved_unit: string;
		value_unit: string;
	};
}

export function useDashboardMetrics() {
	return useQuery<DashboardMetrics>({
		queryKey: ["dashboard-metrics"],
		queryFn: async () => {
			const { data, error } = await apiClient.GET("/api/metrics", {});
			if (error)
				throw new Error(`Failed to fetch dashboard metrics: ${error}`);
			return data as DashboardMetrics;
		},
		refetchInterval: 30000, // Refresh every 30 seconds
		staleTime: 15000, // Consider stale after 15 seconds
		retry: 3, // Retry failed requests 3 times
		retryDelay: 1000, // Wait 1 second between retries
	});
}
