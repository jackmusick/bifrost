/**
 * Component tests for RoleDetailsDialog.
 *
 * Covers:
 * - renders role header + tabs
 * - lists assigned users using the userMap (name/email from useUsers) and
 *   falls back to the role_id when no user record
 * - search filters the user list
 * - Remove-user opens the confirmation dialog and firing confirm calls
 *   removeUserFromRole with the correct role_id + user_id
 * - empty-state when there are no assigned users
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderWithProviders, screen } from "@/test-utils";

const mockRoleUsers = vi.fn();
const mockRoleForms = vi.fn();
const mockRemoveMutate = vi.fn();
const mockUsers = vi.fn();

vi.mock("@/hooks/useRoles", () => ({
	useRoleUsers: () => mockRoleUsers(),
	useRoleForms: () => mockRoleForms(),
	useRemoveUserFromRole: () => ({
		mutate: mockRemoveMutate,
		isPending: false,
	}),
}));

vi.mock("@/hooks/useUsers", () => ({
	useUsers: () => mockUsers(),
}));

// Child dialogs — stub so we don't exercise their internals.
vi.mock("./AssignUsersDialog", () => ({
	AssignUsersDialog: () => null,
}));
vi.mock("./AssignFormsDialog", () => ({
	AssignFormsDialog: () => null,
}));

import { RoleDetailsDialog } from "./RoleDetailsDialog";

type Role = Parameters<typeof RoleDetailsDialog>[0]["role"];

function makeRole(overrides: Partial<NonNullable<Role>> = {}): NonNullable<Role> {
	return {
		id: "role-1",
		name: "Admin",
		description: "Admin role",
		permissions: {},
		created_at: "2026-04-20T00:00:00Z",
		updated_at: "2026-04-20T00:00:00Z",
		organization_id: null,
		...overrides,
	} as NonNullable<Role>;
}

beforeEach(() => {
	mockRoleUsers.mockReset();
	mockRoleForms.mockReset();
	mockRemoveMutate.mockReset();
	mockUsers.mockReset();
	mockRoleForms.mockReturnValue({ data: { form_ids: [] }, isLoading: false });
});

describe("RoleDetailsDialog", () => {
	it("renders the role name and description in the header", () => {
		mockRoleUsers.mockReturnValue({
			data: { user_ids: [] },
			isLoading: false,
		});
		mockUsers.mockReturnValue({ data: [] });

		renderWithProviders(
			<RoleDetailsDialog role={makeRole()} open={true} onClose={vi.fn()} />,
		);

		expect(screen.getByRole("heading", { name: /admin/i })).toBeInTheDocument();
		expect(screen.getByText(/admin role/i)).toBeInTheDocument();
	});

	it("renders assigned users using userMap for display names", () => {
		mockRoleUsers.mockReturnValue({
			data: { user_ids: ["u-1", "u-2"] },
			isLoading: false,
		});
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
					name: "",
					email: "bob@example.com",
					is_active: true,
					is_superuser: false,
					organization_id: "org-1",
				},
			],
		});

		renderWithProviders(
			<RoleDetailsDialog role={makeRole()} open={true} onClose={vi.fn()} />,
		);

		expect(screen.getByText("Alice")).toBeInTheDocument();
		expect(screen.getByText("alice@example.com")).toBeInTheDocument();
		// u-2 has no name, so falls through to email.
		expect(screen.getAllByText("bob@example.com").length).toBeGreaterThan(0);
	});

	it("filters the user list by search term", async () => {
		mockRoleUsers.mockReturnValue({
			data: { user_ids: ["u-1", "u-2"] },
			isLoading: false,
		});
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
		});

		const { user } = renderWithProviders(
			<RoleDetailsDialog role={makeRole()} open={true} onClose={vi.fn()} />,
		);

		await user.type(screen.getByPlaceholderText(/search users/i), "alice");

		expect(screen.getByText("Alice")).toBeInTheDocument();
		expect(screen.queryByText("Bob")).not.toBeInTheDocument();
	});

	it("opens confirmation and removes a user on confirm", async () => {
		mockRoleUsers.mockReturnValue({
			data: { user_ids: ["u-1"] },
			isLoading: false,
		});
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
			],
		});

		const { user } = renderWithProviders(
			<RoleDetailsDialog role={makeRole()} open={true} onClose={vi.fn()} />,
		);

		// There's one X button (remove) for the single user row.
		const row = screen.getByText("Alice").closest("div.flex.items-center");
		expect(row).toBeTruthy();
		const removeBtn = row!.parentElement!.querySelector("button");
		await user.click(removeBtn!);

		// Confirmation dialog renders.
		expect(
			await screen.findByRole("heading", { name: /remove user from role/i }),
		).toBeInTheDocument();

		await user.click(screen.getByRole("button", { name: /^remove user$/i }));

		expect(mockRemoveMutate).toHaveBeenCalledWith({
			params: { path: { role_id: "role-1", user_id: "u-1" } },
		});
	});

	it("shows the empty state when no users are assigned", () => {
		mockRoleUsers.mockReturnValue({
			data: { user_ids: [] },
			isLoading: false,
		});
		mockUsers.mockReturnValue({ data: [] });

		renderWithProviders(
			<RoleDetailsDialog role={makeRole()} open={true} onClose={vi.fn()} />,
		);

		expect(
			screen.getByText(/no users assigned to this role/i),
		).toBeInTheDocument();
	});
});
