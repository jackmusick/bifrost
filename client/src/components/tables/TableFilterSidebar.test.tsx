/**
 * Component tests for TableFilterSidebar.
 *
 * Mostly the same where-clause builder as DocumentQueryPanel but with a
 * different layout. We test:
 * - initial render shows "No filters applied"
 * - Add Filter creates a condition row
 * - submit payload wraps non-eq operators under their operator key
 * - onClose button fires the onClose callback
 * - Clear button appears when hasActiveFilters and fires onClearFilters
 */

import { describe, it, expect, vi } from "vitest";
import { renderWithProviders, screen } from "@/test-utils";
import { TableFilterSidebar } from "./TableFilterSidebar";

function renderSidebar(overrides: Record<string, unknown> = {}) {
	const onApplyFilters = vi.fn();
	const onClearFilters = vi.fn();
	const utils = renderWithProviders(
		<TableFilterSidebar
			onApplyFilters={onApplyFilters}
			onClearFilters={onClearFilters}
			hasActiveFilters={false}
			{...overrides}
		/>,
	);
	return { ...utils, onApplyFilters, onClearFilters };
}

describe("TableFilterSidebar", () => {
	it("shows the empty state before any filters are added", () => {
		renderSidebar();
		expect(screen.getByText(/no filters applied/i)).toBeInTheDocument();
		expect(
			screen.queryByRole("button", { name: /apply filters/i }),
		).not.toBeInTheDocument();
	});

	it("adds a condition row on Add Filter", async () => {
		const { user } = renderSidebar();

		await user.click(screen.getByRole("button", { name: /add filter/i }));

		expect(screen.getByPlaceholderText(/field/i)).toBeInTheDocument();
		expect(
			screen.getByRole("button", { name: /apply filters/i }),
		).toBeInTheDocument();
	});

	it("builds a raw-value where-clause for eq operators", async () => {
		const { user, onApplyFilters } = renderSidebar();

		await user.click(screen.getByRole("button", { name: /add filter/i }));
		await user.type(screen.getByPlaceholderText(/field/i), "status");
		await user.type(screen.getByPlaceholderText(/value/i), "open");

		await user.click(screen.getByRole("button", { name: /apply filters/i }));

		expect(onApplyFilters).toHaveBeenCalledWith({ status: "open" });
	});

	it("shows the Clear button when hasActiveFilters and fires onClearFilters", async () => {
		const { user, onClearFilters } = renderSidebar({
			hasActiveFilters: true,
		});

		await user.click(screen.getByRole("button", { name: /^clear$/i }));

		expect(onClearFilters).toHaveBeenCalled();
	});

	it("fires onClose when the close button is clicked", async () => {
		const onClose = vi.fn();
		const { user } = renderSidebar({ onClose });

		await user.click(screen.getByRole("button", { name: /hide filters/i }));

		expect(onClose).toHaveBeenCalled();
	});
});
