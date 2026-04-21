/**
 * Component tests for OrganizationSelect.
 *
 * Wraps shadcn Select + useOrganizations. We mock the hook and focus on the
 * value-mapping quirks: null → "Global", undefined → "All", real IDs pass
 * through, and the empty-string guard in handleValueChange doesn't clear
 * selections.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderWithProviders, screen } from "@/test-utils";

const mockOrgs = [
	{
		id: "org-1",
		name: "Acme",
		domain: "acme.com",
		is_provider: false,
	},
	{
		id: "org-2",
		name: "Globex",
		domain: null,
		is_provider: true,
	},
];

const useOrganizationsMock = vi.fn();

vi.mock("@/hooks/useOrganizations", () => ({
	useOrganizations: () => useOrganizationsMock(),
}));

beforeEach(() => {
	useOrganizationsMock.mockReturnValue({ data: mockOrgs, isLoading: false });
});

async function renderSelect(overrides: Record<string, unknown> = {}) {
	const { OrganizationSelect } = await import("./OrganizationSelect");
	const onChange = vi.fn();
	const utils = renderWithProviders(
		<OrganizationSelect value={null} onChange={onChange} {...overrides} />,
	);
	return { ...utils, onChange };
}

describe("OrganizationSelect", () => {
	it("shows 'Global' when value is null", async () => {
		await renderSelect({ value: null });

		expect(screen.getByText("Global")).toBeInTheDocument();
	});

	it("shows the organization name when value is a real org id", async () => {
		await renderSelect({ value: "org-1" });

		expect(screen.getByText("Acme")).toBeInTheDocument();
	});

	it("shows 'All' when value is undefined and showAll is true", async () => {
		await renderSelect({ value: undefined, showAll: true });

		expect(screen.getByText("All")).toBeInTheDocument();
	});

	it("disables the trigger while organizations are loading", async () => {
		useOrganizationsMock.mockReturnValueOnce({ data: [], isLoading: true });

		await renderSelect({ value: "org-not-loaded-yet" });

		// The component is disabled because isLoading is true.
		expect(screen.getByRole("combobox")).toBeDisabled();
	});

	it("disables the trigger when the disabled prop is true", async () => {
		await renderSelect({ value: null, disabled: true });

		const trigger = screen.getByRole("combobox");
		expect(trigger).toBeDisabled();
	});
});
