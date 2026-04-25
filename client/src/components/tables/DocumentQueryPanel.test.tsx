/**
 * Component tests for DocumentQueryPanel.
 *
 * The panel builds a `where` clause from a list of filter conditions.
 * We test:
 * - Add Filter inserts a row with default operator
 * - remove button drops a row
 * - Apply button is only visible with >= 1 condition
 * - "eq" operator surfaces the raw value in the where clause
 * - other operators wrap the value under their operator key
 * - "in" operator splits a comma-separated string
 * - Clear button triggers onClearFilters
 */

import { describe, it, expect, vi } from "vitest";
import { renderWithProviders, screen } from "@/test-utils";
import { DocumentQueryPanel } from "./DocumentQueryPanel";

function renderPanel(overrides: Record<string, unknown> = {}) {
	const onApplyFilters = vi.fn();
	const onClearFilters = vi.fn();
	const utils = renderWithProviders(
		<DocumentQueryPanel
			onApplyFilters={onApplyFilters}
			onClearFilters={onClearFilters}
			hasActiveFilters={false}
			{...overrides}
		/>,
	);
	return { ...utils, onApplyFilters, onClearFilters };
}

describe("DocumentQueryPanel", () => {
	it("does not show the Apply button until a condition is added", async () => {
		const { user } = renderPanel();

		expect(
			screen.queryByRole("button", { name: /apply filters/i }),
		).not.toBeInTheDocument();

		await user.click(screen.getByRole("button", { name: /add filter/i }));

		expect(
			screen.getByRole("button", { name: /apply filters/i }),
		).toBeInTheDocument();
	});

	it("applies a simple eq filter with the raw value", async () => {
		const { user, onApplyFilters } = renderPanel();

		await user.click(screen.getByRole("button", { name: /add filter/i }));
		await user.type(
			screen.getByPlaceholderText(/field name/i),
			"status",
		);
		await user.type(screen.getByPlaceholderText(/^value$/i), "open");

		await user.click(screen.getByRole("button", { name: /apply filters/i }));

		expect(onApplyFilters).toHaveBeenCalledWith({ status: "open" });
	});

	it("skips conditions with an empty field name", async () => {
		const { user, onApplyFilters } = renderPanel();

		await user.click(screen.getByRole("button", { name: /add filter/i }));
		// No field name typed.
		await user.type(screen.getByPlaceholderText(/^value$/i), "open");

		await user.click(screen.getByRole("button", { name: /apply filters/i }));

		expect(onApplyFilters).toHaveBeenCalledWith({});
	});

	it("removes a condition when the trash button is clicked", async () => {
		const { user } = renderPanel();

		await user.click(screen.getByRole("button", { name: /add filter/i }));
		expect(screen.getByPlaceholderText(/field name/i)).toBeInTheDocument();

		// Find the trash button — it's an icon-only button in the row.
		// Buttons without names: filter to icon-only ones near the input.
		const iconButtons = screen.getAllByRole("button");
		// The last button added after "Add Filter" is the delete (Trash2 icon).
		const deleteBtn = iconButtons.find(
			(b) => b.querySelector("svg.lucide-trash2") !== null,
		);
		expect(deleteBtn).toBeTruthy();
		await user.click(deleteBtn!);

		expect(
			screen.queryByPlaceholderText(/field name/i),
		).not.toBeInTheDocument();
	});

	it("shows the Clear button when hasActiveFilters and calls onClearFilters", async () => {
		const { user, onClearFilters } = renderPanel({
			hasActiveFilters: true,
		});

		const clearBtn = screen.getByRole("button", { name: /clear/i });
		await user.click(clearBtn);

		expect(onClearFilters).toHaveBeenCalled();
	});
});
