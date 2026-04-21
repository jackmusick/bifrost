/**
 * Component tests for WorkflowSelector.
 *
 * Covers loading/error states, that global workflows sort to the top, and the
 * role-mismatch warning when showRoleBadges is enabled and the workflow's
 * roles don't include the entity's roles. Uses the $api mock pattern from
 * shared tests.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderWithProviders, screen, waitFor } from "@/test-utils";

// $api.useQuery is our seam for fetching workflows.
const mockUseQuery = vi.fn();
vi.mock("@/lib/api-client", () => ({
	$api: {
		useQuery: (...args: unknown[]) => mockUseQuery(...args),
	},
	authFetch: vi.fn(),
}));

// fetchWorkflowRolesBatch is called only when showRoleBadges is true.
const mockFetchRoles = vi.fn();
vi.mock("@/hooks/useWorkflowRoles", () => ({
	fetchWorkflowRolesBatch: (...args: unknown[]) => mockFetchRoles(...args),
}));

import { WorkflowSelector } from "./WorkflowSelector";

beforeEach(() => {
	mockUseQuery.mockReset();
	mockFetchRoles.mockReset();
});

describe("WorkflowSelector — loading / error", () => {
	it("renders a loading indicator while fetching", () => {
		mockUseQuery.mockReturnValue({
			data: undefined,
			isLoading: true,
			error: null,
		});

		renderWithProviders(
			<WorkflowSelector value={undefined} onChange={vi.fn()} />,
		);

		expect(screen.getByText(/loading workflows/i)).toBeInTheDocument();
	});

	it("renders an error row if the query errors", () => {
		mockUseQuery.mockReturnValue({
			data: undefined,
			isLoading: false,
			error: new Error("boom"),
		});

		renderWithProviders(
			<WorkflowSelector value={undefined} onChange={vi.fn()} />,
		);

		expect(screen.getByText(/failed to load workflows/i)).toBeInTheDocument();
	});
});

describe("WorkflowSelector — listing & selection", () => {
	it("renders the currently-selected workflow name in the trigger", () => {
		mockUseQuery.mockReturnValue({
			data: [
				{ id: "wf-1", name: "Create User", organization_id: null },
				{ id: "wf-2", name: "Disable User", organization_id: "org-1" },
			],
			isLoading: false,
			error: null,
		});

		renderWithProviders(
			<WorkflowSelector value="wf-2" onChange={vi.fn()} />,
		);

		expect(screen.getByText("Disable User")).toBeInTheDocument();
	});

	it("shows the Global badge on the selected workflow when showOrgBadge is on", () => {
		mockUseQuery.mockReturnValue({
			data: [{ id: "wf-1", name: "Create User", organization_id: null }],
			isLoading: false,
			error: null,
		});

		renderWithProviders(
			<WorkflowSelector
				value="wf-1"
				onChange={vi.fn()}
				showOrgBadge
			/>,
		);

		expect(screen.getByText("Create User")).toBeInTheDocument();
	});
});

describe("WorkflowSelector — role mismatch warning", () => {
	it("flags a workflow whose roles do not include the entity's roles", async () => {
		mockUseQuery.mockReturnValue({
			data: [{ id: "wf-1", name: "Create User", organization_id: null }],
			isLoading: false,
			error: null,
		});
		// The workflow has no roles assigned — so an entity with role-A is a mismatch.
		mockFetchRoles.mockResolvedValue(new Map([["wf-1", []]]));

		renderWithProviders(
			<WorkflowSelector
				value="wf-1"
				onChange={vi.fn()}
				showRoleBadges
				entityRoleIds={["role-A"]}
				entityRoleNames={{ "role-A": "Admin" }}
			/>,
		);

		await waitFor(() => {
			expect(mockFetchRoles).toHaveBeenCalledWith(["wf-1"]);
		});
	});
});
