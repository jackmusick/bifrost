/**
 * JsonTree tests — primitives, objects, arrays, expand/collapse, and the
 * jsonPreview / isEmptyJson helpers used by callers.
 */

import { describe, it, expect } from "vitest";
import { fireEvent } from "@testing-library/react";

import { renderWithProviders, screen } from "@/test-utils";
import { JsonTree, isEmptyJson, jsonPreview } from "./JsonTree";

describe("JsonTree primitives", () => {
	it("renders null", () => {
		renderWithProviders(<JsonTree value={null} />);
		expect(screen.getByText(/null/i)).toBeInTheDocument();
	});
	it("renders booleans", () => {
		renderWithProviders(<JsonTree value={true} />);
		expect(screen.getByText("true")).toBeInTheDocument();
	});
	it("renders numbers", () => {
		renderWithProviders(<JsonTree value={42} />);
		expect(screen.getByText("42")).toBeInTheDocument();
	});
	it("renders strings with quotes", () => {
		renderWithProviders(<JsonTree value="hello" />);
		expect(screen.getByText(/"hello"/)).toBeInTheDocument();
	});
});

describe("JsonTree containers", () => {
	it("renders object keys as quoted strings and values inline", () => {
		renderWithProviders(<JsonTree value={{ name: "Acme", count: 3 }} />);
		expect(screen.getByText(/"name"/)).toBeInTheDocument();
		expect(screen.getByText(/"Acme"/)).toBeInTheDocument();
		expect(screen.getByText("3")).toBeInTheDocument();
	});

	it("renders empty object/array as {} or []", () => {
		const { rerender } = renderWithProviders(<JsonTree value={{}} />);
		expect(screen.getByText(/^\{\}$/)).toBeInTheDocument();
		rerender(<JsonTree value={[]} />);
		expect(screen.getByText(/^\[\]$/)).toBeInTheDocument();
	});

	it("collapses nested children beyond openDepth by default", () => {
		// Outer open, inner closed → inner shows "1 keys" hint.
		renderWithProviders(
			<JsonTree
				value={{ outer: { inner: "deep" } }}
				openDepth={1}
			/>,
		);
		// Inner key should be in DOM but its value (the string "deep") not visible.
		expect(screen.queryByText(/"deep"/)).not.toBeInTheDocument();
		// And the collapsed-hint text appears.
		expect(screen.getByText(/1 keys/)).toBeInTheDocument();
	});

	it("expands a closed container when its chevron is clicked", () => {
		renderWithProviders(
			<JsonTree
				value={{ outer: { inner: "deep" } }}
				openDepth={1}
			/>,
		);
		// There are two Expand buttons (one for outer, one for inner-collapsed).
		const buttons = screen.getAllByRole("button", { name: /expand/i });
		fireEvent.click(buttons[0]);
		expect(screen.getByText(/"deep"/)).toBeInTheDocument();
	});
});

describe("jsonPreview", () => {
	it("returns null for nullish", () => {
		expect(jsonPreview(null)).toBe("null");
		expect(jsonPreview(undefined)).toBe("null");
	});
	it("returns short quoted string for short string", () => {
		expect(jsonPreview("hi")).toBe('"hi"');
	});
	it("returns counts for arrays/objects", () => {
		expect(jsonPreview([1, 2, 3])).toBe("[3]");
		expect(jsonPreview({ a: 1, b: 2 })).toBe("{2}");
	});
});

describe("isEmptyJson", () => {
	it.each([
		[null, true],
		[undefined, true],
		["", true],
		[{}, true],
		[[], true],
		[{ a: 1 }, false],
		[[1], false],
		["x", false],
		[0, false],
	])("isEmptyJson(%j) → %s", (value, expected) => {
		expect(isEmptyJson(value)).toBe(expected);
	});
});
