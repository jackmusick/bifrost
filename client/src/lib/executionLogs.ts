import type { StreamingLog } from "@/stores/executionStreamStore";

/** A log entry as returned by the execution logs API. */
export interface ExecutionLogEntry {
	id?: number; // Unique log ID for exact deduplication
	level?: string;
	message?: string;
	timestamp?: string;
	data?: Record<string, unknown>;
	sequence?: number; // For ordering and range-based deduplication
}

/**
 * Merge API logs with streaming logs, deduplicating by sequence number.
 * API logs are the baseline; only keep streaming logs with sequence > max API sequence.
 */
export function mergeLogsWithDedup(
	apiLogs: ExecutionLogEntry[],
	streamingLogs: StreamingLog[],
): ExecutionLogEntry[] {
	if (streamingLogs.length === 0) return apiLogs;
	if (apiLogs.length === 0) return streamingLogs as ExecutionLogEntry[];

	// Find the highest sequence in API logs — anything at or below is already covered
	const maxApiSeq = apiLogs.reduce(
		(max, log) => Math.max(max, log.sequence ?? -1),
		-1,
	);

	// Only keep streaming logs with sequence beyond what the API returned
	const newStreamingLogs = streamingLogs.filter(
		(log) => (log.sequence ?? -1) > maxApiSeq,
	);

	if (newStreamingLogs.length === 0) return apiLogs;
	return [...apiLogs, ...newStreamingLogs];
}
