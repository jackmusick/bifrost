/**
 * Component tests for UserRolesDialog.
 *
 * Covers:
 * - superuser shows the "Cannot Modify" notice
 * - regular user shows role checkboxes
 * - pre-check state matches userRoles
 * - toggling an unchecked box calls assignUsersToRole
 * - toggling a checked box calls removeUserFromRole
 * - empty state when no roles exist
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderWithProviders, screen, waitFor } from "@/test-utils";

const mockUserRoles = vi.fn();
const mockRoles = vi.fn();
const mockAssignMutate = vi.fn();
const mockRemoveMutate = vi.fn();

vi.mock("@/hooks/useUsers", () => ({
	useUserRoles: () => mockUserRoles(),
}));

vi.mock("@/hooks/useRoles", () => ({
	useRoles: () => mockRoles(),
	useAssignUsersToRole: () => ({
		mutateAsync: mockAssignMutate,
		isPending: false,
	}),
	useRemoveUserFromRole: () => ({
		mutateAsync: mockRemoveMutate,
		isPending: false,
	}),
}));

import { UserRolesDialog } from "./UserRolesDialog";

type User = Parameters<typeof UserRolesDialog>[0]["user"];

function makeUser(overrides: Partial<NonNullable<User>> = {}): NonNullable<User> {
	return {
		id: "u-1",
		email: "alice@example.com",
		name: "Alice",
		is_active: true,
		is_superuser: false,
		organization_id: "org-1",
		created_at: "2026-04-20T00:00:00Z",
		updated_at: "2026-04-20T00:00:00Z",
		last_login: null,
		...overrides,
	} as NonNullable<User>;
}

beforeEach(() => {
	mockUserRoles.mockReset();
	mockRoles.mockReset();
	mockAssignMutate.mockReset();
	mockAssignMutate.mockResolvedValue({});
	mockRemoveMutate.mockReset();
	mockRemoveMutate.mockResolvedValue({});
});

describe("UserRolesDialog", () => {
	it("shows the superuser notice for superusers", () => {
		mockUserRoles.mockReturnValue({ data: { role_ids: [] }, isLoading: false });
		mockRoles.mockReturnValue({ data: [], isLoading: false });

		renderWithProviders(
			<UserRolesDialog
				user={makeUser({ is_superuser: true })}
				open={true}
				onClose={vi.fn()}
			/>,
		);

		expect(
			screen.getByText(/cannot modify superuser roles/i),
		).toBeInTheDocument();
	});

	it("renders role checkboxes with the correct pre-check state", () => {
		mockUserRoles.mockReturnValue({
			data: { role_ids: ["r-1"] },
			isLoading: false,
		});
		mockRoles.mockReturnValue({
			data: [
				{ id: "r-1", name: "Admin", description: "Admin role" },
				{ id: "r-2", name: "Viewer", description: "Viewer role" },
			],
			isLoading: false,
		});

		renderWithProviders(
			<UserRolesDialog user={makeUser()} open={true} onClose={vi.fn()} />,
		);

		const adminCheckbox = screen.getByRole("checkbox", { name: /admin/i });
		const viewerCheckbox = screen.getByRole("checkbox", { name: /viewer/i });
		expect(adminCheckbox).toBeChecked();
		expect(viewerCheckbox).not.toBeChecked();
	});

	it("calls assignUsersToRole when toggling an unchecked role", async () => {
		mockUserRoles.mockReturnValue({
			data: { role_ids: [] },
			isLoading: false,
		});
		mockRoles.mockReturnValue({
			data: [{ id: "r-1", name: "Admin", description: null }],
			isLoading: false,
		});

		const { user } = renderWithProviders(
			<UserRolesDialog user={makeUser()} open={true} onClose={vi.fn()} />,
		);

		await user.click(screen.getByRole("checkbox", { name: /admin/i }));

		await waitFor(() => expect(mockAssignMutate).toHaveBeenCalled());
		expect(mockAssignMutate.mock.calls[0]![0]).toEqual({
			params: { path: { role_id: "r-1" } },
			body: { user_ids: ["u-1"] },
		});
	});

	it("calls removeUserFromRole when unchecking an assigned role", async () => {
		mockUserRoles.mockReturnValue({
			data: { role_ids: ["r-1"] },
			isLoading: false,
		});
		mockRoles.mockReturnValue({
			data: [{ id: "r-1", name: "Admin", description: null }],
			isLoading: false,
		});

		const { user } = renderWithProviders(
			<UserRolesDialog user={makeUser()} open={true} onClose={vi.fn()} />,
		);

		await user.click(screen.getByRole("checkbox", { name: /admin/i }));

		await waitFor(() => expect(mockRemoveMutate).toHaveBeenCalled());
		expect(mockRemoveMutate.mock.calls[0]![0]).toEqual({
			params: { path: { role_id: "r-1", user_id: "u-1" } },
		});
	});

	it("shows 'No roles available' when roles list is empty", () => {
		mockUserRoles.mockReturnValue({
			data: { role_ids: [] },
			isLoading: false,
		});
		mockRoles.mockReturnValue({ data: [], isLoading: false });

		renderWithProviders(
			<UserRolesDialog user={makeUser()} open={true} onClose={vi.fn()} />,
		);

		expect(screen.getByText(/no roles available/i)).toBeInTheDocument();
	});
});
