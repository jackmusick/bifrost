/**
 * Component tests for IntegrationMappingsTab.
 *
 * Covers the three user-visible states: no data provider, no orgs, and the
 * populated table — plus the Delete and Edit callbacks. EntitySelector +
 * AutoMatchControls are rendered as-is since they're purely callback-driven.
 */

import { describe, it, expect, vi } from "vitest";
import { renderWithProviders, screen, within } from "@/test-utils";
import { IntegrationMappingsTab } from "./IntegrationMappingsTab";
import type { OrgWithMapping } from "./IntegrationMappingsTab";

function renderTab(
	overrides: Partial<Parameters<typeof IntegrationMappingsTab>[0]> = {},
) {
	const handlers = {
		onRunAutoMatch: vi.fn(),
		onAcceptAllSuggestions: vi.fn(),
		onClearSuggestions: vi.fn(),
		onAcceptSuggestion: vi.fn(),
		onRejectSuggestion: vi.fn(),
		onUpdateOrgMapping: vi.fn(),
		onOpenConfigDialog: vi.fn(),
		onDeleteMapping: vi.fn(),
		onEditIntegration: vi.fn(),
	};
	const utils = renderWithProviders(
		<IntegrationMappingsTab
			orgsWithMappings={[]}
			entities={[]}
			isLoadingEntities={false}
			hasDataProvider={true}
			configSchema={[]}
			configDefaults={{}}
			autoMatchSuggestions={new Map()}
			matchStats={null}
			isMatching={false}
			isDeletePending={false}
			{...handlers}
			{...overrides}
		/>,
	);
	return { ...utils, ...handlers };
}

describe("IntegrationMappingsTab — empty states", () => {
	it("shows a no-data-provider CTA that fires onEditIntegration", async () => {
		const { user, onEditIntegration } = renderTab({ hasDataProvider: false });

		expect(
			screen.getByText(/no data provider configured/i),
		).toBeInTheDocument();
		await user.click(
			screen.getByRole("button", { name: /edit integration/i }),
		);
		expect(onEditIntegration).toHaveBeenCalledTimes(1);
	});

	it("shows 'No organizations available' when no orgs were passed in", () => {
		renderTab({ orgsWithMappings: [] });
		expect(
			screen.getByText(/no organizations available/i),
		).toBeInTheDocument();
	});
});

describe("IntegrationMappingsTab — populated", () => {
	const orgs: OrgWithMapping[] = [
		{
			id: "org-1",
			name: "Acme",
			mapping: {
				id: "map-1",
				integration_id: "int-1",
				organization_id: "org-1",
				entity_id: "ent-a",
				entity_name: "Entity A",
				oauth_token_id: null,
				config: {},
			} as unknown as OrgWithMapping["mapping"],
			formData: {
				organization_id: "org-1",
				entity_id: "ent-a",
				entity_name: "Entity A",
				config: {},
			},
		},
		{
			id: "org-2",
			name: "Beta",
			mapping: undefined,
			formData: {
				organization_id: "org-2",
				entity_id: "",
				entity_name: "",
				config: {},
			},
		},
	];

	it("renders a row for each organization with the right status badge", () => {
		renderTab({
			orgsWithMappings: orgs,
			entities: [
				{ value: "ent-a", label: "Entity A" },
				{ value: "ent-b", label: "Entity B" },
			],
		});

		expect(screen.getByText("Acme")).toBeInTheDocument();
		expect(screen.getByText("Beta")).toBeInTheDocument();
		// Acme is mapped
		expect(screen.getByText("Mapped")).toBeInTheDocument();
		// Beta has no mapping and no entity_id -> Not Mapped
		expect(screen.getByText("Not Mapped")).toBeInTheDocument();
	});

	it("fires onDeleteMapping for the org whose Unlink button is clicked", async () => {
		const { user, onDeleteMapping } = renderTab({
			orgsWithMappings: orgs,
			entities: [{ value: "ent-a", label: "Entity A" }],
		});

		// Unlink title is "Unlink mapping" for mapped orgs. Find it via title.
		const unlinkButtons = screen
			.getAllByRole("button")
			.filter((b) => b.getAttribute("title") === "Unlink mapping");
		expect(unlinkButtons).toHaveLength(1);
		await user.click(unlinkButtons[0]);
		expect(onDeleteMapping).toHaveBeenCalledWith(orgs[0]);
	});

	it("opens the config dialog for the clicked row", async () => {
		const { user, onOpenConfigDialog } = renderTab({
			orgsWithMappings: orgs,
			entities: [{ value: "ent-a", label: "Entity A" }],
		});

		const configureBtn = screen
			.getAllByRole("button")
			.find((b) => b.getAttribute("title") === "Configure");
		expect(configureBtn).toBeDefined();
		await user.click(configureBtn!);
		expect(onOpenConfigDialog).toHaveBeenCalledWith("org-1");
	});

	it("keeps the Unlink button disabled when there is no mapping to unlink", () => {
		renderTab({
			orgsWithMappings: orgs,
			entities: [{ value: "ent-a", label: "Entity A" }],
		});

		const row = screen.getByText("Beta").closest("tr")!;
		const unlinkBtn = within(row)
			.getAllByRole("button")
			.find((b) => b.getAttribute("title") === "No mapping to unlink");
		expect(unlinkBtn).toBeDefined();
		expect(unlinkBtn).toBeDisabled();
	});
});
