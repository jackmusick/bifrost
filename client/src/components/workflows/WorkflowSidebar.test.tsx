/**
 * Component tests for WorkflowSidebar.
 *
 * We mock the usage-stats query so the sidebar can render without a backend.
 * Focus is on the Orphaned filter toggle added in this PR — it should call
 * back on click and surface in the active-filter chip.
 */

import { describe, it, expect, vi } from "vitest";
import { renderWithProviders, screen } from "@/test-utils";
import { WorkflowSidebar } from "./WorkflowSidebar";

vi.mock("@/lib/api-client", () => ({
	$api: {
		useQuery: () => ({
			data: { forms: [], apps: [], agents: [] },
			isLoading: false,
		}),
	},
}));

function renderSidebar(overrides: Record<string, unknown> = {}) {
	const onCategorySelect = vi.fn();
	const onFormSelect = vi.fn();
	const onAppSelect = vi.fn();
	const onAgentSelect = vi.fn();
	const onEndpointFilterChange = vi.fn();
	const onOrphanedFilterChange = vi.fn();

	const utils = renderWithProviders(
		<WorkflowSidebar
			categories={[]}
			categoriesLoading={false}
			selectedCategory={null}
			selectedFormId={null}
			selectedAppId={null}
			selectedAgentId={null}
			endpointFilter={false}
			orphanedFilter={false}
			onCategorySelect={onCategorySelect}
			onFormSelect={onFormSelect}
			onAppSelect={onAppSelect}
			onAgentSelect={onAgentSelect}
			onEndpointFilterChange={onEndpointFilterChange}
			onOrphanedFilterChange={onOrphanedFilterChange}
			{...overrides}
		/>,
	);

	return { ...utils, onOrphanedFilterChange, onEndpointFilterChange };
}

describe("WorkflowSidebar — Orphaned filter", () => {
	it("calls onOrphanedFilterChange(true) when clicked while off", async () => {
		const { user, onOrphanedFilterChange } = renderSidebar();

		await user.click(screen.getByRole("button", { name: /orphaned/i }));

		expect(onOrphanedFilterChange).toHaveBeenCalledWith(true);
	});

	it("calls onOrphanedFilterChange(false) when clicked while on", async () => {
		const { user, onOrphanedFilterChange } = renderSidebar({
			orphanedFilter: true,
		});

		await user.click(screen.getByRole("button", { name: /orphaned/i }));

		expect(onOrphanedFilterChange).toHaveBeenCalledWith(false);
	});

	it("surfaces 'Orphaned' in the active-filter chip when the toggle is on", () => {
		renderSidebar({ orphanedFilter: true });

		expect(screen.getByText(/filtering by/i)).toBeInTheDocument();
		// The chip renders "Orphaned" as the filter name.
		expect(screen.getAllByText("Orphaned").length).toBeGreaterThan(0);
	});

	it("Clear button resets the orphaned filter alongside others", async () => {
		const { user, onOrphanedFilterChange, onEndpointFilterChange } =
			renderSidebar({ orphanedFilter: true, endpointFilter: true });

		await user.click(screen.getByRole("button", { name: /clear/i }));

		expect(onOrphanedFilterChange).toHaveBeenCalledWith(false);
		expect(onEndpointFilterChange).toHaveBeenCalledWith(false);
	});
});
