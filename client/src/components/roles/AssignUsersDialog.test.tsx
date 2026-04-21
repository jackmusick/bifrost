/**
 * Component tests for AssignUsersDialog.
 *
 * Covers:
 * - renders user list from useUsers
 * - clicking a user toggles the Selected badge and the Assign button label
 * - Assign button is disabled with 0 selections
 * - submit fires assignUsersToRole with the role_id + selected user_ids
 * - empty-state message when no users
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderWithProviders, screen, waitFor } from "@/test-utils";

const mockUsers = vi.fn();
const mockAssignMutate = vi.fn();

vi.mock("@/hooks/useUsers", () => ({
	useUsers: () => mockUsers(),
}));

vi.mock("@/hooks/useRoles", () => ({
	useAssignUsersToRole: () => ({
		mutateAsync: mockAssignMutate,
		isPending: false,
	}),
}));

import { AssignUsersDialog } from "./AssignUsersDialog";

type Role = Parameters<typeof AssignUsersDialog>[0]["role"];

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
	mockUsers.mockReset();
	mockAssignMutate.mockReset();
	mockAssignMutate.mockResolvedValue({});
});

describe("AssignUsersDialog", () => {
	it("lists users and disables Assign when nothing is selected", () => {
		mockUsers.mockReturnValue({
			data: [
				{
					id: "u-1",
					name: "Alice",
					email: "alice@example.com",
					is_active: true,
					is_superuser: false,
					organization_id: "org-1",
				},
				{
					id: "u-2",
					name: "Bob",
					email: "bob@example.com",
					is_active: true,
					is_superuser: false,
					organization_id: "org-1",
				},
			],
			isLoading: false,
		});

		renderWithProviders(
			<AssignUsersDialog
				role={makeRole()}
				open={true}
				onClose={vi.fn()}
			/>,
		);

		expect(screen.getByText("Alice")).toBeInTheDocument();
		expect(screen.getByText("Bob")).toBeInTheDocument();
		expect(
			screen.getByRole("button", { name: /assign 0 users/i }),
		).toBeDisabled();
	});

	it("submits selected user ids to assignUsersToRole", async () => {
		mockUsers.mockReturnValue({
			data: [
				{
					id: "u-1",
					name: "Alice",
					email: "alice@example.com",
					is_active: true,
					is_superuser: false,
					organization_id: "org-1",
				},
				{
					id: "u-2",
					name: "Bob",
					email: "bob@example.com",
					is_active: true,
					is_superuser: false,
					organization_id: "org-1",
				},
			],
			isLoading: false,
		});

		const onClose = vi.fn();
		const { user } = renderWithProviders(
			<AssignUsersDialog
				role={makeRole()}
				open={true}
				onClose={onClose}
			/>,
		);

		await user.click(screen.getByText("Alice"));
		expect(
			screen.getByRole("button", { name: /assign 1 user$/i }),
		).toBeEnabled();

		await user.click(screen.getByText("Bob"));
		expect(
			screen.getByRole("button", { name: /assign 2 users/i }),
		).toBeEnabled();

		await user.click(screen.getByRole("button", { name: /assign 2 users/i }));

		await waitFor(() => expect(mockAssignMutate).toHaveBeenCalled());
		expect(mockAssignMutate.mock.calls[0]![0]).toEqual({
			params: { path: { role_id: "role-1" } },
			body: { user_ids: ["u-1", "u-2"] },
		});
		expect(onClose).toHaveBeenCalled();
	});

	it("shows an empty state when there are no users", () => {
		mockUsers.mockReturnValue({ data: [], isLoading: false });

		renderWithProviders(
			<AssignUsersDialog
				role={makeRole()}
				open={true}
				onClose={vi.fn()}
			/>,
		);

		expect(
			screen.getByText(/no organization users available/i),
		).toBeInTheDocument();
	});
});
