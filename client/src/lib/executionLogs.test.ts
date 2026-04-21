import { describe, expect, it } from "vitest";
import type { StreamingLog } from "@/stores/executionStreamStore";
import {
	mergeLogsWithDedup,
	type ExecutionLogEntry,
} from "./executionLogs";

const apiLog = (
	sequence: number | undefined,
	message: string,
	extra: Partial<ExecutionLogEntry> = {},
): ExecutionLogEntry => ({
	level: "info",
	message,
	timestamp: "2026-04-20T00:00:00Z",
	sequence,
	...extra,
});

const streamLog = (
	sequence: number | undefined,
	message: string,
): StreamingLog => ({
	level: "info",
	message,
	timestamp: "2026-04-20T00:00:00Z",
	sequence,
});

describe("mergeLogsWithDedup", () => {
	it("returns empty array when both inputs are empty", () => {
		expect(mergeLogsWithDedup([], [])).toEqual([]);
	});

	it("returns API logs as-is when stream is empty", () => {
		const api = [apiLog(1, "a"), apiLog(2, "b")];
		const result = mergeLogsWithDedup(api, []);
		expect(result).toEqual(api);
		// Should be the same reference — no copy when short-circuiting
		expect(result).toBe(api);
	});

	it("returns streaming logs as-is when API is empty", () => {
		const stream = [streamLog(1, "x"), streamLog(2, "y")];
		const result = mergeLogsWithDedup([], stream);
		// Cast through unknown because StreamingLog is structurally compatible with ExecutionLogEntry
		expect(result).toEqual(stream as unknown as ExecutionLogEntry[]);
	});

	it("drops streaming logs whose sequence is <= max API sequence (API wins on overlap)", () => {
		const api = [apiLog(1, "api-1"), apiLog(2, "api-2"), apiLog(3, "api-3")];
		const stream = [
			streamLog(2, "stream-2-dup"),
			streamLog(3, "stream-3-dup"),
		];
		const result = mergeLogsWithDedup(api, stream);
		// No new entries beyond API's max sequence of 3 → API returned unchanged
		expect(result).toEqual(api);
		expect(result).toBe(api);
	});

	it("appends only streaming logs beyond the API's max sequence", () => {
		const api = [apiLog(1, "api-1"), apiLog(2, "api-2")];
		const stream = [
			streamLog(2, "stream-2-dup"), // dropped: covered by API
			streamLog(3, "stream-3-new"),
			streamLog(4, "stream-4-new"),
		];
		const result = mergeLogsWithDedup(api, stream);
		expect(result).toHaveLength(4);
		expect(result.map((log) => log.message)).toEqual([
			"api-1",
			"api-2",
			"stream-3-new",
			"stream-4-new",
		]);
	});

	it("merges non-overlapping ranges in API-then-stream order", () => {
		const api = [apiLog(1, "api-1"), apiLog(2, "api-2")];
		const stream = [streamLog(3, "stream-3"), streamLog(4, "stream-4")];
		const result = mergeLogsWithDedup(api, stream);
		expect(result.map((log) => log.sequence)).toEqual([1, 2, 3, 4]);
	});

	it("preserves streaming log order when called with already-ordered stream", () => {
		// Caller is responsible for ordering — store buffers out-of-order logs
		// into pendingLogs before handing us an ordered array. We verify the
		// function faithfully preserves whatever order the stream came in.
		const api: ExecutionLogEntry[] = [];
		const stream = [
			streamLog(1, "first"),
			streamLog(2, "second"),
			streamLog(3, "third"),
		];
		const result = mergeLogsWithDedup(api, stream);
		expect(result.map((log) => log.message)).toEqual([
			"first",
			"second",
			"third",
		]);
	});

	it("does not reorder stream logs — passes through input order verbatim", () => {
		// Important: mergeLogsWithDedup does NOT sort. If the caller passes
		// stream logs out of sequence order, they stay out of order. This
		// documents actual behavior (ordering is the store's responsibility).
		const api: ExecutionLogEntry[] = [];
		const stream = [
			streamLog(3, "third"),
			streamLog(1, "first"),
			streamLog(2, "second"),
		];
		const result = mergeLogsWithDedup(api, stream);
		expect(result.map((log) => log.sequence)).toEqual([3, 1, 2]);
	});

	it("treats missing sequence on API logs as -1 (so all stream logs with a sequence are kept)", () => {
		const api = [apiLog(undefined, "api-no-seq")];
		const stream = [streamLog(0, "stream-0"), streamLog(1, "stream-1")];
		const result = mergeLogsWithDedup(api, stream);
		// maxApiSeq = -1, so both stream logs (seq 0 and 1) are > -1 → kept
		expect(result).toHaveLength(3);
		expect(result.map((log) => log.message)).toEqual([
			"api-no-seq",
			"stream-0",
			"stream-1",
		]);
	});

	it("treats missing sequence on stream logs as -1 (dropped when API has any sequenced log)", () => {
		const api = [apiLog(0, "api-0")];
		const stream = [streamLog(undefined, "stream-no-seq")];
		const result = mergeLogsWithDedup(api, stream);
		// maxApiSeq = 0, stream seq = -1, -1 > 0 is false → dropped
		expect(result).toEqual(api);
	});

	it("keeps stream logs with sequence 0 when all API sequences are missing", () => {
		const api = [apiLog(undefined, "api-a"), apiLog(undefined, "api-b")];
		const stream = [streamLog(0, "stream-0")];
		const result = mergeLogsWithDedup(api, stream);
		// maxApiSeq = -1, stream seq 0 > -1 → kept
		expect(result.map((log) => log.message)).toEqual([
			"api-a",
			"api-b",
			"stream-0",
		]);
	});

	it("handles single-element inputs on both sides", () => {
		const api = [apiLog(5, "only-api")];
		const stream = [streamLog(6, "only-stream")];
		const result = mergeLogsWithDedup(api, stream);
		expect(result).toHaveLength(2);
		expect(result.map((log) => log.sequence)).toEqual([5, 6]);
	});

	it("uses the maximum API sequence (not just the last entry's sequence) as the cutoff", () => {
		// If the API returns sequences out of order (e.g. [3, 1, 2]), we still
		// want the cutoff to be 3 — otherwise we'd duplicate entries.
		const api = [apiLog(3, "api-3"), apiLog(1, "api-1"), apiLog(2, "api-2")];
		const stream = [
			streamLog(2, "stream-2-dup"),
			streamLog(3, "stream-3-dup"),
			streamLog(4, "stream-4-new"),
		];
		const result = mergeLogsWithDedup(api, stream);
		expect(result.map((log) => log.message)).toEqual([
			"api-3",
			"api-1",
			"api-2",
			"stream-4-new",
		]);
	});
});
