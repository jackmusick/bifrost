/**
 * Component tests for AssignFormsDialog.
 *
 * Covers:
 * - renders form list
 * - toggling a form updates selection + button count
 * - Assign button disabled when nothing is selected
 * - submit sends role_id + selected form_ids
 * - empty state when no forms
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderWithProviders, screen, waitFor } from "@/test-utils";

const mockForms = vi.fn();
const mockAssignMutate = vi.fn();

vi.mock("@/hooks/useForms", () => ({
	useForms: () => mockForms(),
}));

vi.mock("@/hooks/useRoles", () => ({
	useAssignFormsToRole: () => ({
		mutateAsync: mockAssignMutate,
		isPending: false,
	}),
}));

import { AssignFormsDialog } from "./AssignFormsDialog";

type Role = Parameters<typeof AssignFormsDialog>[0]["role"];

function makeRole(): NonNullable<Role> {
	return {
		id: "role-1",
		name: "Admin",
		description: null,
		permissions: {},
		created_at: "2026-04-20T00:00:00Z",
		updated_at: "2026-04-20T00:00:00Z",
		organization_id: null,
		created_by: "creator-1",
	} as unknown as NonNullable<Role>;
}

beforeEach(() => {
	mockForms.mockReset();
	mockAssignMutate.mockReset();
	mockAssignMutate.mockResolvedValue({});
});

describe("AssignFormsDialog", () => {
	it("lists forms and marks Global badge for forms with null organization_id", () => {
		mockForms.mockReturnValue({
			data: [
				{
					id: "f-1",
					name: "Onboarding",
					description: "Welcome flow",
					workflow_id: "wf-1",
					organization_id: null,
					is_active: true,
				},
				{
					id: "f-2",
					name: "Offboarding",
					description: null,
					workflow_id: "wf-2",
					organization_id: "org-1",
					is_active: false,
				},
			],
			isLoading: false,
		});

		renderWithProviders(
			<AssignFormsDialog
				role={makeRole()}
				open={true}
				onClose={vi.fn()}
			/>,
		);

		expect(screen.getByText("Onboarding")).toBeInTheDocument();
		expect(screen.getByText("Offboarding")).toBeInTheDocument();
		expect(screen.getByText(/^global$/i)).toBeInTheDocument();
		expect(screen.getByText(/^inactive$/i)).toBeInTheDocument();
	});

	it("submits selected form ids to assignFormsToRole", async () => {
		mockForms.mockReturnValue({
			data: [
				{
					id: "f-1",
					name: "Onboarding",
					description: "Welcome flow",
					workflow_id: "wf-1",
					organization_id: null,
					is_active: true,
				},
			],
			isLoading: false,
		});

		const onClose = vi.fn();
		const { user } = renderWithProviders(
			<AssignFormsDialog
				role={makeRole()}
				open={true}
				onClose={onClose}
			/>,
		);

		// Disabled before selection.
		expect(
			screen.getByRole("button", { name: /assign 0 forms/i }),
		).toBeDisabled();

		await user.click(screen.getByText("Onboarding"));

		const assignBtn = screen.getByRole("button", { name: /assign 1 form$/i });
		expect(assignBtn).toBeEnabled();

		await user.click(assignBtn);

		await waitFor(() => expect(mockAssignMutate).toHaveBeenCalled());
		expect(mockAssignMutate.mock.calls[0]![0]).toEqual({
			params: { path: { role_id: "role-1" } },
			body: { form_ids: ["f-1"] },
		});
		expect(onClose).toHaveBeenCalled();
	});

	it("shows empty state when there are no forms", () => {
		mockForms.mockReturnValue({ data: [], isLoading: false });

		renderWithProviders(
			<AssignFormsDialog
				role={makeRole()}
				open={true}
				onClose={vi.fn()}
			/>,
		);

		expect(screen.getByText(/no forms available/i)).toBeInTheDocument();
	});
});
