import { describe, expect, it, vi } from "vitest";
import { renderHook } from "@testing-library/react";
import { useParams } from "./useParams";

vi.mock("react-router-dom", () => ({
	useParams: vi.fn(),
}));

import { useParams as useRouterParams } from "react-router-dom";

const mockedUseRouterParams = vi.mocked(useRouterParams);

describe("useParams", () => {
	it("returns plain string params and drops undefined values", () => {
		mockedUseRouterParams.mockReturnValue({
			clientId: "123",
			optional: undefined,
			contactId: "abc",
		});
		const { result } = renderHook(() => useParams());
		expect(result.current.clientId).toBe("123");
		expect(result.current.contactId).toBe("abc");
		expect(Object.prototype.hasOwnProperty.call(result.current, "optional")).toBe(false);
	});

	it("rejects prototype-pollution keys from URL params", () => {
		// Build the malicious params object without writing literal `__proto__`
		// in source — the literal trips static analyzers (and would mutate the
		// prototype chain rather than create an own-property at parse time).
		// Using Object.defineProperty against a null-proto object guarantees
		// own-property semantics for the test fixture.
		const malicious: Record<string, string> = Object.create(null);
		const protoKey = ["__", "proto", "__"].join("");
		const defineString = (obj: object, key: string, value: string) => {
			Object.defineProperty(obj, key, {
				value,
				enumerable: true,
				configurable: true,
				writable: true,
			});
		};
		defineString(malicious, protoKey, "polluted");
		defineString(malicious, "constructor", "polluted");
		defineString(malicious, "prototype", "polluted");
		malicious.clientId = "123";

		mockedUseRouterParams.mockReturnValue(malicious);
		const { result } = renderHook(() => useParams());
		expect(result.current.clientId).toBe("123");
		// Forbidden keys are not assigned to result
		expect(Object.prototype.hasOwnProperty.call(result.current, protoKey)).toBe(false);
		expect(Object.prototype.hasOwnProperty.call(result.current, "constructor")).toBe(false);
		expect(Object.prototype.hasOwnProperty.call(result.current, "prototype")).toBe(false);
		// And Object.prototype is not polluted
		// eslint-disable-next-line @typescript-eslint/no-explicit-any
		expect(({} as any).polluted).toBeUndefined();
	});

	it("uses a null-prototype object so accidental property lookups don't fall back to Object.prototype", () => {
		mockedUseRouterParams.mockReturnValue({ clientId: "123" });
		const { result } = renderHook(() => useParams());
		expect(Object.getPrototypeOf(result.current)).toBeNull();
	});
});
