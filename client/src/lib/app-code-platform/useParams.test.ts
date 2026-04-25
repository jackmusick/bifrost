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
		mockedUseRouterParams.mockReturnValue({
			clientId: "123",
			__proto__: "polluted",
			constructor: "polluted",
			prototype: "polluted",
		});
		const { result } = renderHook(() => useParams());
		expect(result.current.clientId).toBe("123");
		// Forbidden keys are not assigned to result
		expect(Object.prototype.hasOwnProperty.call(result.current, "__proto__")).toBe(false);
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
