import { afterEach, describe, expect, it, vi } from "vitest";

import { safeRandomUUID } from "./uuid";

const UUID_V4 =
	/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

describe("safeRandomUUID", () => {
	afterEach(() => {
		vi.restoreAllMocks();
	});

	it("returns a v4 UUID via the native randomUUID when present", () => {
		const id = safeRandomUUID();
		expect(id).toMatch(UUID_V4);
	});

	it("falls back to getRandomValues when crypto.randomUUID is unavailable", () => {
		// Simulate a non-secure context: native randomUUID missing.
		const original = crypto.randomUUID;
		// @ts-expect-error — intentional: simulate undefined for fallback path
		delete crypto.randomUUID;
		try {
			const id = safeRandomUUID();
			expect(id).toMatch(UUID_V4);
		} finally {
			crypto.randomUUID = original;
		}
	});

	it("produces unique values across calls", () => {
		const seen = new Set<string>();
		for (let i = 0; i < 100; i++) {
			seen.add(safeRandomUUID());
		}
		expect(seen.size).toBe(100);
	});
});
