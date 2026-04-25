/**
 * Component tests for FormContextPanel.
 *
 * Developer panel reads from useFormContext; we mock that hook. Covers:
 * - empty state messages when each bucket is empty
 * - non-empty buckets render data (via VariablesTreeView)
 * - loading spinner for the workflow section when launch workflow is pending.
 */

import { describe, it, expect, vi } from "vitest";
import { renderWithProviders, screen } from "@/test-utils";

const mockUseFormContext = vi.fn();

vi.mock("@/contexts/FormContext", () => ({
	useFormContext: () => mockUseFormContext(),
}));

// VariablesTreeView rendering is orthogonal to FormContextPanel responsibilities;
// we only care that children are rendered when data exists. Stub to a simple
// marker so we can assert "section has content" without pulling in its deps.
vi.mock("@/components/ui/variables-tree-view", () => ({
	VariablesTreeView: ({ data }: { data: Record<string, unknown> }) => (
		<div data-marker="tree">{Object.keys(data).join(",") || "empty"}</div>
	),
}));

async function renderPanel() {
	const { FormContextPanel } = await import("./FormContextPanel");
	return renderWithProviders(<FormContextPanel />);
}

describe("FormContextPanel", () => {
	it("shows empty-state messages when every bucket is empty", async () => {
		mockUseFormContext.mockReturnValue({
			context: { workflow: {}, query: {}, field: {} },
			isLoadingLaunchWorkflow: false,
		});

		await renderPanel();

		expect(
			screen.getByText(/no launch workflow configured/i),
		).toBeInTheDocument();
		expect(screen.getByText(/no query parameters/i)).toBeInTheDocument();
		expect(screen.getByText(/no field values yet/i)).toBeInTheDocument();
	});

	it("renders the tree view when a bucket has data", async () => {
		mockUseFormContext.mockReturnValue({
			context: {
				workflow: { user_id: "u1" },
				query: {},
				field: { name: "Jack" },
			},
			isLoadingLaunchWorkflow: false,
		});

		await renderPanel();

		// The query bucket still shows empty, but workflow and field render trees.
		expect(screen.getByText(/no query parameters/i)).toBeInTheDocument();
		const trees = screen.getAllByText(/user_id|name/);
		expect(trees.length).toBeGreaterThanOrEqual(2);
	});

	it("renders a Loading indicator inside the workflow section when launch workflow is pending", async () => {
		mockUseFormContext.mockReturnValue({
			context: { workflow: {}, query: {}, field: {} },
			isLoadingLaunchWorkflow: true,
		});

		await renderPanel();

		// The header shows a spinner, and the workflow section shows "Loading..."
		expect(screen.getByText(/^Loading\.\.\.$/)).toBeInTheDocument();
	});
});
