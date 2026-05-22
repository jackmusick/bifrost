/**
 * Tests for useUserSelection.
 *
 * Covers single toggle, shift-range, select-all-visible, filter pruning,
 * and disabled-row no-op behaviour.
 */

import { describe, expect, it } from "vitest";
import { renderHook, act } from "@testing-library/react";

import { useUserSelection } from "./useUserSelection";

const items = (ids: string[]) => ids.map((id) => ({ id }));

describe("useUserSelection", () => {
	it("starts empty", () => {
		const { result } = renderHook(() => useUserSelection(items(["a", "b", "c"])));
		expect(result.current.count).toBe(0);
		expect(result.current.allVisibleSelected).toBe(false);
		expect(result.current.someVisibleSelected).toBe(false);
	});

	it("toggles a single id on/off", () => {
		const { result } = renderHook(() => useUserSelection(items(["a", "b", "c"])));

		act(() => result.current.toggle("b"));
		expect(result.current.isSelected("b")).toBe(true);
		expect(result.current.count).toBe(1);

		act(() => result.current.toggle("b"));
		expect(result.current.isSelected("b")).toBe(false);
		expect(result.current.count).toBe(0);
	});

	it("shift-click selects a range from the last toggled id", () => {
		const { result } = renderHook(() =>
			useUserSelection(items(["a", "b", "c", "d", "e"])),
		);

		act(() => result.current.toggle("b"));
		act(() => result.current.toggle("d", { shiftKey: true }));

		expect(result.current.isSelected("b")).toBe(true);
		expect(result.current.isSelected("c")).toBe(true);
		expect(result.current.isSelected("d")).toBe(true);
		expect(result.current.isSelected("a")).toBe(false);
		expect(result.current.isSelected("e")).toBe(false);
		expect(result.current.count).toBe(3);
	});

	it("shift-click can deselect a range", () => {
		const { result } = renderHook(() =>
			useUserSelection(items(["a", "b", "c", "d", "e"])),
		);

		// Select b..d first
		act(() => result.current.toggle("b"));
		act(() => result.current.toggle("d", { shiftKey: true }));
		// Toggle "b" off, then shift-click "d" → all three (b,c,d) deselect
		act(() => result.current.toggle("b"));
		act(() => result.current.toggle("d", { shiftKey: true }));

		expect(result.current.count).toBe(0);
	});

	it("toggleAllVisible adds every visible id, then clears them", () => {
		const { result } = renderHook(() => useUserSelection(items(["a", "b", "c"])));

		act(() => result.current.toggleAllVisible());
		expect(result.current.count).toBe(3);
		expect(result.current.allVisibleSelected).toBe(true);

		act(() => result.current.toggleAllVisible());
		expect(result.current.count).toBe(0);
	});

	it("toggleAllVisible skips disabled ids", () => {
		const { result } = renderHook(() =>
			useUserSelection(items(["a", "b", "c"]), ["b"]),
		);

		act(() => result.current.toggleAllVisible());

		expect(result.current.isSelected("a")).toBe(true);
		expect(result.current.isSelected("b")).toBe(false);
		expect(result.current.isSelected("c")).toBe(true);
		expect(result.current.allVisibleSelected).toBe(true); // all *selectable* visible
	});

	it("toggle on a disabled id is a no-op", () => {
		const { result } = renderHook(() =>
			useUserSelection(items(["a", "b", "c"]), ["b"]),
		);

		act(() => result.current.toggle("b"));
		expect(result.current.isSelected("b")).toBe(false);
		expect(result.current.count).toBe(0);
	});

	it("prunes selection when items shrink (filter narrows)", () => {
		const initial = items(["a", "b", "c", "d"]);
		const { result, rerender } = renderHook(
			({ data }: { data: { id: string }[] }) => useUserSelection(data),
			{ initialProps: { data: initial } },
		);

		act(() => result.current.toggle("a"));
		act(() => result.current.toggle("c"));
		expect(result.current.count).toBe(2);

		// Filter applied: only "a" remains
		rerender({ data: items(["a"]) });

		expect(result.current.isSelected("a")).toBe(true);
		expect(result.current.isSelected("c")).toBe(false);
		expect(result.current.count).toBe(1);
	});

	it("clear empties the selection", () => {
		const { result } = renderHook(() => useUserSelection(items(["a", "b"])));

		act(() => result.current.toggleAllVisible());
		expect(result.current.count).toBe(2);

		act(() => result.current.clear());
		expect(result.current.count).toBe(0);
	});

	it("someVisibleSelected reflects partial selection", () => {
		const { result } = renderHook(() => useUserSelection(items(["a", "b", "c"])));

		act(() => result.current.toggle("a"));

		expect(result.current.someVisibleSelected).toBe(true);
		expect(result.current.allVisibleSelected).toBe(false);
	});

	it("selectedItems preserves the order of the input items", () => {
		const data = items(["a", "b", "c", "d"]);
		const { result } = renderHook(() => useUserSelection(data));

		act(() => result.current.toggle("d"));
		act(() => result.current.toggle("a"));
		act(() => result.current.toggle("c"));

		expect(result.current.selectedItems.map((i) => i.id)).toEqual(["a", "c", "d"]);
	});
});
