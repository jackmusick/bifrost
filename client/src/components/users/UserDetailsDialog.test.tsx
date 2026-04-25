/**
 * Component tests for UserDetailsDialog.
 *
 * Covers:
 * - shows user name + email in header
 * - Platform Admin badge and full-access card for superusers
 * - Active / Inactive status badge
 * - role + form tabs only render for org users with an organization
 * - empty state for roles list
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderWithProviders, screen } from "@/test-utils";

const mockUserRoles = vi.fn();
const mockUserForms = vi.fn();

vi.mock("@/hooks/useUsers", () => ({
	useUserRoles: () => mockUserRoles(),
	useUserForms: () => mockUserForms(),
}));

import { UserDetailsDialog } from "./UserDetailsDialog";

type User = Parameters<typeof UserDetailsDialog>[0]["user"];

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
	mockUserForms.mockReset();
	mockUserRoles.mockReturnValue({ data: { role_ids: [] }, isLoading: false });
	mockUserForms.mockReturnValue({ data: { form_ids: [] }, isLoading: false });
});

describe("UserDetailsDialog", () => {
	it("renders the user name and email in the header", () => {
		renderWithProviders(
			<UserDetailsDialog
				user={makeUser()}
				open={true}
				onClose={vi.fn()}
			/>,
		);

		expect(
			screen.getByRole("heading", { name: /alice/i }),
		).toBeInTheDocument();
		expect(
			screen.getByText(/alice@example.com/i),
		).toBeInTheDocument();
	});

	it("shows Platform Admin badge + full access card for superusers", () => {
		renderWithProviders(
			<UserDetailsDialog
				user={makeUser({ is_superuser: true, organization_id: null })}
				open={true}
				onClose={vi.fn()}
			/>,
		);

		expect(screen.getByText(/platform admin/i)).toBeInTheDocument();
		expect(screen.getByText(/full platform access/i)).toBeInTheDocument();
		// Roles/Forms tabs only render for org users — should NOT show here.
		expect(
			screen.queryByRole("tab", { name: /roles/i }),
		).not.toBeInTheDocument();
	});

	it("shows Active status badge when user is active", () => {
		renderWithProviders(
			<UserDetailsDialog
				user={makeUser()}
				open={true}
				onClose={vi.fn()}
			/>,
		);

		expect(screen.getByText(/^active$/i)).toBeInTheDocument();
	});

	it("shows Inactive badge when user is inactive", () => {
		renderWithProviders(
			<UserDetailsDialog
				user={makeUser({ is_active: false })}
				open={true}
				onClose={vi.fn()}
			/>,
		);

		expect(screen.getByText(/^inactive$/i)).toBeInTheDocument();
	});

	it("renders Roles + Form Access tabs for org users", () => {
		renderWithProviders(
			<UserDetailsDialog
				user={makeUser()}
				open={true}
				onClose={vi.fn()}
			/>,
		);

		expect(screen.getByRole("tab", { name: /roles/i })).toBeInTheDocument();
		expect(
			screen.getByRole("tab", { name: /form access/i }),
		).toBeInTheDocument();
	});

	it("shows an empty state when the user has no assigned roles", () => {
		renderWithProviders(
			<UserDetailsDialog
				user={makeUser()}
				open={true}
				onClose={vi.fn()}
			/>,
		);

		expect(
			screen.getByText(/no roles assigned to this user/i),
		).toBeInTheDocument();
	});
});
