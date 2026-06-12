/**
 * Tests for the newly-exported parseBackendDate helper.
 *
 * The backend emits Python isoformat() strings WITHOUT a "Z" suffix that
 * are nonetheless UTC. parseBackendDate's contract is: bare timestamps get
 * "Z" appended; explicit timezones are respected as-is.
 */

import { describe, it, expect } from "vitest";
import { parseBackendDate } from "./utils";

describe("parseBackendDate", () => {
	it("treats a bare backend timestamp as UTC", () => {
		const date = parseBackendDate("2026-06-11T10:00:00");
		expect(date.toISOString()).toBe("2026-06-11T10:00:00.000Z");
	});

	it("leaves Z-suffixed timestamps untouched", () => {
		const date = parseBackendDate("2026-06-11T10:00:00Z");
		expect(date.toISOString()).toBe("2026-06-11T10:00:00.000Z");
	});

	it("respects explicit timezone offsets", () => {
		const date = parseBackendDate("2026-06-11T10:00:00+02:00");
		expect(date.toISOString()).toBe("2026-06-11T08:00:00.000Z");
	});
});
