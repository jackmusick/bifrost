import { describe, expect, it, vi, beforeEach } from "vitest";
import { renderWithProviders, screen, within } from "@/test-utils";

const mockUseUsersFiltered = vi.fn();
const mockUseOrganizations = vi.fn();
const mockRefetch = vi.fn();

vi.mock("@/hooks/useUsers", () => ({
	useUsersFiltered: (...args: unknown[]) => mockUseUsersFiltered(...args),
	useDeleteUser: () => ({ mutateAsync: vi.fn(), isPending: false }),
	useUpdateUser: () => ({ mutateAsync: vi.fn(), isPending: false }),
}));

vi.mock("@/hooks/useOrganizations", () => ({
	useOrganizations: (...args: unknown[]) => mockUseOrganizations(...args),
}));

vi.mock("@/hooks/useUserInvites", () => ({
	useRegenerateInvite: () => ({ mutate: vi.fn(), isPending: false }),
	useResendInvite: () => ({ mutate: vi.fn(), isPending: false }),
	useRevokeInvite: () => ({ mutate: vi.fn(), isPending: false }),
}));

vi.mock("@/contexts/AuthContext", () => ({
	useAuth: () => ({
		isPlatformAdmin: true,
		user: { id: "current-user" },
	}),
}));

vi.mock("@/contexts/OrgScopeContext", () => ({
	useOrgScope: () => ({
		scope: { type: "global", orgId: null, orgName: null },
	}),
}));

vi.mock("@/components/forms/OrganizationSelect", () => ({
	OrganizationSelect: () => null,
}));

vi.mock("@/components/users/CreateUserDialog", () => ({
	CreateUserDialog: () => null,
}));

vi.mock("@/components/users/EditUserDialog", () => ({
	EditUserDialog: () => null,
}));

vi.mock("@/components/users/BulkUserDialogs", () => ({
	BulkMoveOrgDialog: () => null,
	BulkReplaceRolesDialog: () => null,
	BulkResultDialog: () => null,
	BulkSetActiveDialog: () => null,
}));

vi.mock("sonner", () => ({
	toast: {
		success: vi.fn(),
		error: vi.fn(),
	},
}));

import { Users } from "./Users";

function makeUser(overrides: Record<string, unknown> = {}) {
	return {
		id: "user-1",
		email: "dev@gobifrost.com",
		name: "Dev Admin",
		is_active: true,
		is_superuser: true,
		is_verified: true,
		is_registered: true,
		is_system: false,
		mfa_enabled: false,
		organization_id: "org-provider",
		last_login: null,
		created_at: "2026-06-01T00:00:00Z",
		updated_at: "2026-06-01T00:00:00Z",
		invite_status: "active",
		...overrides,
	};
}

beforeEach(() => {
	mockRefetch.mockReset();
	mockUseUsersFiltered.mockReset();
	mockUseUsersFiltered.mockReturnValue({
		data: [makeUser()],
		isLoading: false,
		refetch: mockRefetch,
	});
	mockUseOrganizations.mockReset();
	mockUseOrganizations.mockReturnValue({
		data: [
			{
				id: "org-provider",
				name: "Provider",
				domain: null,
				is_provider: true,
				is_active: true,
			},
		],
	});
});

describe("Users", () => {
	it("shows the provider organization for provider-scoped superusers", () => {
		renderWithProviders(<Users />);

		const row = screen.getByText("Dev Admin").closest("tr");
		expect(row).not.toBeNull();
		expect(within(row!).getByText("Provider")).toBeInTheDocument();
		expect(row).not.toHaveTextContent("—");
	});
});
